import os
import stat
import subprocess
from pathlib import Path

import infinigen


def test_sync_download_rewrites_aliyunpan_absolute_path_layout(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/sync.sh"
    workspace = tmp_path / "workspace"
    bin_dir = tmp_path / "bin"
    fake_aliyunpan = bin_dir / "aliyunpan"
    rel_path = "outputs/benchmark/structured_light_indoors/seed_0"
    expected_target = workspace / rel_path

    bin_dir.mkdir()
    workspace.mkdir()

    fake_aliyunpan.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" != "download" ]]; then
    exit 0
fi

shift
saveto=""
remote_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --saveto)
            saveto="$2"
            shift 2
            ;;
        *)
            remote_path="$1"
            shift
            ;;
    esac
done

downloaded_path="$saveto/$remote_path"
mkdir -p "$downloaded_path"
touch "$downloaded_path/payload.txt"
""",
        encoding="utf-8",
    )
    fake_aliyunpan.chmod(fake_aliyunpan.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(script_path), "download", rel_path],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert expected_target.is_dir()
    assert (expected_target / "payload.txt").exists()
    assert not (workspace / "outputs/benchmark/structured_light_indoors/Research").exists()
