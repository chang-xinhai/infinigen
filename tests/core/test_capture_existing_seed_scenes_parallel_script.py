# Copyright (C) 2026.

import os
import stat
import subprocess
from pathlib import Path

import infinigen


def _make_seed(scene_root: Path, seed: int) -> Path:
    scene_dir = scene_root / f"seed_{seed}"
    coarse_dir = scene_dir / "coarse"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")
    return scene_dir


def test_parallel_existing_seed_capture_skips_completed_and_sets_worker_env(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scenes_parallel.sh"
    fake_capture = tmp_path / "fake_capture.sh"
    output_root = tmp_path / "outputs" / "benchmark" / "structured_light_indoors"

    seed_0 = _make_seed(output_root, 0)
    seed_1 = _make_seed(output_root, 1)
    seed_2 = _make_seed(output_root, 2)

    completed_marker = seed_1 / "capture" / "full" / "output" / "calibration" / "capture_complete.json"
    completed_marker.parent.mkdir(parents=True, exist_ok=True)
    completed_marker.write_text("", encoding="utf-8")

    fake_capture.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

scene_dir="$1"
setting="$2"
capture_root="$scene_dir/capture/$setting"

mkdir -p "$capture_root/output/calibration"
printf 'gpu=%s\\nthreads=%s\\ntmpdir=%s\\nmplconfig=%s\\nblender_config=%s\\n' \
    "${CUDA_VISIBLE_DEVICES:-unset}" \
    "${OMP_NUM_THREADS:-unset}" \
    "${TMPDIR:-unset}" \
    "${MPLCONFIGDIR:-unset}" \
    "${BLENDER_USER_CONFIG:-unset}" \
    > "$capture_root/worker_env.txt"
touch "$capture_root/output/calibration/capture_complete.json"
""",
        encoding="utf-8",
    )
    fake_capture.chmod(fake_capture.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "CAPTURE_SCRIPT": str(fake_capture),
            "GPU_IDS": "2,5",
            "TOTAL_CPUS": "6",
            "MAX_PARALLEL_SCENES": "2",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(output_root), "full"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Pending scenes: 2" in result.stdout
    assert "Skipped completed: 1" in result.stdout

    worker_env_texts = []
    for scene_dir in (seed_0, seed_2):
        worker_env = (scene_dir / "capture" / "full" / "worker_env.txt").read_text(encoding="utf-8")
        worker_env_texts.append(worker_env)
        assert "threads=3" in worker_env
        assert "gpu=2" in worker_env or "gpu=5" in worker_env
        assert "tmpdir=" in worker_env
        assert "mplconfig=" in worker_env
        assert "blender_config=" in worker_env
        assert (scene_dir / "capture" / "full" / "output" / "calibration" / "capture_complete.json").exists()

    tmpdirs = {
        next(line.split("=", 1)[1] for line in text.splitlines() if line.startswith("tmpdir="))
        for text in worker_env_texts
    }
    assert len(tmpdirs) == 2
    assert all("capture_existing_seed_scenes_parallel" in path for path in tmpdirs)

    assert not (seed_1 / "capture" / "full" / "worker_env.txt").exists()

    summary_files = sorted((output_root / "logs" / "existing_seed_capture").glob("summary_full_*.tsv"))
    assert summary_files
    summary_text = summary_files[-1].read_text(encoding="utf-8")
    assert "seed_0\tsuccess\t" in summary_text
    assert "seed_2\tsuccess\t" in summary_text
    assert "seed_1" not in summary_text

    batch_config_files = sorted((output_root / "logs" / "existing_seed_capture").glob("batch_full_*.env"))
    assert batch_config_files
    batch_config_text = batch_config_files[-1].read_text(encoding="utf-8")
    assert "ISOLATE_RUNTIME=1" in batch_config_text


def test_parallel_existing_seed_capture_returns_nonzero_after_scene_failures(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scenes_parallel.sh"
    fake_capture = tmp_path / "fake_capture_fail.sh"
    output_root = tmp_path / "outputs" / "benchmark" / "structured_light_indoors"

    _make_seed(output_root, 0)
    _make_seed(output_root, 1)
    _make_seed(output_root, 2)

    fake_capture.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

scene_dir="$1"
setting="$2"
scene_name="$(basename "$scene_dir")"
capture_root="$scene_dir/capture/$setting"

mkdir -p "$capture_root/output/calibration"

if [[ "$scene_name" == "seed_1" ]]; then
    echo "simulated failure for $scene_name" >&2
    exit 9
fi

touch "$capture_root/output/calibration/capture_complete.json"
""",
        encoding="utf-8",
    )
    fake_capture.chmod(fake_capture.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "CAPTURE_SCRIPT": str(fake_capture),
            "GPU_IDS": "0,1",
            "TOTAL_CPUS": "4",
            "MAX_PARALLEL_SCENES": "2",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(output_root), "full"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert (output_root / "seed_0" / "capture" / "full" / "output" / "calibration" / "capture_complete.json").exists()
    assert (output_root / "seed_2" / "capture" / "full" / "output" / "calibration" / "capture_complete.json").exists()
    assert not (output_root / "seed_1" / "capture" / "full" / "output" / "calibration" / "capture_complete.json").exists()

    summary_files = sorted((output_root / "logs" / "existing_seed_capture").glob("summary_full_*.tsv"))
    assert summary_files
    summary_text = summary_files[-1].read_text(encoding="utf-8")
    assert "seed_0\tsuccess\t" in summary_text
    assert "seed_1\tfailed(9)\t" in summary_text
    assert "seed_2\tsuccess\t" in summary_text
    assert "Failed scenes: 1" in result.stdout


def test_parallel_existing_seed_capture_does_not_treat_calibration_npz_as_complete(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scenes_parallel.sh"
    fake_capture = tmp_path / "fake_capture.sh"
    output_root = tmp_path / "outputs" / "benchmark" / "structured_light_indoors"

    seed_0 = _make_seed(output_root, 0)
    calibration_npz = seed_0 / "capture" / "full" / "output" / "calibration" / "calibration.npz"
    calibration_npz.parent.mkdir(parents=True, exist_ok=True)
    calibration_npz.write_text("", encoding="utf-8")

    fake_capture.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

scene_dir="$1"
setting="$2"
capture_root="$scene_dir/capture/$setting"

mkdir -p "$capture_root/output/calibration"
touch "$capture_root/output/calibration/capture_complete.json"
""",
        encoding="utf-8",
    )
    fake_capture.chmod(fake_capture.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update({"CAPTURE_SCRIPT": str(fake_capture), "GPU_IDS": "0"})

    result = subprocess.run(
        ["bash", str(script_path), str(output_root), "full"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Pending scenes: 1" in result.stdout
    assert "Skipped completed: 0" in result.stdout
    assert (seed_0 / "capture" / "full" / "output" / "calibration" / "capture_complete.json").exists()


def test_parallel_existing_seed_capture_forwards_single_scene_args(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scenes_parallel.sh"
    fake_capture = tmp_path / "fake_capture_args.sh"
    output_root = tmp_path / "outputs" / "benchmark" / "structured_light_indoors"

    seed_0 = _make_seed(output_root, 0)

    fake_capture.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

scene_dir="$1"
setting="$2"
shift 2
capture_root="$scene_dir/capture/$setting"

mkdir -p "$capture_root/output/calibration"
printf '%s\\n' "$*" > "$capture_root/forwarded_args.txt"
touch "$capture_root/output/calibration/capture_complete.json"
""",
        encoding="utf-8",
    )
    fake_capture.chmod(fake_capture.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update({"CAPTURE_SCRIPT": str(fake_capture), "GPU_IDS": "0"})

    result = subprocess.run(
        [
            "bash",
            str(script_path),
            str(output_root),
            "full",
            "--resume",
            "--resume-from",
            "7",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    forwarded_args = (seed_0 / "capture" / "full" / "forwarded_args.txt").read_text(encoding="utf-8").strip()
    assert forwarded_args == "--resume --resume-from 7"
    assert "Capture args: --resume --resume-from 7" in result.stdout
