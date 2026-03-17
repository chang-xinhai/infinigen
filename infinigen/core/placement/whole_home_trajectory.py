# Copyright (C) 2026.

import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import bpy
import gin
import numpy as np
from mathutils import Euler, Vector

from infinigen.core.util import blender as butil

logger = logging.getLogger(__name__)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _yaw_from_vector(vec: Vector) -> float:
    return math.atan2(vec.y, vec.x) - math.pi / 2


def _look_rotation(origin: Vector, target: Vector, pitch_deg: float = 0.0) -> Euler:
    direction = target - origin
    if direction.length < 1e-6:
        return Euler((math.radians(90 + pitch_deg), 0.0, 0.0))
    yaw = _yaw_from_vector(direction)
    xy_len = math.hypot(direction.x, direction.y)
    pitch = math.atan2(direction.z, max(xy_len, 1e-6))
    return Euler((math.pi / 2 + pitch + math.radians(pitch_deg), 0.0, yaw))


def _resample_polyline(points: list[Vector], step: float) -> list[Vector]:
    if len(points) <= 1:
        return list(points)
    result = [points[0].copy()]
    carry = 0.0
    for idx in range(1, len(points)):
        start = points[idx - 1]
        end = points[idx]
        segment = end - start
        seg_len = segment.length
        if seg_len < 1e-6:
            continue
        direction = segment.normalized()
        distance = step - carry if carry > 1e-8 else step
        while distance <= seg_len + 1e-8:
            result.append(start + direction * distance)
            distance += step
        carry = max(0.0, seg_len - (distance - step))
    if (result[-1] - points[-1]).length > 1e-6:
        result.append(points[-1].copy())
    return result


def _clear_animation(obj: bpy.types.Object):
    if obj.animation_data is not None:
        obj.animation_data_clear()


@dataclass
class RoomRecord:
    name: str
    mesh_name: str
    semantic: str
    area: float
    center: Vector
    floor_z: float
    bbox_min: Vector
    bbox_max: Vector


@dataclass
class DoorRecord:
    name: str
    mesh_name: str
    rooms: tuple[str, ...]
    center: Vector


class WholeHomeWalkError(RuntimeError):
    pass


def _load_state(scene_folder: Path) -> dict:
    state_path = scene_folder / "solve_state.json"
    if not state_path.exists():
        raise WholeHomeWalkError(f"Missing solve state at {state_path}")
    with state_path.open("r", encoding="utf-8") as f:
        return json.load(f)["objs"]


def _semantic_from_tags(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith("Semantics(") and tag not in {"Semantics(room)", "Semantics(door)", "Semantics(cutter)"}:
            return tag.removeprefix("Semantics(").removesuffix(")")
    return "room"


def _resolve_object(mesh_name: str) -> bpy.types.Object | None:
    if mesh_name in bpy.data.objects:
        return bpy.data.objects[mesh_name]
    stem = mesh_name.removesuffix(".meshed")
    for obj in bpy.data.objects:
        if obj.name == stem or obj.name.startswith(stem):
            return obj
        if obj.name == mesh_name or obj.name.startswith(mesh_name):
            return obj
    return None


def _bounds(obj: bpy.types.Object):
    bounds = np.array(butil.bounds(obj))
    return bounds.min(axis=0), bounds.max(axis=0)


def _candidate_ring(center: Vector, radii: tuple[float, ...], samples: int) -> list[Vector]:
    candidates = [center.copy()]
    for radius in radii:
        for angle in np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False):
            candidates.append(
                Vector(
                    (
                        center.x + radius * math.cos(angle),
                        center.y + radius * math.sin(angle),
                        center.z,
                    )
                )
            )
    return candidates


def _pick_room_anchor(
    room_obj: bpy.types.Object,
    initial_center: Vector,
    search_radii: tuple[float, ...],
    search_angles: int,
) -> Vector:
    bbox_min, bbox_max = _bounds(room_obj)
    margin_x = max(0.05, 0.1 * (bbox_max[0] - bbox_min[0]))
    margin_y = max(0.05, 0.1 * (bbox_max[1] - bbox_min[1]))
    for candidate in _candidate_ring(initial_center, search_radii, search_angles):
        if not (bbox_min[0] + margin_x <= candidate.x <= bbox_max[0] - margin_x):
            continue
        if not (bbox_min[1] + margin_y <= candidate.y <= bbox_max[1] - margin_y):
            continue
        candidate.z = initial_center.z
        return candidate
    return initial_center


