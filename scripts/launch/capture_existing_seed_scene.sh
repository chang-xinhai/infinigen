#!/bin/bash
# Capture data from an existing benchmark seed scene using a manifest-driven
# structured-light task.
#
# Usage:
#   bash scripts/launch/capture_existing_seed_scene.sh <SCENE_DIR> [SETTING] [--resume] [--resume-from N]
#
# Examples:
#   bash scripts/launch/capture_existing_seed_scene.sh \
#       outputs/benchmark/structured_light_indoors/seed_0 full
#
#   CAPTURE_MANIFEST=infinigen_examples/configs_indoor/capture_manifests/debug.yaml \
#   bash scripts/launch/capture_existing_seed_scene.sh \
#       outputs/benchmark/structured_light_indoors/seed_0 debug

set -euo pipefail

usage() {
    echo "Usage: bash scripts/launch/capture_existing_seed_scene.sh <SCENE_DIR> [SETTING] [--resume] [--resume-from N]"
}

SCENE_DIR=""
SETTING=""
RESUME_CAPTURE=0
RESUME_FROM_FRAME=""
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume)
            RESUME_CAPTURE=1
            shift
            ;;
        --resume-from)
            if [[ $# -lt 2 ]]; then
                usage
                exit 1
            fi
            RESUME_CAPTURE=1
            RESUME_FROM_FRAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

SCENE_DIR="${POSITIONAL_ARGS[0]:-}"
SETTING="${POSITIONAL_ARGS[1]:-${CAPTURE_SETTING:-full}}"

if [[ -z "${SCENE_DIR}" ]]; then
    usage
    exit 1
fi

if [[ -n "${RESUME_FROM_FRAME}" ]] && ! [[ "${RESUME_FROM_FRAME}" =~ ^[0-9]+$ ]]; then
    echo "--resume-from must be a non-negative integer, got: ${RESUME_FROM_FRAME}"
    exit 1
fi

if [[ ! -f "${SCENE_DIR}/coarse/scene.blend" ]]; then
    echo "Expected coarse scene at ${SCENE_DIR}/coarse/scene.blend"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_MANIFEST_DIR="${REPO_ROOT}/infinigen_examples/configs_indoor/capture_manifests"
DEFAULT_CAPTURE_MANIFEST="${DEFAULT_MANIFEST_DIR}/${SETTING}.yaml"

TRAJECTORY_DIR="${TRAJECTORY_DIR:-${SCENE_DIR}/trajectory}"
CAPTURE_ROOT="${CAPTURE_ROOT:-${SCENE_DIR}/capture/${SETTING}}"
CONFIG_DIR="${CONFIG_DIR:-${CAPTURE_ROOT}/config}"
LOG_DIR="${LOG_DIR:-${CAPTURE_ROOT}/logs}"
STATS_DIR="${STATS_DIR:-${CAPTURE_ROOT}/stats}"
OUTPUT_DIR="${OUTPUT_DIR:-${CAPTURE_ROOT}/output}"
STRUCTURED_LIGHT_DIR="${STRUCTURED_LIGHT_DIR:-${CAPTURE_ROOT}/structured_light}"
ARCHIVED_CAPTURE_MANIFEST="${CONFIG_DIR}/capture_manifest.yaml"
ARCHIVED_CAPTURE_SETTINGS="${CONFIG_DIR}/capture_settings.env"

CAPTURE_MANIFEST_SOURCE="setting_default"
if [[ "${RESUME_CAPTURE}" == "1" && -f "${ARCHIVED_CAPTURE_MANIFEST}" ]]; then
    CAPTURE_MANIFEST="${ARCHIVED_CAPTURE_MANIFEST}"
    CAPTURE_MANIFEST_SOURCE="archived_config"
elif [[ "${RESUME_CAPTURE}" == "1" ]]; then
    echo "Warning: archived capture manifest missing at ${ARCHIVED_CAPTURE_MANIFEST}; falling back to configured manifest source" >&2
    if [[ -n "${CAPTURE_MANIFEST:-}" ]]; then
        CAPTURE_MANIFEST_SOURCE="env_override"
    else
        CAPTURE_MANIFEST="${DEFAULT_CAPTURE_MANIFEST}"
        CAPTURE_MANIFEST_SOURCE="setting_default"
    fi
else
    CAPTURE_MANIFEST="${CAPTURE_MANIFEST:-${DEFAULT_CAPTURE_MANIFEST}}"
    if [[ -n "${CAPTURE_MANIFEST:-}" && "${CAPTURE_MANIFEST}" != "${DEFAULT_CAPTURE_MANIFEST}" ]]; then
        CAPTURE_MANIFEST_SOURCE="env_override"
    fi
fi

if [[ ! -f "${CAPTURE_MANIFEST}" ]]; then
    echo "Capture manifest not found: ${CAPTURE_MANIFEST}"
    exit 1
fi

load_archived_capture_settings() {
    local settings_file="$1"
    local key
    local value
    if [[ ! -f "${settings_file}" ]]; then
        echo "Warning: archived capture settings missing at ${settings_file}; using current environment defaults" >&2
        return
    fi

    while IFS='=' read -r key value; do
        if [[ -z "${key}" ]]; then
            continue
        fi
        if [[ "${key}" =~ ^# ]]; then
            continue
        fi
        if [[ -n "${!key+x}" ]]; then
            continue
        fi
        printf -v "${key}" '%s' "${value}"
        export "${key}"
    done <"${settings_file}"
}

if [[ "${RESUME_CAPTURE}" == "1" ]]; then
    load_archived_capture_settings "${ARCHIVED_CAPTURE_SETTINGS}"
fi

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
POST_PYTHON_BIN="${POST_PYTHON_BIN:-python}"

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"
mkdir -p "${MPLCONFIGDIR}"

WALK_CAMERA_HEIGHT_M="${WALK_CAMERA_HEIGHT_M:-1.55}"
WALK_FPS="${WALK_FPS:-3}"
WALK_TRAVERSAL_SPEED_MPS="${WALK_TRAVERSAL_SPEED_MPS:-0.30}"
WALK_ORBIT_SPEED_MPS="${WALK_ORBIT_SPEED_MPS:-0.18}"
WALK_STEP_M="${WALK_STEP_M:-0.10}"
WALK_CLEARANCE_M="${WALK_CLEARANCE_M:-0.20}"
WALK_PATH_MARGIN_M="${WALK_PATH_MARGIN_M:-0.18}"
WALK_PATH_RESOLUTION="${WALK_PATH_RESOLUTION:-160000}"
WALK_ROOM_SWEEP_ANGLE_DEG="${WALK_ROOM_SWEEP_ANGLE_DEG:-180.0}"
WALK_ROOM_SWEEP_YAW_SPEED_DEG_S="${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S:-24.0}"
WALK_ENABLE_ROOM_ORBIT="${WALK_ENABLE_ROOM_ORBIT:-False}"
WALK_ROOM_GRID_STEP_M="${WALK_ROOM_GRID_STEP_M:-0.10}"
WALK_HEIGHT_PERTURBATION_AMPLITUDE_M="${WALK_HEIGHT_PERTURBATION_AMPLITUDE_M:-0.04}"
WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ="${WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ:-0.35}"
WALK_FORCE_OPEN_ACCESS_DOORS="${WALK_FORCE_OPEN_ACCESS_DOORS:-True}"
WALK_FORCE_OPEN_ACCESS_DOORS_MODE="${WALK_FORCE_OPEN_ACCESS_DOORS_MODE:-hide}"

CAPTURE_WIDTH="${CAPTURE_WIDTH:-${RGB_WIDTH:-848}}"
CAPTURE_HEIGHT="${CAPTURE_HEIGHT:-${RGB_HEIGHT:-480}}"
SL_MAX_SAMPLES="${SL_MAX_SAMPLES:-128}"
SL_PATTERN_DIR="${SL_PATTERN_DIR:-}"
SL_PATTERN_WHITE="${SL_PATTERN_WHITE:-white.png}"
RGB_FORCE_LIGHTING="${RGB_FORCE_LIGHTING:-True}"
RGB_WORLD_STRENGTH="${RGB_WORLD_STRENGTH:-0.25}"
RGB_SUN_ENERGY="${RGB_SUN_ENERGY:-1.0}"
RGB_CAMERA_LIGHT_ENERGY="${RGB_CAMERA_LIGHT_ENERGY:-120.0}"
RGB_FORCE_DENOISING="${RGB_FORCE_DENOISING:-True}"
RGB_DISABLE_CAUSTICS="${RGB_DISABLE_CAUSTICS:-True}"
RGB_SAMPLE_CLAMP_INDIRECT="${RGB_SAMPLE_CLAMP_INDIRECT:-0.75}"
RGB_SAMPLE_CLAMP_DIRECT="${RGB_SAMPLE_CLAMP_DIRECT:-2.5}"

DEPTH_HISTOGRAM_ENABLED="${DEPTH_HISTOGRAM_ENABLED:-1}"
DEPTH_HISTOGRAM_BINS="${DEPTH_HISTOGRAM_BINS:-80}"
DEPTH_HISTOGRAM_MIN_M="${DEPTH_HISTOGRAM_MIN_M:-0.0}"
DEPTH_HISTOGRAM_MAX_M="${DEPTH_HISTOGRAM_MAX_M:-10.0}"
DEPTH_HISTOGRAM_SAMPLE_LIMIT="${DEPTH_HISTOGRAM_SAMPLE_LIMIT:-200000}"

REUSE_EXISTING_TRAJECTORY="${REUSE_EXISTING_TRAJECTORY:-1}"
FRAME_RANGE="${FRAME_RANGE:-}"

mkdir -p "${TRAJECTORY_DIR}" "${CAPTURE_ROOT}" "${CONFIG_DIR}" "${LOG_DIR}" "${STATS_DIR}"

RENDER_LOG="${LOG_DIR}/render.log"
CAPTURE_SETTINGS_FILE="${CONFIG_DIR}/capture_settings.env"
CAPTURE_MANIFEST_COPY="${CONFIG_DIR}/capture_manifest.yaml"
DEPTH_HISTOGRAM_JSON="${STATS_DIR}/depth_histogram.json"
DEPTH_HISTOGRAM_PNG="${STATS_DIR}/depth_histogram.png"
CAPTURE_DONE_MARKER="${OUTPUT_DIR}/calibration/capture_complete.json"

TRAJECTORY_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
CAPTURE_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin)

COMMON_OVERRIDES=("compose_indoors.terrain_enabled=False")
TRAJECTORY_OVERRIDES=(
    "animate_whole_home_walk.camera_height_m=${WALK_CAMERA_HEIGHT_M}"
    "animate_whole_home_walk.planner_fps=${WALK_FPS}"
    "animate_whole_home_walk.traversal_speed_mps=${WALK_TRAVERSAL_SPEED_MPS}"
    "animate_whole_home_walk.orbit_speed_mps=${WALK_ORBIT_SPEED_MPS}"
    "animate_whole_home_walk.traversal_point_step_m=${WALK_STEP_M}"
    "animate_whole_home_walk.clearance_m=${WALK_CLEARANCE_M}"
    "animate_whole_home_walk.path_margin_m=${WALK_PATH_MARGIN_M}"
    "animate_whole_home_walk.path_resolution=${WALK_PATH_RESOLUTION}"
    "animate_whole_home_walk.room_sweep_angle_deg=${WALK_ROOM_SWEEP_ANGLE_DEG}"
    "animate_whole_home_walk.room_sweep_yaw_speed_deg_s=${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S}"
    "animate_whole_home_walk.enable_room_orbit=${WALK_ENABLE_ROOM_ORBIT}"
    "animate_whole_home_walk.room_grid_step_m=${WALK_ROOM_GRID_STEP_M}"
    "animate_whole_home_walk.height_perturbation_amplitude_m=${WALK_HEIGHT_PERTURBATION_AMPLITUDE_M}"
    "animate_whole_home_walk.height_perturbation_frequency_hz=${WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ}"
    "animate_whole_home_walk.force_open_access_doors=${WALK_FORCE_OPEN_ACCESS_DOORS}"
    "animate_whole_home_walk.force_open_access_doors_mode=\"${WALK_FORCE_OPEN_ACCESS_DOORS_MODE}\""
)
CAPTURE_OVERRIDES=(
    "execute_tasks.use_scene_frame_range=True"
    "render_structured_light.sl_capture_manifest_path=\"${CAPTURE_MANIFEST}\""
    "render_structured_light.sl_resolution_x=${CAPTURE_WIDTH}"
    "render_structured_light.sl_resolution_y=${CAPTURE_HEIGHT}"
    "render_structured_light.sl_max_samples=${SL_MAX_SAMPLES}"
    "render_structured_light.sl_pattern_white=\"${SL_PATTERN_WHITE}\""
    "render_structured_light.sl_preview_force_lighting=${RGB_FORCE_LIGHTING}"
    "render_structured_light.sl_preview_world_strength=${RGB_WORLD_STRENGTH}"
    "render_structured_light.sl_preview_sun_energy=${RGB_SUN_ENERGY}"
    "render_structured_light.sl_preview_camera_light_energy=${RGB_CAMERA_LIGHT_ENERGY}"
    "render_structured_light.sl_preview_force_denoising=${RGB_FORCE_DENOISING}"
    "render_structured_light.sl_preview_disable_caustics=${RGB_DISABLE_CAUSTICS}"
    "render_structured_light.sl_preview_sample_clamp_indirect=${RGB_SAMPLE_CLAMP_INDIRECT}"
    "render_structured_light.sl_preview_sample_clamp_direct=${RGB_SAMPLE_CLAMP_DIRECT}"
    "render_structured_light.sl_resume=${RESUME_CAPTURE}"
)

if [[ -n "${SL_PATTERN_DIR}" ]]; then
    CAPTURE_OVERRIDES+=("render_structured_light.sl_pattern_dir=\"${SL_PATTERN_DIR}\"")
fi

if [[ -n "${FRAME_RANGE}" ]]; then
    IFS=',' read -r FRAME_START FRAME_END <<<"${FRAME_RANGE}"
    CAPTURE_OVERRIDES=(
        "execute_tasks.use_scene_frame_range=False"
        "execute_tasks.frame_range=[${FRAME_START},${FRAME_END}]"
        "render_structured_light.sl_frame_index_offset=${FRAME_START}"
        "${CAPTURE_OVERRIDES[@]:1}"
    )
fi

if [[ -n "${RESUME_FROM_FRAME}" ]]; then
    CAPTURE_OVERRIDES+=("render_structured_light.sl_resume_from_frame=${RESUME_FROM_FRAME}")
fi

append_log_header() {
    local stage="$1"
    {
        echo ""
        echo "================================================================"
        echo "### ${stage}"
        echo "================================================================"
    } >>"${RENDER_LOG}"
}

write_capture_settings() {
    {
        echo "SCENE_DIR=${SCENE_DIR}"
        echo "SCENE_SEED=${SCENE_SEED}"
        echo "SETTING=${SETTING}"
        echo "CAPTURE_MANIFEST=${CAPTURE_MANIFEST}"
        echo "CAPTURE_MANIFEST_SOURCE=${CAPTURE_MANIFEST_SOURCE}"
        echo "TRAJECTORY_DIR=${TRAJECTORY_DIR}"
        echo "CAPTURE_ROOT=${CAPTURE_ROOT}"
        echo "OUTPUT_DIR=${OUTPUT_DIR}"
        echo "STRUCTURED_LIGHT_DIR=${STRUCTURED_LIGHT_DIR}"
        echo "RESUME_CAPTURE=${RESUME_CAPTURE}"
        if [[ -n "${RESUME_FROM_FRAME}" ]]; then
            echo "RESUME_FROM_FRAME=${RESUME_FROM_FRAME}"
        fi
        echo "CAPTURE_WIDTH=${CAPTURE_WIDTH}"
        echo "CAPTURE_HEIGHT=${CAPTURE_HEIGHT}"
        echo "SL_MAX_SAMPLES=${SL_MAX_SAMPLES}"
        echo "RGB_FORCE_LIGHTING=${RGB_FORCE_LIGHTING}"
        echo "RGB_WORLD_STRENGTH=${RGB_WORLD_STRENGTH}"
        echo "RGB_SUN_ENERGY=${RGB_SUN_ENERGY}"
        echo "RGB_CAMERA_LIGHT_ENERGY=${RGB_CAMERA_LIGHT_ENERGY}"
        echo "RGB_FORCE_DENOISING=${RGB_FORCE_DENOISING}"
        echo "RGB_DISABLE_CAUSTICS=${RGB_DISABLE_CAUSTICS}"
        echo "RGB_SAMPLE_CLAMP_INDIRECT=${RGB_SAMPLE_CLAMP_INDIRECT}"
        echo "RGB_SAMPLE_CLAMP_DIRECT=${RGB_SAMPLE_CLAMP_DIRECT}"
        echo "WALK_FPS=${WALK_FPS}"
        echo "WALK_TRAVERSAL_SPEED_MPS=${WALK_TRAVERSAL_SPEED_MPS}"
        echo "WALK_STEP_M=${WALK_STEP_M}"
        if [[ -n "${FRAME_RANGE}" ]]; then
            echo "FRAME_RANGE=${FRAME_RANGE}"
        fi
    } >"${CAPTURE_SETTINGS_FILE}"

    if [[ "$(realpath "${CAPTURE_MANIFEST}")" != "$(realpath "${CAPTURE_MANIFEST_COPY}")" ]]; then
        cp "${CAPTURE_MANIFEST}" "${CAPTURE_MANIFEST_COPY}"
    fi
}

print_header() {
    echo "═══════════════════════════════════════════════════════════"
    echo "  Existing Seed Scene Capture"
    echo "  Scene dir: ${SCENE_DIR}"
    echo "  Setting: ${SETTING}"
    echo "  Scene seed: ${SCENE_SEED}"
    echo "  Trajectory dir: ${TRAJECTORY_DIR}"
    echo "  Capture root: ${CAPTURE_ROOT}"
    echo "  Manifest: ${CAPTURE_MANIFEST}"
    echo "  Manifest source: ${CAPTURE_MANIFEST_SOURCE}"
    echo "  Resolution: ${CAPTURE_WIDTH}x${CAPTURE_HEIGHT}"
    echo "  SL max samples: ${SL_MAX_SAMPLES}"
    echo "  Resume capture: ${RESUME_CAPTURE}"
    if [[ -n "${RESUME_FROM_FRAME}" ]]; then
        echo "  Resume from frame: ${RESUME_FROM_FRAME}"
    fi
    if [[ -n "${FRAME_RANGE}" ]]; then
        echo "  Frame range override: ${FRAME_RANGE}"
    fi
    echo "═══════════════════════════════════════════════════════════"
}

run_trajectory() {
    if [[ "${REUSE_EXISTING_TRAJECTORY}" == "1" && -f "${TRAJECTORY_DIR}/scene.blend" ]]; then
        echo "Reusing trajectory scene at ${TRAJECTORY_DIR}/scene.blend"
        return
    fi

    append_log_header "Trajectory"
    "${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task trajectory \
        --input_folder "${SCENE_DIR}/coarse" \
        --output_folder "${TRAJECTORY_DIR}" \
        -g "${TRAJECTORY_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${TRAJECTORY_OVERRIDES[@]}" \
        >>"${RENDER_LOG}" 2>&1
}

run_capture() {
    append_log_header "Structured Light Capture"
    rm -f "${CAPTURE_DONE_MARKER}"
    "${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task structured_light \
        --input_folder "${TRAJECTORY_DIR}" \
        --output_folder "${CAPTURE_ROOT}" \
        -g "${CAPTURE_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${CAPTURE_OVERRIDES[@]}" \
        >>"${RENDER_LOG}" 2>&1
}

write_done_marker() {
    mkdir -p "$(dirname "${CAPTURE_DONE_MARKER}")"
    cat >"${CAPTURE_DONE_MARKER}" <<EOF
{"status":"complete","setting":"${SETTING}","scene_seed":"${SCENE_SEED}"}
EOF
}

run_depth_histogram() {
    if [[ "${DEPTH_HISTOGRAM_ENABLED}" != "1" ]]; then
        echo "Skipping depth histogram because DEPTH_HISTOGRAM_ENABLED=${DEPTH_HISTOGRAM_ENABLED}"
        return
    fi

    append_log_header "Depth Histogram"
    "${POST_PYTHON_BIN}" scripts/scene_depth_histogram.py \
        --capture-root "${CAPTURE_ROOT}" \
        --output-json "${DEPTH_HISTOGRAM_JSON}" \
        --output-png "${DEPTH_HISTOGRAM_PNG}" \
        --bins "${DEPTH_HISTOGRAM_BINS}" \
        --min-depth-m "${DEPTH_HISTOGRAM_MIN_M}" \
        --max-depth-m "${DEPTH_HISTOGRAM_MAX_M}" \
        --quantile-sample-limit "${DEPTH_HISTOGRAM_SAMPLE_LIMIT}" \
        >>"${RENDER_LOG}" 2>&1
}

print_summary() {
    echo "### Summary"
    echo "Trajectory scene: ${TRAJECTORY_DIR}/scene.blend"
    echo "Capture root: ${CAPTURE_ROOT}"
    echo "Manifest copy: ${CAPTURE_MANIFEST_COPY}"
    echo "Settings file: ${CAPTURE_SETTINGS_FILE}"
    if [[ -d "${OUTPUT_DIR}" ]]; then
        echo "Output dir: ${OUTPUT_DIR}"
    fi
    if [[ -d "${STRUCTURED_LIGHT_DIR}/patterns" ]]; then
        echo "Pattern dir: ${STRUCTURED_LIGHT_DIR}/patterns"
    fi
    if [[ -f "${OUTPUT_DIR}/calibration/calibration.npz" ]]; then
        echo "Calibration npz: ${OUTPUT_DIR}/calibration/calibration.npz"
    fi
    if [[ -f "${OUTPUT_DIR}/calibration/calibration.jsonl" ]]; then
        echo "Calibration jsonl: ${OUTPUT_DIR}/calibration/calibration.jsonl"
    fi
    if [[ -f "${CAPTURE_DONE_MARKER}" ]]; then
        echo "Done marker: ${CAPTURE_DONE_MARKER}"
    fi
    if [[ -f "${DEPTH_HISTOGRAM_JSON}" ]]; then
        echo "Depth histogram json: ${DEPTH_HISTOGRAM_JSON}"
    fi
    if [[ -f "${DEPTH_HISTOGRAM_PNG}" ]]; then
        echo "Depth histogram png: ${DEPTH_HISTOGRAM_PNG}"
    fi
    echo "Render log: ${RENDER_LOG}"
}

prune_empty_dirs() {
    rmdir "${CAPTURE_ROOT}/assets" 2>/dev/null || true
    rmdir "${STATS_DIR}" 2>/dev/null || true
}

if [[ "${RESUME_CAPTURE}" != "1" ]]; then
    : >"${RENDER_LOG}"
else
    touch "${RENDER_LOG}"
fi
write_capture_settings
print_header
run_trajectory
run_capture
run_depth_histogram
write_done_marker
prune_empty_dirs
print_summary
