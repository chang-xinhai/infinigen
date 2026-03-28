from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from scripts.benchmark.neural_rgbd.scene_calibrations import (
    DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD,
    get_scene_calibration,
)

POSE_SOURCE_OPENGL = "poses.txt"
POSE_SOURCE_TRAINVAL = "trainval_poses.txt"
POSE_SOURCE_BLENDER = "blender_poses"
POSE_SOURCES = (POSE_SOURCE_OPENGL, POSE_SOURCE_TRAINVAL, POSE_SOURCE_BLENDER)
BLENDER_TO_CV_CAMERA = np.diag((1.0, -1.0, -1.0, 1.0))

@dataclass(frozen=True)
class BlenderPoseSpec:
    filename: str
    line_stride: int = 1
    line_offset: int = 0


BLENDER_POSE_SPECS = {
    "breakfast_room": BlenderPoseSpec("blender_breakfast_poses.txt"),
    "complete_kitchen": BlenderPoseSpec("blender_complete_kitchen_poses.txt"),
    "green_room": BlenderPoseSpec("blender_green_room_poses.txt"),
    "grey_white_room": BlenderPoseSpec("blender_grey_white_room_poses.txt"),
    "kitchen": BlenderPoseSpec("blender_kitchen_poses.txt"),
    "morning_apartment": BlenderPoseSpec("blender_morning_apartment_poses.txt"),
    "staircase": BlenderPoseSpec("blender_staircase_poses.txt"),
    "thin_geometry": BlenderPoseSpec("blender_thin_objects_poses.txt"),
    "whiteroom": BlenderPoseSpec("blender_whiteroom_poses.txt", line_stride=2, line_offset=0),
}


@dataclass(frozen=True)
class ScenePaths:
    scene_name: str
    dataset_root: Path
    scene_blend_dir: Path
    scene_blend_path: Path
    scene_data_dir: Path
    images_dir: Path
    focal_path: Path
    pose_path: Path


@dataclass(frozen=True)
class SceneSpec:
    paths: ScenePaths
    focal_px: float
    image_width: int
    image_height: int
    pose_source: str
    pose_format: str
    poses_cv: np.ndarray


def discover_scene_names(dataset_root: Path) -> list[str]:
    dataset_root = Path(dataset_root)
    blends_root = dataset_root / "blendswap_scenes"
    data_root = dataset_root / "neural_rgbd_data"
    if not blends_root.is_dir() or not data_root.is_dir():
        return []

    names = []
    for scene_dir in sorted(data_root.iterdir()):
        if not scene_dir.is_dir():
            continue
        if (blends_root / scene_dir.name).is_dir():
            names.append(scene_dir.name)
    return names


def find_scene_blend(scene_blend_dir: Path) -> Path:
    candidates = sorted(Path(scene_blend_dir).glob("*.blend"))
    if not candidates:
        raise FileNotFoundError(f"No .blend file found under {scene_blend_dir}")
    if len(candidates) > 1:
        raise ValueError(
            f"Expected exactly one .blend file under {scene_blend_dir}, found {len(candidates)}"
        )
    return candidates[0]


def resolve_scene_paths(
    dataset_root: Path,
    scene_name: str,
    pose_source: str = POSE_SOURCE_OPENGL,
) -> ScenePaths:
    if pose_source not in POSE_SOURCES:
        raise ValueError(f"Unsupported pose source {pose_source!r}")

    dataset_root = Path(dataset_root)
    scene_data_dir = dataset_root / "neural_rgbd_data" / scene_name
    scene_blend_dir = dataset_root / "blendswap_scenes" / scene_name
    if not scene_data_dir.is_dir():
        raise FileNotFoundError(f"Neural RGB-D scene data not found: {scene_data_dir}")
    if not scene_blend_dir.is_dir():
        raise FileNotFoundError(
            f"Neural RGB-D Blender scene directory not found: {scene_blend_dir}"
        )

    images_dir = scene_data_dir / "images"
    focal_path = scene_data_dir / "focal.txt"
    if pose_source == POSE_SOURCE_BLENDER:
        try:
            blender_pose_spec = BLENDER_POSE_SPECS[scene_name]
        except KeyError as exc:
            raise FileNotFoundError(
                f"No blender pose archive mapping configured for scene {scene_name!r}"
            ) from exc
        pose_path = dataset_root / "blender_poses" / blender_pose_spec.filename
    else:
        pose_path = scene_data_dir / pose_source
    scene_blend_path = find_scene_blend(scene_blend_dir)

    for path in (images_dir, focal_path, pose_path, scene_blend_path):
        if not path.exists():
            raise FileNotFoundError(f"Required Neural RGB-D input missing: {path}")

    return ScenePaths(
        scene_name=scene_name,
        dataset_root=dataset_root,
        scene_blend_dir=scene_blend_dir,
        scene_blend_path=scene_blend_path,
        scene_data_dir=scene_data_dir,
        images_dir=images_dir,
        focal_path=focal_path,
        pose_path=pose_path,
    )


