# Copyright (C) 2026.

import bpy
import numpy as np

import infinigen
from infinigen.core.rendering.structured_light import (
    StructuredLightRig,
    _resolve_pattern_paths,
)


def test_structured_light_rig_offsets_rgb_left_of_left_ir():
    baseline = 0.055
    rgb_offset_scale = -0.55
    rig = StructuredLightRig(
        baseline=baseline,
        rgb_offset_scale=rgb_offset_scale,
    )
    rig.build()

    assert np.isclose(rig.left_cam.location.x, -baseline / 2)
    assert np.isclose(rig.right_cam.location.x, baseline / 2)
    assert np.isclose(rig.proj_obj.location.x, 0.0)
    assert np.isclose(rig.rgb_cam.location.x, baseline * rgb_offset_scale)
    assert rig.rgb_cam.location.x < rig.left_cam.location.x < rig.proj_obj.location.x


def test_structured_light_calibration_payload_includes_rgb_relative_calibration():
    rig = StructuredLightRig(baseline=0.055, rgb_offset_scale=-0.55)
    rig.build()

    scene = bpy.data.scenes["Scene"]
    scene.render.resolution_x = rig.resolution_x
    scene.render.resolution_y = rig.resolution_y

    extrinsics = [
        {
            "L": np.eye(4).tolist(),
            "R": np.eye(4).tolist(),
            "RGB": np.eye(4).tolist(),
        }
    ]
    parameters = rig.build_calibration_dict(
        frame_ids=[1],
        extrinsics=extrinsics,
        patterns=["D415", "white"],
        manifest_setting="full",
    )

    assert parameters["setting"] == "full"
    assert set(parameters["intrinsic"]) == {"L", "R", "RGB", "Proj"}
    assert set(parameters["rel_R"]) == {"L", "R", "RGB"}
    assert set(parameters["rel_T"]) == {"L", "R", "RGB"}
    assert np.allclose(parameters["rel_R"]["RGB"], np.eye(3))
    assert np.allclose(parameters["rel_T"]["L"], [-0.0275, 0.0, 0.0])
    assert np.allclose(parameters["rel_T"]["R"], [0.0275, 0.0, 0.0])
    assert np.allclose(parameters["rel_T"]["RGB"], [-0.03025, 0.0, 0.0])
    assert parameters["frame_ids"] == [1]
    assert parameters["patterns"] == ["D415", "white"]
    assert parameters["extrinsic"] == extrinsics


def test_structured_light_default_patterns_resolve_from_repo_assets():
    repo_pattern_dir = infinigen.repo_root() / "data" / "patterns"

    pattern_dir, white_pattern_path, pattern_paths = _resolve_pattern_paths(
        sl_pattern_dir=None,
        sl_pattern_white="white.png",
        sl_pattern_names=["d415", "d435", "kinectsp"],
    )

    assert pattern_dir == repo_pattern_dir
    assert white_pattern_path == repo_pattern_dir / "white.png"
    assert [path.name for path in pattern_paths] == [
        "D415.png",
        "D435.png",
        "kinectsp.png",
    ]