def _extract_graph(
    scene_folder: Path,
    camera_height_m: float,
    center_search_radii_m: tuple[float, ...],
    center_search_angles: int,
) -> tuple[dict[str, RoomRecord], dict[str, DoorRecord], dict[str, set[str]]]:
    state = _load_state(scene_folder)
    rooms: dict[str, RoomRecord] = {}
    doors: dict[str, DoorRecord] = {}
    adjacency: dict[str, set[str]] = defaultdict(set)

    for name, rec in state.items():
        tags = rec.get("tags", [])
        if "Semantics(room)" not in tags:
            continue
        mesh_name = rec.get("obj") or name
        room_obj = _resolve_object(mesh_name)
        if room_obj is None:
            logger.warning("Failed to resolve room mesh for %s (%s)", name, mesh_name)
            continue
        bbox_min, bbox_max = _bounds(room_obj)
        floor_z = float(bbox_min[2])
        center = Vector(
            (
                float((bbox_min[0] + bbox_max[0]) * 0.5),
                float((bbox_min[1] + bbox_max[1]) * 0.5),
                floor_z + camera_height_m,
            )
        )
        center = _pick_room_anchor(
            room_obj=room_obj,
            initial_center=center,
            search_radii=center_search_radii_m,
            search_angles=center_search_angles,
        )
        rooms[name] = RoomRecord(
            name=name,
            mesh_name=room_obj.name,
            semantic=_semantic_from_tags(tags),
            area=float((bbox_max[0] - bbox_min[0]) * (bbox_max[1] - bbox_min[1])),
            center=center,
            floor_z=floor_z,
            bbox_min=Vector(tuple(float(v) for v in bbox_min)),
            bbox_max=Vector(tuple(float(v) for v in bbox_max)),
        )

    for name, rec in state.items():
        tags = rec.get("tags", [])
        if "Semantics(door)" not in tags:
            continue
        connected_rooms = sorted(
            {
                relation.get("target_name")
                for relation in rec.get("relations", [])
                if relation.get("target_name") in rooms
            }
        )
        if len(connected_rooms) < 2:
            continue
        mesh_name = rec.get("obj") or name
        door_obj = _resolve_object(mesh_name)
        if door_obj is None:
            logger.warning("Failed to resolve door object for %s (%s)", name, mesh_name)
            continue
        center = _infer_portal_center(
            rooms[connected_rooms[0]],
            rooms[connected_rooms[1]],
            camera_height_m=camera_height_m,
        )
        doors[name] = DoorRecord(
            name=name,
            mesh_name=door_obj.name,
            rooms=tuple(connected_rooms),
            center=center,
        )
        for src in connected_rooms:
            for dst in connected_rooms:
                if src == dst:
                    continue
                adjacency[src].add(dst)

    return rooms, doors, adjacency


def _interval_overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> tuple[float, float, float]:
    lo = max(a_min, b_min)
    hi = min(a_max, b_max)
    return lo, hi, max(0.0, hi - lo)


def _midpoint_or_average(lo: float, hi: float, fallback_a: float, fallback_b: float) -> float:
    if hi >= lo:
        return 0.5 * (lo + hi)
    return 0.5 * (fallback_a + fallback_b)


