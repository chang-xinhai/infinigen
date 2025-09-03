# Copyright (C) 2024, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors:
# - Karhan Kayan

import os
import random
import json

import bpy

import sys
sys.path.append("/home/xinhai/Documents/automoma/third_party/infinigen")

from automoma.utils.config import abs_path

from infinigen.assets.static_assets.base import StaticAssetFactory
from infinigen.core.tagging import tag_support_surfaces
from infinigen.core.util.math import FixedSeed
def static_category_factory(
    asset_type: str,
    tag_support=False,
    x_dim: float = None,
    y_dim: float = None,
    z_dim: float = None,
    scale: float = None,
    rotation_euler: tuple[float] = None,
) -> StaticAssetFactory:
    """
    Create a factory for external asset import.
    tag_support: tag the planes of the object that are parallel to xy plane as support surfaces (e.g. shelves)
    x_dim, y_dim, z_dim: specify ONLY ONE dimension for the imported object. The object will be scaled accordingly.
    rotation_euler: sets the rotation of the object in euler angles. The object will not be rotated if not specified.
    """
    class StaticCategoryFactory(StaticAssetFactory):
        def __init__(self, factory_seed, coarse=False, asset_type=asset_type):
            self.asset_type = asset_type
            self.asset_id = None
            self.urdf_path = None
            self.requirement_scale = None
            
            # Try to load from requirements first, fallback to random loading
            if not self.loading_from_requirement():
                self.loading_randomly()
            
            # Initialize the parent class and set parameters
            super().__init__(factory_seed, coarse)
            with FixedSeed(factory_seed):
                self.tag_support = tag_support
                self.x_dim, self.y_dim, self.z_dim = x_dim, y_dim, z_dim
                self.scale = self.requirement_scale if self.requirement_scale is not None else scale
                self.rotation_euler = rotation_euler

        def loading_from_requirement(self) -> bool:
            """
            Load asset configuration from requirement.json file.
            Returns True if successfully loaded from requirements, False otherwise.
            """
            try:
                # Get the path to requirement.json in the same directory
                current_dir = os.path.dirname(os.path.abspath(__file__))
                requirements_path = os.path.join(current_dir, "requirement.json")
                
                if not os.path.exists(requirements_path):
                    print(f"[StaticCategoryFactory] requirement.json not found at {requirements_path}")
                    return False
                
                # Load and parse the requirements file
                with open(requirements_path, 'r') as f:
                    requirements_data = json.load(f)
                
                # Filter objects by asset_type
                matching_objects = [
                    obj for obj in requirements_data.get("static_objects", [])
                    if obj.get("asset_type") == self.asset_type
                ]
                
                if not matching_objects:
                    print(f"[StaticCategoryFactory] Asset type '{self.asset_type}' not found in requirements.json")
                    return False
                
                # Randomly select from matching objects
                selected_object = random.choice(matching_objects)
                self.asset_id = selected_object.get("asset_id")
                self.urdf_path = selected_object.get("urdf_path")
                self.requirement_scale = selected_object.get("scale")
                
                # Set paths based on requirements
                self.asset_file = self.asset_id
                self.asset_file_path = self.urdf_path.replace("mobility.urdf", os.path.join("mobility", "mobility.glb"))
                
                print(f"[StaticCategoryFactory] Loading from requirements.json:")
                print(f"  - Asset ID: {self.asset_id}")
                print(f"  - Asset Type: {self.asset_type}")
                print(f"  - Scale: {self.requirement_scale}")
                print(f"  - File Path: {self.asset_file_path}")
                
                return True
                
            except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
                print(f"[StaticCategoryFactory] Error reading requirements.json: {e}")
                return False
        
        def loading_randomly(self) -> None:
            """
            Load asset configuration by randomly selecting from available assets.
            """
            print(f"[StaticCategoryFactory] Loading randomly for asset type '{self.asset_type}'")
            
            # Set up paths for partnet_mobility assets
            self.asset_dir = f"assets/object/{self.asset_type}"
            
            # Find available asset directories
            asset_files = [
                f for f in os.listdir(self.asset_dir)
                if os.path.isdir(os.path.join(self.asset_dir, f))
            ]
            
            if not asset_files:
                raise ValueError(f"No valid asset files found in {self.asset_dir}")
            
            # Randomly select an asset
            self.asset_file = random.choice(asset_files)
            self.asset_file_path = os.path.join(
                self.asset_dir, self.asset_file, "mobility", "mobility.glb"
            )
            
            print(f"[StaticCategoryFactory] Random selection:")
            print(f"  - Available assets: {len(asset_files)} options")
            print(f"  - Selected asset: {self.asset_file}")
            print(f"  - Asset directory: {self.asset_dir}")
            print(f"  - File path: {self.asset_file_path}")
        def __repr__(self) -> str:
            """Custom string representation for the StaticCategoryFactory."""
            if self.asset_type:
                asset_identifier = self.asset_id if self.asset_id else self.asset_file
                return f"{self.__class__.__name__}({self.asset_type}_{asset_identifier}_{self.factory_seed}_mobility)"
            return super().__repr__()

        def create_asset(self, **params) -> bpy.types.Object:
            """Create and import the asset object with proper scaling."""
            imported_obj = self.import_file(self.asset_file_path)
            
            # Apply scaling based on different parameters
            if self.scale is not None:
                scale = self.scale
                imported_obj.scale = (scale, scale, scale)
            elif any(dim is not None for dim in [self.x_dim, self.y_dim, self.z_dim]):
                scale = self._calculate_dimension_scale(imported_obj)
                imported_obj.scale = (scale, scale, scale)
            
            # Tag support surfaces if requested
            if self.tag_support:
                tag_support_surfaces(imported_obj)

            if imported_obj:
                return imported_obj
            else:
                asset_identifier = self.asset_id if self.asset_id else self.asset_file
                raise ValueError(f"Failed to import asset: {asset_identifier}")
        
        def _calculate_dimension_scale(self, imported_obj) -> float:
            """Calculate scale based on specified dimensions."""
            # Check only one dimension is provided
            dimensions = [self.x_dim, self.y_dim, self.z_dim]
            non_none_dims = [dim for dim in dimensions if dim is not None]
            
            if len(non_none_dims) != 1:
                raise ValueError("Only one dimension can be provided")
            
            if self.x_dim is not None:
                return self.x_dim / imported_obj.dimensions[0]
            elif self.y_dim is not None:
                return self.y_dim / imported_obj.dimensions[1]
            else:  # self.z_dim is not None
                return self.z_dim / imported_obj.dimensions[2]

    return StaticCategoryFactory


