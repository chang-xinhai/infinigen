# Copyright (C) 2026.

import bpy

from infinigen.core.placement import camera
from infinigen.core.util import camera as camera_util


def test_adjust_camera_sensor_supports_848x480():
    bpy.context.scene.render.resolution_x = 848
    bpy.context.scene.render.resolution_y = 480
    cam = camera.spawn_camera()

    camera.adjust_camera_sensor(cam)

    assert cam.data.sensor_height == 18
    assert abs(cam.data.sensor_width - 31.8) < 1e-6
    camera_util.get_calibration_matrix_K_from_blender(cam.data)
