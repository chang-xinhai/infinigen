#!/usr/bin/env python3
"""
Batch processing script for converting URDF files to GLB format.
Supports multiple export modes: all, random N objects, specific category, specific object ID.
"""

import os
import sys
import json
import argparse
import random
import shutil
from pathlib import Path
from typing import List, Dict, Set
import time

import numpy as np
import trimesh
from scene_synthesizer.procedural_assets import URDFAsset


class URDFToGLBConverter:
    """Batch converter for URDF to GLB files."""
    
    def __init__(self, processed_data_dir: str, scale: float = 1.0):
        self.processed_data_dir = Path(processed_data_dir)
        self.stats_file = self.processed_data_dir / "stats.json"
        self.stats_data = self._load_stats()
        self.scale = scale
        
        # self.trans = np.eye(4)
        self.trans = np.array([
            [-1,  0, 0 , 0],
            [ 0,  0, 1, 0],
            [ 0,  1, 0, 0],
            [ 0,  0, 0, 1]
        ])

        self.conversion_stats = {
            "total_attempted": 0,
            "total_successful": 0,
            "total_failed": 0,
            "failed_objects": [],
            "categories_processed": set(),
            "start_time": None,
            "end_time": None
        }
    
    def _load_stats(self) -> Dict:
        """Load statistics from stats.json file."""
        if not self.stats_file.exists():
            print(f"Warning: Stats file not found at {self.stats_file}")
            return {"categories": {}}
        
        with open(self.stats_file, 'r') as f:
            return json.load(f)
    
    def preprocess_object_dir(self, object_dir: Path) -> bool:
        """
        Preprocess object directory by removing existing mobility subdirectory if it exists.
        
        Args:
            object_dir: Path to the object directory
            
        Returns:
            bool: True if preprocessing was successful
        """
        mobility_dir = object_dir / "mobility"
        if mobility_dir.exists():
            print(f"  Removing existing mobility directory: {mobility_dir}")
            try:
                shutil.rmtree(mobility_dir)
                return True
            except Exception as e:
                print(f"  Error removing mobility directory: {e}")
                return False
        return True
    
    def convert_urdf_to_glb(self, urdf_path: Path, glb_path: Path) -> bool:
        """
        Convert a single URDF file to GLB format.
        
        Args:
            urdf_path: Path to the URDF file
            glb_path: Destination path for the GLB file
            
        Returns:
            bool: True if conversion was successful
        """
        try:
            # Create destination directory
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Load URDF asset
            asset = URDFAsset(str(urdf_path), scale=self.scale, transform=self.trans)

            # Convert to trimesh scene
            mesh = asset.as_trimesh_scene()
            
            # Export as GLB
            mesh.export(str(glb_path))
            
            return True
            
        except Exception as e:
            print(f"  Error converting {urdf_path}: {e}")
            return False
    
    def process_object(self, category: str, object_id: str) -> bool:
        """
        Process a single object for URDF to GLB conversion.
        
        Args:
            category: Object category
            object_id: Object ID
            
        Returns:
            bool: True if processing was successful
        """
        object_dir = self.processed_data_dir / category / object_id
        urdf_path = object_dir / "mobility.urdf"
        glb_path = object_dir / "mobility" / "mobility.glb"
        
        if not object_dir.exists():
            print(f"  Object directory not found: {object_dir}")
            return False
        
        if not urdf_path.exists():
            print(f"  URDF file not found: {urdf_path}")
            return False
        
        print(f"  Processing {category}/{object_id}...")
        
        # Preprocess: remove existing mobility directory
        if not self.preprocess_object_dir(object_dir):
            return False
        
        # Convert URDF to GLB
        success = self.convert_urdf_to_glb(urdf_path, glb_path)
        
        if success:
            print(f"  ✓ Successfully converted {category}/{object_id}")
            self.conversion_stats["categories_processed"].add(category)
        else:
            print(f"  ✗ Failed to convert {category}/{object_id}")
            self.conversion_stats["failed_objects"].append(f"{category}/{object_id}")
        
        return success
    
    def get_objects_to_process(self, mode: str, **kwargs) -> List[tuple]:
        """
        Get list of objects to process based on the specified mode.
        
        Args:
            mode: Processing mode ('all', 'random', 'category', 'object')
            **kwargs: Additional arguments for specific modes
            
        Returns:
            List of tuples (category, object_id)
        """
        objects_to_process = []
        
        if mode == "all":
            for category, category_data in self.stats_data.get("categories", {}).items():
                for object_id in category_data.get("objects", []):
                    objects_to_process.append((category, object_id))
        
        elif mode == "random":
            n = kwargs.get("count", 10)
            all_objects = []
            for category, category_data in self.stats_data.get("categories", {}).items():
                for object_id in category_data.get("objects", []):
                    all_objects.append((category, object_id))
            objects_to_process = random.sample(all_objects, min(n, len(all_objects)))
        
        elif mode == "category":
            target_category = kwargs.get("category")
            if target_category in self.stats_data.get("categories", {}):
                category_data = self.stats_data["categories"][target_category]
                for object_id in category_data.get("objects", []):
                    objects_to_process.append((target_category, object_id))
            else:
                print(f"Category '{target_category}' not found in stats.")
        
        elif mode == "object":
            target_object_id = kwargs.get("object_id")
            # Find the category for this object ID
            for category, category_data in self.stats_data.get("categories", {}).items():
                if target_object_id in category_data.get("objects", []):
                    objects_to_process.append((category, target_object_id))
                    break
            else:
                print(f"Object ID '{target_object_id}' not found in stats.")
        
        return objects_to_process
    
    def process_batch(self, mode: str, **kwargs):
        """
        Process a batch of objects based on the specified mode.
        
        Args:
            mode: Processing mode ('all', 'random', 'category', 'object')
            **kwargs: Additional arguments for specific modes
        """
        print(f"\n=== Starting URDF to GLB Batch Conversion ===")
        print(f"Processing mode: {mode}")
        print(f"Processed data directory: {self.processed_data_dir}")
        print(f"Scale factor: {self.scale}")
        
        self.conversion_stats["start_time"] = time.time()
        
        # Get objects to process
        objects_to_process = self.get_objects_to_process(mode, **kwargs)
        
        if not objects_to_process:
            print("No objects to process.")
            return
        
        print(f"Total objects to process: {len(objects_to_process)}")
        
        # Process each object
        for i, (category, object_id) in enumerate(objects_to_process, 1):
            print(f"\n[{i}/{len(objects_to_process)}] Processing {category}/{object_id}")
            self.conversion_stats["total_attempted"] += 1
            
            success = self.process_object(category, object_id)
            if success:
                self.conversion_stats["total_successful"] += 1
            else:
                self.conversion_stats["total_failed"] += 1
        
        self.conversion_stats["end_time"] = time.time()
        self._print_final_stats()
    
    def _print_final_stats(self):
        """Print final conversion statistics."""
        duration = self.conversion_stats["end_time"] - self.conversion_stats["start_time"]
        
        print(f"\n=== URDF to GLB Conversion Statistics ===")
        print(f"Total processing time: {duration:.2f} seconds")
        print(f"Total objects attempted: {self.conversion_stats['total_attempted']}")
        print(f"Total objects successful: {self.conversion_stats['total_successful']}")
        print(f"Total objects failed: {self.conversion_stats['total_failed']}")
        print(f"Success rate: {(self.conversion_stats['total_successful'] / self.conversion_stats['total_attempted'] * 100):.1f}%")
        print(f"Categories processed: {len(self.conversion_stats['categories_processed'])}")
        print(f"Category list: {sorted(self.conversion_stats['categories_processed'])}")
        
        if self.conversion_stats["failed_objects"]:
            print(f"\nFailed objects ({len(self.conversion_stats['failed_objects'])}):")
            for failed_obj in self.conversion_stats["failed_objects"]:
                print(f"  - {failed_obj}")
        
        # Save conversion stats
        stats_output_file = self.processed_data_dir / "glb_conversion_stats.json"
        conversion_stats_serializable = self.conversion_stats.copy()
        conversion_stats_serializable["categories_processed"] = list(conversion_stats_serializable["categories_processed"])
        
        with open(stats_output_file, 'w') as f:
            json.dump(conversion_stats_serializable, f, indent=2)
        
        print(f"\nConversion statistics saved to: {stats_output_file}")


