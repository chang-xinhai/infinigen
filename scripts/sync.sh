#!/bin/bash

set -euo pipefail

REMOTE_ROOT="/Research/infinigen"
TAR_BUNDLE_SUFFIX=".__sync_tar__"
TAR_PART_SIZE="5G"
TAR_COMPRESSION_CMD="zstd -19 -T0"
PROGRESS_INTERVAL_SECONDS="${SYNC_PROGRESS_INTERVAL_SECONDS:-30}"
TEMP_DIRS=()

cleanup_temp_dirs() {
    local dir
    for dir in "${TEMP_DIRS[@]}"; do
        [[ -d "${dir}" ]] && rm -rf "${dir}"
    done
}

trap cleanup_temp_dirs EXIT

usage() {
    cat <<'EOF'
Usage:
  bash scripts/sync.sh upload [--tar] <relative_path>
  bash scripts/sync.sh download [--tar] <relative_path>

Examples:
  bash scripts/sync.sh upload outputs/benchmark/structured_light_indoors/seed_0
  bash scripts/sync.sh download outputs/benchmark/structured_light_indoors/seed_0
  bash scripts/sync.sh upload --tar outputs/benchmark/structured_light_indoors/
  bash scripts/sync.sh download --tar outputs/benchmark/structured_light_indoors/

Behavior:
  Local relative path:  relative_path/to/local/file_or_dir
  Remote full path:     /Research/infinigen/relative_path/to/remote/file_or_dir

Tar mode:
  --tar uploads a compressed tar.zst bundle stored remotely as:
    /Research/infinigen/<parent>/<basename>.__sync_tar__/
  The bundle contains 5GB split parts, a manifest, and SHA256 checksums.
EOF
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command not found: $1" >&2
        exit 1
    fi
}

log_progress() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

format_elapsed() {
    local total_seconds="$1"
    local hours=$((total_seconds / 3600))
    local minutes=$(((total_seconds % 3600) / 60))
    local seconds=$((total_seconds % 60))

    if (( hours > 0 )); then
        printf '%dh%02dm%02ds' "${hours}" "${minutes}" "${seconds}"
    elif (( minutes > 0 )); then
        printf '%dm%02ds' "${minutes}" "${seconds}"
    else
        printf '%ds' "${seconds}"
    fi
}

run_with_heartbeat() {
    local description="$1"
    shift

    local start_ts
    start_ts="$(date +%s)"
    log_progress "${description} started"

    "$@" &
    local cmd_pid=$!
    local exit_code=0

    while kill -0 "${cmd_pid}" >/dev/null 2>&1; do
        sleep "${PROGRESS_INTERVAL_SECONDS}"
        if ! kill -0 "${cmd_pid}" >/dev/null 2>&1; then
            break
        fi
        local now_ts
        now_ts="$(date +%s)"
        log_progress "${description} still running ($(format_elapsed "$((now_ts - start_ts))") elapsed)"
    done

    if wait "${cmd_pid}"; then
        :
    else
        exit_code=$?
        local now_ts
        now_ts="$(date +%s)"
        log_progress "${description} failed after $(format_elapsed "$((now_ts - start_ts))")"
        return "${exit_code}"
    fi

    local now_ts
    now_ts="$(date +%s)"
    log_progress "${description} completed in $(format_elapsed "$((now_ts - start_ts))")"
}

register_temp_dir() {
    TEMP_DIRS+=("$1")
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

parse_args() {
    MODE=""
    REL_PATH=""
    USE_TAR=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            upload|download)
                if [[ -n "${MODE}" ]]; then
                    echo "Error: mode specified multiple times" >&2
                    usage
                    exit 1
                fi
                MODE="$1"
                shift
                ;;
            --tar)
                USE_TAR=1
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                if [[ -n "${REL_PATH}" ]]; then
                    echo "Error: unexpected extra argument: $1" >&2
                    usage
                    exit 1
                fi
                REL_PATH="$(normalize_relative_path "$1")"
                shift
                ;;
        esac
    done

    if [[ -z "${MODE}" || -z "${REL_PATH}" ]]; then
        usage
        exit 1
    fi
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

get_tar_bundle_name() {
    printf '%s%s\n' "$(basename "$1")" "${TAR_BUNDLE_SUFFIX}"
}

get_tar_archive_name() {
    local rel_path="$1"
    printf '%s.tar.zst\n' "$(basename "${rel_path}")"
}

find_downloaded_bundle_dir() {
    local search_root="$1"
    local bundle_name="$2"
    local match

    match="$(find "${search_root}" -type d -name "${bundle_name}" | sort | head -n 1 || true)"
    if [[ -z "${match}" ]]; then
        echo "Error: downloaded tar bundle not found locally: ${bundle_name}" >&2
        exit 1
    fi

    printf '%s\n' "${match}"
}

