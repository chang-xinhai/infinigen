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
    echo "Env:"
    echo "  CAPTURE_LOG_MODE   compact (default), full, or none"
    echo "  CAPTURE_LOG_LINES  Number of first/last lines kept in compact mode (default: 100)"
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
SETTING_GIN_CONFIG="${REPO_ROOT}/infinigen_examples/configs_indoor/${SETTING}.gin"

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

DEPTH_HISTOGRAM_ENABLED="${DEPTH_HISTOGRAM_ENABLED:-1}"
DEPTH_HISTOGRAM_BINS="${DEPTH_HISTOGRAM_BINS:-80}"
DEPTH_HISTOGRAM_MIN_M="${DEPTH_HISTOGRAM_MIN_M:-0.0}"
DEPTH_HISTOGRAM_MAX_M="${DEPTH_HISTOGRAM_MAX_M:-10.0}"
DEPTH_HISTOGRAM_SAMPLE_LIMIT="${DEPTH_HISTOGRAM_SAMPLE_LIMIT:-200000}"
CAPTURE_LOG_MODE="${CAPTURE_LOG_MODE:-compact}"
CAPTURE_LOG_LINES="${CAPTURE_LOG_LINES:-100}"

if [[ "${CAPTURE_LOG_MODE}" != "compact" && "${CAPTURE_LOG_MODE}" != "full" && "${CAPTURE_LOG_MODE}" != "none" ]]; then
    echo "CAPTURE_LOG_MODE must be one of compact, full, none; got: ${CAPTURE_LOG_MODE}"
    exit 1
fi

if ! [[ "${CAPTURE_LOG_LINES}" =~ ^[0-9]+$ ]] || [[ "${CAPTURE_LOG_LINES}" -lt 1 ]]; then
    echo "CAPTURE_LOG_LINES must be a positive integer, got: ${CAPTURE_LOG_LINES}"
    exit 1
fi

if [[ -z "${REUSE_EXISTING_TRAJECTORY+x}" ]]; then
    if [[ "${SETTING}" == "test_traj" ]]; then
        REUSE_EXISTING_TRAJECTORY=0
    else
        REUSE_EXISTING_TRAJECTORY=1
    fi
fi
FRAME_RANGE="${FRAME_RANGE:-}"

mkdir -p "${TRAJECTORY_DIR}" "${CAPTURE_ROOT}" "${CONFIG_DIR}" "${LOG_DIR}" "${STATS_DIR}"

RENDER_LOG="${LOG_DIR}/render.log"
RENDER_LOG_HEAD="${LOG_DIR}/render.head.log"
RENDER_LOG_TAIL="${LOG_DIR}/render.tail.log"
RENDER_LOG_COUNT="${LOG_DIR}/render.line_count"
CAPTURE_SETTINGS_FILE="${CONFIG_DIR}/capture_settings.env"
CAPTURE_MANIFEST_COPY="${CONFIG_DIR}/capture_manifest.yaml"
DEPTH_HISTOGRAM_JSON="${STATS_DIR}/depth_histogram.json"
DEPTH_HISTOGRAM_PNG="${STATS_DIR}/depth_histogram.png"
CAPTURE_DONE_MARKER="${OUTPUT_DIR}/calibration/capture_complete.json"

TRAJECTORY_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
CAPTURE_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin)
if [[ -f "${SETTING_GIN_CONFIG}" ]]; then
    TRAJECTORY_CONFIGS+=("${SETTING}.gin")
    CAPTURE_CONFIGS+=("${SETTING}.gin")
fi

TRAJECTORY_OVERRIDES=()
CAPTURE_OVERRIDES=(
    "render_structured_light.sl_capture_manifest_path=\"${CAPTURE_MANIFEST}\""
    "render_structured_light.sl_resume=${RESUME_CAPTURE}"
)

if [[ -n "${FRAME_RANGE}" ]]; then
    IFS=',' read -r FRAME_START FRAME_END <<<"${FRAME_RANGE}"
    CAPTURE_OVERRIDES=(
        "execute_tasks.use_scene_frame_range=False"
        "execute_tasks.frame_range=[${FRAME_START},${FRAME_END}]"
        "render_structured_light.sl_frame_index_offset=${FRAME_START}"
        "${CAPTURE_OVERRIDES[@]}"
    )
fi

if [[ -n "${RESUME_FROM_FRAME}" ]]; then
    CAPTURE_OVERRIDES+=("render_structured_light.sl_resume_from_frame=${RESUME_FROM_FRAME}")
fi

