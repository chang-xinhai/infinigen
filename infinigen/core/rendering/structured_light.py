# Structured Light rendering module for Infinigen.
#
# The capture layout is manifest-driven and writes:
#   capture_root/
#     output/
#       rgb/
#       IR_left/
#       IR_right/
#       calibration/
#     structured_light/
#       patterns/
#
# RGB is rendered inside the structured-light task using a white projector
# baseline state to avoid a second full scene render pass.

import copy
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

import bpy
import gin
import mathutils
import numpy as np
import yaml
from imageio.v2 import imwrite

from infinigen.core import init
from infinigen.core.rendering.post_render import (
    colorize_depth,
    colorize_normals,
    load_depth,
    load_normals,
)
from infinigen.core.rendering.render import (
    _configure_preview_cycles,
    _ensure_preview_lighting,
)

logger = logging.getLogger(__name__)

SL_ROOT_NAME = "_SL_Root_"
SL_LEFT_CAM_NAME = "_SL_LeftIR_"
SL_RIGHT_CAM_NAME = "_SL_RightIR_"
SL_RGB_CAM_NAME = "_SL_RGB_"
SL_PROJ_OBJ_NAME = "_SL_Projector_"
SL_PROJ_SPOT_NAME = "_SL_Projector_Spot_"

DEFAULT_CAPTURE_MANIFEST = {
    "setting": "full",
    "patterns": {
        "names": ["d415", "d435", "kinectsp"],
        "white": "white.png",
    },
    "cameras": {
        "rgb": {
            "outputs": {
                "image": ["png"],
                "depth": ["png", "exr"],
                "normal": ["png", "exr"],
            },
            "calibration": {
                "intrinsic": True,
                "extrinsic": True,
            },
        },
        "left": {
            "outputs": {
                "image": ["png"],
            },
            "calibration": {
                "intrinsic": True,
                "extrinsic": False,
            },
        },
        "right": {
            "outputs": {
                "image": ["png"],
            },
            "calibration": {
                "intrinsic": True,
                "extrinsic": False,
            },
        },
    },
    "calibration": {
        "save_npz": True,
        "save_jsonl": False,
    },
}


def _calibration_header_from_payload(calibration_payload):
    return {
        "type": "rig",
        "setting": calibration_payload["setting"],
        "baseline": calibration_payload["baseline"],
        "intrinsic": calibration_payload["intrinsic"],
        "rel_R": calibration_payload["rel_R"],
        "rel_T": calibration_payload["rel_T"],
        "patterns": calibration_payload["patterns"],
    }


def _frame_calibration_record(frame_id, extrinsic):
    return {
        "type": "frame",
        "frame": int(frame_id),
        "extrinsic": extrinsic,
    }


def _write_jsonl_atomic(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f"{path.stem}_", suffix=path.suffix, dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _rewrite_incremental_calibration(progress_path, header, frame_records):
    records = [header]
    for frame_id in sorted(frame_records):
        records.append(_frame_calibration_record(frame_id, frame_records[frame_id]))
    _write_jsonl_atomic(progress_path, records)


def _append_incremental_calibration_frame(progress_path, frame_id, extrinsic):
    progress_path = Path(progress_path)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_frame_calibration_record(frame_id, extrinsic)) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_incremental_calibration(progress_path):
    progress_path = Path(progress_path)
    if not progress_path.exists():
        return None, {}

    header = None
    frame_records = {}
    with progress_path.open("r", encoding="utf-8") as handle:
        for lineno, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "Ignoring malformed calibration progress line %s:%d",
                    progress_path,
                    lineno,
                )
                continue
            record_type = payload.get("type")
            if record_type == "rig":
                header = payload
            elif record_type == "frame":
                frame_id = payload.get("frame")
                extrinsic = payload.get("extrinsic")
                if frame_id is None or extrinsic is None:
                    logger.warning(
                        "Ignoring incomplete calibration frame record %s:%d",
                        progress_path,
                        lineno,
                    )
                    continue
                frame_records[int(frame_id)] = extrinsic
    return header, frame_records


def _calibration_headers_compatible(existing_header, expected_header):
    return existing_header == expected_header

def _deep_merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def _apply_manifest_override_sections(manifest, loaded):
    for camera_key, camera_cfg in loaded.get("cameras", {}).items():
        if not isinstance(camera_cfg, dict):
            continue
        manifest_camera_cfg = manifest.setdefault("cameras", {}).setdefault(camera_key, {})
        if "outputs" in camera_cfg:
            manifest_camera_cfg["outputs"] = copy.deepcopy(camera_cfg["outputs"])
        if "calibration" in camera_cfg:
            manifest_camera_cfg["calibration"] = copy.deepcopy(camera_cfg["calibration"])
    return manifest


def _load_capture_manifest(path):
    manifest = copy.deepcopy(DEFAULT_CAPTURE_MANIFEST)
    if path is None:
        return manifest

    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Capture manifest must be a mapping: {manifest_path}")
    manifest = _deep_merge(manifest, loaded)
    return _apply_manifest_override_sections(manifest, loaded)