read_manifest_value() {
    local manifest_path="$1"
    local key="$2"
    awk -F= -v target="${key}" '$1 == target { sub(/^[^=]*=/, "", $0); print $0; exit }' "${manifest_path}"
}

remove_local_target() {
    local target_path="$1"

    if [[ -e "${target_path}" || -L "${target_path}" ]]; then
        rm -rf "${target_path}"
    fi
}

create_tar_parts() {
    local rel_path="$1"
    local part_prefix="$2"

    tar -I "${TAR_COMPRESSION_CMD}" -cf - "${rel_path}" | split -d -a 4 -b "${TAR_PART_SIZE}" - "${part_prefix}"
}

write_bundle_checksums() {
    local bundle_dir="$1"
    shift

    (
        cd "${bundle_dir}"
        sha256sum "$@" > sha256sums.txt
    )
}

verify_bundle_checksums() {
    local bundle_dir="$1"

    (
        cd "${bundle_dir}"
        sha256sum -c sha256sums.txt
    )
}

extract_tar_bundle() {
    local -a part_paths=("$@")
    cat "${part_paths[@]}" | tar -I "${TAR_COMPRESSION_CMD}" -xf - -C "${PWD}"
}

create_tar_bundle() {
    local rel_path="$1"
    local local_path="$2"
    local bundle_dir="$3"
    local archive_name
    archive_name="$(get_tar_archive_name "${rel_path}")"
    local part_prefix="${bundle_dir}/${archive_name}.part-"
    local source_kind="file"
    local -a part_paths=()
    local -a part_files=()
    local part_path
    local manifest_path="${bundle_dir}/manifest.txt"

    if [[ -d "${local_path}" ]]; then
        source_kind="directory"
    fi

    mkdir -p "${bundle_dir}"

    run_with_heartbeat "Creating compressed tar parts for ${rel_path}" create_tar_parts "${rel_path}" "${part_prefix}"

    mapfile -t part_paths < <(find "${bundle_dir}" -maxdepth 1 -type f -name "${archive_name}.part-*" | sort)
    if [[ ${#part_paths[@]} -eq 0 ]]; then
        echo "Error: failed to create tar bundle parts for ${rel_path}" >&2
        exit 1
    fi

    for part_path in "${part_paths[@]}"; do
        part_files+=("$(basename "${part_path}")")
    done

    log_progress "Created ${#part_files[@]} tar part(s) for ${rel_path}"
    run_with_heartbeat "Writing SHA256 checksums for ${rel_path}" write_bundle_checksums "${bundle_dir}" "${part_files[@]}"

    cat > "${manifest_path}" <<EOF
VERSION=1
REL_PATH=${rel_path}
SOURCE_KIND=${source_kind}
ENTRY_NAME=$(basename "${rel_path}")
ARCHIVE_NAME=${archive_name}
PART_COUNT=${#part_files[@]}
PART_SIZE=${TAR_PART_SIZE}
COMPRESSION=${TAR_COMPRESSION_CMD}
EOF

    log_progress "Wrote tar bundle manifest to ${manifest_path}"
}

upload_tar_bundle() {
    local rel_path="$1"
    local local_path="$2"
    local remote_parent="$3"
    local bundle_name
    bundle_name="$(get_tar_bundle_name "${rel_path}")"
    local remote_bundle_path="${remote_parent}/${bundle_name}"
    local temp_root
    temp_root="$(mktemp -d)"
    register_temp_dir "${temp_root}"
    local bundle_dir="${temp_root}/${bundle_name}"

    log_progress "Preparing tar bundle upload for ${rel_path}"
    log_progress "Remote bundle: ${remote_bundle_path}"
    create_tar_bundle "${rel_path}" "${local_path}" "${bundle_dir}"

    log_progress "Ensuring remote parent exists: ${remote_parent}"
    mkdir_remote_parents "${remote_parent}"
    aliyunpan rm "${remote_bundle_path}" >/dev/null 2>&1 || true
    log_progress "Removed any previous remote tar bundle at ${remote_bundle_path}"
    run_with_heartbeat "Uploading tar bundle ${rel_path} to aliyunpan" aliyunpan upload "${bundle_dir}" "${remote_parent}"
}

download_tar_bundle() {
    local rel_path="$1"
    local local_path="$2"
    local local_parent="$3"
    local remote_parent="$4"
    local bundle_name
    bundle_name="$(get_tar_bundle_name "${rel_path}")"
    local remote_bundle_path="${remote_parent}/${bundle_name}"
    local archive_name
    archive_name="$(get_tar_archive_name "${rel_path}")"
    local temp_root
    temp_root="$(mktemp -d)"
    register_temp_dir "${temp_root}"
    local bundle_dir
    local manifest_path
    local checksum_path
    local manifest_rel_path
    local -a part_paths=()

    mkdir -p "${local_parent}"

    log_progress "Preparing tar bundle download for ${rel_path}"
    log_progress "Remote bundle: ${remote_bundle_path}"
    log_progress "Local target: ${rel_path}"

    run_with_heartbeat "Downloading tar bundle ${rel_path} from aliyunpan" aliyunpan download --saveto "${temp_root}" "${remote_bundle_path}"
    bundle_dir="$(find_downloaded_bundle_dir "${temp_root}" "${bundle_name}")"
    log_progress "Downloaded tar bundle into ${bundle_dir}"

    manifest_path="${bundle_dir}/manifest.txt"
    checksum_path="${bundle_dir}/sha256sums.txt"

    if [[ ! -f "${manifest_path}" ]]; then
        echo "Error: tar bundle manifest missing: ${manifest_path}" >&2
        exit 1
    fi

    manifest_rel_path="$(read_manifest_value "${manifest_path}" "REL_PATH")"
    if [[ -n "${manifest_rel_path}" && "${manifest_rel_path}" != "${rel_path}" ]]; then
        echo "Error: tar bundle path mismatch, expected ${rel_path}, got ${manifest_rel_path}" >&2
        exit 1
    fi

    mapfile -t part_paths < <(find "${bundle_dir}" -maxdepth 1 -type f -name "${archive_name}.part-*" | sort)
    if [[ ${#part_paths[@]} -eq 0 ]]; then
        echo "Error: tar bundle parts missing for ${rel_path}" >&2
        exit 1
    fi

    if [[ -f "${checksum_path}" ]]; then
        run_with_heartbeat "Verifying tar bundle checksums for ${rel_path}" verify_bundle_checksums "${bundle_dir}"
    fi

    log_progress "Replacing local target path ${local_path}"
    remove_local_target "${local_path}"
    mkdir -p "${local_parent}"
    run_with_heartbeat "Extracting tar bundle for ${rel_path}" extract_tar_bundle "${part_paths[@]}"

    if [[ ! -e "${local_path}" ]]; then
        echo "Error: tar bundle extraction did not restore target: ${rel_path}" >&2
        exit 1
    fi

    log_progress "Restored ${rel_path} from tar bundle"
}

main() {
    parse_args "$@"

    require_command aliyunpan

    if [[ ! "${PROGRESS_INTERVAL_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: SYNC_PROGRESS_INTERVAL_SECONDS must be a positive integer, got: ${PROGRESS_INTERVAL_SECONDS}" >&2
        exit 1
    fi

    local rel_path="${REL_PATH}"
    local local_path="${PWD}/${rel_path}"
    local remote_path="${REMOTE_ROOT}/${rel_path}"
    local remote_parent
    remote_parent="$(dirname "${remote_path}")"
    local local_parent
    local_parent="$(dirname "${local_path}")"

    if [[ "${USE_TAR}" -eq 1 ]]; then
        require_command tar
        require_command zstd
        require_command split
        require_command sha256sum
    fi

    case "${MODE}" in
        upload)
            if [[ ! -e "${local_path}" ]]; then
                echo "Error: local path does not exist: ${rel_path}" >&2
                exit 1
            fi

            if [[ "${USE_TAR}" -eq 1 ]]; then
                upload_tar_bundle "${rel_path}" "${local_path}" "${remote_parent}"
            else
                log_progress "Preparing upload for ${rel_path}"
                log_progress "Remote target: ${remote_path}"

                mkdir_remote_parents "${remote_parent}"
                run_with_heartbeat "Uploading ${rel_path} to aliyunpan" aliyunpan upload "${local_path}" "${remote_parent}"
            fi
            ;;
        download)
            if [[ "${USE_TAR}" -eq 1 ]]; then
                download_tar_bundle "${rel_path}" "${local_path}" "${local_parent}" "${remote_parent}"
            else
                mkdir -p "${local_parent}"

                log_progress "Preparing download for ${rel_path}"
                log_progress "Remote target: ${remote_path}"
                log_progress "Local target: ${rel_path}"

                run_with_heartbeat "Downloading ${rel_path} from aliyunpan" aliyunpan download --saveto "${local_parent}" "${remote_path}"
                fix_download_layout "${rel_path}" "${local_parent}"
                log_progress "Restored ${rel_path}"
            fi
            ;;
        *)
            echo "Error: unsupported mode: ${MODE}" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"
