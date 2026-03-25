from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SceneRenderOverrides:
    hide_render_objects: tuple[str, ...] = ()
    world_background_color: tuple[float, float, float, float] | None = None
    world_background_strength: float = 1.0


@dataclass(frozen=True)
class SceneCalibration:
    rotation: np.ndarray
    translation: np.ndarray
    scale: float
    render_overrides: SceneRenderOverrides
    description: str


DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD = np.array(
    [
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=np.float64,
)

DEFAULT_SCENE_CALIBRATION = SceneCalibration(
    rotation=DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD,
    translation=np.zeros(3, dtype=np.float64),
    scale=1.0,
    render_overrides=SceneRenderOverrides(),
    description="Default OpenGL-world Y-up to Blender-world Z-up transform",
)

SCENE_CALIBRATIONS = {
    "breakfast_room": SceneCalibration(
        rotation=np.array(
            [
                [0.9986136, 0.00242596, 0.05257983],
                [0.04988489, 0.275104, -0.96011466],
                [-0.01679528, 0.96141579, 0.27460282],
            ],
            dtype=np.float64,
        ),
        translation=np.array([0.11825254, 2.00876153, -1.28263893], dtype=np.float64),
        scale=3.65,
        render_overrides=SceneRenderOverrides(
            hide_render_objects=(
                "Lamp",
                "Area Light",
                "Lampshade",
                "Lampshade.001",
                "Venetian Blind",
                "Wall Canvas ",
            ),
            world_background_color=(0.78, 0.78, 0.78, 1.0),
            world_background_strength=1.0,
        ),
        description=(
            "Breakfast room calibration validated against Neural RGB-D img0 to correct "
            "world alignment, scale mismatch, and obvious scene-setup differences"
        ),
    ),
}


def get_scene_calibration(scene_name: str) -> SceneCalibration:
    return SCENE_CALIBRATIONS.get(scene_name, DEFAULT_SCENE_CALIBRATION)
