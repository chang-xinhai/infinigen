# Copyright (C) 2026.

import bpy
import numpy as np

from infinigen.core.rendering.structured_light import StructuredLightRig


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


def test_structured_light_parameters_include_rgb_relative_calibration():
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
    parameters = rig.build_parameters_dict(extrinsics, ["D415", "white"])

    assert set(parameters["intrinsic"]) == {"L", "R", "RGB", "Proj"}
    assert set(parameters["rel_R"]) == {"L", "R", "RGB"}
    assert set(parameters["rel_T"]) == {"L", "R", "RGB"}
    assert np.allclose(parameters["rel_R"]["RGB"], np.eye(3))
    assert np.allclose(parameters["rel_T"]["L"], [-0.0275, 0.0, 0.0])
    assert np.allclose(parameters["rel_T"]["R"], [0.0275, 0.0, 0.0])
    assert np.allclose(parameters["rel_T"]["RGB"], [-0.03025, 0.0, 0.0])
    assert parameters["patterns"] == ["D415", "white"]
    assert parameters["extrinsic"] == extrinsics