def _infer_portal_center(
    src_room: RoomRecord,
    dst_room: RoomRecord,
    camera_height_m: float,
) -> Vector:
    x_lo, x_hi, x_overlap = _interval_overlap(
        float(src_room.bbox_min.x),
        float(src_room.bbox_max.x),
        float(dst_room.bbox_min.x),
        float(dst_room.bbox_max.x),
    )
    y_lo, y_hi, y_overlap = _interval_overlap(
        float(src_room.bbox_min.y),
        float(src_room.bbox_max.y),
        float(dst_room.bbox_min.y),
        float(dst_room.bbox_max.y),
    )

    if x_overlap >= y_overlap:
        center_x = _midpoint_or_average(x_lo, x_hi, src_room.center.x, dst_room.center.x)
        if src_room.center.y <= dst_room.center.y:
            boundary_y = 0.5 * (float(src_room.bbox_max.y) + float(dst_room.bbox_min.y))
        else:
            boundary_y = 0.5 * (float(src_room.bbox_min.y) + float(dst_room.bbox_max.y))
        return Vector((center_x, boundary_y, min(src_room.floor_z, dst_room.floor_z) + camera_height_m))

    center_y = _midpoint_or_average(y_lo, y_hi, src_room.center.y, dst_room.center.y)
    if src_room.center.x <= dst_room.center.x:
        boundary_x = 0.5 * (float(src_room.bbox_max.x) + float(dst_room.bbox_min.x))
    else:
        boundary_x = 0.5 * (float(src_room.bbox_min.x) + float(dst_room.bbox_max.x))
    return Vector((boundary_x, center_y, min(src_room.floor_z, dst_room.floor_z) + camera_height_m))


def _choose_start_room(rooms: dict[str, RoomRecord], start_room_semantics: tuple[str, ...]) -> str:
    semantic_priority = {semantic: idx for idx, semantic in enumerate(start_room_semantics)}
    ordered = sorted(
        rooms.values(),
        key=lambda room: (
            semantic_priority.get(room.semantic, len(semantic_priority)),
            -room.area,
            room.name,
        ),
    )
    if not ordered:
        raise WholeHomeWalkError("No rooms found for whole-home walk planning")
    return ordered[0].name


def _find_doors_between(doors: dict[str, DoorRecord], src: str, dst: str) -> list[DoorRecord]:
    return [
        door
        for door in doors.values()
        if src in door.rooms and dst in door.rooms
    ]


def _choose_door(doors: dict[str, DoorRecord], rooms: dict[str, RoomRecord], src: str, dst: str) -> DoorRecord:
    candidates = _find_doors_between(doors, src, dst)
    if not candidates:
        raise WholeHomeWalkError(f"No door found between {src} and {dst}")
    src_center = rooms[src].center
    dst_center = rooms[dst].center
    return min(
        candidates,
        key=lambda door: (door.center - src_center).length + (door.center - dst_center).length,
    )


def _ordered_neighbors(
    room_name: str,
    adjacency: dict[str, set[str]],
    rooms: dict[str, RoomRecord],
) -> list[str]:
    return sorted(
        adjacency.get(room_name, []),
        key=lambda name: (-rooms[name].area, rooms[name].name),
    )


def _dfs_room_sequence(
    start_room: str,
    adjacency: dict[str, set[str]],
    rooms: dict[str, RoomRecord],
    return_to_start: bool,
) -> list[str]:
    sequence = [start_room]
    visited = {start_room}

    def dfs(room_name: str):
        for neighbor in _ordered_neighbors(room_name, adjacency, rooms):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            sequence.append(neighbor)
            dfs(neighbor)
            sequence.append(room_name)

    dfs(start_room)
    if return_to_start and sequence[-1] != start_room:
        sequence.append(start_room)
    return sequence


def _path_segment(
    start: Vector,
    end: Vector,
    linear_step_m: float,
) -> list[Vector]:
    return _resample_polyline([start, end], linear_step_m)


def _door_anchor(
    door: DoorRecord,
    room: RoomRecord,
    offset_m: float,
    clearance_m: float,
) -> Vector:
    direction = room.center - door.center
    direction.z = 0.0
    if direction.length < 1e-6:
        direction = Vector((1.0, 0.0, 0.0))
    direction.normalize()
    anchor = door.center.copy()
    anchor += direction * offset_m
    margin = max(clearance_m, 0.05)
    anchor.x = _clamp(anchor.x, room.bbox_min.x + margin, room.bbox_max.x - margin)
    anchor.y = _clamp(anchor.y, room.bbox_min.y + margin, room.bbox_max.y - margin)
    anchor.z = room.center.z
    return anchor


