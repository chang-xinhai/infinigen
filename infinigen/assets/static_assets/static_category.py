# Copyright (C) 2024, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

# Authors:
# - Karhan Kayan

import os
import random

import bpy

import sys
sys.path.append("/home/xinhai/Documents/cuakr-docker/scene/infinigen")

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
            
            # For exmaple assets
            # self.path_to_assets = f"infinigen/assets/static_assets/source/{self.asset_type}"
            # self.asset_dir = self.path_to_assets
            # asset_files = [
            #     f
            #     for f in os.listdir(self.asset_dir)
            #     if f.lower().endswith(tuple(self.import_map.keys()))
            # ]
                        
            # For partnet_mobility assets
            self.path_to_assets = f"assets/partnet_mobility/processed_data/{self.asset_type}"
            self.asset_dir = self.path_to_assets
            asset_files = [
                f
                for f in os.listdir(self.asset_dir)
                if os.path.isdir(os.path.join(self.asset_dir, f))
            ]
            if not asset_files or len(asset_files) == 0:
                raise ValueError(f"No valid asset files found in {self.asset_dir}")
            
            # TODO: for testing
            # asset_files = [f for f in asset_files if f.count("test")]
            
            print(f"[StaticCategoryFactory] asset_files: {asset_files}")
            
            self.asset_file = random.choice(asset_files)
            
            # Isaacsim usd cannot perfectly import the mobility.usd into blender type
            # self.asset_file_path = os.path.join(self.asset_dir, self.asset_file, "mobility", "mobility.usd")
            self.asset_file_path = os.path.join(self.asset_dir, self.asset_file, "mobility", "mobility.glb")
            

            super().__init__(factory_seed, coarse)
            with FixedSeed(factory_seed):
                self.tag_support = tag_support
                self.x_dim, self.y_dim, self.z_dim = x_dim, y_dim, z_dim
                self.scale = scale
                self.rotation_euler = rotation_euler

                print(f"[StaticCategoryFactory] Selected asset file: {self.asset_file} from {self.asset_dir}, asset type: {self.asset_type}, factory seed: {self.factory_seed}")
                print(f"[StaticCategoryFactory] Asset file path: {self.asset_file_path}")
        # Custom string representation for the StaticCategoryFactory
        def __repr__(self):
            if self.asset_type:
                return f"{self.__class__.__name__}({self.asset_type}_{self.asset_file}_{self.factory_seed}_mobility)"
            return super().__repr__()

        def create_asset(self, **params) -> bpy.types.Object:
            imported_obj = self.import_file(self.asset_file_path)
            if self.scale is not None:
                scale = self.scale
                imported_obj.scale = (scale, scale, scale)
            elif (
                self.x_dim is not None
                or self.y_dim is not None
                or self.z_dim is not None
            ):
                # check only one dimension is provided
                if (
                    sum(
                        [
                            1
                            for dim in [self.x_dim, self.y_dim, self.z_dim]
                            if dim is not None
                        ]
                    )
                    != 1
                ):
                    raise ValueError("Only one dimension can be provided")
                if self.x_dim is not None:
                    scale = self.x_dim / imported_obj.dimensions[0]
                elif self.y_dim is not None:
                    scale = self.y_dim / imported_obj.dimensions[1]
                else:
                    scale = self.z_dim / imported_obj.dimensions[2]
                imported_obj.scale = (scale, scale, scale)
            if self.tag_support:
                tag_support_surfaces(imported_obj)

            if imported_obj:
                return imported_obj
            else:
                raise ValueError(f"Failed to import asset: {self.asset_file}")

    return StaticCategoryFactory


# Create factory instances for different categories

# Infinigen examples
# StaticSofaFactory = static_category_factory("Sofa")
# StaticTableFactory = static_category_factory("Table")
# StaticShelfFactory = static_category_factory("Shelf", tag_support=True, z_dim=2)

# PartNet-Mobility examples
StaticMicrowaveFactory = static_category_factory("Microwave", scale=0.4)
# StaticRefrigeratorFactory = static_category_factory("Refrigerator")


if __name__ == "__main__":
    print("[static_category] Defined static asset factories for categories: Microwave, Refrigerator")
    microwave = StaticMicrowaveFactory(42)
