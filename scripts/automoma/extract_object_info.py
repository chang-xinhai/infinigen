#!/usr/bin/env python3
"""
Extract Object Information from Blender Files

This script extracts object metadata from a single Blender scene file.
Designed to be called from the kitchen generation pipeline.

Usage:
    blender --background scene.blend --python extract_object_info.py -- --blend_file scene.blend --output metadata.json
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

# Blender imports (must be available when run in Blender context)
try:
    import bpy
    from mathutils import Vector, Matrix
    BLENDER_AVAILABLE = True
except ImportError:
    print("Error: This script must be run in Blender context")
    sys.exit(1)


def matrix_to_list(matrix: Matrix) -> List[List[float]]:
    """Convert Blender Matrix to numpy-compatible list."""
    return [[float(matrix[i][j]) for j in range(4)] for i in range(4)]


def vector_to_list(vector) -> List[float]:
    """Convert Blender Vector to numpy-compatible list."""
    return [float(x) for x in vector]


def extract_single_object_info(obj) -> Optional[Dict]:
    """Extract information from a single Blender object."""
    name = obj.name.split(".")[0]
    
    # Parse asset information from object name
    asset_type = None
    asset_id = None
    
    if "(" in name and ")" in name:
        inside = name.split("(")[1].split(")")[0]
        parts = inside.split("_")
        if len(parts) >= 2:
            asset_type = parts[0]
            asset_id = parts[1]
    
    # Get transformation information
    matrix = obj.matrix_world
    position = matrix.to_translation()
    rotation = matrix.to_euler()
    scale = matrix.to_scale()
    dimensions = obj.dimensions
    
    # Calculate bounding box corners in world space
    bbox_corners = [matrix @ Vector(corner) for corner in obj.bound_box]
    
    return {
        "name": name,
        "asset_type": asset_type,
        "asset_id": asset_id,
        "matrix": matrix_to_list(matrix),
        "position": vector_to_list(position),
        "rotation": vector_to_list(rotation),
        "scale": vector_to_list(scale),
        "dimensions": vector_to_list(dimensions),
        "bbox_corners": [vector_to_list(corner) for corner in bbox_corners]
    }


def extract_object_info_from_blender(blend_file_path: str) -> Dict:
    """Extract object information from a Blender file."""
    # Load the Blender file
    bpy.ops.wm.open_mainfile(filepath=blend_file_path)
    
    # Scene metadata
    scene_info = {
        "total_objects": len(bpy.data.objects),
        "total_materials": len(bpy.data.materials),
        "total_meshes": len(bpy.data.meshes)
    }
    
    # Extract static objects
    static_objects = {}
    static_name = "StaticCategoryFactory"
    dataset_name = "mobility"
    
    for obj in bpy.data.objects:
        if (static_name.lower() in obj.name.lower() and 
            dataset_name.lower() in obj.name.lower()):
            
            obj_info = extract_single_object_info(obj)
            if obj_info:
                static_objects[obj_info["name"]] = obj_info
    
    return {
        "scene_info": scene_info,
        "static_objects": static_objects
    }


def run_extraction(blend_file_path: str, output_json_path: str):
    """Run object extraction and save to JSON."""
    # Extract object information
    object_data = extract_object_info_from_blender(blend_file_path)
    
    # Find USD file in the same directory structure
    blend_path = Path(blend_file_path)
    scene_dir = blend_path.parent.parent  # Go up from scene/scene.blend to scene_X_seedY/
    export_dir = scene_dir / "export"
    usd_file_path = None
    
    if export_dir.exists():
        usd_files = list(export_dir.glob("**/*.usdc")) + list(export_dir.glob("**/*.usd"))
        if usd_files:
            usd_file_path = str(usd_files[0])
    
    # Create metadata
    metadata = {
        "scene_name": scene_dir.name,
        "blender_file_path": blend_file_path,
        "usd_file_path": usd_file_path,
        "static_objects": object_data.get("static_objects", {}),
        "scene_stats": object_data.get("scene_info", {}),
        "extraction_info": {
            "extracted_with_blender": True,
            "total_static_objects": len(object_data.get("static_objects", {}))
        }
    }
    
    # Save as JSON
    with open(output_json_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Extracted {len(object_data.get('static_objects', {}))} static objects")
    print(f"💾 Object information extracted to: {output_json_path}")


def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Extract object information from Blender files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Usage in pipeline:
            blender --background scene.blend --python extract_object_info.py -- --blend_file scene.blend --output metadata.json

            Example:
            python -m infinigen.launch_blender scene.blend --background --python extract_object_info.py -- --blend_file scene.blend --output metadata.json
                    """
    )
    
    parser.add_argument(
        "--blend_file", 
        required=True, 
        help="Path to the Blender scene file (.blend)"
    )
    
    parser.add_argument(
        "--output", 
        required=True, 
        help="Path to the output JSON metadata file"
    )
    
    # Parse arguments
    try:
        args = parser.parse_args()
    except SystemExit:
        # argparse calls sys.exit() on error, but we want to ensure proper exit
        sys.exit(1)
    
    # Validate inputs
    blend_file = Path(args.blend_file)
    if not blend_file.exists():
        print(f"Error: Blender file not found: {blend_file}")
        sys.exit(1)
    
    if not blend_file.suffix.lower() == '.blend':
        print(f"Error: Input file must be a .blend file: {blend_file}")
        sys.exit(1)
    
    # Create output directory if needed
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Run extraction
    try:
        run_extraction(str(blend_file), str(output_file))
    except Exception as e:
        print(f"Error during extraction: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
