# Copyright (C) 2026.

import struct
from pathlib import Path

import bpy

from infinigen.core.util import blender as butil
from infinigen.tools import export_scene_ply


def _create_triangle(name: str, location=(0.0, 0.0, 0.0), hidden: bool = False) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    if hidden:
        obj.hide_set(True)
        obj.hide_render = True
    return obj


def _read_ply_vertices(path: Path) -> list[tuple[float, float, float, float, float, float]]:
    header_lines = []
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ValueError(f"Unexpected end of file while reading PLY header from {path}")
            decoded = line.decode("utf-8").rstrip("\n")
            header_lines.append(decoded)
            if decoded == "end_header":
                break
        payload = handle.read()

    vertex_count = None
    ply_format = None
    for line in header_lines:
        if line.startswith("format "):
            ply_format = line.split(" ", 1)[1]
        if line.startswith("element vertex "):
            vertex_count = int(line.rsplit(" ", 1)[1])

    if vertex_count is None or ply_format is None:
        raise ValueError(f"Malformed PLY header in {path}")

    if ply_format == "ascii 1.0":
        rows = payload.decode("utf-8").strip().splitlines()
        return [tuple(float(value) for value in row.split()) for row in rows if row.strip()]

    if ply_format == "binary_little_endian 1.0":
        stride = struct.calcsize("<6f")
        return [
            struct.unpack("<6f", payload[idx * stride : (idx + 1) * stride])
            for idx in range(vertex_count)
        ]

    raise ValueError(f"Unsupported PLY format in test helper: {ply_format}")


def test_export_scene_point_cloud_writes_world_space_vertices(tmp_path):
    butil.clear_scene()
    _create_triangle("triangle_world", location=(1.5, -2.0, 3.25))

    output_path = tmp_path / "scene_ascii.ply"
    vertex_count, ply_format = export_scene_ply.export_scene_point_cloud(
        output_path,
        ascii_format=True,
    )

    vertices = _read_ply_vertices(output_path)
    assert ply_format == "ascii 1.0"
    assert vertex_count == 3
    assert len(vertices) == 3
    assert {tuple(round(value, 6) for value in vertex[:3]) for vertex in vertices} == {
        (1.5, -2.0, 3.25),
        (2.5, -2.0, 3.25),
        (1.5, -1.0, 3.25),
    }


def test_export_scene_point_cloud_skips_hidden_objects_by_default(tmp_path):
    butil.clear_scene()
    _create_triangle("visible_triangle", location=(0.0, 0.0, 0.0))
    _create_triangle("hidden_triangle", location=(10.0, 0.0, 0.0), hidden=True)

    hidden_default_path = tmp_path / "default_binary.ply"
    include_hidden_path = tmp_path / "include_hidden_binary.ply"

    default_count, _ = export_scene_ply.export_scene_point_cloud(hidden_default_path)
    include_hidden_count, _ = export_scene_ply.export_scene_point_cloud(
        include_hidden_path,
        include_hidden=True,
    )

    assert default_count == 3
    assert include_hidden_count == 6
