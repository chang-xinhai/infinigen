#!/bin/bash
# Batch capture existing benchmark seed scenes across multiple GPUs on one node.
#
# Usage:
#   bash scripts/launch/capture_existing_seed_scenes_parallel.sh [OUTPUT_ROOT] [SETTING] [single-scene args...]
#
# Example:
#   CONDA_ENV=infinigen_311 \
#   MAX_PARALLEL_SCENES=8 \
#   TOTAL_CPUS=120 \
#   bash scripts/launch/capture_existing_seed_scenes_parallel.sh \
#       outputs/benchmark/structured_light_indoors \
#       full \
#       --resume

set -euo pipefail

usage() {
    echo "Usage: bash scripts/launch/capture_existing_seed_scenes_parallel.sh [OUTPUT_ROOT] [SETTING] [single-scene args...]"
    echo ""
    echo "Positional arguments:"
    echo "  OUTPUT_ROOT         Defaults to outputs/benchmark/structured_light_indoors"
    echo "  SETTING             Defaults to CAPTURE_SETTING or full"
    echo "  single-scene args   Forwarded verbatim to capture_existing_seed_scene.sh"
    echo ""
    echo "Useful env:"
    echo "  CAPTURE_LOG_MODE    compact (default), full, or none"
    echo "  CAPTURE_LOG_LINES   Number of first/last lines kept per scene in compact mode"
}

shell_join() {
    local quoted=()
    local arg
    for arg in "$@"; do
        quoted+=("$(printf '%q' "${arg}")")
    done
    printf '%s' "${quoted[*]:-}"
}

POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
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

OUTPUT_ROOT="${OUTPUT_ROOT:-${POSITIONAL_ARGS[0]:-outputs/benchmark/structured_light_indoors}}"
SETTING="${SETTING:-${POSITIONAL_ARGS[1]:-${CAPTURE_SETTING:-full}}}"
CAPTURE_ARGS=()
if [[ "${#POSITIONAL_ARGS[@]}" -gt 2 ]]; then
    CAPTURE_ARGS=("${POSITIONAL_ARGS[@]:2}")
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CAPTURE_SCRIPT="${CAPTURE_SCRIPT:-${REPO_ROOT}/scripts/launch/capture_existing_seed_scene.sh}"

SKIP_COMPLETED="${SKIP_COMPLETED:-1}"
DONE_MARKER_REL="${DONE_MARKER_REL:-capture/${SETTING}/output/calibration/capture_complete.json}"
SCENE_GLOB="${SCENE_GLOB:-seed_*}"
TOTAL_CPUS="${TOTAL_CPUS:-${SLURM_CPUS_PER_TASK:-$(nproc)}}"
MAX_PARALLEL_SCENES="${MAX_PARALLEL_SCENES:-0}"
GPU_IDS_RAW="${GPU_IDS:-${CUDA_VISIBLE_DEVICES:-}}"
QUEUE_POLL_INTERVAL_S="${QUEUE_POLL_INTERVAL_S:-0.05}"
DRY_RUN="${DRY_RUN:-0}"
ISOLATE_RUNTIME="${ISOLATE_RUNTIME:-1}"
KEEP_RUNTIME="${KEEP_RUNTIME:-0}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
SUMMARY_DIR="${SUMMARY_DIR:-${OUTPUT_ROOT}/logs/existing_seed_capture}"
RUNTIME_PARENT="${RUNTIME_PARENT:-${TMPDIR:-/tmp}}"

if [[ ! -f "${CAPTURE_SCRIPT}" ]]; then
    echo "Capture script not found: ${CAPTURE_SCRIPT}"
    exit 1
fi

if [[ ! -d "${OUTPUT_ROOT}" ]]; then
    echo "Output root not found: ${OUTPUT_ROOT}"
    exit 1
fi

if ! [[ "${TOTAL_CPUS}" =~ ^[0-9]+$ ]] || [[ "${TOTAL_CPUS}" -lt 1 ]]; then
    echo "TOTAL_CPUS must be a positive integer, got: ${TOTAL_CPUS}"
    exit 1
fi

