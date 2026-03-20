# Copyright (C) 2026.

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import infinigen
import yaml


def test_capture_existing_seed_scene_uses_manifest_capture_layout_and_depth_stats(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_7"
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
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p \
        "$output_folder/output/rgb/image" \
        "$output_folder/output/rgb/depth" \
        "$output_folder/output/rgb/normal" \
        "$output_folder/output/IR_left/image/d415" \
        "$output_folder/output/IR_right/image/d415" \
        "$output_folder/output/calibration" \
        "$output_folder/structured_light/patterns"
    printf '%s\n' "$*" > "$output_folder/structured_light_invocation.txt"
    touch "$output_folder/output/rgb/image/frame_0000.png"
    touch "$output_folder/output/IR_left/image/d415/frame_0000.png"
    touch "$output_folder/output/IR_right/image/d415/frame_0000.png"
    touch "$output_folder/structured_light/patterns/D415.png"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/rgb/depth/frame_0000.npy" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.save(path, np.array([[0.8, 1.2], [1.6, 2.4]], dtype=np.float32))
PY
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "baseline": 0.055,
    "intrinsic": {"RGB": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    "rel_R": {"RGB": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    "rel_T": {"RGB": [0, 0, 0]},
    "frame_ids": [0],
    "extrinsic": [{"RGB": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}],
    "patterns": ["d415"],
}
np.savez(path, payload)
PY
    exit 0
fi

exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
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

    trajectory_root = scene_dir / "trajectory"
    capture_root = scene_dir / "capture" / "full"
    assert (trajectory_root / "scene.blend").exists()
    assert (trajectory_root / "trajectory_metadata.json").exists()
    settings_text = (capture_root / "config" / "capture_settings.env").read_text(encoding="utf-8")
    assert "SETTING_GIN_CONFIG=" in settings_text
    assert "CAPTURE_CONFIGS=benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin full.gin" in settings_text
    assert (capture_root / "config" / "capture_manifest.yaml").exists()
    assert (capture_root / "logs" / "render.log").exists()
    assert (capture_root / "output" / "rgb" / "image" / "frame_0000.png").exists()
    assert (capture_root / "output" / "rgb" / "depth" / "frame_0000.npy").exists()
    assert (capture_root / "output" / "IR_left" / "image" / "d415" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_right" / "image" / "d415" / "frame_0000.png").exists()
    assert (capture_root / "output" / "calibration" / "calibration.npz").exists()
    assert (capture_root / "structured_light" / "patterns" / "D415.png").exists()
    assert (capture_root / "output" / "calibration" / "capture_complete.json").exists()

    histogram = json.loads((capture_root / "stats" / "depth_histogram.json").read_text(encoding="utf-8"))
    assert histogram["status"] == "ok"
    assert histogram["depth_file_count"] == 1
    assert histogram["depth_files"] == ["output/rgb/depth/frame_0000.npy"]
    assert (capture_root / "stats" / "depth_histogram.png").exists()
    assert "Capture root:" in result.stdout


def test_capture_existing_seed_scene_resume_prefers_archived_manifest_and_forwards_resume_flags(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_8"
    coarse_dir = scene_dir / "coarse"
    capture_config_dir = scene_dir / "capture" / "full" / "config"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    capture_config_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")
    (capture_config_dir / "capture_manifest.yaml").write_text(
        "setting: archived_full\npatterns:\n  names: [d415]\n",
        encoding="utf-8",
    )

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
printf '%s\n' "$*" > "$output_folder/invocation.txt"

if [[ "$task" == "trajectory" ]]; then
    touch "$output_folder/scene.blend"
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p "$output_folder/output/calibration"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.savez(path, {"frame_ids": [0], "extrinsic": [{"RGB": [[1, 0, 0, 0]]}]})
PY
    exit 0
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
            "DEPTH_HISTOGRAM_ENABLED": "0",
            "CAPTURE_MANIFEST": str(tmp_path / "ignored.yaml"),
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(script_path),
            str(scene_dir),
            "full",
            "--resume",
            "--resume-from",
            "563",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    capture_root = scene_dir / "capture" / "full"
    settings_text = (capture_root / "config" / "capture_settings.env").read_text(encoding="utf-8")
    assert "CAPTURE_MANIFEST_SOURCE=archived_config" in settings_text
    assert f"CAPTURE_MANIFEST={capture_root / 'config' / 'capture_manifest.yaml'}" in settings_text
    assert "RESUME_CAPTURE=1" in settings_text
    assert "RESUME_FROM_FRAME=563" in settings_text
    assert "Manifest source: archived_config" in result.stdout
    assert "Resume from frame: 563" in result.stdout


def test_capture_existing_seed_scene_resume_warns_and_falls_back_without_archived_manifest(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_9"
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
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p "$output_folder/output/calibration"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.savez(path, {"frame_ids": [0], "extrinsic": [{"RGB": [[1, 0, 0, 0]]}]})
PY
    exit 0
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
            "DEPTH_HISTOGRAM_ENABLED": "0",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(scene_dir), "full", "--resume"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    settings_text = (
        scene_dir / "capture" / "full" / "config" / "capture_settings.env"
    ).read_text(encoding="utf-8")
    assert "CAPTURE_MANIFEST_SOURCE=setting_default" in settings_text
    assert "archived capture manifest missing" in result.stderr.lower()


def test_full_capture_manifest_rgb_outputs_match_default_full_setting():
    repo_root = infinigen.repo_root()
    manifest_path = repo_root / "infinigen_examples" / "configs_indoor" / "capture_manifests" / "full.yaml"

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    rgb_outputs = manifest["cameras"]["rgb"]["outputs"]

    assert rgb_outputs["image"] == ["png"]
    assert rgb_outputs["depth"] == ["exr"]
    assert rgb_outputs["normal"] == ["exr"]


def test_capture_existing_seed_scene_test_setting_uses_test_manifest_and_smoother_defaults(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_10"
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
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p \
        "$output_folder/output/rgb/image" \
        "$output_folder/output/IR_left/image/d435" \
        "$output_folder/output/IR_right/image/d435" \
        "$output_folder/output/calibration" \
        "$output_folder/structured_light/patterns"
    touch "$output_folder/output/rgb/image/frame_0000.png"
    touch "$output_folder/output/IR_left/image/d435/frame_0000.png"
    touch "$output_folder/output/IR_right/image/d435/frame_0000.png"
    touch "$output_folder/structured_light/patterns/D435.png"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.savez(path, {"frame_ids": [0], "extrinsic": [{"RGB": [[1, 0, 0, 0]]}]})
PY
    exit 0
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
            "DEPTH_HISTOGRAM_ENABLED": "0",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(scene_dir), "test"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    capture_root = scene_dir / "capture" / "test"
    settings_text = (capture_root / "config" / "capture_settings.env").read_text(encoding="utf-8")
    manifest = yaml.safe_load(
        (capture_root / "config" / "capture_manifest.yaml").read_text(encoding="utf-8")
    )

    assert "SETTING=test" in settings_text
    assert f"SETTING_GIN_CONFIG={repo_root / 'infinigen_examples' / 'configs_indoor' / 'test.gin'}" in settings_text
    assert "CAPTURE_CONFIGS=benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin test.gin" in settings_text
    assert manifest["patterns"]["names"] == ["d435"]
    assert manifest["cameras"]["rgb"]["outputs"] == {"image": ["png"]}
    assert (capture_root / "output" / "rgb" / "image" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_left" / "image" / "d435" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_right" / "image" / "d435" / "frame_0000.png").exists()


def test_capture_existing_seed_scene_test_traj_setting_uses_preview_defaults(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
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
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p \
        "$output_folder/output/rgb/image" \
        "$output_folder/output/IR_left/image/d435" \
        "$output_folder/output/IR_right/image/d435" \
        "$output_folder/output/calibration" \
        "$output_folder/structured_light/patterns"
    touch "$output_folder/output/rgb/image/frame_0000.png"
    touch "$output_folder/output/IR_left/image/d435/frame_0000.png"
    touch "$output_folder/output/IR_right/image/d435/frame_0000.png"
    touch "$output_folder/structured_light/patterns/D435.png"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.savez(path, {"frame_ids": [0], "extrinsic": [{"RGB": [[1, 0, 0, 0]]}]})
PY
    exit 0
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
            "DEPTH_HISTOGRAM_ENABLED": "0",
            "FRAME_RANGE": "0,39",
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

    capture_root = scene_dir / "capture" / "test_traj"
    settings_text = (capture_root / "config" / "capture_settings.env").read_text(encoding="utf-8")
    manifest = yaml.safe_load(
        (capture_root / "config" / "capture_manifest.yaml").read_text(encoding="utf-8")
    )

    assert "SETTING=test_traj" in settings_text
    assert f"SETTING_GIN_CONFIG={repo_root / 'infinigen_examples' / 'configs_indoor' / 'test_traj.gin'}" in settings_text
    assert "CAPTURE_CONFIGS=benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin test_traj.gin" in settings_text
    assert "FRAME_RANGE=0,39" in settings_text
    assert "REUSE_EXISTING_TRAJECTORY=0" in settings_text
    assert manifest["setting"] == "test_traj"
    assert manifest["patterns"]["names"] == ["d435"]
    assert manifest["cameras"]["rgb"]["outputs"] == {"image": ["png"]}
    assert (capture_root / "output" / "rgb" / "image" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_left" / "image" / "d435" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_right" / "image" / "d435" / "frame_0000.png").exists()

    test_traj_gin = (
        repo_root / "infinigen_examples" / "configs_indoor" / "test_traj.gin"
    ).read_text(encoding="utf-8")
    assert "animate_whole_home_walk.planner_fps = 16" in test_traj_gin
    assert "animate_whole_home_walk.traversal_speed_mps = 0.48" in test_traj_gin
    assert "animate_whole_home_walk.traversal_point_step_m = 0.03" in test_traj_gin
    assert "animate_whole_home_walk.room_sweep_angle_deg = 60.0" in test_traj_gin
    assert "animate_whole_home_walk.enable_room_orbit = False" in test_traj_gin
    assert "animate_whole_home_walk.handheld_lateral_amplitude_m = 0.0" in test_traj_gin
    assert "animate_whole_home_walk.handheld_yaw_amplitude_deg = 0.0" in test_traj_gin
    assert "render_structured_light.sl_resolution_x = 320" in test_traj_gin
    assert "render_structured_light.sl_resolution_y = 240" in test_traj_gin
    assert "render_structured_light.sl_max_samples = 6" in test_traj_gin


def test_capture_existing_seed_scene_test_traj_regenerates_existing_trajectory_by_default(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_13"
    coarse_dir = scene_dir / "coarse"
    trajectory_dir = scene_dir / "trajectory"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")
    (trajectory_dir / "scene.blend").write_text("old", encoding="utf-8")

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
    printf 'regenerated\n' > "$output_folder/trajectory_was_regenerated.txt"
    touch "$output_folder/scene.blend"
    printf '{"planner":"whole_home_walk"}\n' > "$output_folder/trajectory_metadata.json"
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p "$output_folder/output/calibration"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.savez(path, {"frame_ids": [0], "extrinsic": [{"RGB": [[1, 0, 0, 0]]}]})
PY
    exit 0
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
            "DEPTH_HISTOGRAM_ENABLED": "0",
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
    assert "Reuse existing trajectory: 0" in result.stdout
    assert "Regenerating trajectory scene" in result.stdout
    assert (trajectory_dir / "trajectory_was_regenerated.txt").exists()


def test_capture_existing_seed_scene_only_forwards_runtime_overrides(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/capture_existing_seed_scene.sh"
    fake_python = tmp_path / "fake_generate_indoors.sh"
    manifest_path = tmp_path / "custom_manifest.yaml"
    scene_dir = tmp_path / "outputs" / "benchmark" / "structured_light_indoors" / "seed_12"
    coarse_dir = scene_dir / "coarse"
    coarse_dir.mkdir(parents=True, exist_ok=True)
    (coarse_dir / "scene.blend").write_text("", encoding="utf-8")
    manifest_path.write_text("setting: custom\npatterns:\n  names: []\n", encoding="utf-8")

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

task=""
output_folder=""
declare -a overrides=()

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
        -g)
            shift
            while [[ $# -gt 0 && "$1" != --* && "$1" != -g && "$1" != -p ]]; do
                shift
            done
            ;;
        -p)
            shift
            while [[ $# -gt 0 && "$1" != --* && "$1" != -g && "$1" != -p ]]; do
                overrides+=("$1")
                shift
            done
            ;;
        *)
            shift
            ;;
    esac
done

mkdir -p "$output_folder"
printf '%s\n' "${overrides[@]}" > "$output_folder/overrides.txt"

if [[ "$task" == "trajectory" ]]; then
    touch "$output_folder/scene.blend"
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p "$output_folder/output/calibration"
    "$FAKE_HELPER_PYTHON" - "$output_folder/output/calibration/calibration.npz" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.savez(path, {"frame_ids": [0], "extrinsic": [{"RGB": [[1, 0, 0, 0]]}]})
PY
    exit 0
fi
""",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "POST_PYTHON_BIN": sys.executable,
            "FAKE_HELPER_PYTHON": sys.executable,
            "DEPTH_HISTOGRAM_ENABLED": "0",
            "FRAME_RANGE": "10,19",
            "CAPTURE_MANIFEST": str(manifest_path),
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), str(scene_dir), "full", "--resume-from", "12"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    trajectory_overrides = (
        scene_dir / "trajectory" / "overrides.txt"
    ).read_text(encoding="utf-8").splitlines()
    capture_overrides = (
        scene_dir / "capture" / "full" / "overrides.txt"
    ).read_text(encoding="utf-8").splitlines()

    assert trajectory_overrides in ([], [""])
    assert f'render_structured_light.sl_capture_manifest_path="{manifest_path}"' in capture_overrides
    assert "render_structured_light.sl_resume=1" in capture_overrides
    assert "render_structured_light.sl_resume_from_frame=12" in capture_overrides
    assert "execute_tasks.use_scene_frame_range=False" in capture_overrides
    assert "execute_tasks.frame_range=[10,19]" in capture_overrides
    assert "render_structured_light.sl_frame_index_offset=10" in capture_overrides
    assert all(not item.startswith("animate_whole_home_walk.") for item in capture_overrides)
    assert all("sl_resolution_" not in item for item in capture_overrides)
    assert all("sl_max_samples" not in item for item in capture_overrides)
