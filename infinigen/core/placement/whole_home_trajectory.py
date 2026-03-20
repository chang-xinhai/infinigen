# Copyright (C) 2026.

import json
import logging
import math
from heapq import heappop, heappush
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import bpy
import gin
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

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


def _world_bounds_from_box(bound_box, matrix_world) -> tuple[np.ndarray, np.ndarray]:
    points = np.array([matrix_world @ Vector(corner) for corner in bound_box], dtype=float)
    return points.min(axis=0), points.max(axis=0)


def _bounds(obj: bpy.types.Object):
    return _world_bounds_from_box(obj.bound_box, obj.matrix_world)


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
) -> tuple[dict[str, RoomRecord], dict[str, DoorRecord], dict[str, set[str]], dict[str, set[str]]]:
    state = _load_state(scene_folder)
    rooms: dict[str, RoomRecord] = {}
    doors: dict[str, DoorRecord] = {}
    adjacency: dict[str, set[str]] = defaultdict(set)
    wall_adjacency: dict[str, set[str]] = defaultdict(set)

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
        for relation in rec.get("relations", []):
            relation_info = relation.get("relation", {})
            if relation_info.get("relation_type") != "RoomNeighbour":
                continue
            if "Wall" in relation_info.get("connector_types", []):
                target_name = relation.get("target_name")
                if target_name is not None:
                    wall_adjacency[name].add(target_name)

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
        bbox_min, bbox_max = _bounds(door_obj)
        center = Vector(
            (
                float((bbox_min[0] + bbox_max[0]) * 0.5),
                float((bbox_min[1] + bbox_max[1]) * 0.5),
                min(rooms[connected_rooms[0]].floor_z, rooms[connected_rooms[1]].floor_z) + camera_height_m,
            )
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

    return rooms, doors, adjacency, wall_adjacency


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


def _astar_grid_path(
    valid_mask: np.ndarray,
    start_idx: tuple[int, int],
    end_idx: tuple[int, int],
    is_edge_valid=None,
) -> list[tuple[int, int]] | None:
    if not valid_mask[start_idx] or not valid_mask[end_idx]:
        return None
    if start_idx == end_idx:
        return [start_idx]

    def h(idx):
        di = abs(idx[0] - end_idx[0])
        dj = abs(idx[1] - end_idx[1])
        diag = min(di, dj)
        straight = max(di, dj) - diag
        return math.sqrt(2.0) * diag + straight

    frontier = [(h(start_idx), 0.0, start_idx)]
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start_idx: None}
    cost = {start_idx: 0.0}

    while frontier:
        _, curr_cost, curr = heappop(frontier)
        if curr == end_idx:
            path = [curr]
            while parent[path[-1]] is not None:
                path.append(parent[path[-1]])
            path.reverse()
            return path
        if curr_cost > cost[curr]:
            continue
        for di, dj, step_cost in (
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 1, math.sqrt(2.0)),
            (1, -1, math.sqrt(2.0)),
            (-1, 1, math.sqrt(2.0)),
            (-1, -1, math.sqrt(2.0)),
        ):
            nxt = (curr[0] + di, curr[1] + dj)
            if (
                nxt[0] < 0
                or nxt[1] < 0
                or nxt[0] >= valid_mask.shape[0]
                or nxt[1] >= valid_mask.shape[1]
                or not valid_mask[nxt]
            ):
                continue
            if abs(di) + abs(dj) == 2:
                side_a = (curr[0] + di, curr[1])
                side_b = (curr[0], curr[1] + dj)
                if not valid_mask[side_a] or not valid_mask[side_b]:
                    continue
            if is_edge_valid is not None and not is_edge_valid(curr, nxt):
                continue
            next_cost = curr_cost + step_cost
            if next_cost >= cost.get(nxt, math.inf):
                continue
            cost[nxt] = next_cost
            parent[nxt] = curr
            heappush(frontier, (next_cost + h(nxt), next_cost, nxt))
    return None


def _shortcut_polyline(points: list[Vector], is_segment_valid) -> list[Vector]:
    if len(points) <= 2:
        return list(points)

    result = [points[0].copy()]
    anchor = 0
    while anchor < len(points) - 1:
        next_idx = anchor + 1
        for candidate in range(len(points) - 1, anchor, -1):
            if is_segment_valid(points[anchor], points[candidate]):
                next_idx = candidate
                break
        result.append(points[next_idx].copy())
        anchor = next_idx
    return result


def _interior_point(room: RoomRecord, point: Vector, clearance_m: float) -> Vector:
    margin = max(clearance_m, 0.05)
    return Vector(
        (
            _clamp(point.x, room.bbox_min.x + margin, room.bbox_max.x - margin),
            _clamp(point.y, room.bbox_min.y + margin, room.bbox_max.y - margin),
            room.center.z,
        )
    )


def _room_path_segment(
    room: RoomRecord,
    start: Vector,
    end: Vector,
    linear_step_m: float,
    clearance_m: float,
) -> list[Vector]:
    start = _interior_point(room, start, clearance_m)
    end = _interior_point(room, end, clearance_m)
    if (start - end).length < 1e-6:
        return [start]

    via_x = _interior_point(
        room,
        Vector((end.x, start.y, room.center.z)),
        clearance_m,
    )
    via_y = _interior_point(
        room,
        Vector((start.x, end.y, room.center.z)),
        clearance_m,
    )

    center = room.center
    candidates = [
        [start, via_x, end],
        [start, via_y, end],
    ]
    candidates.sort(
        key=lambda pts: sum((pts[i] - pts[i - 1]).length for i in range(1, len(pts)))
        + 0.1 * (pts[1] - center).length
    )
    points = [candidates[0][0]]
    for point in candidates[0][1:]:
        if (point - points[-1]).length > 1e-6:
            points.append(point)
    return _resample_polyline(points, linear_step_m)


