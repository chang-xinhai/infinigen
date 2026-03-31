#!/usr/bin/env python

from __future__ import annotations

import argparse
import hashlib
import logging
import math
import struct
import sys
import tempfile
from pathlib import Path

import bpy


logger = logging.getLogger(__name__)
SAMPLE_MODE_VERTICES = "vertices"
SAMPLE_MODE_SURFACE = "surface"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a Blender scene to a world-space PLY point cloud."
    )
    parser.add_argument("--input_blend", type=Path, required=True)
    parser.add_argument("--output_path", type=Path, required=True)
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="Write ASCII PLY instead of binary little-endian PLY.",
    )
    parser.add_argument(
        "--include_hidden",
        action="store_true",
        help="Include hidden objects in the exported point cloud.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the destination file if it already exists.",
    )
    parser.add_argument(
        "--sample_mode",
        type=str,
        default=SAMPLE_MODE_SURFACE,
        choices=[SAMPLE_MODE_VERTICES, SAMPLE_MODE_SURFACE],
        help="Point export mode: raw mesh vertices or deterministic face-interior surface sampling.",
    )
    parser.add_argument(
        "--sample_spacing",
        type=float,
        default=0.05,
        help="Target spacing in Blender world units for surface sampling.",
    )
    parser.add_argument(
        "--include_vertices",
        action="store_true",
        help="When surface sampling, also include the original evaluated mesh vertices.",
    )
    parser.add_argument(
        "--object_name",
        action="append",
        default=[],
        help=(
            "Optional exact object name filter. Repeat the flag to include multiple objects. "
            "When omitted, all eligible mesh objects are exported."
        ),
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    return parser.parse_args(argv)


def _iter_object_vertices(
    obj: bpy.types.Object,
    *,
    matrix_world,
    depsgraph,
):
    mesh = obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    if mesh is None:
        return

    try:
        if not mesh.vertices:
            return

        normal_matrix = matrix_world.to_3x3()

        for vertex in mesh.vertices:
            position = matrix_world @ vertex.co
            normal = normal_matrix @ vertex.normal
            if normal.length_squared > 0.0:
                normal.normalize()
            yield (
                float(position.x),
                float(position.y),
                float(position.z),
                float(normal.x),
                float(normal.y),
                float(normal.z),
            )
    finally:
        obj.to_mesh_clear()


def _iter_triangle_surface_samples(
    mesh: bpy.types.Mesh,
    *,
    matrix_world,
    sample_spacing: float,
    seed_base: int,
):
    if sample_spacing <= 0.0:
        raise ValueError(f"sample_spacing must be positive, got {sample_spacing}")

    if not mesh.loop_triangles:
        mesh.calc_loop_triangles()

    target_area_per_point = (math.sqrt(3.0) / 2.0) * (sample_spacing ** 2)
    normal_matrix = matrix_world.to_3x3()

    for triangle_index, triangle in enumerate(mesh.loop_triangles):
        vertices_local = [mesh.vertices[index].co.copy() for index in triangle.vertices]
        vertices_world = [matrix_world @ vertex for vertex in vertices_local]
        edge_a = vertices_world[1] - vertices_world[0]
        edge_b = vertices_world[2] - vertices_world[0]
        triangle_area = 0.5 * edge_a.cross(edge_b).length
        if triangle_area <= 0.0:
            continue

        exact_sample_count = triangle_area / target_area_per_point
        sample_count = int(math.floor(exact_sample_count))
        fractional = exact_sample_count - sample_count
        if fractional > _hash_to_unit_float(seed_base, triangle_index):
            sample_count += 1
        if sample_count <= 0:
            continue

        normal = normal_matrix @ triangle.normal
        if normal.length_squared > 0.0:
            normal.normalize()

        for sample_index in range(sample_count):
            u, v = _triangle_sample_uv(seed_base, triangle_index, sample_index)
            r1 = math.sqrt(u)
            b0 = 1.0 - r1
            b1 = r1 * (1.0 - v)
            b2 = r1 * v
            position = (
                (vertices_world[0] * b0)
                + (vertices_world[1] * b1)
                + (vertices_world[2] * b2)
            )
            yield (
                float(position.x),
                float(position.y),
                float(position.z),
                float(normal.x),
                float(normal.y),
                float(normal.z),
            )


def _hash_to_unit_float(*values: int) -> float:
    digest = hashlib.blake2b(
        ":".join(str(value) for value in values).encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "little") / float(1 << 64)


def _triangle_sample_uv(
    seed_base: int,
    triangle_index: int,
    sample_index: int,
) -> tuple[float, float]:
    u = _hash_to_unit_float(seed_base, triangle_index, sample_index, 0)
    v = _hash_to_unit_float(seed_base, triangle_index, sample_index, 1)
    u = min(max(u, 1e-7), 1.0 - 1e-7)
    v = min(max(v, 1e-7), 1.0 - 1e-7)
    return u, v


def _iter_object_points(
    obj: bpy.types.Object,
    *,
    matrix_world,
    depsgraph,
    sample_mode: str,
    sample_spacing: float,
    include_vertices: bool,
):
    if sample_mode == SAMPLE_MODE_VERTICES or include_vertices:
        yield from _iter_object_vertices(
            obj,
            matrix_world=matrix_world,
            depsgraph=depsgraph,
        )
    if sample_mode == SAMPLE_MODE_SURFACE:
        mesh = obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
        if mesh is None:
            return
        try:
            seed_base = int(
                hashlib.blake2b(
                    f"{obj.name}:{tuple(round(value, 6) for row in matrix_world for value in row)}".encode("utf-8"),
                    digest_size=8,
                ).hexdigest(),
                16,
            )
            yield from _iter_triangle_surface_samples(
                mesh,
                matrix_world=matrix_world,
                sample_spacing=sample_spacing,
                seed_base=seed_base,
            )
        finally:
            obj.to_mesh_clear()


def _iter_scene_vertices(
    include_hidden: bool,
    *,
    sample_mode: str,
    sample_spacing: float,
    include_vertices: bool,
    object_names: set[str] | None = None,
):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    view_layer = bpy.context.view_layer

    for source_obj in bpy.context.scene.objects:
        if source_obj.type != "MESH":
            continue
        if object_names is not None and source_obj.name not in object_names:
            continue

        if not include_hidden and not source_obj.visible_get(view_layer=view_layer):
            continue

        evaluated_obj = source_obj.evaluated_get(depsgraph)
        yield from _iter_object_points(
            evaluated_obj,
            matrix_world=evaluated_obj.matrix_world.copy(),
            depsgraph=depsgraph,
            sample_mode=sample_mode,
            sample_spacing=sample_spacing,
            include_vertices=include_vertices,
        )

    for instance in depsgraph.object_instances:
        if not instance.is_instance:
            continue

        obj = instance.object
        if obj is None or obj.type != "MESH":
            continue

        source_obj = obj.original if getattr(obj, "original", None) is not None else obj
        if object_names is not None and source_obj.name not in object_names:
            continue
        if not include_hidden and not source_obj.visible_get(view_layer=view_layer):
            continue

        yield from _iter_object_points(
            obj,
            matrix_world=instance.matrix_world.copy(),
            depsgraph=depsgraph,
            sample_mode=sample_mode,
            sample_spacing=sample_spacing,
            include_vertices=include_vertices,
        )


def _write_binary_vertex(temp_file, vertex: tuple[float, float, float, float, float, float]) -> None:
    temp_file.write(struct.pack("<6f", *vertex))


def _write_ascii_vertex(temp_file, vertex: tuple[float, float, float, float, float, float]) -> None:
    temp_file.write(("%0.9f %0.9f %0.9f %0.9f %0.9f %0.9f\n" % vertex).encode("utf-8"))


def export_scene_point_cloud(
    output_path: Path,
    *,
    ascii_format: bool = False,
    include_hidden: bool = False,
    sample_mode: str = SAMPLE_MODE_SURFACE,
    sample_spacing: float = 0.05,
    include_vertices: bool = False,
    object_names: set[str] | None = None,
) -> tuple[int, str]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if sample_mode not in {SAMPLE_MODE_VERTICES, SAMPLE_MODE_SURFACE}:
        raise ValueError(f"Unsupported sample_mode: {sample_mode}")
    if sample_spacing <= 0.0:
        raise ValueError(f"sample_spacing must be positive, got {sample_spacing}")

    writer = _write_ascii_vertex if ascii_format else _write_binary_vertex
    ply_format = "ascii 1.0" if ascii_format else "binary_little_endian 1.0"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=output_path.parent,
            prefix=f"{output_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            vertex_count = 0
            for vertex in _iter_scene_vertices(
                include_hidden=include_hidden,
                sample_mode=sample_mode,
                sample_spacing=sample_spacing,
                include_vertices=include_vertices,
                object_names=object_names,
            ):
                writer(temp_file, vertex)
                vertex_count += 1

        header = "\n".join(
            [
                "ply",
                f"format {ply_format}",
                f"element vertex {vertex_count}",
                "property float x",
                "property float y",
                "property float z",
                "property float nx",
                "property float ny",
                "property float nz",
                "end_header",
                "",
            ]
        ).encode("utf-8")

        with output_path.open("wb") as output_file, temp_path.open("rb") as temp_file:
            output_file.write(header)
            while True:
                chunk = temp_file.read(1024 * 1024)
                if not chunk:
                    break
                output_file.write(chunk)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return vertex_count, ply_format


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv if argv is None else argv)

    logging.basicConfig(
        format="[%(asctime)s.%(msecs)03d] [%(module)s] [%(levelname)s] | %(message)s",
        datefmt="%H:%M:%S",
        level=getattr(logging, args.log_level),
    )

    if args.output_path.suffix.lower() != ".ply":
        raise ValueError(f"output_path must end with .ply, got {args.output_path}")
    if not args.input_blend.exists():
        raise FileNotFoundError(f"Blend file not found: {args.input_blend}")
    if args.output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output file already exists: {args.output_path}. Pass --overwrite to replace it."
        )

    logger.info("Opening blend file %s", args.input_blend)
    bpy.ops.wm.open_mainfile(filepath=str(args.input_blend))

    vertex_count, ply_format = export_scene_point_cloud(
        args.output_path,
        ascii_format=args.ascii,
        include_hidden=args.include_hidden,
        sample_mode=args.sample_mode,
        sample_spacing=args.sample_spacing,
        include_vertices=args.include_vertices,
        object_names=set(args.object_name) if args.object_name else None,
    )
    logger.info(
        "Exported %d world-space points to %s using %s (%s mode, spacing=%s, include_vertices=%s)",
        vertex_count,
        args.output_path,
        ply_format,
        args.sample_mode,
        args.sample_spacing,
        args.include_vertices,
    )


if __name__ == "__main__":
    main()
