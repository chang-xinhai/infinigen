# Copyright (C) 2026.

import os
import stat
import subprocess
from pathlib import Path

import infinigen


def test_preview_existing_seed_trajectory_regenerates_and_launches_blender(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/preview_existing_seed_trajectory.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    fake_blender = tmp_path / "fake_blender.sh"
    blender_log = tmp_path / "fake_blender.log"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_11"
    coarse_dir = scene_dir / "coarse"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

task=""
output_folder=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m)
            shift 2
            ;;
        --task)
            task="$2"
            shift 2
            ;;
        --output_folder)
            output_folder="$2"
            shift 2
            ;;
        --input_folder|--seed)
            shift 2
            ;;
        -g|-p)
            shift
            while [[ $# -gt 0 && "$1" != --* && "$1" != -g && "$1" != -p ]]; do
                shift
            done
            ;;
        *)
            shift
            ;;
    esac
done

mkdir -p "$output_folder"

if [[ "$task" == "trajectory" ]]; then
    touch "$output_folder/scene.blend"
    printf '{"planner":"whole_home_walk"}\n' > "$output_folder/trajectory_metadata.json"
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    fake_blender.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$BLENDER_LOG"
""",
        encoding="utf-8",
    )
    fake_blender.chmod(fake_blender.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "BLENDER_BIN": str(fake_blender),
            "BLENDER_LOG": str(blender_log),
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(scene_dir), "test_traj"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (scene_dir / "trajectory" / "scene.blend").exists()

    blender_invocation = blender_log.read_text(encoding="utf-8")
    assert str(scene_dir / "trajectory" / "scene.blend") in blender_invocation
    assert str(repo_root / "scripts/blender_trajectory_preview.py") in blender_invocation
    assert "--shading MATERIAL" in blender_invocation
    assert "--autoplay 1" in blender_invocation
    assert "Existing Seed Trajectory Preview" in result.stdout


def test_preview_existing_seed_trajectory_reuses_existing_scene_when_requested(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/preview_existing_seed_trajectory.sh"
    fake_python = tmp_path / "fake_generate_should_not_run.sh"
    fake_blender = tmp_path / "fake_blender_reuse.sh"
    blender_log = tmp_path / "fake_blender_reuse.log"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_12"
    coarse_dir = scene_dir / "coarse"
    trajectory_dir = scene_dir / "trajectory"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")
    (trajectory_dir / "scene.blend").write_text("", encoding="utf-8")

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "trajectory generation should not run" >&2
exit 99
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    fake_blender.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$BLENDER_LOG"
""",
        encoding="utf-8",
    )
    fake_blender.chmod(fake_blender.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "BLENDER_BIN": str(fake_blender),
            "BLENDER_LOG": str(blender_log),
            "REUSE_EXISTING_TRAJECTORY": "1",
            "BLENDER_VIEWPORT_SHADING": "RENDERED",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(scene_dir), "full"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Reusing trajectory scene" in result.stdout

    blender_invocation = blender_log.read_text(encoding="utf-8")
    assert "--shading RENDERED" in blender_invocation
    assert str(trajectory_dir / "scene.blend") in blender_invocation


def test_preview_existing_seed_trajectory_falls_back_to_blender_in_path(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/preview_existing_seed_trajectory.sh"
    fake_python = tmp_path / "fake_python_with_failed_bundle_lookup.sh"
    fake_bin = tmp_path / "bin"
    fake_blender = fake_bin / "blender"
    blender_log = tmp_path / "fake_blender_path.log"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_13"
    coarse_dir = scene_dir / "coarse"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")
    fake_bin.mkdir(parents=True, exist_ok=True)

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-c" ]]; then
    exit 1
fi

task=""
output_folder=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m)
            shift 2
            ;;
        --task)
            task="$2"
            shift 2
            ;;
        --output_folder)
            output_folder="$2"
            shift 2
            ;;
        --input_folder|--seed)
            shift 2
            ;;
        -g|-p)
            shift
            while [[ $# -gt 0 && "$1" != --* && "$1" != -g && "$1" != -p ]]; do
                shift
            done
            ;;
        *)
            shift
            ;;
    esac
done

mkdir -p "$output_folder"

if [[ "$task" == "trajectory" ]]; then
    touch "$output_folder/scene.blend"
    printf '{"planner":"whole_home_walk"}\n' > "$output_folder/trajectory_metadata.json"
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    fake_blender.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$BLENDER_LOG"
""",
        encoding="utf-8",
    )
    fake_blender.chmod(fake_blender.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "BLENDER_LOG": str(blender_log),
            "PATH": f"{fake_bin}:{env['PATH']}",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(scene_dir), "test_traj"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    blender_invocation = blender_log.read_text(encoding="utf-8")
    assert str(scene_dir / "trajectory" / "scene.blend") in blender_invocation
