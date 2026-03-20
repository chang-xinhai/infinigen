#!/bin/bash
# Generate or reuse a trajectory scene for an existing seed and launch Blender
# in interactive preview mode so camera motion can be inspected without running
# the full structured-light capture.
#
# Usage:
#   BLENDER_BIN=/home/xinhai/blender/blender \
#   bash scripts/launch/preview_existing_seed_trajectory.sh <SCENE_DIR> [SETTING]
#
# Examples:
#   bash scripts/launch/preview_existing_seed_trajectory.sh \
#       outputs/benchmark/structured_light_indoors/seed_42 test_traj
#
#   REUSE_EXISTING_TRAJECTORY=1 BLENDER_VIEWPORT_SHADING=RENDERED \
#   bash scripts/launch/preview_existing_seed_trajectory.sh \
#       outputs/benchmark/structured_light_indoors/seed_42 full

set -euo pipefail

usage() {
    echo "Usage: bash scripts/launch/preview_existing_seed_trajectory.sh <SCENE_DIR> [SETTING]"
}

SCENE_DIR="${1:-}"
SETTING="${2:-${TRAJECTORY_PREVIEW_SETTING:-test_traj}}"

if [[ -z "${SCENE_DIR}" ]]; then
    usage
    exit 1
fi

if [[ "${SCENE_DIR}" == "-h" || "${SCENE_DIR}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ ! -f "${SCENE_DIR}/coarse/scene.blend" ]]; then
    echo "Expected coarse scene at ${SCENE_DIR}/coarse/scene.blend"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SETTING_GIN_CONFIG="${REPO_ROOT}/infinigen_examples/configs_indoor/${SETTING}.gin"
BLENDER_PREVIEW_SCRIPT="${REPO_ROOT}/scripts/blender_trajectory_preview.py"

SCENE_SEED="${SCENE_SEED:-}"
if [[ -z "${SCENE_SEED}" ]]; then
    SCENE_BASENAME="$(basename "${SCENE_DIR}")"
    if [[ "${SCENE_BASENAME}" =~ ^seed_([0-9]+)$ ]]; then
        SCENE_SEED="${BASH_REMATCH[1]}"
    else
        echo "Failed to infer scene seed from ${SCENE_DIR}. Set SCENE_SEED explicitly."
        exit 1
    fi
fi

CONDA_ENV="${CONDA_ENV:-}"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -n "${CONDA_ENV}" ]]; then
    PY_CMD=(conda run -n "${CONDA_ENV}" python)
else
    PY_CMD=("${PYTHON_BIN}")
fi

if [[ -z "${REUSE_EXISTING_TRAJECTORY+x}" ]]; then
    REUSE_EXISTING_TRAJECTORY=0
fi

TRAJECTORY_DIR="${TRAJECTORY_DIR:-${SCENE_DIR}/trajectory}"
PREVIEW_LOG_FILE="${PREVIEW_LOG_FILE:-/tmp/infinigen_trajectory_preview_seed_${SCENE_SEED}_${SETTING}.log}"

BLENDER_VIEWPORT_SHADING="${BLENDER_VIEWPORT_SHADING:-MATERIAL}"
BLENDER_RENDER_ENGINE="${BLENDER_RENDER_ENGINE:-BLENDER_EEVEE}"
BLENDER_AUTO_PLAY="${BLENDER_AUTO_PLAY:-1}"
BLENDER_HIDE_OVERLAYS="${BLENDER_HIDE_OVERLAYS:-1}"
BLENDER_UNHIDE_RENDERABLES="${BLENDER_UNHIDE_RENDERABLES:-1}"

TRAJECTORY_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
if [[ -f "${SETTING_GIN_CONFIG}" ]]; then
    TRAJECTORY_CONFIGS+=("${SETTING}.gin")
fi