def main():
    """Main function to handle command line arguments and start batch processing."""
    parser = argparse.ArgumentParser(description="Batch convert URDF files to GLB format")
    parser.add_argument("--processed_data_dir", required=True, help="Path to the processed data directory")
    parser.add_argument("--mode", choices=["all", "random", "category", "object"], 
                       default="all", help="Processing mode")
    parser.add_argument("--count", type=int, default=10, 
                       help="Number of random objects to process (for random mode)")
    parser.add_argument("--category", type=str, 
                       help="Specific category to process (for category mode)")
    parser.add_argument("--object-id", type=str, 
                       help="Specific object ID to process (for object mode)")
    parser.add_argument("--scale", type=float, default=1.0, 
                       help="Scale factor for the URDF assets")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.mode == "category" and not args.category:
        parser.error("--category is required when using category mode")
    if args.mode == "object" and not args.object_id:
        parser.error("--object-id is required when using object mode")
    
    # Initialize converter
    converter = URDFToGLBConverter(args.processed_data_dir, scale=args.scale)
    
    # Process based on mode
    if args.mode == "all":
        converter.process_batch("all")
    elif args.mode == "random":
        converter.process_batch("random", count=args.count)
    elif args.mode == "category":
        converter.process_batch("category", category=args.category)
    elif args.mode == "object":
        converter.process_batch("object", object_id=args.object_id)
    
    print("GLB conversion completed.")


if __name__ == "__main__":
    main()
