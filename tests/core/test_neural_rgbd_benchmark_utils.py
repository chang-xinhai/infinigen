# Copyright (C) 2026.

import math
import sys
from pathlib import Path

import bpy
import numpy as np
from PIL import Image

import infinigen

sys.path.insert(0, str(infinigen.repo_root()))

from scripts.benchmark.neural_rgbd.common import (
    BLENDER_POSE_SPECS,
    POSE_SOURCE_BLENDER,
    blender_pose_to_cv_camera,
    cv_camera_to_blender_pose,
    default_output_root,
    discover_scene_names,
    estimate_metric_scale_from_pose_sequences,
    focal_px_to_fov_deg,
    frame_numbers,
    frame_to_image_index,
    image_index_to_frame,
    load_scene_spec,
    opengl_camera_to_blender_pose,
    parse_blender_pose_file,
    parse_pose_file,
    resolve_scene_paths,
    source_pose_to_blender_pose,
)
from scripts.benchmark.neural_rgbd.scene_calibrations import get_scene_calibration
from scripts.benchmark.neural_rgbd.comparison import compare_rgb_pair, write_comparison_reports
from scripts.benchmark.neural_rgbd.run_neural_rgbd import (
    MISSING_TEXTURE_PLACEHOLDER_NAME,
    _set_scene_render_resolution,
    _sanitize_missing_texture_images,
)


def test_parse_pose_file_reads_multiple_poses(tmp_path):
    pose_path = tmp_path / "poses.txt"
    pose_path.write_text(
        "\n".join(
            [
                "1 0 0 0",
                "0 1 0 0",
                "0 0 1 0",
                "0 0 0 1",
                "1 0 0 1",
                "0 1 0 2",
                "0 0 1 3",
                "0 0 0 1",
            ]
        ),
        encoding="utf-8",
    )

    poses = parse_pose_file(pose_path)

    assert poses.shape == (2, 4, 4)
    np.testing.assert_allclose(poses[1][:3, 3], [1.0, 2.0, 3.0])