def _scene_ray_hit(origin: Vector, direction: Vector, distance: float) -> bool:
    if distance <= 1e-6 or direction.length <= 1e-6:
        return False
    deps = bpy.context.evaluated_depsgraph_get()
    hit, *_ = bpy.context.scene.ray_cast(deps, origin, direction.normalized(), distance=distance)
    return bool(hit)


def _segment_is_clear(start: Vector, end: Vector, clearance_m: float) -> bool:
    delta = end - start
    distance = delta.length
    if distance <= 1e-6:
        return True
    direction = delta.normalized()
    offsets = [Vector((0.0, 0.0, 0.0))]
    lateral = Vector((-direction.y, direction.x, 0.0))
    if lateral.length > 1e-6 and clearance_m > 1e-6:
        lateral.normalize()
        offsets.extend([
            lateral * (0.5 * clearance_m),
            -lateral * (0.5 * clearance_m),
        ])
    for offset in offsets:
        if _scene_ray_hit(start + offset, delta, distance):
            return False
    return True


def _room_object_ray_cast(
    room_obj: bpy.types.Object,
    point: Vector,
    direction: Vector,
):
    world_to_local = room_obj.matrix_world.inverted()
    local_origin = world_to_local @ point
    local_direction = world_to_local.to_3x3() @ direction
    if local_direction.length <= 1e-6:
        return None
    try:
        hit, location, normal, face_index = room_obj.ray_cast(local_origin, local_direction.normalized())
    except RuntimeError:
        return None
    if hit:
        return location, normal, face_index
    return None


def _point_is_inside_room(
    room_obj: bpy.types.Object,
    room_bvh: BVHTree | None,
    point: Vector,
) -> bool:
    if room_bvh is not None:
        cast_up = room_bvh.ray_cast(point, Vector((0.0, 0.0, 1.0)))
        cast_down = room_bvh.ray_cast(point, Vector((0.0, 0.0, -1.0)))
        return cast_up[0] is not None and cast_down[0] is not None
    return (
        _room_object_ray_cast(room_obj, point, Vector((0.0, 0.0, 1.0))) is not None
        and _room_object_ray_cast(room_obj, point, Vector((0.0, 0.0, -1.0))) is not None
    )


def _build_object_bvh(obj: bpy.types.Object) -> BVHTree | None:
    deps = bpy.context.evaluated_depsgraph_get()
    candidates = [obj]
    try:
        candidates.insert(0, obj.evaluated_get(deps))
    except Exception:
        pass
    for candidate in candidates:
        try:
            return BVHTree.FromObject(candidate, deps)
        except Exception:
            continue
    logger.warning("Failed to build BVH for %s; planner will use fallback logic", obj.name)
    return None


def _point_has_scene_clearance(point: Vector, clearance_m: float) -> bool:
    if clearance_m <= 1e-6:
        return True
    for angle in np.linspace(0.0, 2.0 * np.pi, 8, endpoint=False):
        direction = Vector((math.cos(angle), math.sin(angle), 0.0))
        half_probe = 0.5 * clearance_m * direction
        if not _segment_is_clear(point - half_probe, point + half_probe, 0.0):
            return False
        if _scene_ray_hit(point, direction, clearance_m):
            return False
    return True


def _point_in_bbox(point: Vector, bbox_min: Vector, bbox_max: Vector, margin: float) -> bool:
    return (
        bbox_min.x - margin <= point.x <= bbox_max.x + margin
        and bbox_min.y - margin <= point.y <= bbox_max.y + margin
    )


def _point_has_room_floor(room: RoomRecord, point: Vector, floor_tol_m: float = 0.25) -> bool:
    deps = bpy.context.evaluated_depsgraph_get()
    origin = point + Vector((0.0, 0.0, 0.5))
    max_drop = max(2.5, point.z - room.floor_z + 1.0)
    hit, loc, *_ = bpy.context.scene.ray_cast(
        deps,
        origin,
        Vector((0.0, 0.0, -1.0)),
        distance=max_drop,
    )
    return bool(hit) and abs(loc.z - room.floor_z) <= floor_tol_m


def _is_navigable_room_point(
    room: RoomRecord,
    room_obj: bpy.types.Object,
    room_bvh: BVHTree | None,
    point: Vector,
    clearance_m: float,
    forbidden_bboxes: list[tuple[Vector, Vector]] | None = None,
) -> bool:
    if not _point_in_bbox(point, room.bbox_min, room.bbox_max, -clearance_m):
        return False
    if forbidden_bboxes is not None:
        for bbox_min, bbox_max in forbidden_bboxes:
            if _point_in_bbox(point, bbox_min, bbox_max, clearance_m):
                return False
    return _point_has_room_floor(room, point) and _point_has_scene_clearance(point, clearance_m)


