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
    assert (capture_root / "config" / "capture_settings.env").exists()
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
    assert "WALK_FPS=8" in settings_text
    assert "WALK_STEP_M=0.05" in settings_text
    assert manifest["patterns"]["names"] == ["d435"]
    assert manifest["cameras"]["rgb"]["outputs"] == {"image": ["png"]}
    assert (capture_root / "output" / "rgb" / "image" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_left" / "image" / "d435" / "frame_0000.png").exists()
    assert (capture_root / "output" / "IR_right" / "image" / "d435" / "frame_0000.png").exists()
