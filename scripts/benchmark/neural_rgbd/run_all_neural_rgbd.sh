#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
RUN_NEURAL_RGBD_BIN="${RUN_NEURAL_RGBD_BIN:-${SCRIPT_DIR}/run_neural_rgbd.sh}"

OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/outputs/benchmark/neural_rgbd}"
POSE_SOURCE="${POSE_SOURCE:-blender_poses}"
TASKS="${TASKS:-trajectory render structured_light}"
SCENES="${SCENES:-ALL}"
EXCLUDED_SCENES="${EXCLUDED_SCENES:-full_kitchen complete_kitchen morning_apartment whiteroom}"
FRAME_START="${FRAME_START:-}"
FRAME_END="${FRAME_END:-}"
RENDER_ENGINE="${RENDER_ENGINE:-}"
RENDER_SAMPLES="${RENDER_SAMPLES:-}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-1}"
GPU_IDS_RAW="${GPU_IDS:-${CUDA_VISIBLE_DEVICES:-}}"
MAX_PARALLEL_SCENES="${MAX_PARALLEL_SCENES:-0}"
QUEUE_POLL_INTERVAL_S="${QUEUE_POLL_INTERVAL_S:-0.05}"
ISOLATE_RUNTIME="${ISOLATE_RUNTIME:-1}"
KEEP_RUNTIME="${KEEP_RUNTIME:-0}"
INHERIT_BLENDER_ADDONS="${INHERIT_BLENDER_ADDONS:-1}"
RUNTIME_PARENT="${RUNTIME_PARENT:-${TMPDIR:-/tmp}}"
STRUCTURED_LIGHT_SETTING="${STRUCTURED_LIGHT_SETTING:-full}"
STRUCTURED_LIGHT_MANIFEST="${STRUCTURED_LIGHT_MANIFEST:-${REPO_ROOT}/infinigen_examples/configs_indoor/capture_manifests/${STRUCTURED_LIGHT_SETTING}.yaml}"
STRUCTURED_LIGHT_CONFIGS="${STRUCTURED_LIGHT_CONFIGS:-structured_light.gin ${STRUCTURED_LIGHT_SETTING}.gin structured_light_neural_rgbd.gin}"
STRUCTURED_LIGHT_OVERRIDES="${STRUCTURED_LIGHT_OVERRIDES:-}"

POSE_STEM="${POSE_SOURCE%.txt}"
LOG_ROOT="${OUTPUT_ROOT}/logs"
SUMMARY_FILE="${LOG_ROOT}/run_all_summary.tsv"
mkdir -p "${LOG_ROOT}"

discover_all_scenes() {
    find "${REPO_ROOT}/data/neural_rgbd/blendswap_scenes" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
}

filter_excluded_scenes() {
    local -a input_scenes=("$@")
    local -a excluded_scenes=()
    local scene_name
    local excluded_name
    local skip_scene

    if [[ -n "${EXCLUDED_SCENES}" ]]; then
        read -r -a excluded_scenes <<<"${EXCLUDED_SCENES}"
    fi

    for scene_name in "${input_scenes[@]}"; do
        skip_scene=0
        for excluded_name in "${excluded_scenes[@]}"; do
            if [[ "${scene_name}" == "${excluded_name}" ]]; then
                skip_scene=1
                break
            fi
        done
        if [[ "${skip_scene}" == "0" ]]; then
            printf '%s\n' "${scene_name}"
        fi
    done
}

if [[ "${SCENES}" == "ALL" ]]; then
    mapfile -t SCENE_LIST < <(discover_all_scenes)
else
    read -r -a SCENE_LIST <<<"${SCENES}"
fi
mapfile -t SCENE_LIST < <(filter_excluded_scenes "${SCENE_LIST[@]}")
if [[ "${#SCENE_LIST[@]}" -eq 0 ]]; then
    echo "No Neural RGB-D scenes left to process after applying EXCLUDED_SCENES=${EXCLUDED_SCENES}"
    exit 1
fi

read -r -a TASK_LIST <<<"${TASKS}"
read -r -a STRUCTURED_LIGHT_CONFIG_LIST <<<"${STRUCTURED_LIGHT_CONFIGS}"
read -r -a STRUCTURED_LIGHT_OVERRIDE_LIST <<<"${STRUCTURED_LIGHT_OVERRIDES}"

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