if ! [[ "${MAX_PARALLEL_SCENES}" =~ ^[0-9]+$ ]]; then
    echo "MAX_PARALLEL_SCENES must be a non-negative integer, got: ${MAX_PARALLEL_SCENES}"
    exit 1
fi

if [[ "${ISOLATE_RUNTIME}" != "0" && "${ISOLATE_RUNTIME}" != "1" ]]; then
    echo "ISOLATE_RUNTIME must be 0 or 1, got: ${ISOLATE_RUNTIME}"
    exit 1
fi

if [[ "${KEEP_RUNTIME}" != "0" && "${KEEP_RUNTIME}" != "1" ]]; then
    echo "KEEP_RUNTIME must be 0 or 1, got: ${KEEP_RUNTIME}"
    exit 1
fi

discover_gpu_ids() {
    local raw_ids="$1"
    local count
    local gpu_count

    if [[ -n "${raw_ids}" ]]; then
        tr ',' '\n' <<<"${raw_ids}" | sed '/^$/d'
        return
    fi

    if [[ -n "${SLURM_GPUS_ON_NODE:-}" && "${SLURM_GPUS_ON_NODE}" =~ ^[0-9]+$ ]]; then
        for ((count = 0; count < SLURM_GPUS_ON_NODE; count++)); do
            echo "${count}"
        done
        return
    fi

    if command -v nvidia-smi >/dev/null 2>&1; then
        gpu_count="$(nvidia-smi --list-gpus | wc -l | tr -d ' ')"
        if [[ -n "${gpu_count}" && "${gpu_count}" =~ ^[0-9]+$ && "${gpu_count}" -gt 0 ]]; then
            for ((count = 0; count < gpu_count; count++)); do
                echo "${count}"
            done
            return
        fi
    fi

    echo "0"
}

cpu_partition_for_slot() {
    local slot="$1"
    local slot_count="$2"
    local total_cpus="$3"
    local base=$((total_cpus / slot_count))
    local remainder=$((total_cpus % slot_count))
    local size
    local start
    local end

    if (( slot < remainder )); then
        size=$((base + 1))
        start=$((slot * size))
    else
        size=${base}
        start=$((remainder * (base + 1) + (slot - remainder) * base))
    fi

    end=$((start + size - 1))
    printf '%s-%s %s\n' "${start}" "${end}" "${size}"
}

queue_lock_acquire() {
    while ! mkdir "${QUEUE_LOCK_DIR}" 2>/dev/null; do
        sleep "${QUEUE_POLL_INTERVAL_S}"
    done
}

queue_lock_release() {
    rmdir "${QUEUE_LOCK_DIR}"
}

next_scene() {
    local index
    local scene_dir

    queue_lock_acquire
    index="$(<"${QUEUE_INDEX_FILE}")"
    scene_dir="$(sed -n "${index}p" "${QUEUE_FILE}")"
    if [[ -n "${scene_dir}" ]]; then
        echo $((index + 1)) >"${QUEUE_INDEX_FILE}"
    fi
    queue_lock_release

    printf '%s\n' "${scene_dir}"
}

prepare_runtime_dir() {
    local slot="$1"
    local scene_name="$2"
    local runtime_dir

    runtime_dir="$(mktemp -d "${RUN_DIR}/runtime/${scene_name}.slot_${slot}.XXXXXX")"
    mkdir -p \
        "${runtime_dir}/tmp" \
        "${runtime_dir}/mpl" \
        "${runtime_dir}/xdg-cache" \
        "${runtime_dir}/xdg-config" \
        "${runtime_dir}/xdg-data" \
        "${runtime_dir}/blender/config" \
        "${runtime_dir}/blender/scripts" \
        "${runtime_dir}/blender/datafiles"
    printf '%s\n' "${runtime_dir}"
}

cleanup_runtime_dir() {
    local runtime_dir="$1"
    if [[ "${KEEP_RUNTIME}" == "1" || -z "${runtime_dir}" ]]; then
        return
    fi
    rm -rf "${runtime_dir}"
}

