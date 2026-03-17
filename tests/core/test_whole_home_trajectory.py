# Copyright (C) 2026.

import numpy as np
from mathutils import Matrix, Vector

from infinigen.core.placement.whole_home_trajectory import (
    DoorRecord,
    RoomRecord,
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
