# Copyright (C) 2026.

import bpy
import numpy as np

import infinigen
from infinigen.core.rendering.structured_light import (
    StructuredLightRig,
    _append_incremental_calibration_frame,
    _calibration_header_from_payload,
    _configure_rgb_capture_lighting,
    _configure_pattern_capture_lighting,
    _frame_outputs_complete,
    _load_capture_manifest,
    _load_incremental_calibration,
    _resolve_shared_baseline_env_strength,
    _resolve_manifest_pattern_config,
    _rewrite_incremental_calibration,
    _restore_pattern_capture_lighting,
    _resolve_pattern_paths,
)


def test_structured_light_rig_offsets_rgb_left_of_left_ir():
    baseline = 0.055
    rgb_offset_scale = -0.55
    rig = StructuredLightRig(
        baseline=baseline,
        rgb_offset_scale=rgb_offset_scale,
    )
    rig.build()

    assert np.isclose(rig.left_cam.location.x, -baseline / 2)
    assert np.isclose(rig.right_cam.location.x, baseline / 2)
    assert np.isclose(rig.proj_obj.location.x, 0.0)
    assert np.isclose(rig.rgb_cam.location.x, baseline * rgb_offset_scale)
    assert rig.rgb_cam.location.x < rig.left_cam.location.x < rig.proj_obj.location.x


def test_structured_light_calibration_payload_includes_rgb_relative_calibration():
    rig = StructuredLightRig(baseline=0.055, rgb_offset_scale=-0.55)
    rig.build()

    scene = bpy.data.scenes["Scene"]
    scene.render.resolution_x = rig.resolution_x
    scene.render.resolution_y = rig.resolution_y

    extrinsics = [
        {
            "L": np.eye(4).tolist(),
            "R": np.eye(4).tolist(),
            "RGB": np.eye(4).tolist(),
        }
    ]
    parameters = rig.build_calibration_dict(
        frame_ids=[1],
        extrinsics=extrinsics,
        patterns=["D415", "white"],
        manifest_setting="full",
    )

    assert parameters["setting"] == "full"
    assert set(parameters["intrinsic"]) == {"L", "R", "RGB", "Proj"}
    assert set(parameters["rel_R"]) == {"L", "R", "RGB"}
    assert set(parameters["rel_T"]) == {"L", "R", "RGB"}
    assert np.allclose(parameters["rel_R"]["RGB"], np.eye(3))
    assert np.allclose(parameters["rel_T"]["L"], [-0.0275, 0.0, 0.0])
    assert np.allclose(parameters["rel_T"]["R"], [0.0275, 0.0, 0.0])
    assert np.allclose(parameters["rel_T"]["RGB"], [-0.03025, 0.0, 0.0])
    assert parameters["frame_ids"] == [1]
    assert parameters["patterns"] == ["D415", "white"]
    assert parameters["extrinsic"] == extrinsics


def test_structured_light_default_patterns_resolve_from_repo_assets():
    repo_pattern_dir = infinigen.repo_root() / "data" / "patterns"

    pattern_dir, white_pattern_path, pattern_paths = _resolve_pattern_paths(
        sl_pattern_dir=None,
        sl_pattern_white="white.png",
        sl_pattern_names=["d415", "d435", "kinectsp"],
    )

    assert pattern_dir == repo_pattern_dir
    assert white_pattern_path == repo_pattern_dir / "white.png"
    assert [path.name for path in pattern_paths] == [
        "D415.png",
        "D435.png",
        "kinectsp.png",
    ]


def test_structured_light_frame_outputs_complete_uses_manifest_and_patterns(tmp_path):
    manifest = _load_capture_manifest(
        infinigen.repo_root()
        / "infinigen_examples"
        / "configs_indoor"
        / "capture_manifests"
        / "full.yaml"
    )
    output_root = tmp_path / "output"
    frame_tag = "0003"
    pattern_specs = [{"name": name, "path": tmp_path / f"{name}.png"} for name in ("d415", "d435", "kinectsp")]

    assert not _frame_outputs_complete(output_root, manifest, pattern_specs, frame_tag)

    required_paths = [
        output_root / "rgb" / "image" / f"frame_{frame_tag}.png",
        output_root / "rgb" / "depth" / f"frame_{frame_tag}.exr",
        output_root / "rgb" / "normal" / f"frame_{frame_tag}.exr",
    ]
    for pattern_name in ("d415", "d435", "kinectsp"):
        required_paths.append(
            output_root / "IR_left" / "image" / pattern_name / f"frame_{frame_tag}.png"
        )
        required_paths.append(
            output_root / "IR_right" / "image" / pattern_name / f"frame_{frame_tag}.png"
        )
    for path in required_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    assert _frame_outputs_complete(output_root, manifest, pattern_specs, frame_tag)


class _RigLightingStub:
    def __init__(self):
        self.calls = []

    def set_projector_visible(self, on=True):
        self.calls.append(("projector", on))

    def set_scene_lights(self, on=True):
        self.calls.append(("scene_lights", on))

    def set_env_strength(self, strength):
        self.calls.append(("env_strength", strength))


