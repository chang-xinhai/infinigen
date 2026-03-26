#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
import gin
import numpy as np
from mathutils import Matrix

from infinigen.core import init
from infinigen.core.placement import camera as cam_placement
from infinigen.core.rendering.structured_light import render_structured_light
from infinigen.core.util import blender as butil

from scripts.benchmark.neural_rgbd.common import (
    POSE_SOURCE_BLENDER,
    POSE_SOURCES,
    SceneSpec,
    blender_pose_to_cv_camera,
    default_output_root,
    discover_scene_names,
    focal_px_to_lens_mm,
    frame_numbers,
    frame_to_image_index,
    load_scene_spec,
    source_pose_to_blender_pose,
)
from scripts.benchmark.neural_rgbd.comparison import compare_rgb_pair, write_comparison_reports
from scripts.benchmark.neural_rgbd.scene_calibrations import get_scene_calibration

logging.basicConfig(
    format="[%(asctime)s.%(msecs)03d] [%(module)s] [%(levelname)s] | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

RIG_NAME = "camrig.0"
CAMERA_NAME = "camera_0_0"
CAMERA_SENSOR_HEIGHT_MM = 18.0
MISSING_TEXTURE_PLACEHOLDER_NAME = "neural_rgbd_missing_texture_placeholder"
MISSING_TEXTURE_PLACEHOLDER_RGBA = (0.5, 0.5, 0.5, 1.0)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Neural RGB-D benchmark pipeline")
    parser.add_argument("--dataset_root", type=Path, default=REPO_ROOT / "data" / "neural_rgbd")
    parser.add_argument("--scene_name", type=str, required=True)
    parser.add_argument(
        "--pose_source",
        type=str,
        default=POSE_SOURCE_BLENDER,
        choices=list(POSE_SOURCES),
    )
    parser.add_argument(
        "--task",
        nargs="+",
        required=True,
        choices=["trajectory", "render", "structured_light"],
    )
    parser.add_argument("--output_root", type=Path, default=None)
    parser.add_argument("--frame_start", type=int, default=None)
    parser.add_argument("--frame_end", type=int, default=None)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument(
        "--render_engine",
        type=str,
        default="KEEP",
        choices=["KEEP", "CYCLES", "BLENDER_EEVEE"],
    )
    parser.add_argument("--render_samples", type=int, default=None)
    parser.add_argument(
        "-g",
        "--configs",
        nargs="+",
        default=[],
        help="Optional gin configs resolved against benchmark-local configs and indoor configs.",
    )
    parser.add_argument(
        "-p",
        "--overrides",
        nargs="+",
        default=[],
        help="Optional gin bindings for benchmark-local rendering and structured-light calls.",
    )
    return parser.parse_args(argv)


def _apply_gin_if_requested(configs: list[str], overrides: list[str]) -> None:
    if not configs and not overrides:
        return
    gin.clear_config()
    init.apply_gin_configs(
        config_folders=[
            Path("scripts/benchmark/neural_rgbd/configs"),
            Path("infinigen_examples/configs_indoor"),
        ],
        configs=configs,
        overrides=overrides,
        skip_unknown=True,
    )


def _frame_numbers_for_spec(spec: SceneSpec, args: argparse.Namespace) -> list[int]:
    return frame_numbers(
        total_frames=len(spec.poses_cv),
        frame_start=args.frame_start,
        frame_end=args.frame_end,
    )


def _ensure_benchmark_camera_names_available() -> None:
    conflicts = [name for name in (RIG_NAME, CAMERA_NAME) if name in bpy.data.objects]
    if conflicts:
        raise ValueError(
            "Neural RGB-D trajectory import requires reserved camera names to be free, "
            f"but found existing objects: {conflicts}"
        )


def _spawn_benchmark_camera(spec: SceneSpec):
    _ensure_benchmark_camera_names_available()
    scene = bpy.context.scene
    scene.render.resolution_x = spec.image_width
    scene.render.resolution_y = spec.image_height

    rig_collection = butil.get_collection("camera_rigs")
    camera_collection = butil.get_collection("cameras")

    rig = butil.spawn_empty(RIG_NAME)
    butil.put_in_collection(rig, rig_collection)

    camera = cam_placement.spawn_camera()
    camera.name = CAMERA_NAME
    camera.parent = rig
    camera.location = (0.0, 0.0, 0.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera.data.sensor_fit = "HORIZONTAL"
    cam_placement.adjust_camera_sensor(camera)
    camera.data.sensor_height = CAMERA_SENSOR_HEIGHT_MM
    camera.data.sensor_width = CAMERA_SENSOR_HEIGHT_MM * spec.image_width / spec.image_height
    camera.data.lens = focal_px_to_lens_mm(
        focal_px=spec.focal_px,
        image_width=spec.image_width,
        sensor_width_mm=camera.data.sensor_width,
    )
    camera.data.dof.use_dof = False
    butil.put_in_collection(camera, camera_collection)
    cam_placement.set_active_camera(camera)
    return rig, camera


def _set_linear_keyframe_interpolation(obj: bpy.types.Object) -> None:
    if obj.animation_data is None or obj.animation_data.action is None:
        return
    for fcurve in obj.animation_data.action.fcurves:
        for keyframe_point in fcurve.keyframe_points:
            keyframe_point.interpolation = "LINEAR"


def _trajectory_output_paths(output_root: Path) -> tuple[Path, Path]:
    trajectory_dir = output_root / "trajectory"
    return trajectory_dir / "scene.blend", trajectory_dir / "trajectory_metadata.json"


def _render_output_paths(output_root: Path) -> tuple[Path, Path, Path]:
    frames_root = output_root / "frames"
    return frames_root / "rgb", frames_root / "camview", frames_root / "comparison"


def _load_trajectory_metadata(metadata_path: Path) -> dict:
    return json.loads(Path(metadata_path).read_text(encoding="utf-8"))


def _samples_for_frame_range(samples: list[dict], frame_start: int | None, frame_end: int | None) -> list[dict]:
    if frame_start is None and frame_end is None:
        return list(samples)
    start = 1 if frame_start is None else int(frame_start)
    end = max(sample["frame"] for sample in samples) if frame_end is None else int(frame_end)
    return [sample for sample in samples if start <= int(sample["frame"]) <= end]


def _ensure_view_layer_name(scene: bpy.types.Scene, target_name: str = "ViewLayer") -> None:
    if target_name in scene.view_layers:
        return
    if not scene.view_layers:
        raise ValueError(f"Scene {scene.name!r} does not contain any view layers")
    scene.view_layers[0].name = target_name


def _apply_scene_render_overrides(scene_name: str) -> None:
    overrides = get_scene_calibration(scene_name).render_overrides

    for object_name in overrides.hide_render_objects:
        obj = bpy.data.objects.get(object_name)
        if obj is None:
            continue
        obj.hide_render = True
        obj.hide_viewport = True

    if overrides.world_background_color is None:
        return

    scene = bpy.context.scene
    world = scene.world
    if world is None:
        return

    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = overrides.world_background_color
    background.inputs["Strength"].default_value = float(overrides.world_background_strength)
    links.new(background.outputs["Background"], output.inputs["Surface"])


def _resolve_image_source_path(image: bpy.types.Image) -> Path | None:
    filepath = image.filepath_raw or image.filepath
    if not filepath:
        return None
    resolved = bpy.path.abspath(filepath, library=image.library)
    if not resolved:
        return None
    return Path(resolved)


def _image_has_packed_data(image: bpy.types.Image) -> bool:
    if getattr(image, "packed_file", None) is not None:
        return True
    packed_files = getattr(image, "packed_files", None)
    return packed_files is not None and len(packed_files) > 0


def _get_missing_texture_placeholder() -> bpy.types.Image:
    image = bpy.data.images.get(MISSING_TEXTURE_PLACEHOLDER_NAME)
    if image is not None:
        return image

    image = bpy.data.images.new(
        name=MISSING_TEXTURE_PLACEHOLDER_NAME,
        width=1,
        height=1,
        alpha=True,
    )
    image.generated_color = MISSING_TEXTURE_PLACEHOLDER_RGBA
    image.use_fake_user = True
    return image


def _sanitize_missing_texture_images() -> list[dict[str, str]]:
    # Imported Neural RGB-D blend files often enable auto-pack while also
    # referencing author-local texture paths. Disable auto-pack first so
    # saving the imported trajectory does not fail on those missing files.
    bpy.data.use_autopack = False

    replacements = []
    placeholder = None
    for image in list(bpy.data.images):
        if image.name == MISSING_TEXTURE_PLACEHOLDER_NAME:
            continue
        if image.source != "FILE" or _image_has_packed_data(image):
            continue

        source_path = _resolve_image_source_path(image)
        if source_path is None or source_path.exists():
            continue

        image_name = image.name
        if image.users == 0:
            logger.warning("Removing unused missing image %s (%s)", image_name, source_path)
            bpy.data.images.remove(image)
            replacements.append({"image_name": image_name, "missing_path": str(source_path), "action": "removed"})
            continue

        if placeholder is None:
            placeholder = _get_missing_texture_placeholder()

        logger.warning(
            "Replacing missing image %s (%s) with generated placeholder %s",
            image_name,
            source_path,
            placeholder.name,
        )
        image.user_remap(placeholder)
        bpy.data.images.remove(image)
        replacements.append(
            {"image_name": image_name, "missing_path": str(source_path), "action": f"remapped_to:{placeholder.name}"}
        )

    if replacements:
        logger.warning("Applied missing-texture fallback to %d image datablock(s)", len(replacements))
    return replacements


def _save_mainfile_without_version_backups(filepath: Path) -> None:
    filepaths_prefs = bpy.context.preferences.filepaths
    original_save_version = int(filepaths_prefs.save_version)
    try:
        filepaths_prefs.save_version = 0
        bpy.ops.wm.save_mainfile(filepath=str(filepath))
    finally:
        filepaths_prefs.save_version = original_save_version


def run_trajectory_task(spec: SceneSpec, output_root: Path, args: argparse.Namespace) -> None:
    bpy.ops.wm.open_mainfile(filepath=str(spec.paths.scene_blend_path))
    scene = bpy.context.scene
    selected_frames = _frame_numbers_for_spec(spec, args)
    calibration = get_scene_calibration(spec.paths.scene_name) if spec.pose_format == "opengl" else None

    scene.render.fps = int(args.fps)
    scene.frame_start = 1
    scene.frame_end = len(selected_frames)
    _apply_scene_render_overrides(spec.paths.scene_name)
    _sanitize_missing_texture_images()

    rig, camera = _spawn_benchmark_camera(spec)

    samples = []
    source_pose_key = "camera_to_world_blender_source" if spec.pose_format == "blender" else "camera_to_world_opengl"
    for local_frame, source_frame in enumerate(selected_frames, start=1):
        image_index = frame_to_image_index(source_frame)
        pose_source = spec.poses_cv[image_index]
        pose_blender = source_pose_to_blender_pose(
            spec.paths.scene_name,
            pose_source,
            pose_format=spec.pose_format,
        )
        pose_cv = blender_pose_to_cv_camera(pose_blender)
        pose_matrix = Matrix(pose_blender.tolist())
        location, rotation, _scale = pose_matrix.decompose()

        rig.location = location
        rig.rotation_mode = "QUATERNION"
        rig.rotation_quaternion = rotation
        rig.keyframe_insert(data_path="location", frame=local_frame)
        rig.keyframe_insert(data_path="rotation_quaternion", frame=local_frame)

        samples.append(
            {
                "frame": local_frame,
                "source_frame": source_frame,
                "image_index": image_index,
                source_pose_key: pose_source.tolist(),
                "camera_to_world_cv": pose_cv.tolist(),
                "camera_to_world_blender": pose_blender.tolist(),
            }
        )

    _set_linear_keyframe_interpolation(rig)
    scene.frame_set(scene.frame_start)
    cam_placement.set_active_camera(camera)

    trajectory_blend_path, metadata_path = _trajectory_output_paths(output_root)
    trajectory_blend_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "planner": "neural_rgbd_import",
        "scene_name": spec.paths.scene_name,
        "scene_blend_path": str(spec.paths.scene_blend_path),
        "dataset_root": str(spec.paths.dataset_root),
        "pose_source": spec.paths.pose_path.name,
        "source_pose_path": str(spec.paths.pose_path),
        "scene_modified": True,
        "planner_fps": int(args.fps),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "source_total_frames": int(len(spec.poses_cv)),
        "selected_frame_count": int(len(samples)),
        "image_width": int(spec.image_width),
        "image_height": int(spec.image_height),
        "focal_px": float(spec.focal_px),
        "camera_name": CAMERA_NAME,
        "camera_rig_name": RIG_NAME,
        "pose_format": spec.pose_format,
        "scene_calibration": (
            {
                "description": calibration.description,
                "rotation": calibration.rotation.tolist(),
                "translation": calibration.translation.tolist(),
                "scale": float(calibration.scale),
                "hidden_objects": list(calibration.render_overrides.hide_render_objects),
                "world_background_color": calibration.render_overrides.world_background_color,
                "world_background_strength": float(calibration.render_overrides.world_background_strength),
            }
            if calibration is not None
            else None
        ),
        "coordinate_convention": {
            "source_camera_space": (
                "+X right, +Y up, forward -Z (Blender)"
                if spec.pose_format == "blender"
                else "+X right, +Y up, forward -Z (OpenGL / NeRF)"
            ),
            "blender_camera_space": "+X right, +Y up, forward -Z",
            "saved_camview_camera_space": "+X right, +Y down, +Z forward",
            "source_pose_interpretation": (
                "Blender pose archive matrices are consumed as Blender-style camera-to-world matrices"
                if spec.pose_format == "blender"
                else "Neural RGB-D pose files are consumed as OpenGL-style camera-to-world matrices"
            ),
            "world_mapping": (
                "None; blender pose archive is already expressed in Blender world coordinates"
                if spec.pose_format == "blender"
                else "Blender scene import first applies an OpenGL-world Y-up to Blender-world Z-up mapping"
            ),
            "scene_calibration_applied": (
                "None; blender pose archive bypasses benchmark-local scene calibration"
                if spec.pose_format == "blender"
                else calibration.description
            ),
            "conversion_applied": (
                "camera_to_world_blender = pose_source"
                if spec.pose_format == "blender"
                else "camera_to_world_blender = scene_calibration(scene_name, camera_to_world_opengl)"
            ),
            "camview_export_conversion": "camera_to_world_cv = camera_to_world_blender @ diag(1, -1, -1, 1)",
        },
        "samples": samples,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _save_mainfile_without_version_backups(trajectory_blend_path)
    logger.info("Wrote Neural RGB-D trajectory scene to %s", trajectory_blend_path)


def _get_benchmark_camera() -> bpy.types.Object:
    camera = bpy.data.objects.get(CAMERA_NAME)
    if camera is None or camera.type != "CAMERA":
        raise FileNotFoundError(
            f"Expected Neural RGB-D benchmark camera {CAMERA_NAME} in the currently loaded scene"
        )
    return camera


def run_render_task(spec: SceneSpec, output_root: Path, args: argparse.Namespace) -> None:
    trajectory_blend_path, metadata_path = _trajectory_output_paths(output_root)
    if not trajectory_blend_path.exists():
        raise FileNotFoundError(
            f"Neural RGB-D trajectory scene not found: {trajectory_blend_path}. Run --task trajectory first."
        )
    bpy.ops.wm.open_mainfile(filepath=str(trajectory_blend_path))
    _apply_scene_render_overrides(spec.paths.scene_name)
    _sanitize_missing_texture_images()

    metadata = _load_trajectory_metadata(metadata_path)
    samples = _samples_for_frame_range(metadata["samples"], args.frame_start, args.frame_end)
    if not samples:
        raise ValueError("Selected frame range produced no Neural RGB-D render samples")

    scene = bpy.context.scene
    scene.render.resolution_x = int(metadata["image_width"])
    scene.render.resolution_y = int(metadata["image_height"])
    _ensure_view_layer_name(scene)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    if args.render_engine != "KEEP":
        scene.render.engine = args.render_engine
    if scene.render.engine == "CYCLES":
        init.configure_cycles_devices()
        if args.render_samples is not None:
            scene.cycles.samples = int(args.render_samples)

    camera = _get_benchmark_camera()
    cam_placement.adjust_camera_sensor(camera)
    camera.data.sensor_height = CAMERA_SENSOR_HEIGHT_MM
    camera.data.sensor_width = CAMERA_SENSOR_HEIGHT_MM * metadata["image_width"] / metadata["image_height"]
    camera.data.lens = focal_px_to_lens_mm(
        focal_px=metadata["focal_px"],
        image_width=metadata["image_width"],
        sensor_width_mm=camera.data.sensor_width,
    )
    cam_placement.set_active_camera(camera)

    rgb_dir, camview_dir, comparison_dir = _render_output_paths(output_root)
    rgb_dir.mkdir(parents=True, exist_ok=True)
    camview_dir.mkdir(parents=True, exist_ok=True)

    for sample in samples:
        frame = int(sample["frame"])
        image_index = int(sample["image_index"])
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        render_target = rgb_dir / f"img{image_index}"
        scene.render.filepath = str(render_target)
        bpy.ops.render.render(write_still=True)
        cam_placement.save_camera_parameters(camera_obj=camera, output_folder=camview_dir, frame=frame)

    frame_reports = []
    for sample in samples:
        frame = int(sample["frame"])
        image_index = int(sample["image_index"])
        reference_path = spec.paths.images_dir / f"img{image_index}.png"
        rendered_path = rgb_dir / f"img{image_index}.png"
        frame_reports.append(
            compare_rgb_pair(
                frame=frame,
                image_index=image_index,
                reference_path=reference_path,
                rendered_path=rendered_path,
            )
        )

    summary = write_comparison_reports(comparison_dir, frame_reports)
    logger.info(
        "Rendered %d Neural RGB-D RGB frames to %s; mean MAE %.6f, mean PSNR %s",
        summary["frame_count"],
        rgb_dir,
        summary["mean_mae"],
        "inf" if np.isinf(summary["mean_psnr"]) else f"{summary['mean_psnr']:.6f}",
    )


def run_structured_light_task(spec: SceneSpec, output_root: Path, args: argparse.Namespace) -> None:
    trajectory_blend_path, metadata_path = _trajectory_output_paths(output_root)
    if not trajectory_blend_path.exists():
        raise FileNotFoundError(
            f"Neural RGB-D trajectory scene not found: {trajectory_blend_path}. Run --task trajectory first."
        )
    bpy.ops.wm.open_mainfile(filepath=str(trajectory_blend_path))
    _apply_scene_render_overrides(spec.paths.scene_name)
    _sanitize_missing_texture_images()

    metadata = _load_trajectory_metadata(metadata_path)
    samples = _samples_for_frame_range(metadata["samples"], args.frame_start, args.frame_end)
    if not samples:
        raise ValueError("Selected frame range produced no Neural RGB-D structured-light samples")

    scene = bpy.context.scene
    scene.frame_start = int(samples[0]["frame"])
    scene.frame_end = int(samples[-1]["frame"])
    _ensure_view_layer_name(scene)

    camera = _get_benchmark_camera()
    cam_placement.set_active_camera(camera)

    frame_index_offset = int(samples[0]["image_index"])

    sl_frames_dir = output_root / "sl_frames"
    sl_frames_dir.mkdir(parents=True, exist_ok=True)
    render_structured_light(
        frames_folder=sl_frames_dir,
        camera=camera,
        sl_resolution_x=int(metadata["image_width"]),
        sl_resolution_y=int(metadata["image_height"]),
        sl_pattern_resolution_x=int(metadata["image_width"]),
        sl_pattern_resolution_y=int(metadata["image_height"]),
        sl_frame_index_offset=frame_index_offset,
    )
    logger.info("Wrote Neural RGB-D structured-light outputs to %s", sl_frames_dir)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    available_scenes = discover_scene_names(args.dataset_root)
    if args.scene_name not in available_scenes:
        raise ValueError(
            f"Unknown Neural RGB-D scene {args.scene_name!r}. Available scenes: {available_scenes}"
        )

    output_root = args.output_root
    if output_root is None:
        output_root = default_output_root(
            repo_root=REPO_ROOT,
            scene_name=args.scene_name,
            pose_source=args.pose_source,
        )
    output_root = Path(output_root).absolute()
    output_root.mkdir(parents=True, exist_ok=True)

    _apply_gin_if_requested(args.configs, args.overrides)
    spec = load_scene_spec(
        dataset_root=args.dataset_root,
        scene_name=args.scene_name,
        pose_source=args.pose_source,
    )

    for task in args.task:
        logger.info("Running Neural RGB-D task %s for scene %s", task, args.scene_name)
        if task == "trajectory":
            run_trajectory_task(spec=spec, output_root=output_root, args=args)
        elif task == "render":
            run_render_task(spec=spec, output_root=output_root, args=args)
        elif task == "structured_light":
            run_structured_light_task(spec=spec, output_root=output_root, args=args)
        else:
            raise ValueError(f"Unsupported Neural RGB-D task {task!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
