# Copyright (C) 2026.

import os
import stat
import subprocess
from pathlib import Path

import infinigen


def _make_scene(dataset_root: Path, scene_name: str) -> None:
    blend_dir = dataset_root / "blendswap_scenes" / scene_name
    data_dir = dataset_root / "neural_rgbd_data" / scene_name
    blend_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    (blend_dir / "scene.blend").write_text("", encoding="utf-8")


def test_export_all_neural_rgbd_scene_ply_discovers_scenes_and_invokes_exporter(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/benchmark/neural_rgbd/export_all_neural_rgbd_scene_ply.sh"
    fake_python = tmp_path / "fake_python.sh"
    invocation_log = tmp_path / "invocation.log"
    dataset_root = tmp_path / "data" / "neural_rgbd"
    output_root = tmp_path / "outputs" / "benchmark" / "neural_rgbd" / "scene_ply"

    _make_scene(dataset_root, "breakfast_room")
    _make_scene(dataset_root, "whiteroom")
    (dataset_root / "neural_rgbd_data" / "ignored_only_data").mkdir(parents=True, exist_ok=True)

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$INVOCATION_LOG"
output_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output_path)
            output_path="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done
if [[ -n "${output_path}" ]]; then
    mkdir -p "$(dirname "${output_path}")"
    : > "${output_path}"
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "INVOCATION_LOG": str(invocation_log),
            "DATASET_ROOT": str(dataset_root),
            "OUTPUT_ROOT": str(output_root),
            "SCENES": "ALL",
            "ASCII_PLY": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    invocation_lines = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len(invocation_lines) == 2
    assert all("-m infinigen.launch_blender -m infinigen.tools.export_scene_ply --" in line for line in invocation_lines)
    assert any("--input_blend" in line and "breakfast_room/scene.blend" in line for line in invocation_lines)
    assert any("--input_blend" in line and "whiteroom/scene.blend" in line for line in invocation_lines)
    assert all("--ascii" in line for line in invocation_lines)
    assert all("--sample_mode surface" in line for line in invocation_lines)
    assert all("--sample_spacing 0.2" in line for line in invocation_lines)
    assert (output_root / "breakfast_room" / "breakfast_room.ply").exists()
    assert (output_root / "whiteroom" / "whiteroom.ply").exists()


def test_export_all_neural_rgbd_scene_ply_forwards_surface_sampling_options(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/benchmark/neural_rgbd/export_all_neural_rgbd_scene_ply.sh"
    fake_python = tmp_path / "fake_python.sh"
    invocation_log = tmp_path / "invocation.log"
    dataset_root = tmp_path / "data" / "neural_rgbd"

    _make_scene(dataset_root, "breakfast_room")

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$INVOCATION_LOG"
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "INVOCATION_LOG": str(invocation_log),
            "DATASET_ROOT": str(dataset_root),
            "SCENES": "breakfast_room",
            "POINT_SAMPLING_MODE": "surface",
            "POINT_SAMPLE_SPACING": "0.2",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    invocation_lines = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len(invocation_lines) == 1
    assert "--sample_mode surface" in invocation_lines[0]
    assert "--sample_spacing 0.2" in invocation_lines[0]
