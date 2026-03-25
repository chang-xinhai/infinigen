# Copyright (C) 2026.

import os
import stat
import subprocess
import sys
from pathlib import Path

import infinigen

sys.path.insert(0, str(infinigen.repo_root()))


def test_run_neural_rgbd_wrapper_invokes_python_entrypoint(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/benchmark/neural_rgbd/run_neural_rgbd.sh"
    fake_python = tmp_path / "fake_python.sh"
    invocation_log = tmp_path / "python_invocation.log"

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" > "$INVOCATION_LOG"
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "INVOCATION_LOG": str(invocation_log),
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(script_path),
            "--scene_name",
            "breakfast_room",
            "--task",
            "trajectory",
            "render",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    invocation = invocation_log.read_text(encoding="utf-8")
    assert str(repo_root / "scripts/benchmark/neural_rgbd/run_neural_rgbd.py") in invocation
    assert "--scene_name breakfast_room --task trajectory render" in invocation


def test_preview_neural_rgbd_trajectory_wrapper_launches_blender(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/benchmark/neural_rgbd/preview_neural_rgbd_trajectory.sh"
    fake_blender = tmp_path / "fake_blender.sh"
    blender_log = tmp_path / "blender.log"
    output_root = tmp_path / "outputs" / "benchmark" / "neural_rgbd" / "breakfast_room" / "poses"
    trajectory_dir = output_root / "trajectory"
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    (trajectory_dir / "scene.blend").write_text("", encoding="utf-8")

    fake_blender.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" > "$BLENDER_LOG"
""",
        encoding="utf-8",
    )
    fake_blender.chmod(fake_blender.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "BLENDER_BIN": str(fake_blender),
            "BLENDER_LOG": str(blender_log),
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(output_root)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    invocation = blender_log.read_text(encoding="utf-8")
    assert str(trajectory_dir / "scene.blend") in invocation
    assert str(repo_root / "scripts/blender_trajectory_preview.py") in invocation


def test_run_all_neural_rgbd_wrapper_invokes_runner_per_scene_and_writes_summary(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/benchmark/neural_rgbd/run_all_neural_rgbd.sh"
    fake_runner = tmp_path / "fake_runner.sh"
    invocation_log = tmp_path / "runner.log"
    output_root = tmp_path / "outputs"

    fake_runner.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'CUDA_VISIBLE_DEVICES=%s :: %s\\n' "${CUDA_VISIBLE_DEVICES:-}" "$*" >> "$INVOCATION_LOG"
""",
        encoding="utf-8",
    )
    fake_runner.chmod(fake_runner.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "RUN_NEURAL_RGBD_BIN": str(fake_runner),
            "INVOCATION_LOG": str(invocation_log),
            "OUTPUT_ROOT": str(output_root),
            "SCENES": "breakfast_room whiteroom",
            "GPU_IDS": "2,3",
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
    invocation = invocation_log.read_text(encoding="utf-8")
    assert "CUDA_VISIBLE_DEVICES=2,3 :: --scene_name breakfast_room --pose_source blender_poses --task trajectory" in invocation
    assert "CUDA_VISIBLE_DEVICES=2,3 :: --scene_name breakfast_room --pose_source blender_poses --task render" in invocation
    assert "CUDA_VISIBLE_DEVICES=2,3 :: --scene_name breakfast_room --pose_source blender_poses --task structured_light" in invocation
    assert "-g structured_light.gin full.gin structured_light_neural_rgbd.gin" in invocation
    assert "render_structured_light.sl_capture_manifest_path=" in invocation
    assert "CUDA_VISIBLE_DEVICES=2,3 :: --scene_name whiteroom --pose_source blender_poses --task trajectory" in invocation

    summary = (output_root / "logs" / "run_all_summary.tsv").read_text(encoding="utf-8")
    assert "breakfast_room\tsuccess" in summary
    assert "whiteroom\tsuccess" in summary
