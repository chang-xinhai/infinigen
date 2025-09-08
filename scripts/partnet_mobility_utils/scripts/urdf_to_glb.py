import numpy as np
import os
import random
import json
from scene_synthesizer.exchange.export import *
import scene_synthesizer.procedural_assets as pa
import scene_synthesizer.utils as utils
from scene_synthesizer.procedural_scenes import *
from trimesh import transformations as tra
from scene_synthesizer.exchange.urdf import scene_as_urdf
from yourdfpy import URDF
import trimesh
from scene_synthesizer.scene import Scene
from scene_synthesizer.usd_import import get_scene_paths
from scene_synthesizer.exchange.usd_export import add_mdl_material, bind_material_to_prims
from pxr import Sdf

import_path = "/home/xinhai/Documents/automoma/assets/object/Microwave/7221/mobility.urdf"
export_type = "glb"
export_path = import_path.replace(".urdf", f"/mobility_3.{export_type}")
# if export_path's folder not exists, create it

trans = np.array([
    [-1,  0, 0 , 0],
    [ 0,  0, 1, 0],
    [ 0,  1, 0, 0],
    [ 0,  0, 0, 1]
])

trans = np.eye(4)

asset = pa.URDFAsset(
    import_path, scale=1.0, transform=trans
)

# asset = pa.URDFAsset(
#     import_path, scale=0.4129899711328229
# )

mesh = asset.as_trimesh_scene()
mesh.export(export_path)
print(f"Exported to {export_path}")
# scene.export(export_path, export_type=export_type)