def _normalize_formats(formats):
    if formats is None:
        return []
    if isinstance(formats, str):
        formats = [formats]
    normalized = []
    for fmt in formats:
        fmt_norm = str(fmt).strip().lower()
        if fmt_norm not in {"png", "exr"}:
            raise ValueError(f"Unsupported output format: {fmt}")
        if fmt_norm not in normalized:
            normalized.append(fmt_norm)
    return normalized


def _camera_manifest(manifest, camera_key):
    return manifest.get("cameras", {}).get(camera_key, {})


def _camera_outputs(manifest, camera_key, modality):
    camera_cfg = _camera_manifest(manifest, camera_key)
    return _normalize_formats(camera_cfg.get("outputs", {}).get(modality))


def _camera_requires_render(manifest, camera_key, modality):
    return bool(_camera_outputs(manifest, camera_key, modality))


def _camera_wants_extrinsic(manifest, camera_key):
    camera_cfg = _camera_manifest(manifest, camera_key)
    return bool(camera_cfg.get("calibration", {}).get("extrinsic", False))


def _resolve_manifest_pattern_config(manifest, sl_pattern_names, sl_pattern_white):
    manifest_patterns = manifest.get("patterns", {})
    if "names" in manifest_patterns:
        sl_pattern_names = manifest_patterns["names"]
    if "white" in manifest_patterns and manifest_patterns["white"] is not None:
        sl_pattern_white = manifest_patterns["white"]
    return sl_pattern_names, sl_pattern_white


