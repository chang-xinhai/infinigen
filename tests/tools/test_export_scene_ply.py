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


def _create_quad(name: str, location=(0.0, 0.0, 0.0), size: float = 2.0) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (size, 0.0, 0.0), (size, size, 0.0), (0.0, size, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return obj


def _create_grid_plane(
    name: str,
    *,
    location=(0.0, 0.0, 0.0),
    size: float = 2.0,
    subdivisions: int = 1,
) -> bpy.types.Object:
    step = size / subdivisions
    vertices = [
        (col * step, row * step, 0.0)
        for row in range(subdivisions + 1)
        for col in range(subdivisions + 1)
    ]
    faces = []
    row_width = subdivisions + 1
    for row in range(subdivisions):
        for col in range(subdivisions):
            v0 = row * row_width + col
            v1 = v0 + 1
            v2 = v0 + row_width + 1
            v3 = v0 + row_width
            faces.append((v0, v1, v2, v3))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
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
        sample_mode=export_scene_ply.SAMPLE_MODE_VERTICES,
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

    default_count, _ = export_scene_ply.export_scene_point_cloud(
        hidden_default_path,
        sample_mode=export_scene_ply.SAMPLE_MODE_VERTICES,
    )
    include_hidden_count, _ = export_scene_ply.export_scene_point_cloud(
        include_hidden_path,
        include_hidden=True,
        sample_mode=export_scene_ply.SAMPLE_MODE_VERTICES,
    )

    assert default_count == 3
    assert include_hidden_count == 6


def test_export_scene_point_cloud_surface_sampling_adds_face_interior_points(tmp_path):
    butil.clear_scene()
    _create_quad("quad_surface", location=(1.0, 2.0, 3.0), size=2.0)

    output_path = tmp_path / "surface_ascii.ply"
    vertex_count, ply_format = export_scene_ply.export_scene_point_cloud(
        output_path,
        ascii_format=True,
        sample_mode=export_scene_ply.SAMPLE_MODE_SURFACE,
        sample_spacing=0.5,
    )

    vertices = _read_ply_vertices(output_path)
    positions = [vertex[:3] for vertex in vertices]

    assert ply_format == "ascii 1.0"
    assert vertex_count == len(vertices)
    assert vertex_count > 8
    assert any(1.0 < x < 3.0 and 2.0 < y < 4.0 for x, y, _ in positions)
    assert all(abs(z - 3.0) < 1e-6 for _, _, z in positions)
    assert all(abs(nx) < 1e-6 and abs(ny) < 1e-6 and abs(nz - 1.0) < 1e-6 for _, _, _, nx, ny, nz in vertices)


def test_surface_sampling_density_is_stable_across_mesh_tessellation(tmp_path):
    butil.clear_scene()
    _create_grid_plane("coarse_plane", size=2.0, subdivisions=1)
    coarse_path = tmp_path / "coarse_surface_ascii.ply"
    coarse_count, _ = export_scene_ply.export_scene_point_cloud(
        coarse_path,
        ascii_format=True,
        sample_mode=export_scene_ply.SAMPLE_MODE_SURFACE,
        sample_spacing=0.5,
    )

    butil.clear_scene()
    _create_grid_plane("fine_plane", size=2.0, subdivisions=8)
    fine_path = tmp_path / "fine_surface_ascii.ply"
    fine_count, _ = export_scene_ply.export_scene_point_cloud(
        fine_path,
        ascii_format=True,
        sample_mode=export_scene_ply.SAMPLE_MODE_SURFACE,
        sample_spacing=0.5,
    )

    assert abs(coarse_count - fine_count) <= 2


def test_export_scene_point_cloud_can_filter_by_exact_object_name(tmp_path):
    butil.clear_scene()
    _create_triangle("kept_triangle", location=(0.0, 0.0, 0.0))
    _create_triangle("dropped_triangle", location=(10.0, 0.0, 0.0))

    output_path = tmp_path / "filtered_ascii.ply"
    vertex_count, ply_format = export_scene_ply.export_scene_point_cloud(
        output_path,
        ascii_format=True,
        sample_mode=export_scene_ply.SAMPLE_MODE_VERTICES,
        object_names={"kept_triangle"},
    )

    vertices = _read_ply_vertices(output_path)
    assert ply_format == "ascii 1.0"
    assert vertex_count == 3
    assert len(vertices) == 3
    assert {tuple(round(value, 6) for value in vertex[:3]) for vertex in vertices} == {
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    }
