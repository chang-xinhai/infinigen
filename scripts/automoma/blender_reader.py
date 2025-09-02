import subprocess
import bpy
from mathutils import Vector

from pathlib import Path

import_path = "/home/xinhai/Documents/cuakr-docker/scene/infinigen/outputs/kitchen_test/kitchen_0901_2/scenes/scene_0_seed_0/scene.blend"

bpy.ops.wm.open_mainfile(filepath=import_path)

# Optional: Print scene information
print(f"Scene loaded with {len(bpy.data.objects)} objects")
print(f"Materials: {len(bpy.data.materials)}")
print(f"Meshes: {len(bpy.data.meshes)}")

static_name = "StaticCategoryFactory"
dataset_name = "mobility"

for o in bpy.data.objects: # can also iterate over "o.obj for o in state.objs"
    if static_name.lower() in o.name.lower() and dataset_name.lower() in o.name.lower():
        name = o.name.split(".")[0]
        if "(" in name and ")" in name:
            inside = name.split("(")[1].split(")")[0]
            parts = inside.split("_")
            if len(parts) == 4:
                asset_type, asset_file, factory_seed, dataset_name = parts
                print(f"  Asset Type: {asset_type}")
                print(f"  Asset File: {asset_file}")
                print(f"  Factory Seed: {factory_seed}")
                print(f"  Dataset Name: {dataset_name}")
        matrix = o.matrix_world
        position = matrix.to_translation()
        rotation = matrix.to_euler()
        scale = matrix.to_scale()
        dimensions = o.dimensions
        bbox_corners = [matrix @ Vector(corner) for corner in o.bound_box]
        print(f"########### Get object info of {name} ###########")
        print(f"  Position: {position}")
        print(f"  Rotation (Euler): {rotation}")
        print(f"  Scale: {scale}")
        print(f"  Dimensions: {dimensions}")
        print(f"  Bounding Box Corners: {bbox_corners}")