@gin.configurable
class StructuredLightRig:
    """Create and manage a structured-light camera rig inside an existing Infinigen scene."""

    def __init__(
        self,
        baseline=0.065,
        cam_fov_deg=69.4,
        cam_sensor_width=6.328,
        cam_sensor_height=4.746,
        rgb_offset_scale=-0.55,
        proj_fov_delta_deg=5.0,
        proj_dlp_size=6.328,
        proj_energy=30.0,
        resolution_x=1280,
        resolution_y=720,
        pattern_resolution_x=1280,
        pattern_resolution_y=720,
    ):
        self.baseline = baseline
        self.cam_fov_deg = cam_fov_deg
        self.cam_sensor_width = cam_sensor_width
        self.cam_sensor_height = cam_sensor_height
        self.rgb_offset_scale = rgb_offset_scale
        self.proj_fov_delta_deg = proj_fov_delta_deg
        self.proj_dlp_size = proj_dlp_size
        self.proj_energy = proj_energy
        self.resolution_x = resolution_x
        self.resolution_y = resolution_y
        self.pattern_resolution_x = pattern_resolution_x
        self.pattern_resolution_y = pattern_resolution_y

        self.root = None
        self.left_cam = None
        self.right_cam = None
        self.rgb_cam = None
        self.proj_obj = None
        self.proj_spot = None

    @property
    def cam_fov_rad(self):
        return np.deg2rad(self.cam_fov_deg)

    @property
    def proj_fov_rad(self):
        return np.deg2rad(self.cam_fov_deg + self.proj_fov_delta_deg)

    def build(self):
        bpy.ops.object.empty_add(type="PLAIN_AXES")
        self.root = bpy.context.active_object
        self.root.name = SL_ROOT_NAME

        self.left_cam = self._make_camera(SL_LEFT_CAM_NAME)
        self.left_cam.location = mathutils.Vector((-self.baseline / 2, 0, 0))

        self.right_cam = self._make_camera(SL_RIGHT_CAM_NAME)
        self.right_cam.location = mathutils.Vector((self.baseline / 2, 0, 0))

        self.rgb_cam = self._make_camera(SL_RGB_CAM_NAME)
        self.rgb_cam.location = mathutils.Vector(
            (self.baseline * self.rgb_offset_scale, 0, 0)
        )

        self._make_projector()

        for child in [self.left_cam, self.right_cam, self.rgb_cam, self.proj_obj]:
            child.parent = self.root
            child.matrix_parent_inverse = self.root.matrix_world.inverted()

        logger.info("Structured-light rig built successfully")

    def _make_camera(self, name: str) -> bpy.types.Object:
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object
        cam.name = name
        cam.data.clip_end = 1e4
        cam.data.sensor_fit = "HORIZONTAL"
        cam.data.sensor_width = self.cam_sensor_width
        cam.data.sensor_height = (
            self.cam_sensor_width * self.resolution_y / self.resolution_x
        )
        cam.data.angle = self.cam_fov_rad
        return cam

    def _make_projector(self):
        addon_available = self._try_enable_projector_addon()
        if addon_available:
            self._make_projector_with_addon()
        else:
            self._make_projector_manual()

    def _try_enable_projector_addon(self) -> bool:
        candidates = [
            "Projectors-main",
            "projectors-main",
            "projectors_main",
            "Projectors",
            "projectors",
        ]
        for name in candidates:
            try:
                bpy.ops.preferences.addon_enable(module=name)
                if name in bpy.context.preferences.addons.keys():
                    logger.info("Projector addon enabled: %s", name)
                    return True
            except (RuntimeError, Exception):
                continue
        logger.warning(
            "Projectors addon not found; using manual spot light projector. "
            "For best results, install https://github.com/Ocupe/Projectors"
        )
        return False

    def _make_projector_with_addon(self):
        bpy.ops.projector.create()
        self.proj_obj = self._find_new_obj("Projector", "CAMERA")
        self.proj_spot = self._find_new_obj("Projector.Spot", "LIGHT")

        self.proj_obj.proj_settings.projected_texture = "custom_texture"
        scale_x, scale_y = self._compute_proj_scales()
        mapping_node = (
            self.proj_spot.data.node_tree.nodes["Group"]
            .node_tree.nodes["Mapping.001"]
        )
        mapping_node.inputs[3].default_value[0] = scale_x
        mapping_node.inputs[3].default_value[1] = scale_y

        self.proj_spot.data.energy = self.proj_energy
        self.proj_obj.name = SL_PROJ_OBJ_NAME
        self.proj_spot.name = SL_PROJ_SPOT_NAME
        self._projector_uses_addon = True

    def _make_projector_manual(self):
        bpy.ops.object.light_add(type="SPOT")
        spot = bpy.context.active_object
        spot.name = SL_PROJ_SPOT_NAME
        spot_data = spot.data
        spot_data.energy = self.proj_energy
        spot_data.spot_size = self.proj_fov_rad
        spot_data.spot_blend = 0.0
        spot_data.shadow_soft_size = 0.0

        spot_data.use_nodes = True
        tree = spot_data.node_tree
        nodes = tree.nodes
        links = tree.links

        emission_node = None
        for node in list(nodes):
            if node.type == "EMISSION":
                emission_node = node
            elif node.type != "OUTPUT_LIGHT":
                nodes.remove(node)

        img_tex = nodes.new(type="ShaderNodeTexImage")
        img_tex.name = "Image Texture"
        img_tex.extension = "CLIP"

        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.name = "Mapping"
        scale_x, scale_y = self._compute_proj_scales()
        mapping.inputs["Scale"].default_value[0] = scale_x
        mapping.inputs["Scale"].default_value[1] = scale_y

        links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], img_tex.inputs["Vector"])
        if emission_node:
            links.new(img_tex.outputs["Color"], emission_node.inputs["Color"])

        bpy.ops.object.empty_add(type="SINGLE_ARROW")
        proj_empty = bpy.context.active_object
        proj_empty.name = SL_PROJ_OBJ_NAME

        self.proj_obj = proj_empty
        self.proj_spot = spot
        self._projector_uses_addon = False

    def _compute_proj_scales(self):
        ratio_w = self.cam_sensor_width
        ratio_h = self.cam_sensor_height
        scale = np.sqrt(self.proj_dlp_size**2 / (ratio_w**2 + ratio_h**2))
        sensor_w = ratio_w * scale
        sensor_h = ratio_h * scale
        lens_dist = sensor_w / (2 * np.tan(self.proj_fov_rad / 2))
        scale_x = sensor_w / lens_dist
        scale_y = scale_x / sensor_w * sensor_h
        return scale_x, scale_y

    @staticmethod
    def _find_new_obj(prefix: str, obj_type: str) -> bpy.types.Object:
        for obj in bpy.data.objects:
            if obj.name.startswith(prefix) and obj.type == obj_type:
                return obj
        raise RuntimeError(f"Cannot find Blender object {prefix} ({obj_type})")

    def set_pose(self, location, rotation_matrix):
        self.root.matrix_world = mathutils.Matrix.Translation(location) @ rotation_matrix.to_4x4()

    def set_pattern(self, pattern_path: str):
        pattern_path = Path(pattern_path)
        img = bpy.data.images.get(pattern_path.name)
        if img is None:
            img = bpy.data.images.load(filepath=str(pattern_path))
        img_tex_node = self.proj_spot.data.node_tree.nodes["Image Texture"]
        img_tex_node.image = img

    def set_projector_visible(self, on=True):
        self.proj_spot.hide_render = not on

    @staticmethod
    def set_scene_lights(on=True):
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and obj.name != SL_PROJ_SPOT_NAME:
                obj.hide_render = not on

    @staticmethod
    def set_env_strength(strength):
        world = bpy.data.worlds.get("World")
        if world is None:
            return 0
        bg = world.node_tree.nodes.get("Background")
        if bg is None:
            return 0
        orig = bg.inputs[1].default_value
        bg.inputs[1].default_value = strength
        return orig

    def get_camera_intrinsic(self):
        return self._intrinsic_from_cam(self.left_cam.data)

    def get_rgb_intrinsic(self):
        return self._intrinsic_from_cam(self.rgb_cam.data)

    def _intrinsic_from_cam(self, camd):
        f_mm = camd.lens
        scene = bpy.data.scenes["Scene"]
        width = scene.render.resolution_x
        height = scene.render.resolution_y
        sensor_width = camd.sensor_width
        fx = f_mm * width / sensor_width
        fy = f_mm * height / (sensor_width * height / width)
        cx = width / 2.0
        cy = height / 2.0
        return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)

    def get_projector_intrinsic(self):
        if getattr(self, "_projector_uses_addon", False):
            mapping_node = (
                self.proj_spot.data.node_tree.nodes["Group"]
                .node_tree.nodes["Mapping.001"]
            )
            scale_x = mapping_node.inputs[3].default_value[0]
            scale_y = mapping_node.inputs[3].default_value[1]
        else:
            scale_x, scale_y = self._compute_proj_scales()

        width = self.pattern_resolution_x
        height = self.pattern_resolution_y
        return np.array(
            [
                [width / scale_x, 0, 0.5 * width],
                [0, height / scale_y, 0.5 * height],
                [0, 0, 1],
            ],
            dtype=np.float64,
        )

    def get_camera_extrinsic(self, cam_obj):
        return np.asarray(cam_obj.matrix_world, dtype=np.float64) @ np.diag(
            (1.0, -1.0, -1.0, 1.0)
        )

    def get_rel_translation(self, camera_name: str):
        name = camera_name.upper()
        if name == "L":
            x = -self.baseline / 2
        elif name == "R":
            x = self.baseline / 2
        elif name == "RGB":
            x = self.baseline * self.rgb_offset_scale
        else:
            raise ValueError(f"Unsupported rig camera {camera_name!r}")
        return np.array([x, 0, 0], dtype=np.float64)

    def build_calibration_dict(self, frame_ids, extrinsics, patterns, manifest_setting):
        return {
            "setting": manifest_setting,
            "baseline": self.baseline,
            "intrinsic": {
                "L": self.get_camera_intrinsic().tolist(),
                "R": self.get_camera_intrinsic().tolist(),
                "RGB": self.get_rgb_intrinsic().tolist(),
                "Proj": self.get_projector_intrinsic().tolist(),
            },
            "rel_R": {
                "L": np.eye(3).tolist(),
                "R": np.eye(3).tolist(),
                "RGB": np.eye(3).tolist(),
            },
            "rel_T": {
                "L": self.get_rel_translation("L").tolist(),
                "R": self.get_rel_translation("R").tolist(),
                "RGB": self.get_rel_translation("RGB").tolist(),
            },
            "frame_ids": frame_ids,
            "extrinsic": extrinsics,
            "patterns": patterns,
        }


