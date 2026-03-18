# Copyright (C) 2026.

import os
import stat
import subprocess

import infinigen


def test_submit_script_executes_payload_directly_by_default():
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts" / "submit.sh"

    env = os.environ.copy()
    env["SUBMIT_TEST_MARKER"] = "direct-launch"

    result = subprocess.run(
        ["bash", str(script_path), "bash", "-lc", 'printf "%s" "${SUBMIT_TEST_MARKER}"'],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "[submit.sh] launching payload directly inside batch allocation" in result.stdout
    assert result.stdout.rstrip().endswith("direct-launch")


def test_submit_script_uses_srun_when_requested(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts" / "submit.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_srun = fake_bin / "srun"
    srun_log = tmp_path / "fake_srun.log"

    fake_srun.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'fake_srun:%s\\n' "$*" >>"${SRUN_LOG}"
exec "$@"
""",
        encoding="utf-8",
    )
    fake_srun.chmod(fake_srun.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SUBMIT_USE_SRUN": "1",
            "SRUN_LOG": str(srun_log),
            "SUBMIT_TEST_MARKER": "srun-launch",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path), "bash", "-lc", 'printf "%s" "${SUBMIT_TEST_MARKER}"'],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "[submit.sh] launching payload with srun" in result.stdout
    assert result.stdout.rstrip().endswith("srun-launch")
    assert srun_log.read_text(encoding="utf-8").strip().startswith("fake_srun:bash -lc")
