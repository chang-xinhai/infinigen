#!/usr/bin/env python

from __future__ import annotations

import argparse
import logging
import struct
import sys
import tempfile
from pathlib import Path

import bpy


logger = logging.getLogger(__name__)


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


def _iter_scene_vertices(include_hidden: bool):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    view_layer = bpy.context.view_layer

    for source_obj in bpy.context.scene.objects:
        if source_obj.type != "MESH":
            continue

        if not include_hidden and not source_obj.visible_get(view_layer=view_layer):
            continue

        evaluated_obj = source_obj.evaluated_get(depsgraph)
        yield from _iter_object_vertices(
            evaluated_obj,
            matrix_world=evaluated_obj.matrix_world.copy(),
            depsgraph=depsgraph,
        )

    for instance in depsgraph.object_instances:
        if not instance.is_instance:
            continue

        obj = instance.object
        if obj is None or obj.type != "MESH":
            continue

        source_obj = obj.original if getattr(obj, "original", None) is not None else obj
        if not include_hidden and not source_obj.visible_get(view_layer=view_layer):
            continue

        yield from _iter_object_vertices(
            obj,
            matrix_world=instance.matrix_world.copy(),
            depsgraph=depsgraph,
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
) -> tuple[int, str]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
            for vertex in _iter_scene_vertices(include_hidden=include_hidden):
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
    )
    logger.info(
        "Exported %d world-space points to %s using %s",
        vertex_count,
        args.output_path,
        ply_format,
    )


if __name__ == "__main__":
    main()