def _resolve_pattern_specs(sl_pattern_dir, sl_pattern_white, sl_pattern_names):
    if sl_pattern_dir is None:
        candidate = Path(__file__).resolve().parents[3] / "data" / "patterns"
        if candidate.is_dir():
            sl_pattern_dir = str(candidate)
            logger.info("Auto-detected built-in pattern directory: %s", sl_pattern_dir)
        else:
            logger.warning(
                "Built-in pattern directory not found at %s; "
                "set render_structured_light.sl_pattern_dir to override. "
                "Only RGB baseline capture will be produced",
                candidate,
            )

    white_pattern_path = None
    if sl_pattern_dir is None:
        return None, white_pattern_path, []

    pattern_dir = Path(sl_pattern_dir).expanduser()
    white_candidate = pattern_dir / sl_pattern_white
    if white_candidate.exists():
        white_pattern_path = white_candidate

    available_files = {}
    for candidate in sorted(pattern_dir.iterdir()):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        available_files[candidate.stem.lower()] = candidate

    pattern_specs = []
    names = [str(name).strip() for name in (sl_pattern_names or []) if str(name).strip()]
    for pattern_name in names:
        candidate = available_files.get(pattern_name.lower())
        if candidate is None:
            raise FileNotFoundError(
                f"Structured-light pattern '{pattern_name}' not found under {pattern_dir}"
            )
        pattern_specs.append(
            {
                "name": pattern_name,
                "path": candidate,
            }
        )

    return pattern_dir, white_pattern_path, pattern_specs


def _resolve_pattern_paths(sl_pattern_dir, sl_pattern_white, sl_pattern_names):
    pattern_dir, white_pattern_path, pattern_specs = _resolve_pattern_specs(
        sl_pattern_dir=sl_pattern_dir,
        sl_pattern_white=sl_pattern_white,
        sl_pattern_names=sl_pattern_names,
    )
    return pattern_dir, white_pattern_path, [spec["path"] for spec in pattern_specs]


def _build_rgb_render_plan(output_root, manifest):
    rgb_root = output_root / "rgb"
    return {
        "image_png": (
            rgb_root / "image" / "frame_{frame_tag}.png"
            if "png" in _camera_outputs(manifest, "rgb", "image")
            else None
        ),
        "image_exr": (
            rgb_root / "image" / "frame_{frame_tag}.exr"
            if "exr" in _camera_outputs(manifest, "rgb", "image")
            else None
        ),
        "depth_png": (
            rgb_root / "depth" / "frame_{frame_tag}.png"
            if "png" in _camera_outputs(manifest, "rgb", "depth")
            else None
        ),
        "depth_exr": (
            rgb_root / "depth" / "frame_{frame_tag}.exr"
            if "exr" in _camera_outputs(manifest, "rgb", "depth")
            else None
        ),
        "normal_png": (
            rgb_root / "normal" / "frame_{frame_tag}.png"
            if "png" in _camera_outputs(manifest, "rgb", "normal")
            else None
        ),
        "normal_exr": (
            rgb_root / "normal" / "frame_{frame_tag}.exr"
            if "exr" in _camera_outputs(manifest, "rgb", "normal")
            else None
        ),
    }


