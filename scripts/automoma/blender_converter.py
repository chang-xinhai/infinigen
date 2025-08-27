import subprocess
import bpy

from pathlib import Path

import_path = "/home/xinhai/Documents/cuakr-docker/scene/infinigen/outputs/kitchen_test/0827_2/scenes/scene.blend"
export_path = "/home/xinhai/Documents/cuakr-docker/scene/infinigen/outputs/kitchen_test/0827_2/exports/scene.glb"


if import_path.endswith('.blend'):
    bpy.ops.wm.open_mainfile(filepath=import_path)
elif import_path.endswith('.glb'):
    bpy.ops.import_scene.gltf(filepath=import_path)
elif import_path.endswith('.fbx'):
    bpy.ops.import_scene.fbx(filepath=import_path)
    if not bpy.context.object:
        print("No object found in the imported file.")
        bpy.context.view_layer.objects.active = bpy.data.objects[0]
        bpy.data.objects[0].select_set(True)
else:
    print("Unsupported file format. Please use .glb or .fbx.")
    raise SystemExit

# Optional: Print scene information
print(f"Scene loaded with {len(bpy.data.objects)} objects")
print(f"Materials: {len(bpy.data.materials)}")
print(f"Meshes: {len(bpy.data.meshes)}")

# Export the model
if export_path.endswith('.glb'):
    bpy.ops.export_scene.gltf(filepath=export_path)
elif export_path.endswith('.fbx'):
    bpy.ops.export_scene.fbx(filepath=export_path)
elif export_path.endswith('.obj'):
    bpy.ops.wm.obj_export(filepath=export_path)
elif export_path.endswith('.stl'):
    bpy.ops.wm.stl_export(filepath=export_path)
elif export_path.endswith('.usd'):
    bpy.ops.wm.usd_export(filepath=export_path)
else:
    print("Unsupported file format. Please use .glb, .fbx, .obj, .stl, or .usdc.")
    raise SystemExit
print(f"Converted {import_path} to {export_path}")
import os
file_size = os.path.getsize(export_path) / (1024 * 1024)  # MB
print(f"Output file size: {file_size:.2f} MB")