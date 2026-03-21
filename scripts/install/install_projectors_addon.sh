#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADDON_NAME="${ADDON_NAME:-Projectors}"
PROJECTORS_REPO="${PROJECTORS_REPO:-https://github.com/Ocupe/Projectors.git}"
PROJECTORS_CACHE_ROOT="${PROJECTORS_CACHE_ROOT:-${HOME}/.cache/deepsl-setup}"
PROJECTORS_SRC="${PROJECTORS_SRC:-${PROJECTORS_CACHE_ROOT}/Projectors}"
BLENDER_EXTENSIONS_USER="${BLENDER_EXTENSIONS_USER:-}"
BLENDER_ADDONS="${BLENDER_ADDONS:-}"
BLENDER_BIN="${BLENDER_BIN:-}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INSTALL_MODE="${INSTALL_MODE:-symlink}"
AUTO_INSTALL_BLENDER="${AUTO_INSTALL_BLENDER:-1}"

download_blender_if_needed() {
    if [[ "${AUTO_INSTALL_BLENDER}" != "1" ]]; then
        return 1
    fi

    echo "Blender installation not found. Installing bundled Blender 4.2 into ${REPO_ROOT}."

    local os arch blender_wget_link blender_wget_file blender_untar_dir blender_dir
    os="$(uname -s)"
    arch="$(uname -m)"

    if ! command -v wget >/dev/null 2>&1; then
        echo "wget is required to auto-install Blender." >&2
        return 1
    fi

    if [[ "${os}" == "Linux" ]]; then
        blender_wget_link='https://download.blender.org/release/Blender4.2/blender-4.2.0-linux-x64.tar.xz'
        blender_wget_file='blender.tar.xz'
        blender_untar_dir='blender-4.2.0-linux-x64'
        blender_dir='blender'
    elif [[ "${os}" == "Darwin" ]]; then
        if [[ "${arch}" == "arm64" ]]; then
            blender_wget_link='https://download.blender.org/release/Blender4.2/blender-4.2.0-macos-arm64.dmg'
        else
            blender_wget_link='https://download.blender.org/release/Blender4.2/blender-4.2.0-macos-x64.dmg'
        fi
        blender_wget_file='blender.dmg'
        blender_dir='Blender.app'
    else
        echo "Unsupported OS for auto-install: ${os}" >&2
        return 1
    fi

    (
        cd "${REPO_ROOT}"
        if [[ -d "${blender_dir}" ]]; then
            exit 0
        fi

        wget -O "${blender_wget_file}" "${blender_wget_link}"

        if [[ "${os}" == "Darwin" ]]; then
            hdiutil attach "${blender_wget_file}"
            cp -r /Volumes/Blender/Blender.app "${blender_dir}"
            hdiutil detach /Volumes/Blender
        else
            tar -xf "${blender_wget_file}"
            mv "${blender_untar_dir}" "${blender_dir}"
        fi

        rm -f "${blender_wget_file}"
    )
}

query_addons_dir_from_blender() {
    local blender_bin="$1"
    "${blender_bin}" --background --factory-startup --python-expr \
        "import addon_utils; paths = addon_utils.paths(); print('__ADDONS_DIR__=' + paths[0] if paths else '', end='')" \
        2>/dev/null | sed -n 's/^__ADDONS_DIR__=//p' | head -n 1
}

query_extensions_user_dir_from_blender() {
    local blender_bin="$1"
    "${blender_bin}" --background --factory-startup --python-expr \
        "import bpy; repos = bpy.context.preferences.extensions.repos; user = next((r.directory for r in repos if r.module == 'user_default'), ''); print('__EXT_DIR__=' + user, end='')" \
        2>/dev/null | sed -n 's/^__EXT_DIR__=//p' | head -n 1
}

resolve_extension_pkg_id() {
    if [[ ! -f "${PROJECTORS_SRC}/blender_manifest.toml" ]]; then
        return 1
    fi

    PROJECTORS_SRC="${PROJECTORS_SRC}" "${PYTHON_BIN}" - <<'PY' 2>/dev/null
import os
from pathlib import Path

manifest = Path(os.environ["PROJECTORS_SRC"]) / "blender_manifest.toml"
pkg_id = None
for raw_line in manifest.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line.startswith("id"):
        continue
    key, _, value = line.partition("=")
    if key.strip() != "id":
        continue
    pkg_id = value.strip().strip('"').strip("'")
    break
if not pkg_id:
    raise SystemExit(1)
print(pkg_id, end="")
PY
}

resolve_extensions_user_dir() {
    if [[ -n "${BLENDER_EXTENSIONS_USER}" ]]; then
        printf '%s\n' "${BLENDER_EXTENSIONS_USER}"
        return 0
    fi

    if [[ -n "${BLENDER_BIN}" && -x "${BLENDER_BIN}" ]]; then
        if resolved="$(query_extensions_user_dir_from_blender "${BLENDER_BIN}")"; then
            if [[ -n "${resolved}" ]]; then
                printf '%s\n' "${resolved}"
                return 0
            fi
        fi
    fi

    if command -v blender >/dev/null 2>&1; then
        if resolved="$(query_extensions_user_dir_from_blender "$(command -v blender)")"; then
            if [[ -n "${resolved}" ]]; then
                printf '%s\n' "${resolved}"
                return 0
            fi
        fi
    fi

    printf '%s\n' "${HOME}/.config/blender/4.2/extensions/user_default"
    return 0
}