def _camera_output_dir_name(camera_key):
    if camera_key == "left":
        return "IR_left"
    if camera_key == "right":
        return "IR_right"
    return camera_key


def _build_pattern_render_plan(output_root, camera_key, pattern_name, manifest):
    image_formats = _camera_outputs(manifest, camera_key, "image")
    cam_root = output_root / _camera_output_dir_name(camera_key)
    return {
        "image_png": (
            cam_root / "image" / pattern_name / "frame_{frame_tag}.png"
            if "png" in image_formats
            else None
        ),
        "image_exr": (
            cam_root / "image" / pattern_name / "frame_{frame_tag}.exr"
            if "exr" in image_formats
            else None
        ),
        "depth_png": None,
        "depth_exr": None,
        "normal_png": None,
        "normal_exr": None,
    }


def _iter_frame_output_targets(output_root, manifest, pattern_specs, frame_tag):
    rgb_plan = _build_rgb_render_plan(output_root, manifest)
    for target in rgb_plan.values():
        resolved = _resolve_target_path(target, frame_tag)
        if resolved is not None:
            yield resolved

    for pattern_spec in pattern_specs:
        pattern_name = pattern_spec["name"]
        for camera_key in ("left", "right"):
            plan = _build_pattern_render_plan(
                output_root=output_root,
                camera_key=camera_key,
                pattern_name=pattern_name,
                manifest=manifest,
            )
            for target in plan.values():
                resolved = _resolve_target_path(target, frame_tag)
                if resolved is not None:
                    yield resolved


def _frame_outputs_complete(output_root, manifest, pattern_specs, frame_tag):
    expected_paths = list(
        _iter_frame_output_targets(
            output_root=output_root,
            manifest=manifest,
            pattern_specs=pattern_specs,
            frame_tag=frame_tag,
        )
    )
    if not expected_paths:
        return True
    return all(path.exists() for path in expected_paths)


def _record_requested_extrinsics(rig, manifest):
    extrinsic = {}
    if _camera_wants_extrinsic(manifest, "left"):
        extrinsic["L"] = rig.get_camera_extrinsic(rig.left_cam).tolist()
    if _camera_wants_extrinsic(manifest, "right"):
        extrinsic["R"] = rig.get_camera_extrinsic(rig.right_cam).tolist()
    if _camera_wants_extrinsic(manifest, "rgb"):
        extrinsic["RGB"] = rig.get_camera_extrinsic(rig.rgb_cam).tolist()
    return extrinsic


def _capture_cycles_state(scene):
    cycles = scene.cycles
    return {
        "use_denoising": cycles.use_denoising,
        "caustics_reflective": cycles.caustics_reflective,
        "caustics_refractive": cycles.caustics_refractive,
        "sample_clamp_indirect": cycles.sample_clamp_indirect,
        "sample_clamp_direct": cycles.sample_clamp_direct,
    }


def _restore_cycles_state(scene, state):
    cycles = scene.cycles
    cycles.use_denoising = state["use_denoising"]
    cycles.caustics_reflective = state["caustics_reflective"]
    cycles.caustics_refractive = state["caustics_refractive"]
    cycles.sample_clamp_indirect = state["sample_clamp_indirect"]
    cycles.sample_clamp_direct = state["sample_clamp_direct"]


def _resolve_target_path(template_path, frame_tag):
    if template_path is None:
        return None
    return Path(str(template_path).format(frame_tag=frame_tag))


def _save_calibration(calibration_dir, calibration_payload, save_npz, save_jsonl):
    calibration_dir.mkdir(parents=True, exist_ok=True)
    if save_npz:
        np.savez(calibration_dir / "calibration.npz", calibration_payload)

    if save_jsonl:
        with (calibration_dir / "calibration.jsonl").open("w", encoding="utf-8") as handle:
            header = _calibration_header_from_payload(calibration_payload)
            handle.write(json.dumps(header) + "\n")
            for frame_id, extrinsic in zip(
                calibration_payload["frame_ids"], calibration_payload["extrinsic"]
            ):
                handle.write(
                    json.dumps(_frame_calibration_record(frame_id, extrinsic)) + "\n"
                )