run_capture_command() {
    local slot="$1"
    local scene_dir="$2"
    local scene_name="$3"
    local gpu_id="$4"
    local cpu_set="$5"
    local thread_count="$6"
    local runtime_dir=""
    local -a env_cmd=(
        env
        "CUDA_VISIBLE_DEVICES=${gpu_id}"
        "OMP_NUM_THREADS=${thread_count}"
        "OPENBLAS_NUM_THREADS=${thread_count}"
        "MKL_NUM_THREADS=${thread_count}"
        "NUMEXPR_NUM_THREADS=${thread_count}"
        "PYTHONUNBUFFERED=1"
    )
    local -a cmd=(bash "${CAPTURE_SCRIPT}" "${scene_dir}" "${SETTING}" "${CAPTURE_ARGS[@]}")

    if [[ "${ISOLATE_RUNTIME}" == "1" ]]; then
        runtime_dir="$(prepare_runtime_dir "${slot}" "${scene_name}")"
        env_cmd+=(
            "TMPDIR=${runtime_dir}/tmp"
            "TMP=${runtime_dir}/tmp"
            "TEMP=${runtime_dir}/tmp"
            "MPLCONFIGDIR=${runtime_dir}/mpl"
            "XDG_CACHE_HOME=${runtime_dir}/xdg-cache"
            "XDG_CONFIG_HOME=${runtime_dir}/xdg-config"
            "XDG_DATA_HOME=${runtime_dir}/xdg-data"
            "BLENDER_USER_CONFIG=${runtime_dir}/blender/config"
            "BLENDER_USER_SCRIPTS=${runtime_dir}/blender/scripts"
            "BLENDER_USER_DATAFILES=${runtime_dir}/blender/datafiles"
        )
    fi

    if command -v taskset >/dev/null 2>&1; then
        cmd=(taskset -c "${cpu_set}" "${cmd[@]}")
    fi

    set +e
    "${env_cmd[@]}" "${cmd[@]}"
    local rc=$?

    if [[ "${rc}" -eq 0 ]]; then
        cleanup_runtime_dir "${runtime_dir}"
    fi

    LAST_RUNTIME_DIR="${runtime_dir}"
    return "${rc}"
}

write_batch_config() {
    {
        echo "OUTPUT_ROOT=${OUTPUT_ROOT}"
        echo "SETTING=${SETTING}"
        echo "CAPTURE_SCRIPT=${CAPTURE_SCRIPT}"
        echo "SKIP_COMPLETED=${SKIP_COMPLETED}"
        echo "DONE_MARKER_REL=${DONE_MARKER_REL}"
        echo "SCENE_GLOB=${SCENE_GLOB}"
        echo "TOTAL_CPUS=${TOTAL_CPUS}"
        echo "MAX_PARALLEL_SCENES=${MAX_PARALLEL_SCENES}"
        echo "GPU_IDS_RAW=${GPU_IDS_RAW}"
        echo "QUEUE_POLL_INTERVAL_S=${QUEUE_POLL_INTERVAL_S}"
        echo "DRY_RUN=${DRY_RUN}"
        echo "ISOLATE_RUNTIME=${ISOLATE_RUNTIME}"
        echo "KEEP_RUNTIME=${KEEP_RUNTIME}"
        echo "CAPTURE_LOG_MODE=${CAPTURE_LOG_MODE:-compact}"
        echo "CAPTURE_LOG_LINES=${CAPTURE_LOG_LINES:-100}"
        echo "RUN_ID=${RUN_ID}"
        echo "CAPTURE_ARGS=$(shell_join "${CAPTURE_ARGS[@]}")"
    } >"${BATCH_CONFIG_FILE}"
}