def test_pattern_capture_lighting_preserves_scene_state_by_default():
    rig = _RigLightingStub()

    _configure_pattern_capture_lighting(
        rig,
        keep_scene_lighting=True,
        baseline_env_strength=0.25,
    )
    _restore_pattern_capture_lighting(
        rig,
        keep_scene_lighting=True,
        baseline_env_strength=0.25,
    )

    assert rig.calls == [
        ("scene_lights", True),
        ("env_strength", 0.25),
        ("projector", True),
        ("projector", False),
        ("scene_lights", True),
        ("env_strength", 0.25),
    ]


def test_pattern_capture_lighting_can_disable_scene_lights_for_legacy_mode():
    rig = _RigLightingStub()

    _configure_pattern_capture_lighting(
        rig,
        keep_scene_lighting=False,
        baseline_env_strength=0.25,
    )
    _restore_pattern_capture_lighting(
        rig,
        keep_scene_lighting=False,
        baseline_env_strength=0.25,
    )

    assert rig.calls == [
        ("scene_lights", False),
        ("env_strength", 0),
        ("projector", True),
        ("projector", False),
        ("scene_lights", True),
        ("env_strength", 0.25),
    ]


def test_rgb_capture_lighting_uses_shared_baseline_without_projector():
    rig = _RigLightingStub()

    _configure_rgb_capture_lighting(
        rig,
        baseline_env_strength=0.5,
    )

    assert rig.calls == [
        ("projector", False),
        ("scene_lights", True),
        ("env_strength", 0.5),
    ]


def test_shared_baseline_env_strength_uses_preview_floor_when_forced():
    assert _resolve_shared_baseline_env_strength(
        orig_env_strength=0.1,
        preview_force_lighting=True,
        preview_world_strength=0.5,
    ) == 0.5
    assert _resolve_shared_baseline_env_strength(
        orig_env_strength=0.8,
        preview_force_lighting=True,
        preview_world_strength=0.5,
    ) == 0.8
    assert _resolve_shared_baseline_env_strength(
        orig_env_strength=0.1,
        preview_force_lighting=False,
        preview_world_strength=0.5,
    ) == 0.1


def test_structured_light_incremental_calibration_loader_tolerates_truncated_tail(tmp_path):
    progress_path = tmp_path / "calibration.jsonl"
    payload = {
        "setting": "full",
        "baseline": 0.055,
        "intrinsic": {"RGB": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "rel_R": {"RGB": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "rel_T": {"RGB": [0, 0, 0]},
        "frame_ids": [],
        "extrinsic": [],
        "patterns": ["d415"],
    }
    header = _calibration_header_from_payload(payload)
    _rewrite_incremental_calibration(progress_path, header, {0: {"RGB": [[1, 0, 0, 0]]}})
    _append_incremental_calibration_frame(progress_path, 2, {"RGB": [[2, 0, 0, 0]]})
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write('{"type":"frame","frame":3')

    loaded_header, frame_records = _load_incremental_calibration(progress_path)

    assert loaded_header == header
    assert frame_records[0] == {"RGB": [[1, 0, 0, 0]]}
    assert frame_records[2] == {"RGB": [[2, 0, 0, 0]]}
    assert 3 not in frame_records


def test_manifest_pattern_config_overrides_gin_defaults():
    manifest = {
        "patterns": {
            "names": ["d415"],
            "white": "manifest_white.png",
        }
    }

    pattern_names, pattern_white = _resolve_manifest_pattern_config(
        manifest=manifest,
        sl_pattern_names=["d415", "d435", "kinectsp"],
        sl_pattern_white="white.png",
    )

    assert pattern_names == ["d415"]
    assert pattern_white == "manifest_white.png"


def test_manifest_pattern_config_can_explicitly_disable_patterns():
    manifest = {
        "patterns": {
            "names": [],
            "white": "manifest_white.png",
        }
    }

    pattern_names, pattern_white = _resolve_manifest_pattern_config(
        manifest=manifest,
        sl_pattern_names=["d415", "d435", "kinectsp"],
        sl_pattern_white="white.png",
    )

    assert pattern_names == []
    assert pattern_white == "manifest_white.png"


def test_debug_manifest_does_not_inherit_default_rgb_normal_outputs():
    manifest = _load_capture_manifest(
        infinigen.repo_root()
        / "infinigen_examples"
        / "configs_indoor"
        / "capture_manifests"
        / "debug.yaml"
    )

    assert manifest["cameras"]["rgb"]["outputs"] == {
        "image": ["png"],
        "depth": ["png"],
    }


def test_rgb_only_manifest_can_disable_ir_outputs():
    manifest = _load_capture_manifest(
        infinigen.repo_root()
        / "infinigen_examples"
        / "configs_indoor"
        / "capture_manifests"
        / "rgb_only.yaml"
    )

    assert manifest["cameras"]["left"]["outputs"] == {}
    assert manifest["cameras"]["right"]["outputs"] == {}


def test_test_manifest_keeps_only_rgb_and_single_d435_pattern():
    manifest = _load_capture_manifest(
        infinigen.repo_root()
        / "infinigen_examples"
        / "configs_indoor"
        / "capture_manifests"
        / "test.yaml"
    )

    assert manifest["patterns"]["names"] == ["d435"]
    assert manifest["cameras"]["rgb"]["outputs"] == {"image": ["png"]}
    assert manifest["cameras"]["left"]["outputs"] == {"image": ["png"]}
    assert manifest["cameras"]["right"]["outputs"] == {"image": ["png"]}