@gin.configurable
def render_structured_light(
    frames_folder: Path,
    camera: bpy.types.Object,
    sl_baseline=0.065,
    sl_cam_fov_deg=69.4,
    sl_cam_sensor_width=6.328,
    sl_cam_sensor_height=4.746,
    sl_rgb_offset_scale=-0.55,
    sl_proj_fov_delta_deg=5.0,
    sl_proj_dlp_size=6.328,
    sl_proj_energy=30.0,
    sl_resolution_x=1280,
    sl_resolution_y=720,
    sl_pattern_resolution_x=1280,
    sl_pattern_resolution_y=720,
    sl_pattern_dir=None,
    sl_pattern_white="white.png",
    sl_pattern_names=None,
    sl_capture_manifest_path=None,
    sl_max_samples=64,
    sl_exr_depth=16,
    sl_preview_force_lighting=True,
    sl_preview_world_strength=0.25,
    sl_preview_sun_energy=1.0,
    sl_preview_sun_rotation_deg=(55.0, 0.0, 35.0),
    sl_preview_camera_light_energy=120.0,
    sl_preview_camera_light_offset_m=(0.0, 0.0, 0.15),
    sl_preview_force_denoising=True,
    sl_preview_disable_caustics=True,
    sl_preview_sample_clamp_indirect=0.75,
    sl_preview_sample_clamp_direct=2.5,
    sl_resume=False,
    sl_resume_from_frame=None,
    sl_frame_index_offset=0,
):
    tic = time.time()

    capture_root = Path(frames_folder)
    output_root = capture_root / "output"
    metadata_root = capture_root / "structured_light"
    pattern_output = metadata_root / "patterns"
    calibration_dir = output_root / "calibration"
    calibration_progress_path = calibration_dir / "calibration.jsonl"
    output_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)

    manifest = _load_capture_manifest(sl_capture_manifest_path)
    sl_pattern_names, sl_pattern_white = _resolve_manifest_pattern_config(
        manifest=manifest,
        sl_pattern_names=sl_pattern_names,
        sl_pattern_white=sl_pattern_white,
    )

    pattern_dir, white_pattern_path, pattern_specs = _resolve_pattern_specs(
        sl_pattern_dir=sl_pattern_dir,
        sl_pattern_white=sl_pattern_white,
        sl_pattern_names=sl_pattern_names,
    )

    init.configure_cycles_devices()

    rig = StructuredLightRig(
        baseline=sl_baseline,
        cam_fov_deg=sl_cam_fov_deg,
        cam_sensor_width=sl_cam_sensor_width,
        cam_sensor_height=sl_cam_sensor_height,
        rgb_offset_scale=sl_rgb_offset_scale,
        proj_fov_delta_deg=sl_proj_fov_delta_deg,
        proj_dlp_size=sl_proj_dlp_size,
        proj_energy=sl_proj_energy,
        resolution_x=sl_resolution_x,
        resolution_y=sl_resolution_y,
        pattern_resolution_x=sl_pattern_resolution_x,
        pattern_resolution_y=sl_pattern_resolution_y,
    )
    rig.build()

    scene = bpy.data.scenes["Scene"]
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = sl_max_samples
    scene.render.use_persistent_data = True
    scene.render.resolution_x = sl_resolution_x
    scene.render.resolution_y = sl_resolution_y

    orig_env_strength = rig.set_env_strength(0)
    rig.set_env_strength(orig_env_strength)
    base_cycles_state = _capture_cycles_state(scene)
    _ensure_preview_lighting(
        rig.rgb_cam,
        preview_force_lighting=sl_preview_force_lighting,
        preview_world_strength=sl_preview_world_strength,
        preview_sun_energy=sl_preview_sun_energy,
        preview_sun_rotation_deg=tuple(sl_preview_sun_rotation_deg),
        preview_camera_light_energy=sl_preview_camera_light_energy,
        preview_camera_light_offset_m=tuple(sl_preview_camera_light_offset_m),
    )

    frame_start = scene.frame_start
    frame_end = scene.frame_end
    cam_rig = camera.parent

    rgb_plan = _build_rgb_render_plan(output_root, manifest)
    want_rgb = any(rgb_plan.values())
    want_pattern_images = any(
        _camera_requires_render(manifest, camera_key, "image")
        for camera_key in ("left", "right")
    )
    if want_pattern_images and not pattern_specs:
        logger.warning(
            "Capture manifest requested IR pattern renders but no pattern files were resolved"
        )

    pattern_output.mkdir(parents=True, exist_ok=True)
    if white_pattern_path is not None:
        shutil.copy2(white_pattern_path, pattern_output / Path(sl_pattern_white).name)
    if pattern_dir is not None:
        for pattern_spec in pattern_specs:
            dst_name = f"{pattern_spec['name']}{pattern_spec['path'].suffix.lower()}"
            shutil.copy2(pattern_spec["path"], pattern_output / dst_name)

    expected_calibration_payload = rig.build_calibration_dict(
        frame_ids=[],
        extrinsics=[],
        patterns=[spec["name"] for spec in pattern_specs],
        manifest_setting=str(manifest.get("setting", "full")),
    )
    expected_header = _calibration_header_from_payload(expected_calibration_payload)

    existing_header = None
    existing_frame_records = {}
    if sl_resume:
        existing_header, existing_frame_records = _load_incremental_calibration(
            calibration_progress_path
        )
        if existing_header is not None and not _calibration_headers_compatible(
            existing_header, expected_header
        ):
            raise ValueError(
                f"Incompatible calibration progress file at {calibration_progress_path}"
            )

    frame_records = dict(existing_frame_records) if sl_resume else {}
    _rewrite_incremental_calibration(
        calibration_progress_path,
        expected_header,
        frame_records,
    )

    for local_frame_idx, scene_frame_idx in enumerate(range(frame_start, frame_end + 1)):
        capture_frame_idx = int(sl_frame_index_offset) + local_frame_idx
        frame_tag = f"{capture_frame_idx:04d}"
        scene.frame_set(scene_frame_idx)
        bpy.context.view_layer.update()

        if cam_rig is not None:
            rig.set_pose(
                cam_rig.matrix_world.translation.copy(),
                cam_rig.matrix_world.to_3x3(),
            )
        else:
            rig.set_pose(
                camera.matrix_world.translation.copy(),
                camera.matrix_world.to_3x3(),
            )

        frame_extrinsic = _record_requested_extrinsics(rig, manifest)
        frame_complete = _frame_outputs_complete(
            output_root=output_root,
            manifest=manifest,
            pattern_specs=pattern_specs,
            frame_tag=frame_tag,
        )
        has_calibration = capture_frame_idx in frame_records
        should_skip_for_resume = False
        if sl_resume:
            if sl_resume_from_frame is not None and capture_frame_idx < int(
                sl_resume_from_frame
            ):
                should_skip_for_resume = True
            elif frame_complete:
                should_skip_for_resume = True

        if should_skip_for_resume:
            if frame_complete and not has_calibration:
                frame_records[capture_frame_idx] = frame_extrinsic
                _append_incremental_calibration_frame(
                    calibration_progress_path,
                    capture_frame_idx,
                    frame_extrinsic,
                )
            continue

        if want_rgb:
            _configure_preview_cycles(
                preview_force_denoising=sl_preview_force_denoising,
                preview_disable_caustics=sl_preview_disable_caustics,
                preview_sample_clamp_indirect=sl_preview_sample_clamp_indirect,
                preview_sample_clamp_direct=sl_preview_sample_clamp_direct,
            )
            if white_pattern_path is not None:
                rig.set_pattern(str(white_pattern_path))
                rig.set_projector_visible(True)
            else:
                rig.set_projector_visible(False)
            rig.set_scene_lights(True)
            rig.set_env_strength(orig_env_strength)
            _render_single(
                scene=scene,
                camera_obj=rig.rgb_cam,
                frame_tag=frame_tag,
                path_plan=rgb_plan,
                exr_depth=sl_exr_depth,
            )

        if want_pattern_images and pattern_specs:
            _restore_cycles_state(scene, base_cycles_state)
            rig.set_projector_visible(True)
            rig.set_scene_lights(False)
            rig.set_env_strength(0)
            for pattern_spec in pattern_specs:
                pattern_name = pattern_spec["name"]
                rig.set_pattern(str(pattern_spec["path"]))
                for camera_key, cam_obj in (
                    ("left", rig.left_cam),
                    ("right", rig.right_cam),
                ):
                    plan = _build_pattern_render_plan(
                        output_root=output_root,
                        camera_key=camera_key,
                        pattern_name=pattern_name,
                        manifest=manifest,
                    )
                    if any(plan.values()):
                        _render_single(
                            scene=scene,
                            camera_obj=cam_obj,
                            frame_tag=frame_tag,
                            path_plan=plan,
                            exr_depth=sl_exr_depth,
                        )

        rig.set_scene_lights(True)
        rig.set_env_strength(orig_env_strength)
        frame_records[capture_frame_idx] = frame_extrinsic
        _append_incremental_calibration_frame(
            calibration_progress_path,
            capture_frame_idx,
            frame_extrinsic,
        )

    frame_ids = sorted(frame_records)
    extrinsics = [frame_records[frame_id] for frame_id in frame_ids]
    calibration_payload = rig.build_calibration_dict(
        frame_ids=frame_ids,
        extrinsics=extrinsics,
        patterns=[spec["name"] for spec in pattern_specs],
        manifest_setting=str(manifest.get("setting", "full")),
    )
    calibration_cfg = manifest.get("calibration", {})
    _save_calibration(
        calibration_dir=calibration_dir,
        calibration_payload=calibration_payload,
        save_npz=bool(calibration_cfg.get("save_npz", True)),
        save_jsonl=True,
    )

    logger.info("Structured light rendering complete in %.1fs", time.time() - tic)
    logger.info("Capture output: %s", capture_root)