resolve_addons_dir() {
    if [[ -n "${BLENDER_ADDONS}" ]]; then
        printf '%s\n' "${BLENDER_ADDONS}"
        return 0
    fi

    if resolved="$("${PYTHON_BIN}" - <<'PY' 2>/dev/null
try:
    import addon_utils
except Exception:
    raise SystemExit(1)

paths = addon_utils.paths()
if not paths:
    raise SystemExit(1)

print(paths[0], end="")
PY
)"; then
        if [[ -n "${resolved}" ]]; then
            printf '%s\n' "${resolved}"
            return 0
        fi
    fi

    if [[ -n "${BLENDER_BIN}" && -x "${BLENDER_BIN}" ]]; then
        if resolved="$(query_addons_dir_from_blender "${BLENDER_BIN}")"; then
            if [[ -n "${resolved}" ]]; then
                printf '%s\n' "${resolved}"
                return 0
            fi
        fi
    fi

    if command -v blender >/dev/null 2>&1; then
        if resolved="$(query_addons_dir_from_blender "$(command -v blender)")"; then
            if [[ -n "${resolved}" ]]; then
                printf '%s\n' "${resolved}"
                return 0
            fi
        fi
    fi

    local bundled_linux_bin="${REPO_ROOT}/blender/blender"
    local bundled_linux_scripts="${REPO_ROOT}/blender/4.2/scripts"
    local bundled_linux="${bundled_linux_scripts}/addons"
    local bundled_macos_bin="${REPO_ROOT}/Blender.app/Contents/MacOS/Blender"
    local bundled_macos_scripts="${REPO_ROOT}/Blender.app/Contents/Resources/4.2/scripts"
    local bundled_macos="${bundled_macos_scripts}/addons"

    if [[ -x "${bundled_linux_bin}" && -d "${bundled_linux_scripts}" ]]; then
        printf '%s\n' "${bundled_linux}"
        return 0
    fi

    if [[ -x "${bundled_macos_bin}" && -d "${bundled_macos_scripts}" ]]; then
        printf '%s\n' "${bundled_macos}"
        return 0
    fi

    download_blender_if_needed

    if [[ -x "${bundled_linux_bin}" && -d "${bundled_linux_scripts}" ]]; then
        printf '%s\n' "${bundled_linux}"
        return 0
    fi

    if [[ -x "${bundled_macos_bin}" && -d "${bundled_macos_scripts}" ]]; then
        printf '%s\n' "${bundled_macos}"
        return 0
    fi

    echo "Could not determine Blender addons directory." >&2
    echo "Set BLENDER_ADDONS=/path/to/blender/.../scripts/addons or BLENDER_BIN=/path/to/blender and rerun." >&2
    return 1
}

prepare_source_tree() {
    if [[ -f "${PROJECTORS_SRC}/__init__.py" ]]; then
        echo "Using existing Projectors source: ${PROJECTORS_SRC}"
        return 0
    fi

    mkdir -p "${PROJECTORS_CACHE_ROOT}"
    echo "Cloning Projectors addon into ${PROJECTORS_SRC}"
    git clone "${PROJECTORS_REPO}" "${PROJECTORS_SRC}"
}

install_addon() {
    local addon_root="$1"
    local target="${addon_root}/${ADDON_NAME}"

    mkdir -p "${addon_root}"
    rm -rf "${target}"

    case "${INSTALL_MODE}" in
        symlink)
            ln -s "${PROJECTORS_SRC}" "${target}"
            ;;
        copy)
            cp -R "${PROJECTORS_SRC}" "${target}"
            ;;
        *)
            echo "Unsupported INSTALL_MODE=${INSTALL_MODE}. Use symlink or copy." >&2
            return 1
            ;;
    esac

    echo "Installed ${ADDON_NAME} addon at ${target}"
}

install_extension() {
    local extension_root="$1"
    local pkg_id="$2"
    local target="${extension_root}/${pkg_id}"

    mkdir -p "${extension_root}"
    rm -rf "${target}"

    case "${INSTALL_MODE}" in
        symlink)
            ln -s "${PROJECTORS_SRC}" "${target}"
            ;;
        copy)
            cp -R "${PROJECTORS_SRC}" "${target}"
            ;;
        *)
            echo "Unsupported INSTALL_MODE=${INSTALL_MODE}. Use symlink or copy." >&2
            return 1
            ;;
    esac

    echo "Installed ${ADDON_NAME} Blender extension at ${target}"
}

main() {
    prepare_source_tree

    local extension_pkg_id=""
    if extension_pkg_id="$(resolve_extension_pkg_id)"; then
        local extension_root
        extension_root="$(resolve_extensions_user_dir)"
        install_extension "${extension_root}" "${extension_pkg_id}"

        cat <<EOF
Next step:
  rerun Blender or your structured-light job; it should enable module 'bl_ext.user_default.${extension_pkg_id}' at runtime.

Resolved settings:
  PROJECTORS_SRC=${PROJECTORS_SRC}
  BLENDER_EXTENSIONS_USER=${extension_root}
  BLENDER_EXTENSION_ID=${extension_pkg_id}
  INSTALL_MODE=${INSTALL_MODE}
EOF
        return 0
    fi

    local addon_root
    addon_root="$(resolve_addons_dir)"
    install_addon "${addon_root}"

    cat <<EOF
Next step:
  enable the addon in Blender, or let structured-light rendering auto-enable module '${ADDON_NAME}' at runtime.

Resolved settings:
  PROJECTORS_SRC=${PROJECTORS_SRC}
  BLENDER_ADDONS=${addon_root}
  INSTALL_MODE=${INSTALL_MODE}
EOF
}

main "$@"