def _find_valid_room_point(
    room: RoomRecord,
    room_obj: bpy.types.Object,
    room_bvh: BVHTree | None,
    desired: Vector,
    clearance_m: float,
    search_step_m: float,
    forbidden_bboxes: list[tuple[Vector, Vector]] | None = None,
) -> Vector:
    desired = _interior_point(room, desired, clearance_m)
    radii = [0.0, search_step_m, 2.0 * search_step_m, 4.0 * search_step_m, 8.0 * search_step_m]
    best = None
    best_score = math.inf
    for radius in radii:
        sample_count = 1 if radius <= 1e-6 else 16
        for angle in np.linspace(0.0, 2.0 * np.pi, sample_count, endpoint=False):
            candidate = Vector(
                (
                    desired.x + radius * math.cos(angle),
                    desired.y + radius * math.sin(angle),
                    room.center.z,
                )
            )
            candidate = _interior_point(room, candidate, clearance_m)
            if not _is_navigable_room_point(
                room,
                room_obj,
                room_bvh,
                candidate,
                clearance_m,
                forbidden_bboxes=forbidden_bboxes,
            ):
                continue
            score = (candidate - desired).length
            if score < best_score:
                best = candidate
                best_score = score
        if best is not None:
            return best
    return desired


def _nearest_valid_grid_index(
    valid_mask: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    point: Vector,
) -> tuple[int, int] | None:
    candidates = np.argwhere(valid_mask)
    if len(candidates) == 0:
        return None
    best = None
    best_dist = math.inf
    for i, j in candidates:
        d = (xs[i] - point.x) ** 2 + (ys[j] - point.y) ** 2
        if d < best_dist:
            best = (int(i), int(j))
            best_dist = d
    return best


def _collision_aware_room_path_segment(
    room: RoomRecord,
    room_obj: bpy.types.Object,
    room_bvh: BVHTree | None,
    start: Vector,
    end: Vector,
    linear_step_m: float,
    clearance_m: float,
    grid_step_m: float,
    forbidden_bboxes: list[tuple[Vector, Vector]] | None = None,
) -> list[Vector]:
    start = _find_valid_room_point(
        room, room_obj, room_bvh, start, clearance_m, grid_step_m, forbidden_bboxes=forbidden_bboxes
    )
    end = _find_valid_room_point(
        room, room_obj, room_bvh, end, clearance_m, grid_step_m, forbidden_bboxes=forbidden_bboxes
    )
    if (start - end).length < 1e-6:
        return [start]
    if _segment_is_clear(start, end, clearance_m) and _is_navigable_room_point(
        room,
        room_obj,
        room_bvh,
        0.5 * (start + end),
        clearance_m,
        forbidden_bboxes=forbidden_bboxes,
    ):
        return _resample_polyline([start, end], linear_step_m)

    margin = max(clearance_m, 0.05)
    xs = np.arange(room.bbox_min.x + margin, room.bbox_max.x - margin + 1e-6, grid_step_m)
    ys = np.arange(room.bbox_min.y + margin, room.bbox_max.y - margin + 1e-6, grid_step_m)
    if len(xs) == 0 or len(ys) == 0:
        return _room_path_segment(room, start, end, linear_step_m, clearance_m)

    valid_mask = np.zeros((len(xs), len(ys)), dtype=bool)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            point = Vector((float(x), float(y), room.center.z))
            valid_mask[i, j] = _is_navigable_room_point(
                room,
                room_obj,
                room_bvh,
                point,
                clearance_m,
                forbidden_bboxes=forbidden_bboxes,
            )

    start_idx = _nearest_valid_grid_index(valid_mask, xs, ys, start)
    end_idx = _nearest_valid_grid_index(valid_mask, xs, ys, end)
    if start_idx is None or end_idx is None:
        return _room_path_segment(room, start, end, linear_step_m, clearance_m)

    def point_for(idx):
        return Vector((float(xs[idx[0]]), float(ys[idx[1]]), room.center.z))

    path_idx = _astar_grid_path(
        valid_mask,
        start_idx,
        end_idx,
        is_edge_valid=lambda a, b: _segment_is_clear(point_for(a), point_for(b), clearance_m),
    )
    if path_idx is None:
        return _room_path_segment(room, start, end, linear_step_m, clearance_m)

    path_points = [start.copy()]
    for idx in path_idx[1:-1]:
        point = point_for(idx)
        if (point - path_points[-1]).length > 1e-6:
            path_points.append(point)
    if (end - path_points[-1]).length > 1e-6:
        path_points.append(end.copy())

    shortcut_points = _shortcut_polyline(
        path_points,
        is_segment_valid=lambda a, b: _segment_is_clear(a, b, clearance_m)
        and _is_navigable_room_point(
            room,
            room_obj,
            room_bvh,
            0.5 * (a + b),
            clearance_m,
            forbidden_bboxes=forbidden_bboxes,
        ),
    )
    return _resample_polyline(shortcut_points, linear_step_m)


