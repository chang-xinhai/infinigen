#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADDON_NAME="${ADDON_NAME:-Projectors}"
PROJECTORS_REPO="${PROJECTORS_REPO:-https://github.com/Ocupe/Projectors.git}"
PROJECTORS_CACHE_ROOT="${PROJECTORS_CACHE_ROOT:-${HOME}/.cache/deepsl-setup}"
PROJECTORS_SRC="${PROJECTORS_SRC:-${PROJECTORS_CACHE_ROOT}/Projectors}"
BLENDER_ADDONS="${BLENDER_ADDONS:-}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INSTALL_MODE="${INSTALL_MODE:-symlink}"

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

print(paths()[0], end="")
PY
)"; then
        if [[ -n "${resolved}" ]]; then
            printf '%s\n' "${resolved}"
            return 0
        fi
    fi

    local bundled_linux="${REPO_ROOT}/blender/4.2/scripts/addons"
    local bundled_macos="${REPO_ROOT}/Blender.app/Contents/Resources/4.2/scripts/addons"

    if [[ -d "${bundled_linux}" ]]; then
        printf '%s\n' "${bundled_linux}"
        return 0
    fi

    if [[ -d "${bundled_macos}" ]]; then
        printf '%s\n' "${bundled_macos}"
        return 0
    fi

    echo "Could not determine Blender addons directory." >&2
    echo "Set BLENDER_ADDONS=/path/to/blender/.../scripts/addons and rerun." >&2
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

main() {
    local addon_root
    addon_root="$(resolve_addons_dir)"
    prepare_source_tree
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
