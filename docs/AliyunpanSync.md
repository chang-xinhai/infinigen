# Aliyunpan Sync Script

This repository provides a thin wrapper script for uploading and downloading result folders with `aliyunpan`.

## Script

```bash
bash scripts/sync.sh upload outputs/benchmark/structured_light_indoors/seed_0
bash scripts/sync.sh download outputs/benchmark/structured_light_indoors/seed_0
```

## Path Mapping

The script always treats the argument as a repository-relative path.

Example:

- Local relative path: `outputs/benchmark/structured_light_indoors/seed_0`
- Remote full path: `/Research/infinigen/outputs/benchmark/structured_light_indoors/seed_0`

Upload behavior:

- The script creates remote parent directories under `/Research/infinigen` if needed.
- It uploads the local file or directory to the corresponding remote parent directory, preserving the final basename.

Download behavior:

- The script downloads the remote file or directory from `/Research/infinigen/...`
- It restores the same relative path under the current repository checkout.
- If `aliyunpan download --saveto` recreates the remote absolute path prefix such as `Research/infinigen/...` under the local target, the script moves the downloaded file or directory back to the requested relative path and removes the empty intermediate directories.

## Requirements

- `aliyunpan` must already be installed and logged in on the machine running the script.
- The target path argument must be relative to the repository root.
- Parent traversal such as `../` is rejected.

## Notes

- The script does not change `aliyunpan` account, drive, or config state.
- If you use a custom `ALIYUNPAN_CONFIG_DIR`, export it before invoking the script.