rebuild_compact_log_state_from_render_log() {
    head -n "${CAPTURE_LOG_LINES}" "${RENDER_LOG}" >"${RENDER_LOG_HEAD}"
    tail -n "${CAPTURE_LOG_LINES}" "${RENDER_LOG}" >"${RENDER_LOG_TAIL}"
    awk 'END {print NR + 0}' "${RENDER_LOG}" >"${RENDER_LOG_COUNT}"
}

initialize_log_state() {
    if [[ "${RESUME_CAPTURE}" != "1" ]]; then
        : >"${RENDER_LOG}"
        : >"${RENDER_LOG_HEAD}"
        : >"${RENDER_LOG_TAIL}"
        echo "0" >"${RENDER_LOG_COUNT}"
        return
    fi

    touch "${RENDER_LOG}" "${RENDER_LOG_HEAD}" "${RENDER_LOG_TAIL}"
    if [[ "${CAPTURE_LOG_MODE}" == "compact" ]]; then
        if [[ ! -f "${RENDER_LOG_COUNT}" ]]; then
            if [[ -s "${RENDER_LOG}" ]]; then
                rebuild_compact_log_state_from_render_log
            else
                echo "0" >"${RENDER_LOG_COUNT}"
            fi
        fi
    elif [[ ! -f "${RENDER_LOG_COUNT}" ]]; then
        echo "0" >"${RENDER_LOG_COUNT}"
    fi
}

log_stream() {
    local line
    local count=0
    local -a tail_buffer=()
    local start_index=0

    case "${CAPTURE_LOG_MODE}" in
        full)
            cat >>"${RENDER_LOG}"
            ;;
        none)
            cat >/dev/null
            ;;
        compact)
            if [[ -f "${RENDER_LOG_COUNT}" ]]; then
                count="$(<"${RENDER_LOG_COUNT}")"
            fi
            if [[ -s "${RENDER_LOG_TAIL}" ]]; then
                mapfile -t tail_buffer <"${RENDER_LOG_TAIL}"
            fi
            while IFS= read -r line || [[ -n "${line}" ]]; do
                count=$((count + 1))
                if [[ "${count}" -le "${CAPTURE_LOG_LINES}" ]]; then
                    printf '%s\n' "${line}" >>"${RENDER_LOG_HEAD}"
                fi
                tail_buffer+=("${line}")
                if [[ "${#tail_buffer[@]}" -gt "${CAPTURE_LOG_LINES}" ]]; then
                    start_index=$((${#tail_buffer[@]} - CAPTURE_LOG_LINES))
                    tail_buffer=("${tail_buffer[@]:${start_index}}")
                fi
                printf '%s\n' "${tail_buffer[@]}" >"${RENDER_LOG_TAIL}"
            done
            printf '%s\n' "${count}" >"${RENDER_LOG_COUNT}"
            ;;
    esac
}

log_text() {
    if [[ "$#" -eq 0 ]]; then
        return
    fi
    printf '%s\n' "$@" | log_stream
}

append_log_header() {
    local stage="$1"
    log_text \
        "" \
        "================================================================" \
        "### ${stage}" \
        "================================================================"
}

run_logged_command() {
    local status_file
    local rc

    status_file="$(mktemp)"
    (
        set +e
        "$@"
        rc=$?
        printf '%s\n' "${rc}" >"${status_file}"
        exit 0
    ) 2>&1 | log_stream
    rc="$(<"${status_file}")"
    rm -f "${status_file}"
    return "${rc}"
}

finalize_log() {
    local total_lines=0
    local overlap=0

    case "${CAPTURE_LOG_MODE}" in
        full)
            return
            ;;
        none)
            cat >"${RENDER_LOG}" <<EOF_NONE
Log mode: none
Command stdout/stderr was not recorded.
EOF_NONE
            return
            ;;
        compact)
            if [[ -f "${RENDER_LOG_COUNT}" ]]; then
                total_lines="$(<"${RENDER_LOG_COUNT}")"
            fi
            : >"${RENDER_LOG}"
            if [[ "${total_lines}" -le "${CAPTURE_LOG_LINES}" ]]; then
                cat "${RENDER_LOG_HEAD}" >>"${RENDER_LOG}"
                return
            fi
            cat "${RENDER_LOG_HEAD}" >>"${RENDER_LOG}"
            if [[ "${total_lines}" -le $((CAPTURE_LOG_LINES * 2)) ]]; then
                overlap=$((CAPTURE_LOG_LINES * 2 - total_lines))
                tail -n "+$((overlap + 1))" "${RENDER_LOG_TAIL}" >>"${RENDER_LOG}"
                return
            fi
            {
                echo ""
                echo "================================================================"
                echo "### Log truncated"
                echo "================================================================"
                echo "Kept first ${CAPTURE_LOG_LINES} lines and last ${CAPTURE_LOG_LINES} lines out of ${total_lines} total lines."
                echo "Live rolling tail is mirrored to ${RENDER_LOG_TAIL} while the run is active."
                echo ""
            } >>"${RENDER_LOG}"
            cat "${RENDER_LOG_TAIL}" >>"${RENDER_LOG}"
            ;;
    esac
}

