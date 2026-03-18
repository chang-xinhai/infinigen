#!/bin/bash

set -euo pipefail

REMOTE_ROOT="/Research/infinigen"

usage() {
    cat <<'EOF'
Usage:
  bash scripts/sync.sh upload <relative_path>
  bash scripts/sync.sh download <relative_path>

Examples:
  bash scripts/sync.sh upload relative_path/to/local/file_or_dir
  bash scripts/sync.sh download relative_path/to/remote/file_or_dir
Behavior:
  Local relative path:  relative_path/to/local/file_or_dir
  Remote full path:     /Research/infinigen/relative_path/to/remote/file_or_dir
EOF
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command not found: $1" >&2
        exit 1
    fi
}

normalize_relative_path() {
    local input="$1"

    if [[ -z "${input}" ]]; then
        echo "Error: relative path is empty" >&2
        exit 1
    fi

    if [[ "${input}" == /* ]]; then
        echo "Error: path must be relative to repository root, got absolute path: ${input}" >&2
        exit 1
    fi

    local normalized="${input#./}"
    normalized="${normalized%/}"

    if [[ "${normalized}" == "." || -z "${normalized}" ]]; then
        echo "Error: invalid relative path: ${input}" >&2
        exit 1
    fi

    if [[ "${normalized}" == ../* || "${normalized}" == *"/../"* || "${normalized}" == ".." ]]; then
        echo "Error: parent traversal is not allowed: ${input}" >&2
        exit 1
    fi

    printf '%s\n' "${normalized}"
}

mkdir_remote_parents() {
    local remote_dir="$1"
    local current=""
    IFS='/' read -r -a parts <<< "${remote_dir#/}"

    for part in "${parts[@]}"; do
        [[ -z "${part}" ]] && continue
        current="${current}/${part}"
        aliyunpan mkdir "${current}" >/dev/null 2>&1 || true
    done
}

prune_empty_dirs() {
    local dir="$1"
    local stop_dir="$2"

    while [[ "${dir}" != "${stop_dir}" && "${dir}" != "/" ]]; do
        rmdir "${dir}" >/dev/null 2>&1 || break
        dir="$(dirname "${dir}")"
    done
}

fix_download_layout() {
    local rel_path="$1"
    local local_parent="$2"
    local target_path="${PWD}/${rel_path}"

    if [[ -e "${target_path}" ]]; then
        return 0
    fi

    local nested_path="${local_parent}/${REMOTE_ROOT#/}/${rel_path}"
    if [[ ! -e "${nested_path}" ]]; then
        return 0
    fi

    mkdir -p "$(dirname "${target_path}")"
    mv "${nested_path}" "${target_path}"
    prune_empty_dirs "$(dirname "${nested_path}")" "${local_parent}"
}

main() {
    if [[ $# -ne 2 ]]; then
        usage
        exit 1
    fi

    require_command aliyunpan

    local mode="$1"
    local rel_path
    rel_path="$(normalize_relative_path "$2")"

    local local_path="${PWD}/${rel_path}"
    local remote_path="${REMOTE_ROOT}/${rel_path}"
    local remote_parent
    remote_parent="$(dirname "${remote_path}")"
    local local_parent
    local_parent="$(dirname "${local_path}")"

    case "${mode}" in
        upload)
            if [[ ! -e "${local_path}" ]]; then
                echo "Error: local path does not exist: ${rel_path}" >&2
                exit 1
            fi

            echo "Uploading ${rel_path}"
            echo "Remote target: ${remote_path}"

            mkdir_remote_parents "${remote_parent}"
            aliyunpan upload "${local_path}" "${remote_parent}"
            ;;
        download)
            mkdir -p "${local_parent}"

            echo "Downloading ${remote_path}"
            echo "Local target: ${rel_path}"

            aliyunpan download --saveto "${local_parent}" "${remote_path}"
            fix_download_layout "${rel_path}" "${local_parent}"
            ;;
        *)
            echo "Error: unsupported mode: ${mode}" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"
