# Copyright (C) 2026.

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import infinigen


def test_capture_existing_seed_scene_uses_structured_layout_and_depth_stats(tmp_path):
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

if [[ "$task" == "render" ]]; then
    root="$(dirname "$output_folder")"
    mkdir -p "$root/frames/Image/camera_0" "$root/frames/camview/camera_0" "$root/frames/Depth/camera_0"
    touch "$root/frames/Image/camera_0/Image_0_0_0001_0.png"
    touch "$root/frames/camview/camera_0/camview_0_0_0001_0.npz"
    "$FAKE_HELPER_PYTHON" - "$root/frames/Depth/camera_0/Depth_0_0_0001_0.npy" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.save(path, np.array([[1.0, 2.0], [2.5, 3.0]], dtype=np.float32))
PY
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p "$output_folder/structured_light"
    touch "$output_folder/structured_light/done.txt"
    "$FAKE_HELPER_PYTHON" - "$output_folder/structured_light/0001_Depth.npy" <<'PY'
import sys
from pathlib import Path
import numpy as np

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
np.save(path, np.array([[0.8, 1.2], [1.6, 2.4]], dtype=np.float32))
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
            "RUN_TAG": "capture_test",
            "GENERATE_PREVIEW_ARTIFACTS": "0",
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

    capture_root = scene_dir / "captures" / "capture_test"
    assert (capture_root / "trajectory" / "scene.blend").exists()
    assert (capture_root / "trajectory" / "trajectory_metadata.json").exists()
    assert (capture_root / "rgb" / "frames" / "Image" / "camera_0" / "Image_0_0_0001_0.png").exists()
    assert (capture_root / "structured_light" / "task" / "structured_light" / "done.txt").exists()
    assert (capture_root / "structured_light" / "frames" / "done.txt").exists()
    assert (capture_root / "config" / "capture_settings.env").exists()

    histogram = json.loads((capture_root / "stats" / "depth_histogram.json").read_text(encoding="utf-8"))
    assert histogram["status"] == "ok"
    assert histogram["depth_file_count"] == 1
    assert histogram["depth_files"] == ["structured_light/task/structured_light/0001_Depth.npy"]
    assert (capture_root / "stats" / "depth_histogram.png").exists()
    assert "Capture root:" in result.stdout