def parse_pose_file(path: Path) -> np.ndarray:
    path = Path(path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append([float(value) for value in stripped.split()])

    if len(rows) % 4 != 0:
        raise ValueError(f"Pose file {path} does not contain a multiple of 4 rows")

    poses = []
    for idx in range(0, len(rows), 4):
        pose = np.asarray(rows[idx : idx + 4], dtype=np.float64)
        if pose.shape != (4, 4):
            raise ValueError(f"Invalid pose shape {pose.shape} in {path}")
        poses.append(pose)

    return np.stack(poses, axis=0)


def parse_blender_pose_file(path: Path, line_stride: int = 1, line_offset: int = 0) -> np.ndarray:
    path = Path(path)
    if line_stride <= 0:
        raise ValueError(f"line_stride must be positive, got {line_stride}")
    if line_offset < 0 or line_offset >= line_stride:
        raise ValueError(
            f"line_offset must satisfy 0 <= line_offset < line_stride, got {line_offset} for stride {line_stride}"
        )

    poses = []
    kept_line_count = 0
    for line_index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if line_index % line_stride != line_offset:
            continue
        values = [float(value) for value in stripped.split()]
        if len(values) != 16:
            raise ValueError(
                f"Blender pose file {path} expected 16 values per line, got {len(values)}"
            )
        poses.append(np.asarray(values, dtype=np.float64).reshape(4, 4))
        kept_line_count += 1

    if kept_line_count == 0:
        raise ValueError(f"Blender pose file {path} did not contain any matrices")
    return np.stack(poses, axis=0)


def read_focal_length(path: Path) -> float:
    return float(Path(path).read_text(encoding="utf-8").strip())


def read_image_resolution(images_dir: Path) -> tuple[int, int]:
    first_image = next(iter(sorted(Path(images_dir).glob("img*.png"))), None)
    if first_image is None:
        raise FileNotFoundError(f"No Neural RGB-D RGB images found under {images_dir}")
    with Image.open(first_image) as img:
        return img.size


def load_scene_spec(
    dataset_root: Path,
    scene_name: str,
    pose_source: str = POSE_SOURCE_OPENGL,
) -> SceneSpec:
    paths = resolve_scene_paths(dataset_root=dataset_root, scene_name=scene_name, pose_source=pose_source)
    focal_px = read_focal_length(paths.focal_path)
    if pose_source == POSE_SOURCE_BLENDER:
        blender_pose_spec = BLENDER_POSE_SPECS[scene_name]
        poses_cv = parse_blender_pose_file(
            paths.pose_path,
            line_stride=blender_pose_spec.line_stride,
            line_offset=blender_pose_spec.line_offset,
        )
        pose_format = "blender"
    else:
        poses_cv = parse_pose_file(paths.pose_path)
        pose_format = "opengl"
    image_width, image_height = read_image_resolution(paths.images_dir)

    image_count = len(list(sorted(paths.images_dir.glob("img*.png"))))
    if image_count != len(poses_cv):
        raise ValueError(
            f"Scene {scene_name} has {image_count} RGB images but {len(poses_cv)} poses in {paths.pose_path.name}"
        )

    return SceneSpec(
        paths=paths,
        focal_px=focal_px,
        image_width=image_width,
        image_height=image_height,
        pose_source=pose_source,
        pose_format=pose_format,
        poses_cv=poses_cv,
    )


def default_output_root(repo_root: Path, scene_name: str, pose_source: str) -> Path:
    pose_stem = Path(pose_source).stem
    return Path(repo_root) / "outputs" / "benchmark" / "neural_rgbd" / scene_name / pose_stem


def frame_numbers(total_frames: int, frame_start: int | None = None, frame_end: int | None = None) -> list[int]:
    if total_frames <= 0:
        raise ValueError(f"Expected a positive frame count, got {total_frames}")
    start = 1 if frame_start is None else int(frame_start)
    end = total_frames if frame_end is None else int(frame_end)
    if start < 1:
        raise ValueError(f"frame_start must be >= 1, got {start}")
    if end > total_frames:
        raise ValueError(f"frame_end must be <= {total_frames}, got {end}")
    if end < start:
        raise ValueError(f"frame_end ({end}) must be >= frame_start ({start})")
    return list(range(start, end + 1))


def frame_to_image_index(frame: int) -> int:
    if frame < 1:
        raise ValueError(f"Frame indices are 1-based, got {frame}")
    return int(frame) - 1


def image_index_to_frame(image_index: int) -> int:
    if image_index < 0:
        raise ValueError(f"Image indices are 0-based, got {image_index}")
    return int(image_index) + 1


def cv_camera_to_blender_pose(pose_cv: np.ndarray) -> np.ndarray:
    pose_cv = np.asarray(pose_cv, dtype=np.float64)
    if pose_cv.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 camera pose, got {pose_cv.shape}")
    return pose_cv @ BLENDER_TO_CV_CAMERA


def blender_pose_to_cv_camera(pose_blender: np.ndarray) -> np.ndarray:
    pose_blender = np.asarray(pose_blender, dtype=np.float64)
    if pose_blender.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 Blender pose, got {pose_blender.shape}")
    return pose_blender @ BLENDER_TO_CV_CAMERA


def opengl_camera_to_blender_pose(pose_opengl: np.ndarray) -> np.ndarray:
    pose_opengl = np.asarray(pose_opengl, dtype=np.float64)
    if pose_opengl.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 camera pose, got {pose_opengl.shape}")
    pose_blender = np.eye(4, dtype=np.float64)
    pose_blender[:3, :3] = DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD @ pose_opengl[:3, :3]
    pose_blender[:3, 3] = DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD @ pose_opengl[:3, 3]
    return pose_blender


def blender_pose_to_opengl_camera(pose_blender: np.ndarray) -> np.ndarray:
    pose_blender = np.asarray(pose_blender, dtype=np.float64)
    if pose_blender.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 Blender pose, got {pose_blender.shape}")
    pose_opengl = np.eye(4, dtype=np.float64)
    pose_opengl[:3, :3] = DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD.T @ pose_blender[:3, :3]
    pose_opengl[:3, 3] = DEFAULT_OPENGL_WORLD_TO_BLENDER_WORLD.T @ pose_blender[:3, 3]
    return pose_opengl


def source_pose_to_blender_pose(
    scene_name: str,
    pose_source: np.ndarray,
    pose_format: str = "opengl",
) -> np.ndarray:
    pose_source = np.asarray(pose_source, dtype=np.float64)
    if pose_source.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 camera pose, got {pose_source.shape}")
    if pose_format == "blender":
        return pose_source.copy()
    if pose_format != "opengl":
        raise ValueError(f"Unsupported pose format {pose_format!r}")
    calibration = get_scene_calibration(scene_name)
    pose_blender = np.eye(4, dtype=np.float64)
    pose_blender[:3, :3] = calibration.rotation @ pose_source[:3, :3]
    pose_blender[:3, 3] = calibration.scale * (
        calibration.rotation @ pose_source[:3, 3]
    ) + calibration.translation
    return pose_blender


def focal_px_to_fov_deg(focal_px: float, image_width: int) -> float:
    return math.degrees(2.0 * math.atan(float(image_width) / (2.0 * float(focal_px))))


def focal_px_to_lens_mm(
    focal_px: float,
    image_width: int,
    sensor_width_mm: float,
) -> float:
    return float(focal_px) * float(sensor_width_mm) / float(image_width)


def estimate_metric_scale_from_pose_sequences(
    metric_poses: np.ndarray,
    blender_poses: np.ndarray,
) -> float:
    metric_poses = np.asarray(metric_poses, dtype=np.float64)
    blender_poses = np.asarray(blender_poses, dtype=np.float64)
    if metric_poses.shape != blender_poses.shape:
        raise ValueError(
            f"Metric and Blender pose arrays must have the same shape, got {metric_poses.shape} and {blender_poses.shape}"
        )
    if metric_poses.ndim != 3 or metric_poses.shape[1:] != (4, 4):
        raise ValueError(f"Expected pose arrays of shape (N, 4, 4), got {metric_poses.shape}")

    metric_centers = metric_poses[:, :3, 3]
    blender_centers = blender_poses[:, :3, 3]

    metric_steps = np.linalg.norm(np.diff(metric_centers, axis=0), axis=1)
    blender_steps = np.linalg.norm(np.diff(blender_centers, axis=0), axis=1)
    valid_steps = (metric_steps > 1e-8) & (blender_steps > 1e-8)
    if np.any(valid_steps):
        return float(np.median(metric_steps[valid_steps] / blender_steps[valid_steps]))

    metric_centered = metric_centers - metric_centers.mean(axis=0, keepdims=True)
    blender_centered = blender_centers - blender_centers.mean(axis=0, keepdims=True)
    metric_radii = np.linalg.norm(metric_centered, axis=1)
    blender_radii = np.linalg.norm(blender_centered, axis=1)
    valid_radii = (metric_radii > 1e-8) & (blender_radii > 1e-8)
    if np.any(valid_radii):
        return float(np.median(metric_radii[valid_radii] / blender_radii[valid_radii]))

    return 1.0


def estimate_blender_pose_metric_scale(
    dataset_root: Path,
    scene_name: str,
) -> float:
    metric_spec = load_scene_spec(
        dataset_root=dataset_root,
        scene_name=scene_name,
        pose_source=POSE_SOURCE_OPENGL,
    )
    blender_spec = load_scene_spec(
        dataset_root=dataset_root,
        scene_name=scene_name,
        pose_source=POSE_SOURCE_BLENDER,
    )
    return estimate_metric_scale_from_pose_sequences(
        metric_poses=metric_spec.poses_cv,
        blender_poses=blender_spec.poses_cv,
    )