def test_parse_blender_pose_file_reads_flattened_matrices(tmp_path):
    pose_path = tmp_path / "blender_poses.txt"
    pose_path.write_text(
        "\n".join(
            [
                "1 0 0 1 0 1 0 2 0 0 1 3 0 0 0 1",
                "1 0 0 4 0 1 0 5 0 0 1 6 0 0 0 1",
            ]
        ),
        encoding="utf-8",
    )

    poses = parse_blender_pose_file(pose_path)

    assert poses.shape == (2, 4, 4)
    np.testing.assert_allclose(poses[0][:3, 3], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(poses[1][:3, 3], [4.0, 5.0, 6.0])


def test_parse_blender_pose_file_supports_stride_and_offset(tmp_path):
    pose_path = tmp_path / "blender_poses.txt"
    pose_path.write_text(
        "\n".join(
            [
                "1 0 0 1 0 1 0 1 0 0 1 1 0 0 0 1",
                "1 0 0 2 0 1 0 2 0 0 1 2 0 0 0 1",
                "1 0 0 3 0 1 0 3 0 0 1 3 0 0 0 1",
                "1 0 0 4 0 1 0 4 0 0 1 4 0 0 0 1",
            ]
        ),
        encoding="utf-8",
    )

    poses = parse_blender_pose_file(pose_path, line_stride=2, line_offset=0)

    assert poses.shape == (2, 4, 4)
    np.testing.assert_allclose(poses[:, :3, 3], [[1.0, 1.0, 1.0], [3.0, 3.0, 3.0]])


def test_scene_resolution_and_pose_count_are_loaded_from_dataset_layout(tmp_path):
    dataset_root = tmp_path / "data" / "neural_rgbd"
    scene_name = "demo_room"
    blend_dir = dataset_root / "blendswap_scenes" / scene_name
    data_dir = dataset_root / "neural_rgbd_data" / scene_name
    images_dir = data_dir / "images"
    blend_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    (blend_dir / "scene.blend").write_text("", encoding="utf-8")
    (data_dir / "focal.txt").write_text("500.0\n", encoding="utf-8")
    (data_dir / "poses.txt").write_text(
        "\n".join(
            [
                "1 0 0 0",
                "0 1 0 0",
                "0 0 1 0",
                "0 0 0 1",
            ]
        ),
        encoding="utf-8",
    )
    Image.new("RGB", (640, 480), (12, 34, 56)).save(images_dir / "img0.png")

    spec = load_scene_spec(dataset_root=dataset_root, scene_name=scene_name)

    assert spec.focal_px == 500.0
    assert spec.image_width == 640
    assert spec.image_height == 480
    assert spec.poses_cv.shape == (1, 4, 4)
    assert resolve_scene_paths(dataset_root, scene_name).scene_blend_path.name == "scene.blend"


def test_blender_pose_source_resolves_from_dataset_root_and_bypasses_scene_calibration(tmp_path):
    dataset_root = tmp_path / "data" / "neural_rgbd"
    scene_name = "breakfast_room"
    blend_dir = dataset_root / "blendswap_scenes" / scene_name
    data_dir = dataset_root / "neural_rgbd_data" / scene_name
    images_dir = data_dir / "images"
    blender_pose_dir = dataset_root / "blender_poses"
    blend_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    blender_pose_dir.mkdir(parents=True, exist_ok=True)

    (blend_dir / "scene.blend").write_text("", encoding="utf-8")
    (data_dir / "focal.txt").write_text("500.0\n", encoding="utf-8")
    (data_dir / "poses.txt").write_text(
        "\n".join(
            [
                "1 0 0 0",
                "0 1 0 0",
                "0 0 1 0",
                "0 0 0 1",
            ]
        ),
        encoding="utf-8",
    )
    (blender_pose_dir / BLENDER_POSE_SPECS[scene_name].filename).write_text(
        "1 0 0 1 0 1 0 2 0 0 1 3 0 0 0 1\n",
        encoding="utf-8",
    )
    Image.new("RGB", (640, 480), (12, 34, 56)).save(images_dir / "img0.png")

    spec = load_scene_spec(dataset_root=dataset_root, scene_name=scene_name, pose_source=POSE_SOURCE_BLENDER)
    resolved = resolve_scene_paths(dataset_root, scene_name, pose_source=POSE_SOURCE_BLENDER)

    assert spec.pose_format == "blender"
    assert resolved.pose_path == blender_pose_dir / BLENDER_POSE_SPECS[scene_name].filename
    np.testing.assert_allclose(spec.poses_cv[0][:3, 3], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(
        source_pose_to_blender_pose(scene_name, spec.poses_cv[0], pose_format=spec.pose_format),
        spec.poses_cv[0],
    )


def test_whiteroom_blender_pose_spec_selects_even_archive_lines():
    spec = BLENDER_POSE_SPECS["whiteroom"]
    assert spec.line_stride == 2
    assert spec.line_offset == 0


def test_discover_scene_names_requires_both_blend_and_data_directories(tmp_path):
    dataset_root = tmp_path / "data" / "neural_rgbd"
    (dataset_root / "blendswap_scenes" / "room_a").mkdir(parents=True, exist_ok=True)
    (dataset_root / "neural_rgbd_data" / "room_a").mkdir(parents=True, exist_ok=True)
    (dataset_root / "neural_rgbd_data" / "room_b").mkdir(parents=True, exist_ok=True)

    assert discover_scene_names(dataset_root) == ["room_a"]


def test_cv_blender_pose_conversion_roundtrip():
    pose_cv = np.array(
        [
            [0.0, -1.0, 0.0, 1.0],
            [1.0, 0.0, 0.0, 2.0],
            [0.0, 0.0, 1.0, 3.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    pose_blender = cv_camera_to_blender_pose(pose_cv)
    roundtrip = blender_pose_to_cv_camera(pose_blender)

    np.testing.assert_allclose(roundtrip, pose_cv)


def test_opengl_blender_pose_conversion_maps_y_up_world_to_z_up_world():
    pose = np.array(
        [
            [1.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0, 2.0],
            [0.0, 1.0, 0.0, 3.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    expected = np.array(
        [
            [1.0, 0.0, 0.0, 1.0],
            [0.0, -1.0, 0.0, -3.0],
            [0.0, 0.0, -1.0, 2.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(opengl_camera_to_blender_pose(pose), expected)


def test_breakfast_room_scene_calibration_changes_scale_and_translation():
    pose = np.eye(4, dtype=np.float64)
    pose[:3, 3] = [-0.30483, 1.367226, 1.462762]

    pose_blender = source_pose_to_blender_pose("breakfast_room", pose)
    calibration = get_scene_calibration("breakfast_room")

    np.testing.assert_allclose(pose_blender[:3, :3], calibration.rotation)
    np.testing.assert_allclose(pose_blender[:3, 3], [-0.7, -1.8, 5.0], atol=1e-6)


def test_frame_helpers_and_default_output_root():
    assert frame_numbers(total_frames=5, frame_start=2, frame_end=4) == [2, 3, 4]
    assert frame_to_image_index(1) == 0
    assert image_index_to_frame(3) == 4
    assert default_output_root(Path("/repo"), "breakfast_room", "poses.txt") == Path(
        "/repo/outputs/benchmark/neural_rgbd/breakfast_room/poses"
    )


def test_focal_px_to_fov_deg_matches_expected_geometry():
    fov = focal_px_to_fov_deg(554.2562584220408, 640)
    assert math.isclose(fov, 60.0, rel_tol=1e-9)


def test_estimate_metric_scale_from_pose_sequences_recovers_blender_to_metric_scalar():
    metric = np.repeat(np.eye(4, dtype=np.float64)[None, ...], 3, axis=0)
    blender = np.repeat(np.eye(4, dtype=np.float64)[None, ...], 3, axis=0)

    metric[:, 0, 3] = [0.0, 1.0, 2.0]
    blender[:, 0, 3] = [0.0, 4.0, 8.0]

    scale = estimate_metric_scale_from_pose_sequences(metric_poses=metric, blender_poses=blender)

    assert math.isclose(scale, 0.25, rel_tol=1e-9)


def test_compare_rgb_pair_and_write_reports(tmp_path):
    reference_path = tmp_path / "reference.png"
    rendered_path = tmp_path / "rendered.png"

    Image.new("RGB", (2, 2), (10, 20, 30)).save(reference_path)
    Image.new("RGB", (2, 2), (11, 18, 35)).save(rendered_path)

    report = compare_rgb_pair(
        frame=1,
        image_index=0,
        reference_path=reference_path,
        rendered_path=rendered_path,
    )

    assert report.frame == 1
    assert report.image_index == 0
    assert report.max_abs_diff == 5
    assert not report.exact_match

    summary = write_comparison_reports(tmp_path / "comparison", [report])

    assert summary["frame_count"] == 1
    assert (tmp_path / "comparison" / "summary.json").exists()
    assert (tmp_path / "comparison" / "frames.jsonl").exists()
    assert (tmp_path / "comparison" / "frames.tsv").exists()


def test_missing_texture_sanitizer_remaps_used_images_and_disables_autopack(tmp_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        missing_path = tmp_path / "missing_texture.jpg"
        existing_path = tmp_path / "existing_texture.jpg"
        existing_path.write_bytes(b"not_an_image_but_exists")

        material = bpy.data.materials.new(name="TestMaterial")
        material.use_nodes = True
        node_tree = material.node_tree
        missing_node = node_tree.nodes.new("ShaderNodeTexImage")
        existing_node = node_tree.nodes.new("ShaderNodeTexImage")

        missing_image = bpy.data.images.new(name="MissingImage", width=1, height=1, alpha=True)
        missing_image.source = "FILE"
        missing_image.filepath = str(missing_path)
        missing_node.image = missing_image

        existing_image = bpy.data.images.new(name="ExistingImage", width=1, height=1, alpha=True)
        existing_image.source = "FILE"
        existing_image.filepath = str(existing_path)
        existing_node.image = existing_image

        bpy.data.use_autopack = True

        replacements = _sanitize_missing_texture_images()

        assert bpy.data.use_autopack is False
        assert len(replacements) == 1
        assert replacements[0]["image_name"] == "MissingImage"
        assert replacements[0]["missing_path"] == str(missing_path)
        assert replacements[0]["action"] == f"remapped_to:{MISSING_TEXTURE_PLACEHOLDER_NAME}"
        assert missing_node.image is bpy.data.images[MISSING_TEXTURE_PLACEHOLDER_NAME]
        assert existing_node.image is existing_image
        assert bpy.data.images.get("MissingImage") is None
    finally:
        bpy.ops.wm.read_factory_settings(use_empty=True)


def test_set_scene_render_resolution_forces_full_scale():
    scene = bpy.context.scene
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 65

    _set_scene_render_resolution(scene, 640, 480)

    assert scene.render.resolution_x == 640
    assert scene.render.resolution_y == 480
    assert scene.render.resolution_percentage == 100