def _estimate_room_radius(
    room_obj: bpy.types.Object,
    center: Vector,
    min_radius: float,
    max_radius: float,
    radius_scale: float,
) -> tuple[float, float]:
    bbox_min, bbox_max = _bounds(room_obj)
    d_wall_min = min(
        center.x - float(bbox_min[0]),
        float(bbox_max[0]) - center.x,
        center.y - float(bbox_min[1]),
        float(bbox_max[1]) - center.y,
    )
    return d_wall_min, _clamp(radius_scale * d_wall_min, min_radius, max_radius)


def _append_traversal_samples(
    samples: list[dict],
    path_points: list[Vector],
    room_name: str,
    state_name: str,
    lookahead_pts: int,
    pitch_deg: float,
):
    if not path_points:
        return
    for idx, point in enumerate(path_points):
        look_idx = min(len(path_points) - 1, idx + lookahead_pts)
        target = path_points[look_idx]
        if look_idx == idx and idx > 0:
            target = point + (point - path_points[idx - 1])
        rotation = _look_rotation(point, target, pitch_deg=pitch_deg)
        samples.append(
            {
                "location": point.copy(),
                "rotation": rotation,
                "room": room_name,
                "state": state_name,
            }
        )


def _append_in_place_sweep(
    samples: list[dict],
    center: Vector,
    room_name: str,
    fps: int,
    sweep_angle_deg: float,
    sweep_yaw_speed_deg_s: float,
    pitch_deg: float,
    start_yaw_deg: float = 0.0,
):
    n_frames = max(2, int(math.ceil(abs(sweep_angle_deg) / max(sweep_yaw_speed_deg_s, 1e-3) * fps)))
    yaw_start = math.radians(start_yaw_deg)
    yaw_end = yaw_start + math.radians(sweep_angle_deg)
    for frame_idx in range(n_frames):
        alpha = frame_idx / max(n_frames - 1, 1)
        yaw = yaw_start + (yaw_end - yaw_start) * alpha
        direction = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        target = center + direction
        samples.append(
            {
                "location": center.copy(),
                "rotation": _look_rotation(center, target, pitch_deg=pitch_deg),
                "room": room_name,
                "state": "room_sweep",
            }
        )


def _append_orbit_sweep(
    samples: list[dict],
    center: Vector,
    room_name: str,
    fps: int,
    orbit_radius_m: float,
    sweep_angle_deg: float,
    orbit_linear_speed_mps: float,
    pitch_deg: float,
    start_phase_deg: float = 0.0,
):
    path_len = math.radians(abs(sweep_angle_deg)) * orbit_radius_m
    n_frames = max(8, int(math.ceil(path_len / max(orbit_linear_speed_mps, 1e-3) * fps)))
    phase_start = math.radians(start_phase_deg)
    phase_end = phase_start + math.radians(sweep_angle_deg)
    for frame_idx in range(n_frames):
        alpha = frame_idx / max(n_frames - 1, 1)
        phase = phase_start + (phase_end - phase_start) * alpha
        location = Vector(
            (
                center.x + orbit_radius_m * math.cos(phase),
                center.y + orbit_radius_m * math.sin(phase),
                center.z,
            )
        )
        target = center.copy()
        samples.append(
            {
                "location": location,
                "rotation": _look_rotation(location, target, pitch_deg=pitch_deg),
                "room": room_name,
                "state": "room_orbit",
            }
        )


def _serialize_sample(sample: dict, frame: int) -> dict:
    return {
        "frame": frame,
        "location": [float(v) for v in sample["location"]],
        "rotation_euler": [float(v) for v in sample["rotation"]],
        "room": sample["room"],
        "state": sample["state"],
    }