def _local_bbox_path(
    start: Vector,
    end: Vector,
    bbox_min: Vector,
    bbox_max: Vector,
    grid_step_m: float,
    linear_step_m: float,
    clearance_m: float,
) -> list[Vector] | None:
    margin = max(clearance_m, 0.05)
    xs = np.arange(bbox_min.x + margin, bbox_max.x - margin + 1e-6, grid_step_m)
    ys = np.arange(bbox_min.y + margin, bbox_max.y - margin + 1e-6, grid_step_m)
    if len(xs) == 0 or len(ys) == 0:
        return None

    def point_for(idx):
        return Vector((float(xs[idx[0]]), float(ys[idx[1]]), start.z))

    valid_mask = np.zeros((len(xs), len(ys)), dtype=bool)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            valid_mask[i, j] = _point_has_scene_clearance(
                Vector((float(x), float(y), start.z)),
                clearance_m,
            )

    start_idx = _nearest_valid_grid_index(valid_mask, xs, ys, start)
    end_idx = _nearest_valid_grid_index(valid_mask, xs, ys, end)
    if start_idx is None or end_idx is None:
        return None

    path_idx = _astar_grid_path(
        valid_mask,
        start_idx,
        end_idx,
        is_edge_valid=lambda a, b: _segment_is_clear(point_for(a), point_for(b), clearance_m),
    )
    if path_idx is None:
        return None
    path_points = [start.copy()]
    for idx in path_idx[1:-1]:
        point = point_for(idx)
        if (point - path_points[-1]).length > 1e-6:
            path_points.append(point)
    if (end - path_points[-1]).length > 1e-6:
        path_points.append(end.copy())
    shortcut_points = _shortcut_polyline(
        path_points,
        is_segment_valid=lambda a, b: _segment_is_clear(a, b, clearance_m),
    )
    return _resample_polyline(shortcut_points, linear_step_m)


def _repair_colliding_samples(
    samples: list[dict],
    rooms: dict[str, RoomRecord],
    linear_step_m: float,
    clearance_m: float,
    grid_step_m: float,
    lookahead_pts: int,
    pitch_deg: float,
    repair_margin_m: float,
) -> list[dict]:
    repaired = list(samples)
    max_passes = 3

    for _ in range(max_passes):
        blocked_segments = [
            idx
            for idx in range(1, len(repaired))
            if not _segment_is_clear(
                repaired[idx - 1]["location"],
                repaired[idx]["location"],
                clearance_m,
            )
        ]
        if not blocked_segments:
            return repaired

        run_start = blocked_segments[0]
        run_end = run_start
        while run_end + 1 in blocked_segments:
            run_end += 1

        start_idx = max(0, run_start - 1)
        end_idx = min(len(repaired) - 1, run_end + 1)
        involved_rooms = {
            repaired[idx]["room"]
            for idx in range(start_idx, end_idx + 1)
            if repaired[idx]["room"] in rooms
        }
        if not involved_rooms:
            break

        bbox_min = Vector((math.inf, math.inf, repaired[start_idx]["location"].z))
        bbox_max = Vector((-math.inf, -math.inf, repaired[start_idx]["location"].z))
        for room_name in involved_rooms:
            room = rooms[room_name]
            bbox_min.x = min(bbox_min.x, room.bbox_min.x)
            bbox_min.y = min(bbox_min.y, room.bbox_min.y)
            bbox_max.x = max(bbox_max.x, room.bbox_max.x)
            bbox_max.y = max(bbox_max.y, room.bbox_max.y)
        bbox_min.x -= repair_margin_m
        bbox_min.y -= repair_margin_m
        bbox_max.x += repair_margin_m
        bbox_max.y += repair_margin_m

        repaired_path = _local_bbox_path(
            start=repaired[start_idx]["location"],
            end=repaired[end_idx]["location"],
            bbox_min=bbox_min,
            bbox_max=bbox_max,
            grid_step_m=grid_step_m,
            linear_step_m=linear_step_m,
            clearance_m=clearance_m,
        )
        if repaired_path is None or len(repaired_path) < 2:
            break

        replacement_samples = []
        _append_traversal_samples(
            samples=replacement_samples,
            path_points=repaired_path,
            room_name=repaired[start_idx + 1]["room"],
            state_name=f"{repaired[start_idx + 1]['state']}_repair",
            lookahead_pts=lookahead_pts,
            pitch_deg=pitch_deg,
        )
        if len(replacement_samples) < 2:
            break
        repaired = (
            repaired[: start_idx + 1]
            + replacement_samples[1:-1]
            + repaired[end_idx:]
        )

    return repaired


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


def _gaussian_kernel1d(sigma_frames: float) -> np.ndarray:
    sigma_frames = max(float(sigma_frames), 1e-3)
    radius = max(1, int(math.ceil(3.0 * sigma_frames)))
    xs = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (xs / sigma_frames) ** 2)
    kernel /= np.sum(kernel)
    return kernel


def _smooth_random_signal(
    sample_count: int,
    amplitude: float,
    sigma_frames: float,
    rng: np.random.Generator,
) -> np.ndarray:
    sample_count = int(sample_count)
    amplitude = max(0.0, float(amplitude))
    if sample_count <= 0 or amplitude <= 1e-6:
        return np.zeros(sample_count, dtype=float)

    kernel = _gaussian_kernel1d(sigma_frames)
    pad = len(kernel) // 2
    noise = rng.standard_normal(sample_count + 2 * pad)
    smooth = np.convolve(noise, kernel, mode="same")[pad: pad + sample_count]
    smooth -= np.mean(smooth)
    peak = float(np.max(np.abs(smooth))) if sample_count else 0.0
    if peak <= 1e-6:
        return np.zeros(sample_count, dtype=float)
    return amplitude * smooth / peak


def _forward_from_rotation(rotation: Euler) -> Vector:
    yaw = rotation.z + math.pi / 2
    return Vector((math.cos(yaw), math.sin(yaw), 0.0))


