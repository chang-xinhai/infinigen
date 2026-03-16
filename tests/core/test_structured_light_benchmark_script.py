# Copyright (C) 2024, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory
# of this source tree.

import os
import stat
import subprocess
from pathlib import Path

import infinigen


def test_benchmark_script_continues_after_seed_failure(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/launch/structured_light_indoors_benchmark.sh"
    fake_python = tmp_path / "fake_python.sh"
    output_root = tmp_path / "benchmark_outputs"

    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

seed=""
task=""
output_folder=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m)
            shift 2
            ;;
        --seed)
            seed="$2"
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
        --input_folder)
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

if [[ "$task" == "coarse" ]]; then
    if [[ "$seed" == "1" ]]; then
        echo "simulated coarse failure for seed $seed" >&2
        exit 7
    fi
    touch "$output_folder/scene.blend"
    exit 0
fi

if [[ "$task" == "render" ]]; then
    touch "$output_folder/render_complete.txt"
    exit 0
fi

if [[ "$task" == "structured_light" ]]; then
    mkdir -p "$output_folder/structured_light"
    touch "$output_folder/structured_light/done.txt"
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
            "NUM_SCENES": "3",
            "SEED_START": "0",
            "PARALLEL_MODE": "coarse_only",
            "MAX_PARALLEL_SCENES": "2",
            "OUTPUT_ROOT": str(output_root),
            "PYTHON_BIN": str(fake_python),
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

    assert result.returncode == 1

    summary_file = output_root / "logs/benchmark_summary.tsv"
    assert summary_file.exists()

    summary = summary_file.read_text(encoding="utf-8")
    assert "0\tsuccess\tsuccess" in summary
    assert "1\tfailed(7)\tskipped" in summary
    assert "2\tsuccess\tsuccess" in summary

    assert (output_root / "seed_0/sl_frames/structured_light/done.txt").exists()
    assert (output_root / "seed_2/sl_frames/structured_light/done.txt").exists()
    assert "Skipping post-processing for seed=1" in result.stdout