# Create factory instances for different categories

# Infinigen examples
# StaticSofaFactory = static_category_factory("Sofa")
# StaticTableFactory = static_category_factory("Table")
# StaticShelfFactory = static_category_factory("Shelf", tag_support=True, z_dim=2)

# PartNet-Mobility examples
# TODO: adjust the scale ranges based on the actual object sizes
'''
For ao-grasp objects:
1. Microwave: scale [0.355 -- 0.433]
2. Oven: scale [0.636 -- 0.760]
3. StorageFurniture: scale [0.446 -- 0.579]
4. TrashCan: scale [0.460 -- 0.547]
5. Dishwasher: scale [0.532 -- 0.701]
'''
import numpy as np
StaticMicrowaveFactory = static_category_factory("Microwave", scale=np.random.uniform(0.355, 0.433))
StaticOvenFactory = static_category_factory("Oven", scale=np.random.uniform(0.636, 0.760))
StaticStorageFurnitureFactory = static_category_factory("StorageFurniture", scale=np.random.uniform(0.446, 0.579), tag_support=True)
StaticTrashCanFactory = static_category_factory("TrashCan", scale=np.random.uniform(0.460, 0.547))
StaticDishwasherFactory = static_category_factory("Dishwasher", scale=np.random.uniform(0.532, 0.701))

# Manually checked
StaticRefrigeratorFactory = static_category_factory("Refrigerator", scale=np.random.uniform(0.8, 1.0))

if __name__ == "__main__":
    print("[static_category] Defined static asset factories for categories: Microwave, Refrigerator")
    microwave = StaticMicrowaveFactory(42)