def _sample_forward_direction(
    locations: list[Vector],
    rotations: list[Euler],
    idx: int,
    window: int,
) -> Vector:
    if not locations:
        return Vector((0.0, 1.0, 0.0))

    window = max(1, int(window))
    start_idx = max(0, idx - window)
    end_idx = min(len(locations) - 1, idx + window)
    delta = locations[end_idx] - locations[start_idx]
    delta.z = 0.0
    if delta.length > 1e-6:
        return delta.normalized()

    for offset in (1, 2):
        prev_idx = max(0, idx - offset)
        next_idx = min(len(locations) - 1, idx + offset)
        delta = locations[next_idx] - locations[prev_idx]
        delta.z = 0.0
        if delta.length > 1e-6:
            return delta.normalized()

    if 0 <= idx < len(rotations):
        return _forward_from_rotation(rotations[idx])
    return Vector((0.0, 1.0, 0.0))


def _orbit_focus_direction(
    location: Vector,
    center: Vector,
    phase: float,
    sweep_angle_deg: float,
    focus_blend: float,
) -> Vector:
    to_center = center - location
    to_center.z = 0.0
    if to_center.length <= 1e-6:
        to_center = Vector((math.cos(phase), math.sin(phase), 0.0))
    else:
        to_center.normalize()

    tangent = Vector((-math.sin(phase), math.cos(phase), 0.0))
    if sweep_angle_deg < 0.0:
        tangent *= -1.0
    tangent.normalize()

    focus_blend = _clamp(float(focus_blend), 0.0, 1.0)
    direction = focus_blend * to_center + (1.0 - focus_blend) * tangent
    if direction.length <= 1e-6:
        direction = to_center
    direction.normalize()
    return direction


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
    start_location: Vector | None = None,
    start_rotation: Euler | None = None,
    entry_transition_sec: float = 0.35,
    focus_blend: float = 0.88,
):
    phase_start = math.radians(start_phase_deg)
    if start_location is not None:
        radial = start_location - center
        radial.z = 0.0
        if radial.length > 1e-6:
            phase_start = math.atan2(radial.y, radial.x)
        elif start_rotation is not None:
            forward = _forward_from_rotation(start_rotation)
            phase_start = math.atan2(forward.y, forward.x)

    start_orbit = Vector(
        (
            center.x + orbit_radius_m * math.cos(phase_start),
            center.y + orbit_radius_m * math.sin(phase_start),
            center.z,
        )
    )
    if start_location is not None:
        transition_len = (start_orbit - start_location).length
        if transition_len > 1e-6:
            transition_frames = max(
                2,
                int(
                    math.ceil(
                        max(
                            transition_len / max(orbit_linear_speed_mps, 1e-3),
                            max(entry_transition_sec, 0.0),
                        )
                        * fps
                    )
                ),
            )
            for frame_idx in range(1, transition_frames + 1):
                alpha = frame_idx / transition_frames
                eased_alpha = 0.5 - 0.5 * math.cos(math.pi * alpha)
                location = start_location.lerp(start_orbit, eased_alpha)
                direction = _orbit_focus_direction(
                    location=location,
                    center=center,
                    phase=phase_start,
                    sweep_angle_deg=sweep_angle_deg,
                    focus_blend=focus_blend,
                )
                samples.append(
                    {
                        "location": location,
                        "rotation": _look_rotation(location, location + direction, pitch_deg=pitch_deg),
                        "room": room_name,
                        "state": "room_orbit_entry",
                    }
                )

    path_len = math.radians(abs(sweep_angle_deg)) * orbit_radius_m
    n_frames = max(8, int(math.ceil(path_len / max(orbit_linear_speed_mps, 1e-3) * fps)))
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
        if samples and (location - samples[-1]["location"]).length < 1e-6:
            continue
        direction = _orbit_focus_direction(
            location=location,
            center=center,
            phase=phase,
            sweep_angle_deg=sweep_angle_deg,
            focus_blend=focus_blend,
        )
        samples.append(
            {
                "location": location,
                "rotation": _look_rotation(location, location + direction, pitch_deg=pitch_deg),
                "room": room_name,
                "state": "room_orbit",
            }
        )


def _collect_access_door_objects(doors: dict[str, DoorRecord]) -> set[bpy.types.Object]:
    result: set[bpy.types.Object] = set()
    factory_name_tokens = ("paneldoorfactory", "glasspaneldoorfactory")

    for door in doors.values():
        obj = bpy.data.objects.get(door.mesh_name)
        if obj is None:
            obj = bpy.data.objects.get(door.name)
        if obj is not None:
            result.add(obj)
            result.update(obj.children_recursive)

    for obj in bpy.data.objects:
        name_l = obj.name.lower()
        if any(token in name_l for token in factory_name_tokens):
            result.add(obj)
            result.update(obj.children_recursive)

    return result


def _force_open_access_doors(
    doors: dict[str, DoorRecord],
    mode: str,
):
    if mode == "none":
        return

    for obj in _collect_access_door_objects(doors):
        if mode == "hide":
            obj.hide_render = True
            obj.hide_viewport = True
        else:
            raise WholeHomeWalkError(f"Unsupported force_open_access_doors_mode={mode}")


