#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
CONDA_ENV="${CONDA_ENV:-}"

DATASET_ROOT="${DATASET_ROOT:-${REPO_ROOT}/data/neural_rgbd}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/outputs/benchmark/neural_rgbd/scene_ply}"
SCENES="${SCENES:-ALL}"
ASCII_PLY="${ASCII_PLY:-0}"
INCLUDE_HIDDEN="${INCLUDE_HIDDEN:-0}"
OVERWRITE="${OVERWRITE:-1}"

discover_all_scenes() {
    local scene_name
    local blend_root="${DATASET_ROOT}/blendswap_scenes"
    local data_root="${DATASET_ROOT}/neural_rgbd_data"

    if [[ ! -d "${blend_root}" || ! -d "${data_root}" ]]; then
        return
    fi

    while IFS= read -r scene_name; do
        if [[ -d "${blend_root}/${scene_name}" ]]; then
            printf '%s\n' "${scene_name}"
        fi
    done < <(find "${data_root}" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
}

resolve_scene_blend() {
    local scene_name="$1"
    local scene_dir="${DATASET_ROOT}/blendswap_scenes/${scene_name}"
    local -a blends=()

    while IFS= read -r blend_path; do
        blends+=("${blend_path}")
    done < <(find "${scene_dir}" -mindepth 1 -maxdepth 1 -type f -name '*.blend' | sort)

    if [[ "${#blends[@]}" -eq 0 ]]; then
        echo "No .blend file found under ${scene_dir}" >&2
        return 1
    fi
    if [[ "${#blends[@]}" -gt 1 ]]; then
        echo "Expected exactly one .blend file under ${scene_dir}, found ${#blends[@]}" >&2
        return 1
    fi

    printf '%s\n' "${blends[0]}"
}

run_export() {
    local input_blend="$1"
    local output_path="$2"
    local -a cmd=()

    if [[ -n "${CONDA_ENV}" ]]; then
        cmd=(conda run -n "${CONDA_ENV}" python)
    else
        cmd=("${PYTHON_BIN}")
    fi

    cmd+=(
        -m infinigen.launch_blender
        -m infinigen.tools.export_scene_ply
        --
        --input_blend "${input_blend}"
        --output_path "${output_path}"
    )

    if [[ "${ASCII_PLY}" == "1" ]]; then
        cmd+=(--ascii)
    fi
    if [[ "${INCLUDE_HIDDEN}" == "1" ]]; then
        cmd+=(--include_hidden)
    fi
    if [[ "${OVERWRITE}" == "1" ]]; then
        cmd+=(--overwrite)
    fi

    printf 'Export command:'
    printf ' %q' "${cmd[@]}"
    printf '\n'
    "${cmd[@]}"
}

if [[ "${SCENES}" == "ALL" ]]; then
    mapfile -t SCENE_LIST < <(discover_all_scenes)
else
    read -r -a SCENE_LIST <<<"${SCENES}"
fi

if [[ "${#SCENE_LIST[@]}" -eq 0 ]]; then
    echo "No Neural RGB-D scenes found under ${DATASET_ROOT}"
    exit 1
fi

mkdir -p "${OUTPUT_ROOT}"

for scene_name in "${SCENE_LIST[@]}"; do
    if [[ ! -d "${DATASET_ROOT}/neural_rgbd_data/${scene_name}" ]]; then
        echo "Neural RGB-D scene data not found for ${scene_name}: ${DATASET_ROOT}/neural_rgbd_data/${scene_name}" >&2
        exit 1
    fi
    blend_path="$(resolve_scene_blend "${scene_name}")"
    scene_output_dir="${OUTPUT_ROOT}/${scene_name}"
    output_path="${scene_output_dir}/${scene_name}.ply"
    mkdir -p "${scene_output_dir}"

    echo "=== Exporting ${scene_name}"
    run_export "${blend_path}" "${output_path}"
    echo "Wrote ${output_path}"
done