print_header() {
    echo "═══════════════════════════════════════════════════════════"
    echo "  Existing Seed Trajectory Preview"
    echo "  Scene dir: ${SCENE_DIR}"
    echo "  Setting: ${SETTING}"
    echo "  Scene seed: ${SCENE_SEED}"
    echo "  Trajectory dir: ${TRAJECTORY_DIR}"
    echo "  Reuse existing trajectory: ${REUSE_EXISTING_TRAJECTORY}"
    echo "  Viewport shading: ${BLENDER_VIEWPORT_SHADING}"
    echo "  Render engine: ${BLENDER_RENDER_ENGINE}"
    echo "  Preview log: ${PREVIEW_LOG_FILE}"
    echo "═══════════════════════════════════════════════════════════"
}

resolve_blender_cmd() {
    if [[ -n "${BLENDER_BIN:-}" ]]; then
        BLENDER_CMD=("${BLENDER_BIN}")
        return
    fi

    local bundled_blender=""
    if bundled_blender="$("${PY_CMD[@]}" -c 'from infinigen.launch_blender import get_standalone_blender_path; print(get_standalone_blender_path())' 2>/dev/null)"; then
        BLENDER_CMD=("${bundled_blender}")
        return
    fi

    local path_blender=""
    if path_blender="$(command -v blender 2>/dev/null)"; then
        BLENDER_CMD=("${path_blender}")
        return
    fi

    if command -v flatpak >/dev/null 2>&1 && flatpak info org.blender.Blender >/dev/null 2>&1; then
        BLENDER_CMD=(flatpak run org.blender.Blender)
        return
    fi

    echo "Could not find Blender."
    echo "Tried:"
    echo "  1. BLENDER_BIN environment variable"
    echo "  2. Repository bundled Blender via infinigen.launch_blender"
    echo "  3. 'blender' in PATH"
    echo "  4. Flatpak app 'org.blender.Blender'"
    echo "Set BLENDER_BIN explicitly if Blender is installed elsewhere."
    exit 1
}

run_trajectory() {
    if [[ "${REUSE_EXISTING_TRAJECTORY}" == "1" && -f "${TRAJECTORY_DIR}/scene.blend" ]]; then
        echo "Reusing trajectory scene at ${TRAJECTORY_DIR}/scene.blend"
        return
    fi

    mkdir -p "${TRAJECTORY_DIR}"

    if [[ -f "${TRAJECTORY_DIR}/scene.blend" ]]; then
        echo "Regenerating trajectory scene at ${TRAJECTORY_DIR}/scene.blend"
    else
        echo "Generating trajectory scene at ${TRAJECTORY_DIR}/scene.blend"
    fi

    : > "${PREVIEW_LOG_FILE}"
    local cmd=("${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task trajectory \
        --input_folder "${SCENE_DIR}/coarse" \
        --output_folder "${TRAJECTORY_DIR}" \
        -g "${TRAJECTORY_CONFIGS[@]}")
    "${cmd[@]}" >>"${PREVIEW_LOG_FILE}" 2>&1

    if [[ ! -f "${TRAJECTORY_DIR}/scene.blend" ]]; then
        echo "Trajectory generation completed without producing ${TRAJECTORY_DIR}/scene.blend"
        exit 1
    fi
}

launch_blender_preview() {
    local trajectory_blend="${TRAJECTORY_DIR}/scene.blend"

    echo "Launching Blender preview from ${trajectory_blend}"

    "${BLENDER_CMD[@]}" "${trajectory_blend}" \
        --python "${BLENDER_PREVIEW_SCRIPT}" \
        -- \
        --scene-blend "${trajectory_blend}" \
        --shading "${BLENDER_VIEWPORT_SHADING}" \
        --render-engine "${BLENDER_RENDER_ENGINE}" \
        --autoplay "${BLENDER_AUTO_PLAY}" \
        --hide-overlays "${BLENDER_HIDE_OVERLAYS}" \
        --unhide-renderables "${BLENDER_UNHIDE_RENDERABLES}"
}

print_header
run_trajectory
declare -a BLENDER_CMD=()
resolve_blender_cmd
launch_blender_preview