def _serialize_sample(sample: dict, frame: int) -> dict:
    payload = {
        "frame": frame,
        "location": [float(v) for v in sample["location"]],
        "rotation_euler": [float(v) for v in sample["rotation"]],
        "room": sample["room"],
        "state": sample["state"],
    }
    if "height_offset_m" in sample:
        payload["height_offset_m"] = float(sample["height_offset_m"])
    return payload


def _apply_height_perturbation(
    samples: list[dict],
    rooms: dict[str, RoomRecord],
    camera_height_m: float,
    planner_fps: int,
    amplitude_m: float,
    frequency_hz: float,
    scene_seed: int,
) -> dict:
    if not samples:
        return {
            "enabled": False,
            "amplitude_m": float(amplitude_m),
            "frequency_hz": float(frequency_hz),
            "phase_rad": 0.0,
            "min_offset_m": 0.0,
            "max_offset_m": 0.0,
        }

    amplitude_m = max(0.0, float(amplitude_m))
    frequency_hz = max(0.0, float(frequency_hz))
    if amplitude_m <= 1e-6 or frequency_hz <= 1e-6 or planner_fps <= 0:
        for sample in samples:
            room = rooms.get(sample["room"])
            if room is not None:
                sample["location"].z = room.floor_z + camera_height_m
            sample["height_offset_m"] = 0.0
        return {
            "enabled": False,
            "amplitude_m": amplitude_m,
            "frequency_hz": frequency_hz,
            "phase_rad": 0.0,
            "min_offset_m": 0.0,
            "max_offset_m": 0.0,
        }

    phase = float(np.random.default_rng(scene_seed).uniform(0.0, 2.0 * math.pi))
    offsets = []
    angular_speed = 2.0 * math.pi * frequency_hz
    for idx, sample in enumerate(samples):
        time_s = idx / planner_fps
        primary = 0.7 * math.sin(angular_speed * time_s + phase)
        secondary = 0.3 * math.sin(2.0 * angular_speed * time_s + 0.5 * phase)
        offset = amplitude_m * (primary + secondary)
        room = rooms.get(sample["room"])
        if room is not None:
            sample["location"].z = room.floor_z + camera_height_m + offset
        else:
            sample["location"].z += offset
        sample["height_offset_m"] = float(offset)
        offsets.append(offset)
    return {
        "enabled": True,
        "amplitude_m": amplitude_m,
        "frequency_hz": frequency_hz,
        "phase_rad": phase,
        "min_offset_m": float(min(offsets)),
        "max_offset_m": float(max(offsets)),
    }


