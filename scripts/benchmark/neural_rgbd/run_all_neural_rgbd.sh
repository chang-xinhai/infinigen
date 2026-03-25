#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
RUN_NEURAL_RGBD_BIN="${RUN_NEURAL_RGBD_BIN:-${SCRIPT_DIR}/run_neural_rgbd.sh}"

OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/outputs/benchmark/neural_rgbd}"
POSE_SOURCE="${POSE_SOURCE:-blender_poses}"
TASKS="${TASKS:-trajectory render structured_light}"
SCENES="${SCENES:-ALL}"
FRAME_START="${FRAME_START:-}"
FRAME_END="${FRAME_END:-}"
RENDER_ENGINE="${RENDER_ENGINE:-}"
RENDER_SAMPLES="${RENDER_SAMPLES:-}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-1}"
GPU_IDS_RAW="${GPU_IDS:-${CUDA_VISIBLE_DEVICES:-}}"
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

if [[ "${SCENES}" == "ALL" ]]; then
    mapfile -t SCENE_LIST < <(discover_all_scenes)
else
    read -r -a SCENE_LIST <<<"${SCENES}"
fi

read -r -a TASK_LIST <<<"${TASKS}"
read -r -a STRUCTURED_LIGHT_CONFIG_LIST <<<"${STRUCTURED_LIGHT_CONFIGS}"
read -r -a STRUCTURED_LIGHT_OVERRIDE_LIST <<<"${STRUCTURED_LIGHT_OVERRIDES}"

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
    local -a cmd=()
    local -a env_prefix=()
    local arg

    while IFS= read -r -d '' arg; do
        cmd+=("${arg}")
    done < <(build_base_cmd "${scene_name}" "${task_name}" "${scene_output_root}")

    if [[ -n "${GPU_IDS_RAW}" ]]; then
        env_prefix+=(env "CUDA_VISIBLE_DEVICES=${GPU_IDS_RAW}")
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

echo "scene	status	output_root	log_file" > "${SUMMARY_FILE}"

echo "═══════════════════════════════════════════════════════════"
echo "  Neural RGB-D Full Benchmark"
echo "  Scenes: ${SCENES}"
echo "  Pose source: ${POSE_SOURCE}"
echo "  Tasks: ${TASKS}"
echo "  Output root: ${OUTPUT_ROOT}"
echo "  Continue on error: ${CONTINUE_ON_ERROR}"
echo "  GPU_IDS: ${GPU_IDS_RAW:-inherit}"
if [[ " ${TASK_LIST[*]} " == *" structured_light "* ]]; then
    echo "  SL manifest: ${STRUCTURED_LIGHT_MANIFEST}"
    echo "  SL configs: ${STRUCTURED_LIGHT_CONFIGS}"
fi
echo "═══════════════════════════════════════════════════════════"

failure_count=0

for scene_name in "${SCENE_LIST[@]}"; do
    scene_output_root="${OUTPUT_ROOT}/${scene_name}/${POSE_STEM}"
    log_file="${LOG_ROOT}/${scene_name}.log"

    mkdir -p "${scene_output_root}"
    : >"${log_file}"

    echo ""
    echo ">>> Running scene ${scene_name}"

    scene_failed=0
    rc=0
    for task_name in "${TASK_LIST[@]}"; do
        if run_scene_task "${scene_name}" "${task_name}" "${scene_output_root}" "${log_file}"; then
            :
        else
            rc=$?
            scene_failed=1
            break
        fi
    done

    if [[ "${scene_failed}" -eq 0 ]]; then
        status="success"
    else
        status="failed(${rc})"
        failure_count=$((failure_count + 1))
        echo "WARNING: scene ${scene_name} failed with exit code ${rc}. See ${log_file}"
        if [[ "${CONTINUE_ON_ERROR}" != "1" ]]; then
            printf "%s\t%s\t%s\t%s\n" "${scene_name}" "${status}" "${scene_output_root}" "${log_file}" >> "${SUMMARY_FILE}"
            exit "${rc}"
        fi
    fi

    printf "%s\t%s\t%s\t%s\n" "${scene_name}" "${status}" "${scene_output_root}" "${log_file}" >> "${SUMMARY_FILE}"
done

echo ""
echo "Summary written to ${SUMMARY_FILE}"

if [[ "${failure_count}" -gt 0 ]]; then
    exit 1
fi
