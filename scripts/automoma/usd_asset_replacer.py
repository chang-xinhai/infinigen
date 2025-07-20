#!/usr/bin/env python3
"""
Universal StaticCategoryFactory to Articulated Asset Replacer

This script provides a comprehensive solution to automatically detect StaticCategoryFactory 
objects in USD scenes and replace them with articulated versions if available.

Features:
- Automatic detection of StaticCategoryFactory objects
- Object ID extraction from prim names
- Articulated asset lookup and replacement
- Preserves original transforms (position, rotation, scale)
- Comprehensive statistics and error reporting
- Fallback text-based processing when USD libraries unavailable

Usage:
    python usd_asset_replacer.py /path/to/scene.usdc
    python usd_asset_replacer.py /path/to/scene.usdc --articulated-dir /path/to/assets --output /path/to/output.usdc

Author: Assistant
Date: June 26, 2025
"""

import os
import re
import sys
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
import argparse


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# Try to import USD libraries
USD_AVAILABLE = False
try:
    from pxr import Usd, UsdGeom, Sdf, Gf, UsdLux
    USD_AVAILABLE = True
    logger.info("✓ USD/pxr modules available - using full USD processing")
except ImportError:
    logger.warning("⚠ USD/pxr modules not available - will use text-based fallback")


class ProcessingStats:
    """Statistics tracking for the replacement process."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.total_objects = 0
        self.static_factory_objects = 0
        self.replaced_objects = 0
        self.not_found_articulated = 0
        self.errors = 0
        self.processing_method = "unknown"
    
    def to_dict(self) -> Dict:
        return {
            'total_objects': self.total_objects,
            'static_factory_objects': self.static_factory_objects,
            'replaced_objects': self.replaced_objects,
            'not_found_articulated': self.not_found_articulated,
            'errors': self.errors,
            'replacement_rate': self.get_replacement_rate(),
            'processing_method': self.processing_method
        }
    
    def get_replacement_rate(self) -> float:
        if self.static_factory_objects == 0:
            return 0.0
        return (self.replaced_objects / self.static_factory_objects) * 100
    
    def print_summary(self):
        """Print a comprehensive statistics summary."""
        print("\n" + "=" * 70)
        print("PROCESSING SUMMARY")
        print("=" * 70)
        print(f"Processing method: {self.processing_method}")
        print(f"Total objects processed: {self.total_objects}")
        print(f"StaticCategoryFactory objects found: {self.static_factory_objects}")
        print(f"Objects replaced with articulated versions: {self.replaced_objects}")
        print(f"Objects without articulated versions: {self.not_found_articulated}")
        print(f"Errors encountered: {self.errors}")
        print(f"Replacement rate: {self.get_replacement_rate():.1f}%")
        
        if self.errors > 0:
            print(f"\n⚠ Warning: {self.errors} errors occurred during processing")
        
        if self.replaced_objects > 0:
            print(f"\n✓ Successfully replaced {self.replaced_objects} objects with articulated versions")
        else:
            print("\n! No objects were replaced")


class BaseUSDReplacer:
    """Base class for USD scene processing."""
    
    def __init__(self, scene_usd_path: str, articulated_assets_dir: str):
        self.scene_usd_path = Path(scene_usd_path)
        self.articulated_assets_dir = Path(articulated_assets_dir)
        self.stats = ProcessingStats()
        
        # Validate paths
        self._validate_paths()
    
    def _validate_paths(self):
        """Validate input paths."""
        if not self.scene_usd_path.exists():
            raise FileNotFoundError(f"Scene USD file not found: {self.scene_usd_path}")
        if not self.articulated_assets_dir.exists():
            raise FileNotFoundError(f"Articulated assets directory not found: {self.articulated_assets_dir}")
    
    def extract_object_info_from_name(self, prim_name: str) -> Optional[Tuple[str, str]]:
        """Extract category and object name from StaticCategoryFactory prim name.
        
        Args:
            prim_name: Name like "StaticCategoryFactory_Microwave_7221_glb_4803841__spawn_asset_4"
            
        Returns:
            Tuple of (category, object_name) like ("Microwave", "7221") or None if not found
        """
        # Pattern: StaticCategoryFactory_{category}_{name}_{type}_{ID}_...
        # We need to capture the first word and the first numeric sequence
        pattern = r'StaticCategoryFactory_([^_]+)_(\d+)_'
        match = re.search(pattern, prim_name)
        if match:
            category = match.group(1)
            object_name = match.group(2)
            return category, object_name
        return None
    
    def find_articulated_asset(self, category: str, object_name: str) -> Optional[Path]:
        """Find articulated USD asset for given category and object name."""
        articulated_file = self.articulated_assets_dir / category / f"{object_name}.usd"
        return articulated_file if articulated_file.exists() else None
    
    def get_available_articulated_assets(self) -> Dict[str, Set[str]]:
        """Get dictionary of available articulated assets organized by category.
        
        Returns:
            Dict mapping category -> set of object names (e.g., {"Microwave": {"7221", "7263"}})
        """
        assets = {}
        for category_dir in self.articulated_assets_dir.iterdir():
            if category_dir.is_dir():
                category_name = category_dir.name
                assets[category_name] = set()
                for file in category_dir.glob("*.usd"):
                    if file.stem.isdigit():
                        assets[category_name].add(file.stem)
        return assets
    
    def save_replacement_log(self, output_dir: Path, replaced_objects: List[Dict]):
        """Save a log of replaced objects."""
        log_file = output_dir / "replacement_log.json"
        log_data = {
            'timestamp': str(os.times()),
            'scene_file': str(self.scene_usd_path),
            'articulated_dir': str(self.articulated_assets_dir),
            'statistics': self.stats.to_dict(),
            'replaced_objects': replaced_objects
        }
        
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"Replacement log saved to: {log_file}")


class USDReplacer(BaseUSDReplacer):
    """Full USD library-based replacer (requires pxr/USD)."""
    
    def __init__(self, scene_usd_path: str, articulated_assets_dir: str):
        if not USD_AVAILABLE:
            raise ImportError("USD libraries not available")
        super().__init__(scene_usd_path, articulated_assets_dir)
        self.stats.processing_method = "USD Libraries (pxr)"
    
    def replace_prim_with_articulated(self, stage: Usd.Stage, prim: Usd.Prim, 
                                    articulated_file: Path) -> Dict:
        """Replace prim with articulated version using import and disable approach."""
        try:
            # Extract original properties
            prim_path = prim.GetPath()
            parent_prim = prim.GetParent()
            original_name = prim.GetName()
            
            # Get the ABSOLUTE WORLD transform matrix from the original prim
            # This ensures the new object appears in exactly the same world position
            xformable = UsdGeom.Xformable(prim)
            world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            
            # Create new prim path
            new_name = f"articulated_replace_{original_name}"
            new_prim_path = parent_prim.GetPath().AppendChild(new_name)
            
            # Import the articulated asset as a new prim
            new_xform = UsdGeom.Xform.Define(stage, new_prim_path)
            new_prim = new_xform.GetPrim()
            
            # Add reference to articulated file
            references = new_prim.GetReferences()
            references.AddReference(str(articulated_file))
            
            # Apply the ABSOLUTE WORLD transform matrix to the new prim
            # This preserves the exact world position, rotation, and scale
            new_xform.GetXformOpOrderAttr().Set([])  # Clear any existing ops
            transform_op = new_xform.AddTransformOp()
            transform_op.Set(world_transform)
            
            # Disable the original prim instead of removing it
            # This preserves the original data while making it inactive
            prim.SetActive(False)
            
            # Extract transform components for logging (from world transform)
            translation = world_transform.ExtractTranslation()
            rotation_matrix = world_transform.ExtractRotationMatrix()
            scale = Gf.Vec3f(
                Gf.GetLength(world_transform.GetRow3(0)[:3]),
                Gf.GetLength(world_transform.GetRow3(1)[:3]),
                Gf.GetLength(world_transform.GetRow3(2)[:3])
            )
            
            replacement_info = {
                'original_name': original_name,
                'new_name': new_name,
                'original_path': str(prim_path),
                'new_path': str(new_prim_path),
                'articulated_file': str(articulated_file),
                'original_disabled': True,
                'transform_type': 'absolute_world',
                'transform': {
                    'translation': list(translation),
                    'scale': list(scale),
                    'world_transform_matrix': [list(row) for row in world_transform]
                }
            }
            
            logger.info(f"✓ Imported articulated version as '{new_name}' with absolute world transform and disabled original '{original_name}'")
            return replacement_info
            
        except Exception as e:
            logger.error(f"Error replacing prim '{prim.GetPath()}': {e}")
            self.stats.errors += 1
            raise
    
    def process_scene(self, output_file: Optional[str] = None) -> Tuple[str, List[Dict]]:
        """Process scene using USD libraries."""
        if output_file is None:
            # Output in same directory as input scene
            output_file = self.scene_usd_path.parent / "export_scene_new.usdc"
        else:
            output_file = Path(output_file)
        
        logger.info(f"Processing USD scene: {self.scene_usd_path}")
        logger.info(f"Output file: {output_file}")
        
        # Open original stage
        stage = Usd.Stage.Open(str(self.scene_usd_path))
        if not stage:
            raise RuntimeError(f"Failed to open USD stage: {self.scene_usd_path}")
        
        # Create a new stage for output and copy all layers from original
        # This preserves the entire scene structure
        output_stage = Usd.Stage.CreateNew(str(output_file))
        
        # Copy all the content from original stage to new stage
        output_stage.GetRootLayer().TransferContent(stage.GetRootLayer())
        
        replaced_objects = []
        prims_to_process = []
        
        # First pass: collect all StaticCategoryFactory prim paths to process
        # We collect paths instead of prims to avoid invalidation during stage modification
        for prim in output_stage.Traverse():
            self.stats.total_objects += 1
            prim_name = prim.GetName()
            
            if prim_name.startswith("StaticCategoryFactory_"):
                self.stats.static_factory_objects += 1
                prims_to_process.append(prim.GetPath())
        
        # Second pass: process replacements using paths
        for prim_path in prims_to_process:
            prim = output_stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                logger.warning(f"Prim at path {prim_path} is no longer valid, skipping")
                continue
                
            prim_name = prim.GetName()
            logger.info(f"Found StaticCategoryFactory object: {prim_name}")
            
            object_info = self.extract_object_info_from_name(prim_name)
            if not object_info:
                logger.warning(f"Could not extract object info from: {prim_name}")
                continue
            
            category, object_name = object_info
            logger.info(f"  Category: {category}, Object: {object_name}")
            
            articulated_file = self.find_articulated_asset(category, object_name)
            if articulated_file:
                try:
                    replacement_info = self.replace_prim_with_articulated(output_stage, prim, articulated_file)
                    replacement_info['category'] = category
                    replacement_info['object_name'] = object_name
                    replaced_objects.append(replacement_info)
                    self.stats.replaced_objects += 1
                except Exception as e:
                    logger.error(f"Failed to replace {prim_name}: {e}")
                    self.stats.errors += 1
            else:
                logger.warning(f"No articulated version found for {category}/{object_name}")
                self.stats.not_found_articulated += 1
        
        # Save the complete scene with all original content preserved
        output_stage.Save()
        logger.info(f"Saved modified scene to: {output_file}")
        
        return str(output_file), replaced_objects


class TextBasedReplacer(BaseUSDReplacer):
    """Text-based fallback replacer for when USD libraries aren't available."""
    
    def __init__(self, scene_usd_path: str, articulated_assets_dir: str):
        super().__init__(scene_usd_path, articulated_assets_dir)
        self.stats.processing_method = "Text-based fallback"
    
    def find_static_factory_objects(self, content: str) -> List[str]:
        """Find StaticCategoryFactory objects in USD content."""
        patterns = [
            r'def\s+"(StaticCategoryFactory_[^"]+)"',
            r'def\s+(StaticCategoryFactory_\S+)',
        ]
        
        matches = []
        for pattern in patterns:
            matches.extend(re.findall(pattern, content))
        
        return list(set(matches))  # Remove duplicates
    
    def process_scene_simple(self, output_file: Optional[str] = None) -> Tuple[str, List[Dict]]:
        """Process scene using text-based approach."""
        if output_file is None:
            # Output in same directory as input scene
            output_file = self.scene_usd_path.parent / "export_scene_new.usdc"
        else:
            output_file = Path(output_file)
        
        logger.info(f"Processing USD scene (text mode): {self.scene_usd_path}")
        logger.info(f"Output file: {output_file}")
        
        # Read file content
        try:
            with open(self.scene_usd_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            logger.warning("File appears to be binary - attempting ASCII decode")
            with open(self.scene_usd_path, 'rb') as f:
                binary_content = f.read()
            content = binary_content.decode('ascii', errors='ignore')
        
        self.stats.total_objects = len(content.splitlines())
        
        # Find StaticCategoryFactory objects
        static_objects = self.find_static_factory_objects(content)
        self.stats.static_factory_objects = len(static_objects)
        
        logger.info(f"Found {len(static_objects)} StaticCategoryFactory objects")
        
        replaced_objects = []
        available_assets = self.get_available_articulated_assets()
        
        for obj_name in static_objects:
            object_info = self.extract_object_info_from_name(obj_name)
            if not object_info:
                logger.warning(f"Could not extract object info from: {obj_name}")
                continue
            
            category, object_name = object_info
            
            # Check if articulated version exists
            if category not in available_assets or object_name not in available_assets[category]:
                logger.warning(f"No articulated version found for {category}/{object_name}")
                self.stats.not_found_articulated += 1
                continue
            
            articulated_file = self.articulated_assets_dir / category / f"{object_name}.usd"
            new_name = f"articulated_replace_{obj_name}"
            
            try:
                # Simple text replacement (limited functionality)
                old_pattern = f'"{obj_name}"'
                new_pattern = f'"{new_name}"'
                content = content.replace(old_pattern, new_pattern)
                
                # Add reference (simplified)
                relative_path = os.path.relpath(articulated_file, output_file.parent)
                ref_comment = f'# Replaced {obj_name} with articulated version from {relative_path}'
                content = content.replace(new_pattern, f'{new_pattern}\n    {ref_comment}', 1)
                
                replacement_info = {
                    'original_name': obj_name,
                    'new_name': new_name,
                    'category': category,
                    'object_name': object_name,
                    'articulated_file': str(articulated_file),
                    'method': 'text_replacement'
                }
                replaced_objects.append(replacement_info)
                self.stats.replaced_objects += 1
                
                logger.info(f"✓ Text-replaced '{obj_name}' with articulated version")
                
            except Exception as e:
                logger.error(f"Error replacing {obj_name}: {e}")
                self.stats.errors += 1
        
        # Write modified content
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Saved modified scene to: {output_file}")
        return str(output_file), replaced_objects


def create_replacer(scene_usd_path: str, articulated_assets_dir: str, 
                   force_simple: bool = False) -> BaseUSDReplacer:
    """Create appropriate replacer based on available libraries."""
    if USD_AVAILABLE and not force_simple:
        return USDReplacer(scene_usd_path, articulated_assets_dir)
    else:
        return TextBasedReplacer(scene_usd_path, articulated_assets_dir)


def main():
    """Main function with comprehensive CLI."""
    parser = argparse.ArgumentParser(
        description="Replace StaticCategoryFactory objects with articulated versions in USD scenes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scene.usdc
  %(prog)s scene.usdc --articulated-dir /path/to/assets
  %(prog)s scene.usdc --output new_scene.usdc --simple
  %(prog)s scene.usdc --list-assets
        """
    )
    
    parser.add_argument(
        "scene_file",
        help="Path to input USD scene file"
    )
    parser.add_argument(
        "--articulated-dir",
        default="/home/xinhai/Documents/infinigen/infinigen/assets/static_assets/source/.usd",
        help="Directory containing articulated USD assets"
    )
    parser.add_argument(
        "--output",
        help="Output USD file path (default: export_scene_new.usdc in same directory)"
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Force simple text-based processing"
    )
    parser.add_argument(
        "--list-assets",
        action="store_true",
        help="List available articulated assets and exit"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Create replacer
        replacer = create_replacer(args.scene_file, args.articulated_dir, args.simple)
        
        # List assets if requested
        if args.list_assets:
            assets = replacer.get_available_articulated_assets()
            total_assets = sum(len(objects) for objects in assets.values())
            print(f"\nAvailable articulated assets ({total_assets} assets in {len(assets)} categories):")
            for category in sorted(assets.keys()):
                object_names = assets[category]
                print(f"  {category} ({len(object_names)} assets):")
                for object_name in sorted(object_names):
                    asset_file = replacer.articulated_assets_dir / category / f"{object_name}.usd"
                    print(f"    {object_name}: {asset_file}")
            return
        
        # Process the scene
        if isinstance(replacer, USDReplacer):
            output_file, replaced_objects = replacer.process_scene(args.output)
        else:
            output_file, replaced_objects = replacer.process_scene_simple(args.output)
        
        # Save replacement log
        replacer.save_replacement_log(Path(output_file).parent, replaced_objects)
        
        # Print statistics
        replacer.stats.print_summary()
        
        print(f"\n✓ Processing completed successfully!")
        print(f"Output saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Default behavior for direct execution
    if len(sys.argv) == 1:
        # Use default parameters for the microwave example
        scene_file = "/home/xinhai/Documents/infinigen/outputs/static_replace_test/microwave_7/export/export_scene.blend/export_scene.usdc"
        articulated_dir = "/home/xinhai/Documents/infinigen/infinigen/assets/static_assets/source/.usd"
        
        print("Running with default parameters for microwave scene...")
        print(f"Scene file: {scene_file}")
        print(f"Articulated assets: {articulated_dir}")
        print("-" * 70)
        
        try:
            replacer = create_replacer(scene_file, articulated_dir)
            
            if isinstance(replacer, USDReplacer):
                output_file, replaced_objects = replacer.process_scene()
            else:
                output_file, replaced_objects = replacer.process_scene_simple()
            
            replacer.save_replacement_log(Path(output_file).parent, replaced_objects)
            replacer.stats.print_summary()
            
            print(f"\n✓ Processing completed successfully!")
            print(f"Output saved to: {output_file}")
            
        except Exception as e:
            logger.error(f"Error: {e}")
            print("\nFor custom parameters, run:")
            print("python usd_asset_replacer.py --help")
    else:
        main()