worker_loop() {
    local slot="$1"
    local gpu_id="$2"
    local cpu_set="$3"
    local thread_count="$4"
    local status_file="${RUN_DIR}/worker_${slot}.tsv"
    local scene_dir
    local scene_name
    local runtime_dir
    local rc

    : >"${status_file}"

    while true; do
        scene_dir="$(next_scene)"
        if [[ -z "${scene_dir}" ]]; then
            break
        fi

        scene_name="$(basename "${scene_dir}")"
        echo "[worker ${slot}] start scene=${scene_name} gpu=${gpu_id} cpus=${cpu_set} threads=${thread_count}"

        if [[ "${DRY_RUN}" == "1" ]]; then
            printf '%s\tsuccess\t%s\t%s\n' "${scene_name}" "${gpu_id}" "${cpu_set}" >>"${status_file}"
            continue
        fi

        LAST_RUNTIME_DIR=""
        set +e
        run_capture_command "${slot}" "${scene_dir}" "${scene_name}" "${gpu_id}" "${cpu_set}" "${thread_count}"
        rc=$?
        set -e
        runtime_dir="${LAST_RUNTIME_DIR:-}"

        if [[ "${rc}" -eq 0 ]]; then
            printf '%s\tsuccess\t%s\t%s\n' "${scene_name}" "${gpu_id}" "${cpu_set}" >>"${status_file}"
            echo "[worker ${slot}] done scene=${scene_name} gpu=${gpu_id}"
        else
            printf '%s\tfailed(%s)\t%s\t%s\n' "${scene_name}" "${rc}" "${gpu_id}" "${cpu_set}" >>"${status_file}"
            if [[ -n "${runtime_dir}" ]]; then
                echo "[worker ${slot}] failed scene=${scene_name} gpu=${gpu_id} rc=${rc} runtime=${runtime_dir}"
            else
                echo "[worker ${slot}] failed scene=${scene_name} gpu=${gpu_id} rc=${rc}"
            fi
        fi
    done
}

mapfile -t AVAILABLE_GPU_IDS < <(discover_gpu_ids "${GPU_IDS_RAW}")
GPU_COUNT="${#AVAILABLE_GPU_IDS[@]}"

if [[ "${GPU_COUNT}" -lt 1 ]]; then
    echo "No GPUs discovered."
    exit 1
fi

mapfile -t SCENE_DIRS < <(find "${OUTPUT_ROOT}" -mindepth 1 -maxdepth 1 -type d -name "${SCENE_GLOB}" | sort -V)

if [[ "${#SCENE_DIRS[@]}" -eq 0 ]]; then
    echo "No scene directories matching ${SCENE_GLOB} found under ${OUTPUT_ROOT}"
    exit 1
fi

PENDING_SCENES=()
SKIPPED_SCENES=()
INVALID_SCENES=()

for scene_dir in "${SCENE_DIRS[@]}"; do
    scene_name="$(basename "${scene_dir}")"
    if ! [[ "${scene_name}" =~ ^seed_[0-9]+$ ]]; then
        continue
    fi

    if [[ ! -f "${scene_dir}/coarse/scene.blend" ]]; then
        INVALID_SCENES+=("${scene_dir}")
        continue
    fi

    if [[ "${SKIP_COMPLETED}" == "1" && -e "${scene_dir}/${DONE_MARKER_REL}" ]]; then
        SKIPPED_SCENES+=("${scene_dir}")
        continue
    fi

    PENDING_SCENES+=("${scene_dir}")
done

if [[ "${#PENDING_SCENES[@]}" -eq 0 ]]; then
    echo "No pending scenes found."
    echo "Valid completed scenes skipped: ${#SKIPPED_SCENES[@]}"
    echo "Invalid scenes skipped: ${#INVALID_SCENES[@]}"
    exit 0
fi

WORKER_COUNT="${GPU_COUNT}"
if [[ "${MAX_PARALLEL_SCENES}" -gt 0 && "${MAX_PARALLEL_SCENES}" -lt "${WORKER_COUNT}" ]]; then
    WORKER_COUNT="${MAX_PARALLEL_SCENES}"
fi
if [[ "${#PENDING_SCENES[@]}" -lt "${WORKER_COUNT}" ]]; then
    WORKER_COUNT="${#PENDING_SCENES[@]}"
fi
if [[ "${TOTAL_CPUS}" -lt "${WORKER_COUNT}" ]]; then
    WORKER_COUNT="${TOTAL_CPUS}"
fi