write_capture_settings() {
    {
        echo "SCENE_DIR=${SCENE_DIR}"
        echo "SCENE_SEED=${SCENE_SEED}"
        echo "SETTING=${SETTING}"
        echo "CAPTURE_MANIFEST=${CAPTURE_MANIFEST}"
        echo "CAPTURE_MANIFEST_SOURCE=${CAPTURE_MANIFEST_SOURCE}"
        if [[ -f "${SETTING_GIN_CONFIG}" ]]; then
            echo "SETTING_GIN_CONFIG=${SETTING_GIN_CONFIG}"
        fi
        echo "TRAJECTORY_CONFIGS=${TRAJECTORY_CONFIGS[*]}"
        echo "CAPTURE_CONFIGS=${CAPTURE_CONFIGS[*]}"
        echo "TRAJECTORY_DIR=${TRAJECTORY_DIR}"
        echo "CAPTURE_ROOT=${CAPTURE_ROOT}"
        echo "OUTPUT_DIR=${OUTPUT_DIR}"
        echo "STRUCTURED_LIGHT_DIR=${STRUCTURED_LIGHT_DIR}"
        echo "RESUME_CAPTURE=${RESUME_CAPTURE}"
        echo "REUSE_EXISTING_TRAJECTORY=${REUSE_EXISTING_TRAJECTORY}"
        echo "CAPTURE_LOG_MODE=${CAPTURE_LOG_MODE}"
        echo "CAPTURE_LOG_LINES=${CAPTURE_LOG_LINES}"
        if [[ -n "${RESUME_FROM_FRAME}" ]]; then
            echo "RESUME_FROM_FRAME=${RESUME_FROM_FRAME}"
        fi
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
    if [[ -f "${SETTING_GIN_CONFIG}" ]]; then
        echo "  Setting gin: ${SETTING_GIN_CONFIG}"
    fi
    echo "  Resume capture: ${RESUME_CAPTURE}"
    echo "  Reuse existing trajectory: ${REUSE_EXISTING_TRAJECTORY}"
    echo "  Log mode: ${CAPTURE_LOG_MODE}"
    if [[ "${CAPTURE_LOG_MODE}" == "compact" ]]; then
        echo "  Log lines kept: first ${CAPTURE_LOG_LINES} + last ${CAPTURE_LOG_LINES}"
    fi
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
    if [[ -f "${TRAJECTORY_DIR}/scene.blend" ]]; then
        echo "Regenerating trajectory scene at ${TRAJECTORY_DIR}/scene.blend"
    fi

    append_log_header "Trajectory"
    local cmd=("${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task trajectory \
        --input_folder "${SCENE_DIR}/coarse" \
        --output_folder "${TRAJECTORY_DIR}" \
        -g "${TRAJECTORY_CONFIGS[@]}")
    if [[ "${#TRAJECTORY_OVERRIDES[@]}" -gt 0 ]]; then
        cmd+=(-p "${TRAJECTORY_OVERRIDES[@]}")
    fi
    run_logged_command "${cmd[@]}"
}

run_capture() {
    append_log_header "Structured Light Capture"
    rm -f "${CAPTURE_DONE_MARKER}"
    local cmd=("${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task structured_light \
        --input_folder "${TRAJECTORY_DIR}" \
        --output_folder "${CAPTURE_ROOT}" \
        -g "${CAPTURE_CONFIGS[@]}")
    if [[ "${#CAPTURE_OVERRIDES[@]}" -gt 0 ]]; then
        cmd+=(-p "${CAPTURE_OVERRIDES[@]}")
    fi
    run_logged_command "${cmd[@]}"
}

write_done_marker() {
    mkdir -p "$(dirname "${CAPTURE_DONE_MARKER}")"
    cat >"${CAPTURE_DONE_MARKER}" <<EOF_DONE
{"status":"complete","setting":"${SETTING}","scene_seed":"${SCENE_SEED}"}
EOF_DONE
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
        |& log_stream
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
    if [[ "${CAPTURE_LOG_MODE}" == "compact" ]]; then
        echo "Live tail log: ${RENDER_LOG_TAIL}"
    fi
}

prune_empty_dirs() {
    rmdir "${CAPTURE_ROOT}/assets" 2>/dev/null || true
    rmdir "${STATS_DIR}" 2>/dev/null || true
}

initialize_log_state
write_capture_settings
print_header
run_trajectory
run_capture
run_depth_histogram
write_done_marker
prune_empty_dirs
finalize_log
print_summary