queue_lock_acquire() {
    local lock_dir="$1"
    while ! mkdir "${lock_dir}" 2>/dev/null; do
        sleep "${QUEUE_POLL_INTERVAL_S}"
    done
}

queue_lock_release() {
    local lock_dir="$1"
    rmdir "${lock_dir}"
}

restore_shopt_state() {
    local state="$1"
    if [[ -n "${state}" ]]; then
        eval "${state}"
    fi
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

link_directory_entries() {
    local src_dir="$1"
    local dst_dir="$2"
    local entry
    local name
    local nullglob_state
    local dotglob_state

    if [[ ! -d "${src_dir}" ]]; then
        return
    fi

    mkdir -p "${dst_dir}"
    nullglob_state="$(shopt -p nullglob || true)"
    dotglob_state="$(shopt -p dotglob || true)"
    shopt -s nullglob dotglob
    for entry in "${src_dir}"/*; do
        name="$(basename "${entry}")"
        if [[ ! -e "${dst_dir}/${name}" ]]; then
            ln -s "${entry}" "${dst_dir}/${name}"
        fi
    done
    restore_shopt_state "${nullglob_state}"
    restore_shopt_state "${dotglob_state}"
}

discover_blender_scripts_source() {
    local config_root="${XDG_CONFIG_HOME:-${HOME}/.config}"
    local candidate

    if [[ -n "${BLENDER_USER_SCRIPTS:-}" && -d "${BLENDER_USER_SCRIPTS}" ]]; then
        printf '%s\n' "${BLENDER_USER_SCRIPTS}"
        return
    fi

    if [[ -n "${BLENDER_ADDONS:-}" && -d "${BLENDER_ADDONS}" ]]; then
        dirname "${BLENDER_ADDONS}"
        return
    fi

    for candidate in "${config_root}"/blender/*/scripts; do
        if [[ -d "${candidate}/addons" || -d "${candidate}/addons_core" ]]; then
            printf '%s\n' "${candidate}"
            return
        fi
    done
}

discover_blender_extensions_source() {
    local config_root="${XDG_CONFIG_HOME:-${HOME}/.config}"
    local candidate

    if [[ -n "${BLENDER_EXTENSIONS_USER:-}" && -d "${BLENDER_EXTENSIONS_USER}" ]]; then
        printf '%s\n' "${BLENDER_EXTENSIONS_USER}"
        return
    fi

    for candidate in "${config_root}"/blender/*/extensions/user_default; do
        if [[ -d "${candidate}" ]]; then
            printf '%s\n' "${candidate}"
            return
        fi
    done
}

blender_version_from_extensions_dir() {
    local ext_dir="$1"
    local version_dir

    version_dir="$(basename "$(dirname "$(dirname "${ext_dir}")")")"
    if [[ -n "${version_dir}" ]]; then
        printf '%s\n' "${version_dir}"
    else
        printf '4.2\n'
    fi
}

inherit_blender_addons_into_runtime() {
    local runtime_dir="$1"
    local scripts_source
    local extensions_source
    local extensions_version

    if [[ "${INHERIT_BLENDER_ADDONS}" != "1" ]]; then
        return
    fi

    scripts_source="$(discover_blender_scripts_source || true)"
    if [[ -n "${scripts_source}" ]]; then
        link_directory_entries "${scripts_source}/addons" "${runtime_dir}/blender/scripts/addons"
        link_directory_entries "${scripts_source}/addons_core" "${runtime_dir}/blender/scripts/addons_core"
    fi

    extensions_source="$(discover_blender_extensions_source || true)"
    if [[ -n "${extensions_source}" ]]; then
        extensions_version="$(blender_version_from_extensions_dir "${extensions_source}")"
        link_directory_entries \
            "${extensions_source}" \
            "${runtime_dir}/xdg-config/blender/${extensions_version}/extensions/user_default"
    fi
}

cleanup_runtime_dir() {
    local runtime_dir="$1"
    if [[ "${KEEP_RUNTIME}" == "1" || -z "${runtime_dir}" ]]; then
        return
    fi
    rm -rf "${runtime_dir}"
}

if [[ " ${TASK_LIST[*]} " == *" structured_light "* ]] && [[ ! -f "${STRUCTURED_LIGHT_MANIFEST}" ]]; then
    echo "Structured-light manifest not found: ${STRUCTURED_LIGHT_MANIFEST}"
    exit 1
fi

build_base_cmd() {
    local scene_name="$1"
    local task_name="$2"
    local scene_output_root="$3"
    local -a cmd=(
        bash "${RUN_NEURAL_RGBD_BIN}"
        --scene_name "${scene_name}"
        --pose_source "${POSE_SOURCE}"
        --task "${task_name}"
        --output_root "${scene_output_root}"
    )

    if [[ -n "${FRAME_START}" ]]; then
        cmd+=(--frame_start "${FRAME_START}")
    fi
    if [[ -n "${FRAME_END}" ]]; then
        cmd+=(--frame_end "${FRAME_END}")
    fi
    if [[ -n "${RENDER_ENGINE}" ]]; then
        cmd+=(--render_engine "${RENDER_ENGINE}")
    fi
    if [[ -n "${RENDER_SAMPLES}" ]]; then
        cmd+=(--render_samples "${RENDER_SAMPLES}")
    fi

    printf '%s\0' "${cmd[@]}"
}

run_scene_task() {
    local scene_name="$1"
    local task_name="$2"
    local scene_output_root="$3"
    local log_file="$4"
    local gpu_id="$5"
    local runtime_dir="$6"
    local -a cmd=()
    local -a env_prefix=()
    local arg

    while IFS= read -r -d '' arg; do
        cmd+=("${arg}")
    done < <(build_base_cmd "${scene_name}" "${task_name}" "${scene_output_root}")

    if [[ -n "${gpu_id}" ]]; then
        env_prefix+=(env "CUDA_VISIBLE_DEVICES=${gpu_id}")
    fi
    if [[ -n "${runtime_dir}" ]]; then
        env_prefix+=(
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

    if [[ "${task_name}" == "structured_light" ]]; then
        if [[ "${#STRUCTURED_LIGHT_CONFIG_LIST[@]}" -gt 0 ]]; then
            cmd+=(-g "${STRUCTURED_LIGHT_CONFIG_LIST[@]}")
        fi
        cmd+=(
            -p
            "render_structured_light.sl_capture_manifest_path=\"${STRUCTURED_LIGHT_MANIFEST}\""
        )
        if [[ "${#STRUCTURED_LIGHT_OVERRIDE_LIST[@]}" -gt 0 ]]; then
            cmd+=("${STRUCTURED_LIGHT_OVERRIDE_LIST[@]}")
        fi
    fi

    {
        echo ">>> Task ${task_name}"
        printf 'Command:'
        printf ' %q' "${env_prefix[@]}" "${cmd[@]}"
        printf '\n'
        if [[ "${#env_prefix[@]}" -gt 0 ]]; then
            "${env_prefix[@]}" "${cmd[@]}"
        else
            "${cmd[@]}"
        fi
    } >>"${log_file}" 2>&1
}

next_scene() {
    local lock_dir="$1"
    local index_file="$2"
    local queue_file="$3"
    local stop_file="$4"
    local index
    local scene_name

    if [[ -f "${stop_file}" && "${CONTINUE_ON_ERROR}" != "1" ]]; then
        printf '\n'
        return
    fi

    queue_lock_acquire "${lock_dir}"
    if [[ -f "${stop_file}" && "${CONTINUE_ON_ERROR}" != "1" ]]; then
        queue_lock_release "${lock_dir}"
        printf '\n'
        return
    fi

    index="$(<"${index_file}")"
    scene_name="$(sed -n "${index}p" "${queue_file}")"
    if [[ -n "${scene_name}" ]]; then
        echo $((index + 1)) >"${index_file}"
    fi
    queue_lock_release "${lock_dir}"

    printf '%s\n' "${scene_name}"
}

append_summary_row() {
    local lock_dir="$1"
    local scene_name="$2"
    local status="$3"
    local scene_output_root="$4"
    local log_file="$5"

    queue_lock_acquire "${lock_dir}"
    printf "%s\t%s\t%s\t%s\n" "${scene_name}" "${status}" "${scene_output_root}" "${log_file}" >> "${SUMMARY_FILE}"
    queue_lock_release "${lock_dir}"
}

record_failure() {
    local lock_dir="$1"
    local scene_name="$2"
    local rc="$3"
    local failure_file="$4"
    local stop_file="$5"
    local stop_rc_file="$6"

    queue_lock_acquire "${lock_dir}"
    printf "%s\t%s\n" "${scene_name}" "${rc}" >> "${failure_file}"
    if [[ "${CONTINUE_ON_ERROR}" != "1" ]]; then
        if [[ ! -f "${stop_rc_file}" ]]; then
            printf "%s\n" "${rc}" > "${stop_rc_file}"
        fi
        : > "${stop_file}"
    fi
    queue_lock_release "${lock_dir}"
}

run_scene() {
    local slot="$1"
    local scene_name="$2"
    local gpu_id="$3"
    local summary_lock_dir="$4"
    local failure_file="$5"
    local stop_file="$6"
    local stop_rc_file="$7"
    local scene_output_root="${OUTPUT_ROOT}/${scene_name}/${POSE_STEM}"
    local log_file="${LOG_ROOT}/${scene_name}.log"
    local scene_failed=0
    local rc=0
    local status
    local task_name
    local runtime_dir=""

    mkdir -p "${scene_output_root}"
    : >"${log_file}"

    if [[ "${ISOLATE_RUNTIME}" == "1" ]]; then
        runtime_dir="$(prepare_runtime_dir "${slot}" "${scene_name}")"
        inherit_blender_addons_into_runtime "${runtime_dir}"
    fi

    echo ""
    echo ">>> Running scene ${scene_name} on GPU ${gpu_id}"
    if [[ -n "${runtime_dir}" ]]; then
        echo ">>> Runtime isolation for ${scene_name}: ${runtime_dir}"
    fi

    for task_name in "${TASK_LIST[@]}"; do
        if run_scene_task "${scene_name}" "${task_name}" "${scene_output_root}" "${log_file}" "${gpu_id}" "${runtime_dir}"; then
            :
        else
            rc=$?
            scene_failed=1
            break
        fi
    done

    if [[ "${scene_failed}" -eq 0 ]]; then
        status="success"
        cleanup_runtime_dir "${runtime_dir}"
    else
        status="failed(${rc})"
        echo "WARNING: scene ${scene_name} failed with exit code ${rc}. See ${log_file}"
        if [[ -n "${runtime_dir}" ]]; then
            echo "WARNING: retained runtime directory ${runtime_dir}"
        fi
        record_failure "${summary_lock_dir}" "${scene_name}" "${rc}" "${failure_file}" "${stop_file}" "${stop_rc_file}"
    fi

    append_summary_row "${summary_lock_dir}" "${scene_name}" "${status}" "${scene_output_root}" "${log_file}"
}

worker_loop() {
    local slot="$1"
    local gpu_id="$2"
    local queue_lock_dir="$3"
    local queue_index_file="$4"
    local queue_file="$5"
    local summary_lock_dir="$6"
    local failure_file="$7"
    local stop_file="$8"
    local stop_rc_file="$9"
    local scene_name

    while true; do
        scene_name="$(next_scene "${queue_lock_dir}" "${queue_index_file}" "${queue_file}" "${stop_file}")"
        if [[ -z "${scene_name}" ]]; then
            break
        fi
        echo ">>> Worker ${slot} picked ${scene_name} on GPU ${gpu_id}"
        run_scene "${slot}" "${scene_name}" "${gpu_id}" "${summary_lock_dir}" "${failure_file}" "${stop_file}" "${stop_rc_file}"
    done
}

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
if [[ "${INHERIT_BLENDER_ADDONS}" != "0" && "${INHERIT_BLENDER_ADDONS}" != "1" ]]; then
    echo "INHERIT_BLENDER_ADDONS must be 0 or 1, got: ${INHERIT_BLENDER_ADDONS}"
    exit 1
fi

mapfile -t DISCOVERED_GPU_IDS < <(discover_gpu_ids "${GPU_IDS_RAW}")
if [[ "${#DISCOVERED_GPU_IDS[@]}" -eq 0 ]]; then
    DISCOVERED_GPU_IDS=("0")
fi

WORKER_COUNT="${#DISCOVERED_GPU_IDS[@]}"
if [[ "${MAX_PARALLEL_SCENES}" -gt 0 && "${MAX_PARALLEL_SCENES}" -lt "${WORKER_COUNT}" ]]; then
    WORKER_COUNT="${MAX_PARALLEL_SCENES}"
fi
if [[ "${#SCENE_LIST[@]}" -lt "${WORKER_COUNT}" ]]; then
    WORKER_COUNT="${#SCENE_LIST[@]}"
fi

echo "scene	status	output_root	log_file" > "${SUMMARY_FILE}"

echo "═══════════════════════════════════════════════════════════"
echo "  Neural RGB-D Full Benchmark"
echo "  Requested scenes: ${SCENES}"
echo "  Excluded scenes: ${EXCLUDED_SCENES:-<none>}"
echo "  Effective scenes: ${SCENE_LIST[*]}"
echo "  Pose source: ${POSE_SOURCE}"
echo "  Tasks: ${TASKS}"
echo "  Output root: ${OUTPUT_ROOT}"
echo "  Continue on error: ${CONTINUE_ON_ERROR}"
echo "  GPU_IDS: ${GPU_IDS_RAW:-auto}"
echo "  Parallel workers: ${WORKER_COUNT}"
echo "  Runtime isolation: ${ISOLATE_RUNTIME}"
echo "  Inherit Blender addons: ${INHERIT_BLENDER_ADDONS}"
if [[ " ${TASK_LIST[*]} " == *" structured_light "* ]]; then
    echo "  SL manifest: ${STRUCTURED_LIGHT_MANIFEST}"
    echo "  SL configs: ${STRUCTURED_LIGHT_CONFIGS}"
fi
echo "═══════════════════════════════════════════════════════════"

RUN_DIR="$(mktemp -d "${RUNTIME_PARENT%/}/neural_rgbd_parallel.XXXXXX")"
mkdir -p "${RUN_DIR}/runtime"
QUEUE_FILE="${RUN_DIR}/scene_queue.txt"
QUEUE_INDEX_FILE="${RUN_DIR}/queue_index.txt"
QUEUE_LOCK_DIR="${RUN_DIR}/queue.lock"
SUMMARY_LOCK_DIR="${RUN_DIR}/summary.lock"
FAILURE_FILE="${RUN_DIR}/failures.tsv"
STOP_FILE="${RUN_DIR}/stop"
STOP_RC_FILE="${RUN_DIR}/stop_rc.txt"
PIDS=()

cleanup() {
    if [[ "${KEEP_RUNTIME}" == "1" ]]; then
        echo "Retained batch runtime: ${RUN_DIR}"
        return
    fi
    rm -rf "${RUN_DIR}"
}
trap cleanup EXIT

printf '%s\n' "${SCENE_LIST[@]}" > "${QUEUE_FILE}"
echo "1" > "${QUEUE_INDEX_FILE}"
: > "${FAILURE_FILE}"

for ((slot = 0; slot < WORKER_COUNT; slot++)); do
    worker_loop \
        "${slot}" \
        "${DISCOVERED_GPU_IDS[slot]}" \
        "${QUEUE_LOCK_DIR}" \
        "${QUEUE_INDEX_FILE}" \
        "${QUEUE_FILE}" \
        "${SUMMARY_LOCK_DIR}" \
        "${FAILURE_FILE}" \
        "${STOP_FILE}" \
        "${STOP_RC_FILE}" &
    PIDS+=($!)
done

for pid in "${PIDS[@]}"; do
    wait "${pid}"
done

echo ""
echo "Summary written to ${SUMMARY_FILE}"

failure_count="$(wc -l < "${FAILURE_FILE}" | tr -d ' ')"
if [[ -f "${STOP_RC_FILE}" ]]; then
    exit "$(<"${STOP_RC_FILE}")"
fi

if [[ "${failure_count}" -gt 0 ]]; then
    exit 1
fi