def _render_single(
    scene,
    camera_obj,
    frame_tag,
    path_plan,
    exr_depth=16,
):
    scene.camera = camera_obj
    scene.use_nodes = True
    tree = scene.node_tree
    for node in list(tree.nodes):
        if node.name.startswith("SL_"):
            tree.nodes.remove(node)

    render_layers = None
    for node in tree.nodes:
        if node.type == "R_LAYERS":
            render_layers = node
            break
    if render_layers is None:
        render_layers = tree.nodes.new(type="CompositorNodeRLayers")

    need_depth = bool(path_plan["depth_png"] or path_plan["depth_exr"])
    need_normal = bool(path_plan["normal_png"] or path_plan["normal_exr"])
    need_image_png = bool(path_plan["image_png"])
    need_image_exr = bool(path_plan["image_exr"])

    view_layer = scene.view_layers["ViewLayer"]
    view_layer.use_pass_z = need_depth
    view_layer.use_pass_normal = need_normal

    composite = None
    for node in tree.nodes:
        if node.type == "COMPOSITE":
            composite = node
            break
    if composite is None:
        composite = tree.nodes.new(type="CompositorNodeComposite")
    for link in list(composite.inputs["Image"].links):
        tree.links.remove(link)
    tree.links.new(render_layers.outputs["Image"], composite.inputs["Image"])

    temp_dir = Path(tempfile.mkdtemp(prefix="sl_render_", dir=str(Path.cwd())))
    try:
        exr_out = None
        png_out = None
        if need_depth or need_normal or need_image_exr:
            exr_out = tree.nodes.new(type="CompositorNodeOutputFile")
            exr_out.name = "SL_ExrOutput"
            exr_out.format.file_format = "OPEN_EXR"
            exr_out.format.color_mode = "RGB"
            exr_out.format.color_depth = str(exr_depth)
            exr_out.base_path = str(temp_dir)
            exr_out.file_slots.clear()

            if need_depth:
                exr_out.file_slots.new("depth_")
                tree.links.new(render_layers.outputs["Depth"], exr_out.inputs["depth_"])
            if need_normal:
                exr_out.file_slots.new("normal_")
                tree.links.new(render_layers.outputs["Normal"], exr_out.inputs["normal_"])
            if need_image_exr:
                exr_out.file_slots.new("image_exr_")
                tree.links.new(render_layers.outputs["Image"], exr_out.inputs["image_exr_"])

        if need_image_png:
            png_out = tree.nodes.new(type="CompositorNodeOutputFile")
            png_out.name = "SL_PngOutput"
            png_out.format.file_format = "PNG"
            png_out.format.color_mode = "RGB"
            png_out.base_path = str(temp_dir)
            png_out.file_slots.clear()
            png_out.file_slots.new("image_png_")
            tree.links.new(render_layers.outputs["Image"], png_out.inputs["image_png_"])

        bpy.ops.render.render(write_still=False)

        depth_exr_path = _pick_output_file(temp_dir, "depth_", ".exr") if need_depth else None
        normal_exr_path = _pick_output_file(temp_dir, "normal_", ".exr") if need_normal else None
        image_exr_path = _pick_output_file(temp_dir, "image_exr_", ".exr") if need_image_exr else None
        image_png_path = _pick_output_file(temp_dir, "image_png_", ".png") if need_image_png else None

        image_exr_target = _resolve_target_path(path_plan["image_exr"], frame_tag)
        image_png_target = _resolve_target_path(path_plan["image_png"], frame_tag)
        depth_exr_target = _resolve_target_path(path_plan["depth_exr"], frame_tag)
        depth_png_target = _resolve_target_path(path_plan["depth_png"], frame_tag)
        normal_exr_target = _resolve_target_path(path_plan["normal_exr"], frame_tag)
        normal_png_target = _resolve_target_path(path_plan["normal_png"], frame_tag)

        if image_exr_target:
            _move_render_output(image_exr_path, image_exr_target)
        if image_png_target:
            _move_render_output(image_png_path, image_png_target)

        if need_depth:
            if depth_exr_target:
                _move_render_output(depth_exr_path, depth_exr_target)
            depth_source = depth_exr_target or depth_exr_path
            if depth_png_target:
                _ensure_parent(depth_png_target)
                imwrite(depth_png_target, colorize_depth(load_depth(depth_source)))
            if depth_exr_target is None and depth_exr_path is not None and depth_exr_path.exists():
                depth_exr_path.unlink()

        if need_normal:
            if normal_exr_target:
                _move_render_output(normal_exr_path, normal_exr_target)
            normal_source = normal_exr_target or normal_exr_path
            if normal_png_target:
                _ensure_parent(normal_png_target)
                imwrite(
                    normal_png_target,
                    colorize_normals(load_normals(normal_source, camera_obj)),
                )
            if normal_exr_target is None and normal_exr_path is not None and normal_exr_path.exists():
                normal_exr_path.unlink()
    finally:
        for node in list(tree.nodes):
            if node.name.startswith("SL_"):
                tree.nodes.remove(node)
        shutil.rmtree(temp_dir, ignore_errors=True)


def _pick_output_file(temp_dir, prefix, suffix):
    matches = sorted(temp_dir.glob(f"{prefix}*{suffix}"))
    if not matches:
        raise FileNotFoundError(f"Missing render output for {prefix} under {temp_dir}")
    return matches[-1]


def _ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def _move_render_output(src, dst):
    _ensure_parent(dst)
    shutil.move(str(src), str(dst))
