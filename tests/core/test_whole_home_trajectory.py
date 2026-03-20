# Copyright (C) 2026.

import math
import numpy as np
from mathutils import Euler, Matrix, Vector

from infinigen.core.placement.whole_home_trajectory import (
    DoorRecord,
    RoomRecord,
    _append_orbit_sweep,
    _apply_handheld_perturbation,
    _apply_height_perturbation,
    _astar_grid_path,
    _door_anchor,
    _infer_portal_center,
    _room_path_segment,
    _shortcut_polyline,
    _world_bounds_from_box,
)


def _room(name: str, bbox_min, bbox_max) -> RoomRecord:
    bbox_min = Vector(bbox_min)
    bbox_max = Vector(bbox_max)
    center = Vector(
        (
            (bbox_min.x + bbox_max.x) * 0.5,
            (bbox_min.y + bbox_max.y) * 0.5,
            1.55,
        )
    )
    return RoomRecord(
        name=name,
        mesh_name=f"{name}.meshed",
        semantic="room",
        area=float((bbox_max.x - bbox_min.x) * (bbox_max.y - bbox_min.y)),
        center=center,
        floor_z=0.0,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
    )


def test_infer_portal_center_for_side_by_side_rooms():
    living = _room("living", (0.0, 0.0, 0.0), (4.0, 6.0, 3.0))
    bedroom = _room("bedroom", (4.0, 1.0, 0.0), (8.0, 5.0, 3.0))

    portal = _infer_portal_center(living, bedroom, camera_height_m=1.55)

    assert portal == Vector((4.0, 3.0, 1.55))


def test_door_anchor_stays_inside_room_bounds():
    room = _room("living", (0.0, 0.0, 0.0), (4.0, 6.0, 3.0))
    door = DoorRecord(
        name="door",
        mesh_name="door",
        rooms=("living", "bedroom"),
        center=Vector((4.0, 3.0, 1.55)),
    )

    anchor = _door_anchor(door, room, offset_m=0.35, clearance_m=0.2)

    assert 0.2 <= anchor.x <= 3.8
    assert 0.2 <= anchor.y <= 5.8
    assert anchor.z == room.center.z
    assert anchor.x < door.center.x


def test_room_path_segment_uses_orthogonal_turn_inside_room():
    room = _room("living", (0.0, 0.0, 0.0), (8.0, 8.0, 3.0))
    start = Vector((6.5, 6.5, 1.55))
    end = Vector((2.0, 1.0, 1.55))

    points = _room_path_segment(
        room=room,
        start=start,
        end=end,
        linear_step_m=0.5,
        clearance_m=0.2,
    )

    assert len(points) >= 3
    assert points[0] == start
    assert points[-1] == end
    turn_points = [p for p in points[1:-1] if p.x == end.x or p.y == end.y]
    assert turn_points
    mid = turn_points[0]
    assert room.bbox_min.x + 0.2 <= mid.x <= room.bbox_max.x - 0.2
    assert room.bbox_min.y + 0.2 <= mid.y <= room.bbox_max.y - 0.2


def test_world_bounds_from_box_applies_world_transform():
    bound_box = [
        (-1.0, -2.0, -0.5),
        (1.0, -2.0, -0.5),
        (1.0, 2.0, -0.5),
        (-1.0, 2.0, -0.5),
        (-1.0, -2.0, 0.5),
        (1.0, -2.0, 0.5),
        (1.0, 2.0, 0.5),
        (-1.0, 2.0, 0.5),
    ]
    matrix_world = Matrix.Translation(Vector((4.0, 5.0, 1.0)))

    bbox_min, bbox_max = _world_bounds_from_box(bound_box, matrix_world)

    assert np.allclose(bbox_min, np.array([3.0, 3.0, 0.5]))
    assert np.allclose(bbox_max, np.array([5.0, 7.0, 1.5]))


def test_astar_grid_path_routes_around_blocked_cells():
    valid = np.ones((5, 5), dtype=bool)
    valid[2, 1:4] = False

    path = _astar_grid_path(valid, (0, 2), (4, 2))

    assert path is not None
    assert path[0] == (0, 2)
    assert path[-1] == (4, 2)
    assert all(valid[idx] for idx in path)
    assert any(step[1] != 2 for step in path)


def test_shortcut_polyline_removes_visibility_redundant_turns():
    points = [
        Vector((0.0, 0.0, 0.0)),
        Vector((1.0, 0.0, 0.0)),
        Vector((1.0, 1.0, 0.0)),
        Vector((2.0, 1.0, 0.0)),
    ]

    shortcut = _shortcut_polyline(points, is_segment_valid=lambda a, b: True)

    assert shortcut == [Vector((0.0, 0.0, 0.0)), Vector((2.0, 1.0, 0.0))]