mkdir -p "${SUMMARY_DIR}"
RUN_DIR="$(mktemp -d "${RUNTIME_PARENT%/}/capture_existing_seed_scenes_parallel.XXXXXX")"
mkdir -p "${RUN_DIR}/runtime"
QUEUE_FILE="${RUN_DIR}/queue.txt"
QUEUE_INDEX_FILE="${RUN_DIR}/queue_index.txt"
QUEUE_LOCK_DIR="${RUN_DIR}/queue.lock"
SUMMARY_FILE="${SUMMARY_DIR}/summary_${SETTING}_${RUN_ID}.tsv"
BATCH_CONFIG_FILE="${SUMMARY_DIR}/batch_${SETTING}_${RUN_ID}.env"

cleanup() {
    if [[ "${KEEP_RUNTIME}" == "1" ]]; then
        echo "Retained batch runtime: ${RUN_DIR}"
        return
    fi
    rm -rf "${RUN_DIR}"
}
trap cleanup EXIT

printf '%s\n' "${PENDING_SCENES[@]}" >"${QUEUE_FILE}"
echo "1" >"${QUEUE_INDEX_FILE}"
write_batch_config

echo "═══════════════════════════════════════════════════════════"
echo "  Parallel Existing Seed Capture"
echo "  Output root: ${OUTPUT_ROOT}"
echo "  Setting: ${SETTING}"
echo "  Capture script: ${CAPTURE_SCRIPT}"
echo "  Capture args: $(shell_join "${CAPTURE_ARGS[@]}")"
echo "  Pending scenes: ${#PENDING_SCENES[@]}"
echo "  Skipped completed: ${#SKIPPED_SCENES[@]}"
echo "  Skipped invalid: ${#INVALID_SCENES[@]}"
echo "  Available GPUs: ${GPU_COUNT} (${AVAILABLE_GPU_IDS[*]})"
echo "  Worker count: ${WORKER_COUNT}"
echo "  Total CPUs: ${TOTAL_CPUS}"
echo "  Skip completed: ${SKIP_COMPLETED}"
echo "  Done marker: ${DONE_MARKER_REL}"
echo "  Runtime isolation: ${ISOLATE_RUNTIME}"
echo "  Log mode: ${CAPTURE_LOG_MODE:-compact}"
if [[ "${CAPTURE_LOG_MODE:-compact}" == "compact" ]]; then
    echo "  Log lines kept: first ${CAPTURE_LOG_LINES:-100} + last ${CAPTURE_LOG_LINES:-100}"
fi
echo "  Batch config: ${BATCH_CONFIG_FILE}"
echo "  Summary file: ${SUMMARY_FILE}"
echo "═══════════════════════════════════════════════════════════"

declare -a WORKER_PIDS=()

for ((slot = 0; slot < WORKER_COUNT; slot++)); do
    read -r cpu_set thread_count < <(cpu_partition_for_slot "${slot}" "${WORKER_COUNT}" "${TOTAL_CPUS}")
    worker_loop "${slot}" "${AVAILABLE_GPU_IDS[$slot]}" "${cpu_set}" "${thread_count}" &
    WORKER_PIDS+=("$!")
done

worker_failures=0
for pid in "${WORKER_PIDS[@]}"; do
    set +e
    wait "${pid}"
    rc=$?
    set -e
    if [[ "${rc}" -ne 0 ]]; then
        worker_failures=$((worker_failures + 1))
    fi
done

{
    printf 'scene\tstatus\tgpu\tcpus\n'
    find "${RUN_DIR}" -maxdepth 1 -type f -name 'worker_*.tsv' -print0 | xargs -0 -r cat | sort -V
} >"${SUMMARY_FILE}"

success_count="$(awk -F '\t' 'NR > 1 && $2 == "success" {count++} END {print count + 0}' "${SUMMARY_FILE}")"
failure_count="$(awk -F '\t' 'NR > 1 && $2 != "success" {count++} END {print count + 0}' "${SUMMARY_FILE}")"

echo ""
echo "### Batch Summary"
echo "Summary file: ${SUMMARY_FILE}"
echo "Successful scenes: ${success_count}"
echo "Failed scenes: ${failure_count}"

if [[ "${failure_count}" -gt 0 ]]; then
    echo "Failed scene rows:"
    awk -F '\t' 'NR == 1 || $2 != "success"' "${SUMMARY_FILE}"
fi

if [[ "${worker_failures}" -gt 0 || "${failure_count}" -gt 0 ]]; then
    exit 1
fi
