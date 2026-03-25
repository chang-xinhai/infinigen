#!/bin/bash

set -euo pipefail

usage() {
    echo "Usage: bash scripts/benchmark/neural_rgbd/preview_neural_rgbd_trajectory.sh <OUTPUT_ROOT>"
}

OUTPUT_ROOT="${1:-}"
if [[ -z "${OUTPUT_ROOT}" ]]; then
    usage
    exit 1
fi

if [[ "${OUTPUT_ROOT}" == "-h" || "${OUTPUT_ROOT}" == "--help" ]]; then
    usage
    exit 0
fi

TRAJECTORY_BLEND="${OUTPUT_ROOT}/trajectory/scene.blend"
if [[ ! -f "${TRAJECTORY_BLEND}" ]]; then
    echo "Expected Neural RGB-D trajectory scene at ${TRAJECTORY_BLEND}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
BLENDER_PREVIEW_SCRIPT="${REPO_ROOT}/scripts/blender_trajectory_preview.py"

resolve_blender_cmd() {
    if [[ -n "${BLENDER_BIN:-}" ]]; then
        BLENDER_CMD=("${BLENDER_BIN}")
        return
    fi

    if command -v blender >/dev/null 2>&1; then
        BLENDER_CMD=("$(command -v blender)")
        return
    fi

    echo "Could not find Blender. Set BLENDER_BIN explicitly."
    exit 1
}

declare -a BLENDER_CMD=()
resolve_blender_cmd

"${BLENDER_CMD[@]}" "${TRAJECTORY_BLEND}" \
    --python "${BLENDER_PREVIEW_SCRIPT}" \
    -- \
    --scene-blend "${TRAJECTORY_BLEND}"
