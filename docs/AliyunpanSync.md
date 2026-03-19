# Aliyunpan Sync Script

This repository provides a small wrapper around `aliyunpan` for repository-relative upload and download workflows.

## Script

```bash
bash scripts/sync.sh upload outputs/benchmark/structured_light_indoors/seed_0
bash scripts/sync.sh download outputs/benchmark/structured_light_indoors/seed_0

bash scripts/sync.sh upload --tar outputs/benchmark/structured_light_indoors/seed_0
bash scripts/sync.sh download --tar outputs/benchmark/structured_light_indoors/seed_0
```

## Path Mapping

The script always treats the argument as a repository-relative path.

Example:

- Local relative path: `outputs/benchmark/structured_light_indoors/seed_0`
- Remote full path: `/Research/infinigen/outputs/benchmark/structured_light_indoors/seed_0`

Default mode behavior:

- `upload` creates remote parent directories under `/Research/infinigen` if needed.
- `upload` then uploads the local file or directory to the corresponding remote parent directory, preserving the final basename.
- `download` fetches the remote file or directory from `/Research/infinigen/...`
- `download` restores the same relative path under the current repository checkout.
- If `aliyunpan download --saveto` recreates the remote absolute path prefix such as `Research/infinigen/...` under the local target, the script moves the downloaded file or directory back to the requested relative path and removes the empty intermediate directories.

## Tar Mode

Use `--tar` when the target contains many small files and direct `aliyunpan upload/download` is unreliable.

Tar mode behavior:

- `upload --tar` creates a high-compression `tar.zst` stream with `zstd -19 -T0`
- The tar stream is split into `5G` parts
- The parts, `manifest.txt`, and `sha256sums.txt` are uploaded as a remote bundle directory:
  `/Research/infinigen/<parent>/<basename>.__sync_tar__/`
- Re-uploading the same tar bundle path replaces the previous remote bundle directory
- `download --tar` downloads the remote bundle directory, validates part checksums, removes the existing local target path if it exists, and extracts the archive back into the repository root
- The extracted local path matches the original repository-relative target path

Operational consequence:

- If you upload with `--tar`, use `download --tar` to restore that target. The cloud-side representation is intentionally an implementation detail.

## Requirements

- `aliyunpan` must already be installed and logged in on the machine running the script.
- The target path argument must be relative to the repository root.
- Parent traversal such as `../` is rejected.
- `--tar` mode also requires `tar`, `zstd`, `split`, and `sha256sum`.

## Notes

- The script does not change `aliyunpan` account, drive, or config state.
- If you use a custom `ALIYUNPAN_CONFIG_DIR`, export it before invoking the script.
- `download --tar` replaces any existing local file or directory at the requested path before extraction so stale files do not survive from an older local copy.
- Long-running upload, download, tar creation, checksum verification, and extraction steps emit timestamped progress logs.
- You can tune the heartbeat interval with `SYNC_PROGRESS_INTERVAL_SECONDS`, for example:
  `SYNC_PROGRESS_INTERVAL_SECONDS=10 bash scripts/sync.sh upload --tar outputs/benchmark/structured_light_indoors/`
