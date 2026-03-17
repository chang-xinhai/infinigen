# Copyright (C) 2026.

from mathutils import Vector

from infinigen.core.placement.whole_home_trajectory import (
    DoorRecord,
    RoomRecord,
    _door_anchor,
    _infer_portal_center,
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
