import os
import stat
import subprocess
from pathlib import Path

import infinigen


FAKE_ALIYUNPAN_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

remote_root="${FAKE_REMOTE_ROOT:?}"
cmd="$1"
shift

copy_path() {
    local src="$1"
    local dst="$2"
    mkdir -p "$(dirname "$dst")"
    if [[ -d "$src" ]]; then
        rm -rf "$dst"
        cp -R "$src" "$dst"
    else
        cp "$src" "$dst"
    fi
}

delay_if_requested() {
    local delay="$1"
    if [[ -n "$delay" ]]; then
        sleep "$delay"
    fi
}

case "$cmd" in
    mkdir)
        mkdir -p "$remote_root/$1"
        ;;
    rm)
        rm -rf "$remote_root/$1"
        ;;
    upload)
        delay_if_requested "${FAKE_ALIYUNPAN_DELAY_UPLOAD_SEC:-}"
        local_path="$1"
        remote_parent="$2"
        mkdir -p "$remote_root/$remote_parent"
        copy_path "$local_path" "$remote_root/$remote_parent/$(basename "$local_path")"
        ;;
    download)
        delay_if_requested "${FAKE_ALIYUNPAN_DELAY_DOWNLOAD_SEC:-}"
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

        copy_path "$remote_root/$remote_path" "$saveto/$remote_path"
        ;;
    *)
        exit 0
        ;;
esac
"""


def _make_fake_aliyunpan(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    bin_dir = tmp_path / "bin"
    remote_root = tmp_path / "remote"
    fake_aliyunpan = bin_dir / "aliyunpan"

    bin_dir.mkdir()
    remote_root.mkdir()
    fake_aliyunpan.write_text(FAKE_ALIYUNPAN_SCRIPT, encoding="utf-8")
    fake_aliyunpan.chmod(fake_aliyunpan.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_REMOTE_ROOT"] = str(remote_root)
    return remote_root, env


def test_sync_download_rewrites_aliyunpan_absolute_path_layout(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/sync.sh"
    workspace = tmp_path / "workspace"
    remote_root, env = _make_fake_aliyunpan(tmp_path)
    rel_path = "outputs/benchmark/structured_light_indoors/seed_0"
    expected_target = workspace / rel_path

    workspace.mkdir()
    (remote_root / "Research/infinigen" / rel_path).mkdir(parents=True)
    (remote_root / "Research/infinigen" / rel_path / "payload.txt").write_text(
        "payload",
        encoding="utf-8",
    )

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


def test_sync_upload_tar_creates_remote_bundle_directory(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/sync.sh"
    workspace = tmp_path / "workspace"
    remote_root, env = _make_fake_aliyunpan(tmp_path)
    rel_path = "outputs/benchmark/structured_light_indoors/seed_0"
    local_target = workspace / rel_path
    remote_bundle = (
        remote_root
        / "Research/infinigen/outputs/benchmark/structured_light_indoors"
        / "seed_0.__sync_tar__"
    )

    local_target.mkdir(parents=True)
    (local_target / "frame_0001.txt").write_text("hello", encoding="utf-8")
    (local_target / "frame_0002.txt").write_text("world", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(script_path), "upload", "--tar", rel_path],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert remote_bundle.is_dir()

    manifest = (remote_bundle / "manifest.txt").read_text(encoding="utf-8")
    assert "REL_PATH=outputs/benchmark/structured_light_indoors/seed_0" in manifest
    assert "SOURCE_KIND=directory" in manifest

    checksum_file = remote_bundle / "sha256sums.txt"
    assert checksum_file.exists()
    part_files = sorted(remote_bundle.glob("seed_0.tar.zst.part-*"))
    assert len(part_files) == 1
    assert part_files[0].stat().st_size > 0


def test_sync_download_tar_restores_bundle_and_replaces_existing_target(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/sync.sh"
    workspace = tmp_path / "workspace"
    remote_root, env = _make_fake_aliyunpan(tmp_path)
    rel_path = "outputs/benchmark/structured_light_indoors/seed_0"
    local_target = workspace / rel_path
    remote_bundle = (
        remote_root
        / "Research/infinigen/outputs/benchmark/structured_light_indoors"
        / "seed_0.__sync_tar__"
    )

    workspace.mkdir()
    local_target.mkdir(parents=True)
    (local_target / "stale.txt").write_text("stale", encoding="utf-8")

    archive_path = tmp_path / "seed_0.tar.zst"
    remote_bundle.mkdir(parents=True)
    archive_root = tmp_path / "archive_root"
    archived_target = archive_root / rel_path
    archived_target.mkdir(parents=True)
    (archived_target / "restored.txt").write_text("fresh", encoding="utf-8")

    tar_result = subprocess.run(
        [
            "tar",
            "-I",
            "zstd -19 -T0",
            "-cf",
            str(archive_path),
            "-C",
            str(archive_root),
            rel_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tar_result.returncode == 0, tar_result.stderr

    part_path = remote_bundle / "seed_0.tar.zst.part-0000"
    part_path.write_bytes(archive_path.read_bytes())
    checksum_result = subprocess.run(
        ["sha256sum", part_path.name],
        cwd=remote_bundle,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checksum_result.returncode == 0, checksum_result.stderr
    (remote_bundle / "sha256sums.txt").write_text(checksum_result.stdout, encoding="utf-8")
    (remote_bundle / "manifest.txt").write_text(
        "\n".join(
            [
                "VERSION=1",
                f"REL_PATH={rel_path}",
                "SOURCE_KIND=directory",
                "ENTRY_NAME=seed_0",
                "ARCHIVE_NAME=seed_0.tar.zst",
                "PART_COUNT=1",
                "PART_SIZE=5G",
                "COMPRESSION=zstd -19 -T0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(script_path), "download", "--tar", rel_path],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (local_target / "stale.txt").exists()
    assert (local_target / "restored.txt").read_text(encoding="utf-8") == "fresh"


def test_sync_upload_tar_emits_progress_heartbeat(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/sync.sh"
    workspace = tmp_path / "workspace"
    _, env = _make_fake_aliyunpan(tmp_path)
    rel_path = "outputs/benchmark/structured_light_indoors/seed_0"
    local_target = workspace / rel_path

    workspace.mkdir()
    local_target.mkdir(parents=True)
    (local_target / "frame_0001.txt").write_text("hello", encoding="utf-8")

    env["SYNC_PROGRESS_INTERVAL_SECONDS"] = "1"
    env["FAKE_ALIYUNPAN_DELAY_UPLOAD_SEC"] = "2"

    result = subprocess.run(
        ["bash", str(script_path), "upload", "--tar", rel_path],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Preparing tar bundle upload" in result.stdout
    assert "Uploading tar bundle" in result.stdout
    assert "still running" in result.stdout