def test_apply_height_perturbation_is_bounded_and_deterministic():
    room = _room("living", (0.0, 0.0, 0.0), (6.0, 6.0, 3.0))
    samples = [
        {
            "location": Vector((float(idx), 0.0, room.center.z)),
            "rotation": Vector((0.0, 0.0, 0.0)),
            "room": room.name,
            "state": "room_to_door",
        }
        for idx in range(6)
    ]

    summary_a = _apply_height_perturbation(
        samples=samples,
        rooms={room.name: room},
        camera_height_m=1.55,
        planner_fps=4,
        amplitude_m=0.04,
        frequency_hz=0.35,
        scene_seed=7,
    )
    z_values_a = [sample["location"].z for sample in samples]
    offsets_a = [sample["height_offset_m"] for sample in samples]

    samples_b = [
        {
            "location": Vector((float(idx), 0.0, room.center.z)),
            "rotation": Vector((0.0, 0.0, 0.0)),
            "room": room.name,
            "state": "room_to_door",
        }
        for idx in range(6)
    ]
    summary_b = _apply_height_perturbation(
        samples=samples_b,
        rooms={room.name: room},
        camera_height_m=1.55,
        planner_fps=4,
        amplitude_m=0.04,
        frequency_hz=0.35,
        scene_seed=7,
    )

    assert summary_a["enabled"] is True
    assert summary_a == summary_b
    assert offsets_a == [sample["height_offset_m"] for sample in samples_b]
    assert z_values_a == [sample["location"].z for sample in samples_b]
    assert all(abs(offset) <= 0.04 + 1e-6 for offset in offsets_a)
    assert any(abs(offset) > 1e-3 for offset in offsets_a)


def test_apply_handheld_perturbation_is_bounded_smooth_and_deterministic():
    samples_a = [
        {
            "location": Vector((0.02 * idx, 0.0, 1.55)),
            "rotation": Euler((math.pi / 2, 0.0, 0.0)),
            "room": "living",
            "state": "room_to_door",
        }
        for idx in range(30)
    ]

    summary_a = _apply_handheld_perturbation(
        samples=samples_a,
        planner_fps=20,
        scene_seed=17,
        lateral_amplitude_m=0.03,
        yaw_amplitude_deg=2.5,
        pitch_amplitude_deg=0.75,
        noise_sigma_s=0.45,
        forward_smoothing_window=4,
    )
    lateral_a = [sample["handheld_lateral_offset_m"] for sample in samples_a]
    yaw_a = [sample["handheld_yaw_offset_deg"] for sample in samples_a]
    pitch_a = [sample["handheld_pitch_offset_deg"] for sample in samples_a]

    samples_b = [
        {
            "location": Vector((0.02 * idx, 0.0, 1.55)),
            "rotation": Euler((math.pi / 2, 0.0, 0.0)),
            "room": "living",
            "state": "room_to_door",
        }
        for idx in range(30)
    ]
    summary_b = _apply_handheld_perturbation(
        samples=samples_b,
        planner_fps=20,
        scene_seed=17,
        lateral_amplitude_m=0.03,
        yaw_amplitude_deg=2.5,
        pitch_amplitude_deg=0.75,
        noise_sigma_s=0.45,
        forward_smoothing_window=4,
    )

    assert summary_a["enabled"] is True
    assert summary_a == summary_b
    assert lateral_a == [sample["handheld_lateral_offset_m"] for sample in samples_b]
    assert yaw_a == [sample["handheld_yaw_offset_deg"] for sample in samples_b]
    assert pitch_a == [sample["handheld_pitch_offset_deg"] for sample in samples_b]
    assert max(abs(offset) for offset in lateral_a) <= 0.03 + 1e-6
    assert max(abs(offset) for offset in yaw_a) <= 2.5 + 1e-6
    assert max(abs(offset) for offset in pitch_a) <= 0.75 + 1e-6
    assert max(abs(lateral_a[idx] - lateral_a[idx - 1]) for idx in range(1, len(lateral_a))) < 0.02
    assert max(abs(yaw_a[idx] - yaw_a[idx - 1]) for idx in range(1, len(yaw_a))) < 1.2


def test_append_orbit_sweep_enters_ring_smoothly_without_position_jump():
    center = Vector((0.0, 0.0, 1.55))
    samples = []

    _append_orbit_sweep(
        samples=samples,
        center=center,
        room_name="living",
        fps=20,
        orbit_radius_m=0.5,
        sweep_angle_deg=180.0,
        orbit_linear_speed_mps=0.15,
        pitch_deg=-2.0,
        start_location=center.copy(),
        start_rotation=Euler((math.pi / 2, 0.0, 0.0)),
        entry_transition_sec=0.45,
        focus_blend=0.9,
    )

    assert samples
    step_lengths = [
        (samples[idx]["location"] - samples[idx - 1]["location"]).length
        for idx in range(1, len(samples))
    ]
    orbit_samples = [sample for sample in samples if sample["state"] == "room_orbit"]
    orbit_radii = [(sample["location"] - center).length for sample in orbit_samples]

    assert samples[0]["state"] == "room_orbit_entry"
    assert max(step_lengths) < 0.08
    assert orbit_samples
    assert min(orbit_radii) >= 0.45 - 1e-6
    assert max(orbit_radii) <= 0.55 + 1e-6
    assert abs(float(np.mean(orbit_radii)) - 0.5) < 0.03