def _apply_handheld_perturbation(
    samples: list[dict],
    planner_fps: int,
    scene_seed: int,
    lateral_amplitude_m: float,
    yaw_amplitude_deg: float,
    pitch_amplitude_deg: float,
    noise_sigma_s: float,
    forward_smoothing_window: int,
) -> dict:
    sample_count = len(samples)
    summary = {
        "enabled": False,
        "lateral_amplitude_m": float(max(0.0, lateral_amplitude_m)),
        "yaw_amplitude_deg": float(max(0.0, yaw_amplitude_deg)),
        "pitch_amplitude_deg": float(max(0.0, pitch_amplitude_deg)),
        "noise_sigma_s": float(max(0.0, noise_sigma_s)),
        "forward_smoothing_window": int(max(1, forward_smoothing_window)),
        "min_lateral_offset_m": 0.0,
        "max_lateral_offset_m": 0.0,
        "min_yaw_offset_deg": 0.0,
        "max_yaw_offset_deg": 0.0,
        "min_pitch_offset_deg": 0.0,
        "max_pitch_offset_deg": 0.0,
    }
    if sample_count == 0 or planner_fps <= 0:
        return summary

    lateral_amplitude_m = max(0.0, float(lateral_amplitude_m))
    yaw_amplitude_deg = max(0.0, float(yaw_amplitude_deg))
    pitch_amplitude_deg = max(0.0, float(pitch_amplitude_deg))
    noise_sigma_s = max(0.0, float(noise_sigma_s))
    forward_smoothing_window = max(1, int(forward_smoothing_window))
    if (
        lateral_amplitude_m <= 1e-6
        and yaw_amplitude_deg <= 1e-6
        and pitch_amplitude_deg <= 1e-6
    ) or noise_sigma_s <= 1e-6:
        for sample in samples:
            sample["handheld_lateral_offset_m"] = 0.0
            sample["handheld_yaw_offset_deg"] = 0.0
            sample["handheld_pitch_offset_deg"] = 0.0
        return summary

    rng = np.random.default_rng(scene_seed + 104729)
    sigma_frames = max(noise_sigma_s * planner_fps, 1.0)
    lateral_offsets = _smooth_random_signal(sample_count, lateral_amplitude_m, sigma_frames, rng)
    yaw_offsets = _smooth_random_signal(sample_count, yaw_amplitude_deg, sigma_frames, rng)
    pitch_offsets = _smooth_random_signal(sample_count, pitch_amplitude_deg, sigma_frames, rng)

    original_locations = [sample["location"].copy() for sample in samples]
    original_rotations = [sample["rotation"].copy() for sample in samples]
    for idx, sample in enumerate(samples):
        forward = _sample_forward_direction(
            locations=original_locations,
            rotations=original_rotations,
            idx=idx,
            window=forward_smoothing_window,
        )
        lateral = Vector((-forward.y, forward.x, 0.0))
        if lateral.length > 1e-6:
            lateral.normalize()
        sample["location"] += lateral * float(lateral_offsets[idx])
        sample["handheld_lateral_offset_m"] = float(lateral_offsets[idx])

    updated_locations = [sample["location"].copy() for sample in samples]
    for idx, sample in enumerate(samples):
        forward = _sample_forward_direction(
            locations=updated_locations,
            rotations=original_rotations,
            idx=idx,
            window=forward_smoothing_window,
        )
        target = sample["location"] + forward
        base_pitch_deg = math.degrees(original_rotations[idx].x - math.pi / 2)
        rotation = _look_rotation(
            sample["location"],
            target,
            pitch_deg=base_pitch_deg + float(pitch_offsets[idx]),
        )
        rotation.z += math.radians(float(yaw_offsets[idx]))
        sample["rotation"] = rotation
        sample["handheld_yaw_offset_deg"] = float(yaw_offsets[idx])
        sample["handheld_pitch_offset_deg"] = float(pitch_offsets[idx])

    summary.update(
        {
            "enabled": True,
            "min_lateral_offset_m": float(np.min(lateral_offsets)),
            "max_lateral_offset_m": float(np.max(lateral_offsets)),
            "min_yaw_offset_deg": float(np.min(yaw_offsets)),
            "max_yaw_offset_deg": float(np.max(yaw_offsets)),
            "min_pitch_offset_deg": float(np.min(pitch_offsets)),
            "max_pitch_offset_deg": float(np.max(pitch_offsets)),
        }
    )
    return summary


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
    room_path_mode: str = "collision_aware_grid",
    room_orbit_min_room_radius_m: float = 1.2,
    room_orbit_radius_scale: float = 0.45,
    room_orbit_radius_min_m: float = 0.35,
    room_orbit_radius_max_m: float = 0.9,
    room_grid_step_m: float = 0.10,
    enable_collision_repair: bool = True,
    collision_repair_margin_m: float = 0.75,
    traversal_pitch_deg: float = -4.0,
    sweep_pitch_deg: float = -2.0,
    traversal_lookahead_pts: int = 5,
    height_perturbation_amplitude_m: float = 0.0,
    height_perturbation_frequency_hz: float = 0.35,
    handheld_lateral_amplitude_m: float = 0.0,
    handheld_yaw_amplitude_deg: float = 0.0,
    handheld_pitch_amplitude_deg: float = 0.0,
    handheld_noise_sigma_s: float = 0.35,
    handheld_forward_smoothing_window: int = 4,
    orbit_entry_transition_sec: float = 0.35,
    orbit_focus_blend: float = 0.88,
    force_open_access_doors: bool = True,
    force_open_access_doors_mode: str = "hide",
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

    rooms, doors, adjacency, wall_adjacency = _extract_graph(
        scene_folder=Path(input_folder),
        camera_height_m=camera_height_m,
        center_search_radii_m=tuple(room_center_search_radii_m),
        center_search_angles=room_center_search_angles,
    )
    if not rooms:
        raise WholeHomeWalkError("Failed to recover any rooms from solve_state / scene")

    forbidden_room_bboxes: dict[str, list[tuple[Vector, Vector]]] = defaultdict(list)
    for room_name, neighbor_names in wall_adjacency.items():
        for neighbor_name in neighbor_names:
            neighbor = rooms.get(neighbor_name)
            if neighbor is None:
                continue
            forbidden_room_bboxes[room_name].append((neighbor.bbox_min, neighbor.bbox_max))

    room_objs: dict[str, bpy.types.Object] = {}
    room_bvhs: dict[str, BVHTree | None] = {}
    for room in rooms.values():
        room_obj = bpy.data.objects.get(room.mesh_name)
        if room_obj is None:
            continue
        room_objs[room.name] = room_obj
        room_bvhs[room.name] = _build_object_bvh(room_obj)
    for room_name, room in rooms.items():
        room_obj = room_objs.get(room_name)
        room_bvh = room_bvhs.get(room_name)
        if room_obj is None:
            continue
        room.center = _find_valid_room_point(
            room=room,
            room_obj=room_obj,
            room_bvh=room_bvh,
            desired=room.center,
            clearance_m=clearance_m,
            search_step_m=max(room_grid_step_m, linear_step_m),
            forbidden_bboxes=forbidden_room_bboxes.get(room_name),
        )

    if force_open_access_doors:
        _force_open_access_doors(
            doors=doors,
            mode=force_open_access_doors_mode,
        )

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
                start_location=None if not samples else samples[-1]["location"].copy(),
                start_rotation=None if not samples else samples[-1]["rotation"].copy(),
                entry_transition_sec=orbit_entry_transition_sec,
                focus_blend=orbit_focus_blend,
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
        src_room_bvh = room_bvhs.get(src)
        dst_room_bvh = room_bvhs.get(dst)
        src_room_obj = room_objs.get(src)
        dst_room_obj = room_objs.get(dst)
        src_anchor = _door_anchor(door, rooms[src], door_offset_m, clearance_m=clearance_m)
        dst_anchor = _door_anchor(door, rooms[dst], door_offset_m, clearance_m=clearance_m)
        if src_room_obj is not None:
            src_anchor = _find_valid_room_point(
                room=rooms[src],
                room_obj=src_room_obj,
                room_bvh=src_room_bvh,
                desired=src_anchor,
                clearance_m=clearance_m,
                search_step_m=max(room_grid_step_m, linear_step_m),
                forbidden_bboxes=forbidden_room_bboxes.get(src),
            )
        if dst_room_obj is not None:
            dst_anchor = _find_valid_room_point(
                room=rooms[dst],
                room_obj=dst_room_obj,
                room_bvh=dst_room_bvh,
                desired=dst_anchor,
                clearance_m=clearance_m,
                search_step_m=max(room_grid_step_m, linear_step_m),
                forbidden_bboxes=forbidden_room_bboxes.get(dst),
            )

        src_start = rooms[src].center
        if samples and samples[-1]["room"] == src:
            src_start = samples[-1]["location"].copy()

        if room_path_mode == "collision_aware_grid" and src_room_obj is not None and dst_room_obj is not None:
            seg_a = _collision_aware_room_path_segment(
                room=rooms[src],
                room_obj=src_room_obj,
                room_bvh=src_room_bvh,
                start=src_start,
                end=src_anchor,
                linear_step_m=linear_step_m,
                clearance_m=clearance_m,
                grid_step_m=room_grid_step_m,
                forbidden_bboxes=forbidden_room_bboxes.get(src),
            )
            seg_c = _collision_aware_room_path_segment(
                room=rooms[dst],
                room_obj=dst_room_obj,
                room_bvh=dst_room_bvh,
                start=dst_anchor,
                end=rooms[dst].center,
                linear_step_m=linear_step_m,
                clearance_m=clearance_m,
                grid_step_m=room_grid_step_m,
                forbidden_bboxes=forbidden_room_bboxes.get(dst),
            )
        elif room_path_mode in {"collision_aware_grid", "orthogonal"}:
            seg_a = _room_path_segment(
                room=rooms[src],
                start=src_start,
                end=src_anchor,
                linear_step_m=linear_step_m,
                clearance_m=clearance_m,
            )
            seg_c = _room_path_segment(
                room=rooms[dst],
                start=dst_anchor,
                end=rooms[dst].center,
                linear_step_m=linear_step_m,
                clearance_m=clearance_m,
            )
        elif room_path_mode == "straight":
            seg_a = _path_segment(
                start=src_start,
                end=src_anchor,
                linear_step_m=linear_step_m,
            )
            seg_c = _path_segment(
                start=dst_anchor,
                end=rooms[dst].center,
                linear_step_m=linear_step_m,
            )
        else:
            raise WholeHomeWalkError(f"Unsupported room_path_mode={room_path_mode}")
        seg_b = _path_segment(
            start=src_anchor,
            end=dst_anchor,
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

    if enable_collision_repair:
        samples = _repair_colliding_samples(
            samples=samples,
            rooms=rooms,
            linear_step_m=linear_step_m,
            clearance_m=clearance_m,
            grid_step_m=room_grid_step_m,
            lookahead_pts=traversal_lookahead_pts,
            pitch_deg=traversal_pitch_deg,
            repair_margin_m=collision_repair_margin_m,
        )

    handheld_perturbation = _apply_handheld_perturbation(
        samples=samples,
        planner_fps=planner_fps,
        scene_seed=scene_seed,
        lateral_amplitude_m=handheld_lateral_amplitude_m,
        yaw_amplitude_deg=handheld_yaw_amplitude_deg,
        pitch_amplitude_deg=handheld_pitch_amplitude_deg,
        noise_sigma_s=handheld_noise_sigma_s,
        forward_smoothing_window=handheld_forward_smoothing_window,
    )

    height_perturbation = _apply_height_perturbation(
        samples=samples,
        rooms=rooms,
        camera_height_m=camera_height_m,
        planner_fps=planner_fps,
        amplitude_m=height_perturbation_amplitude_m,
        frequency_hz=height_perturbation_frequency_hz,
        scene_seed=scene_seed,
    )

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
        "navigation_mode": room_path_mode,
        "scene_modified": True,
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
        "room_path_mode": room_path_mode,
        "room_orbit_min_room_radius_m": room_orbit_min_room_radius_m,
        "room_orbit_radius_scale": room_orbit_radius_scale,
        "room_orbit_radius_min_m": room_orbit_radius_min_m,
        "room_orbit_radius_max_m": room_orbit_radius_max_m,
        "room_grid_step_m": room_grid_step_m,
        "enable_collision_repair": enable_collision_repair,
        "collision_repair_margin_m": collision_repair_margin_m,
        "traversal_pitch_deg": traversal_pitch_deg,
        "sweep_pitch_deg": sweep_pitch_deg,
        "height_perturbation_amplitude_m": height_perturbation_amplitude_m,
        "height_perturbation_frequency_hz": height_perturbation_frequency_hz,
        "handheld_lateral_amplitude_m": handheld_lateral_amplitude_m,
        "handheld_yaw_amplitude_deg": handheld_yaw_amplitude_deg,
        "handheld_pitch_amplitude_deg": handheld_pitch_amplitude_deg,
        "handheld_noise_sigma_s": handheld_noise_sigma_s,
        "handheld_forward_smoothing_window": handheld_forward_smoothing_window,
        "handheld_perturbation": handheld_perturbation,
        "orbit_entry_transition_sec": orbit_entry_transition_sec,
        "orbit_focus_blend": orbit_focus_blend,
        "height_perturbation": height_perturbation,
        "force_open_access_doors": force_open_access_doors,
        "force_open_access_doors_mode": force_open_access_doors_mode,
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
