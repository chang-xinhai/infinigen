#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
CONDA_ENV="${CONDA_ENV:-}"

if [[ -n "${CONDA_ENV}" ]]; then
    exec conda run -n "${CONDA_ENV}" python \
        "${REPO_ROOT}/scripts/benchmark/neural_rgbd/run_neural_rgbd.py" \
        "$@"
else
    exec "${PYTHON_BIN}" \
        "${REPO_ROOT}/scripts/benchmark/neural_rgbd/run_neural_rgbd.py" \
        "$@"
fi