@gin.configurable
def animate_whole_home_walk(
    input_folder: Path,
    output_folder: Path,
    scene_seed: int,
    camera_rigs,
    camera_rig_index: int = 0,
    use_existing_camera_rig_only: bool = True,
    camera_height_m: float = 1.55,
    planner_fps: int = 8,
    traversal_speed_mps: float = 0.45,
    orbit_speed_mps: float = 0.25,
    traversal_point_step_m: float = 0.05,
    door_offset_m: float = 0.35,
    clearance_m: float = 0.20,
    path_margin_m: float = 0.18,
    path_resolution: int = 160000,
    room_center_search_radii_m: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75),
    room_center_search_angles: int = 12,
    start_room_semantics: tuple[str, ...] = ("living-room", "dining-room", "kitchen", "bedroom", "bathroom"),
    return_to_start_room: bool = True,
    room_sweep_angle_deg: float = 300.0,
    room_sweep_yaw_speed_deg_s: float = 40.0,
    enable_room_orbit: bool = False,
    room_orbit_min_room_radius_m: float = 1.2,
    room_orbit_radius_scale: float = 0.45,
    room_orbit_radius_min_m: float = 0.35,
    room_orbit_radius_max_m: float = 0.9,
    traversal_pitch_deg: float = -4.0,
    sweep_pitch_deg: float = -2.0,
    traversal_lookahead_pts: int = 5,
):
    if not camera_rigs:
        raise WholeHomeWalkError("No camera rigs found in scene")
    if use_existing_camera_rig_only and len(camera_rigs) != 1:
        raise WholeHomeWalkError(
            f"Expected exactly one camera rig for whole-home walk, found {len(camera_rigs)}"
        )

    cam_rig = camera_rigs[camera_rig_index]
    _clear_animation(cam_rig)
    linear_step_m = traversal_point_step_m
    expected_step_m = traversal_speed_mps / max(planner_fps, 1)
    if linear_step_m <= 0:
        linear_step_m = expected_step_m
    elif not math.isclose(linear_step_m, expected_step_m, rel_tol=0.05, abs_tol=1e-6):
        logger.info(
            "Whole-home walk uses traversal_point_step_m=%.4f while traversal_speed_mps/planner_fps=%.4f",
            linear_step_m,
            expected_step_m,
        )

    rooms, doors, adjacency = _extract_graph(
        scene_folder=Path(input_folder),
        camera_height_m=camera_height_m,
        center_search_radii_m=tuple(room_center_search_radii_m),
        center_search_angles=room_center_search_angles,
    )
    if not rooms:
        raise WholeHomeWalkError("Failed to recover any rooms from solve_state / scene")

    start_room = _choose_start_room(rooms, tuple(start_room_semantics))
    room_sequence = _dfs_room_sequence(
        start_room=start_room,
        adjacency=adjacency,
        rooms=rooms,
        return_to_start=return_to_start_room,
    )

    logger.info("Whole-home walk room sequence: %s", " -> ".join(room_sequence))

    samples: list[dict] = []
    room_visit_count = defaultdict(int)

    def append_room_coverage(room_name: str, final_pass: bool = False):
        room = rooms[room_name]
        room_obj = bpy.data.objects.get(room.mesh_name)
        if room_obj is None:
            return
        wall_clearance, radius = _estimate_room_radius(
            room_obj=room_obj,
            center=room.center,
            min_radius=room_orbit_radius_min_m,
            max_radius=room_orbit_radius_max_m,
            radius_scale=room_orbit_radius_scale,
        )
        if enable_room_orbit and wall_clearance >= room_orbit_min_room_radius_m:
            _append_orbit_sweep(
                samples=samples,
                center=room.center,
                room_name=room_name,
                fps=planner_fps,
                orbit_radius_m=radius,
                sweep_angle_deg=room_sweep_angle_deg if not final_pass else min(room_sweep_angle_deg, 180.0),
                orbit_linear_speed_mps=orbit_speed_mps,
                pitch_deg=sweep_pitch_deg,
            )
        else:
            start_yaw = 0.0 if not samples else math.degrees(samples[-1]["rotation"].z + math.pi / 2)
            _append_in_place_sweep(
                samples=samples,
                center=room.center,
                room_name=room_name,
                fps=planner_fps,
                sweep_angle_deg=room_sweep_angle_deg if not final_pass else min(room_sweep_angle_deg, 180.0),
                sweep_yaw_speed_deg_s=room_sweep_yaw_speed_deg_s,
                pitch_deg=sweep_pitch_deg,
                start_yaw_deg=start_yaw,
            )

    append_room_coverage(start_room)
    room_visit_count[start_room] += 1

    for idx in range(1, len(room_sequence)):
        src = room_sequence[idx - 1]
        dst = room_sequence[idx]
        if src == dst:
            continue
        door = _choose_door(doors, rooms, src, dst)
        src_anchor = _door_anchor(door, rooms[src], door_offset_m, clearance_m=clearance_m)
        dst_anchor = _door_anchor(door, rooms[dst], door_offset_m, clearance_m=clearance_m)

        seg_a = _path_segment(
            start=rooms[src].center,
            end=src_anchor,
            linear_step_m=linear_step_m,
        )
        seg_b = _path_segment(
            start=src_anchor,
            end=dst_anchor,
            linear_step_m=linear_step_m,
        )
        seg_c = _path_segment(
            start=dst_anchor,
            end=rooms[dst].center,
            linear_step_m=linear_step_m,
        )

        for room_name, state_name, segment in [
            (src, "room_to_door", seg_a),
            (dst, "door_transition", seg_b),
            (dst, "door_to_room", seg_c),
        ]:
            trimmed = segment
            if samples and trimmed:
                while trimmed and (trimmed[0] - samples[-1]["location"]).length < 1e-6:
                    trimmed = trimmed[1:]
            _append_traversal_samples(
                samples=samples,
                path_points=trimmed,
                room_name=room_name,
                state_name=state_name,
                lookahead_pts=traversal_lookahead_pts,
                pitch_deg=traversal_pitch_deg,
            )

        first_visit = room_visit_count[dst] == 0
        last_step = idx == len(room_sequence) - 1
        if first_visit or last_step:
            append_room_coverage(dst, final_pass=last_step and dst == start_room)
        room_visit_count[dst] += 1

    if not samples:
        raise WholeHomeWalkError("Planner produced no camera samples")

    scene = bpy.context.scene
    scene.render.fps = planner_fps
    scene.frame_start = 1
    scene.frame_end = len(samples)

    for frame_idx, sample in enumerate(samples, start=1):
        cam_rig.location = sample["location"]
        cam_rig.rotation_euler = sample["rotation"]
        cam_rig.keyframe_insert(data_path="location", frame=frame_idx)
        cam_rig.keyframe_insert(data_path="rotation_euler", frame=frame_idx)

    if cam_rig.animation_data is not None and cam_rig.animation_data.action is not None:
        for fcurve in cam_rig.animation_data.action.fcurves:
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = "LINEAR"

    metadata = {
        "planner": "whole_home_walk",
        "navigation_mode": "doorway_straight_segments",
        "scene_seed": scene_seed,
        "planner_fps": planner_fps,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "camera_height_m": camera_height_m,
        "traversal_speed_mps": traversal_speed_mps,
        "orbit_speed_mps": orbit_speed_mps,
        "traversal_point_step_m": linear_step_m,
        "door_offset_m": door_offset_m,
        "clearance_m": clearance_m,
        "path_margin_m": path_margin_m,
        "path_resolution": path_resolution,
        "room_sweep_angle_deg": room_sweep_angle_deg,
        "room_sweep_yaw_speed_deg_s": room_sweep_yaw_speed_deg_s,
        "enable_room_orbit": enable_room_orbit,
        "room_orbit_min_room_radius_m": room_orbit_min_room_radius_m,
        "room_orbit_radius_scale": room_orbit_radius_scale,
        "room_orbit_radius_min_m": room_orbit_radius_min_m,
        "room_orbit_radius_max_m": room_orbit_radius_max_m,
        "traversal_pitch_deg": traversal_pitch_deg,
        "sweep_pitch_deg": sweep_pitch_deg,
        "rooms": [
            {
                "name": room.name,
                "semantic": room.semantic,
                "area": room.area,
                "center": [float(v) for v in room.center],
            }
            for room in rooms.values()
        ],
        "doors": [
            {
                "name": door.name,
                "rooms": list(door.rooms),
                "center": [float(v) for v in door.center],
            }
            for door in doors.values()
        ],
        "room_sequence": room_sequence,
        "samples": [_serialize_sample(sample, frame) for frame, sample in enumerate(samples, start=1)],
        "total_path_length_m": float(
            sum(
                (samples[i]["location"] - samples[i - 1]["location"]).length
                for i in range(1, len(samples))
            )
        ),
    }

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    with (output_folder / "trajectory_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info(
        "Whole-home walk planned for %s: %d frames, %.2f m path length",
        start_room,
        len(samples),
        metadata["total_path_length_m"],
    )

    return metadata
