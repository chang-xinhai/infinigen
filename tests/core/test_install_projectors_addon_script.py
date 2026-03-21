# Copyright (C) 2026.

import os
import subprocess
from pathlib import Path

import infinigen


def test_install_projectors_addon_script_links_existing_source(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/install/install_projectors_addon.sh"
    addons_dir = tmp_path / "addons"
    projectors_src = tmp_path / "Projectors"
    projectors_src.mkdir(parents=True, exist_ok=True)
    (projectors_src / "__init__.py").write_text("def register():\n    pass\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "BLENDER_ADDONS": str(addons_dir),
            "PROJECTORS_SRC": str(projectors_src),
            "PYTHON_BIN": "python",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    installed_path = addons_dir / "Projectors"
    assert installed_path.is_symlink()
    assert installed_path.resolve() == projectors_src.resolve()
    assert "Installed Projectors addon" in result.stdout


def test_install_projectors_addon_script_resolves_addons_via_blender_bin(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/install/install_projectors_addon.sh"
    addons_dir = tmp_path / "blender_addons"
    projectors_src = tmp_path / "Projectors"
    fake_blender = tmp_path / "fake_blender.sh"

    projectors_src.mkdir(parents=True, exist_ok=True)
    (projectors_src / "__init__.py").write_text("def register():\n    pass\n", encoding="utf-8")
    fake_blender.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s' '{addons_dir}'
""",
        encoding="utf-8",
    )
    fake_blender.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "BLENDER_BIN": str(fake_blender),
            "PROJECTORS_SRC": str(projectors_src),
            "AUTO_INSTALL_BLENDER": "0",
            "PYTHON_BIN": "python",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    installed_path = addons_dir / "Projectors"
    assert installed_path.is_symlink()
    assert installed_path.resolve() == projectors_src.resolve()


def test_install_projectors_addon_script_parses_blender_banner_output(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/install/install_projectors_addon.sh"
    addons_dir = tmp_path / "blender_addons"
    projectors_src = tmp_path / "Projectors"
    fake_blender = tmp_path / "fake_blender.sh"

    projectors_src.mkdir(parents=True, exist_ok=True)
    (projectors_src / "__init__.py").write_text("def register():\n    pass\n", encoding="utf-8")
    fake_blender.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' '__ADDONS_DIR__={addons_dir}'
printf '%s\\n' 'Blender 4.2.0'
printf '%s\\n' 'Blender quit'
""",
        encoding="utf-8",
    )
    fake_blender.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "BLENDER_BIN": str(fake_blender),
            "PROJECTORS_SRC": str(projectors_src),
            "AUTO_INSTALL_BLENDER": "0",
            "PYTHON_BIN": "python",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    installed_path = addons_dir / "Projectors"
    assert installed_path.is_symlink()
    assert installed_path.resolve() == projectors_src.resolve()


def test_install_projectors_addon_script_installs_manifest_extension_into_user_repo(tmp_path):
    repo_root = infinigen.repo_root()
    script_path = repo_root / "scripts/install/install_projectors_addon.sh"
    ext_repo_dir = tmp_path / "extensions" / "user_default"
    projectors_src = tmp_path / "Projectors"

    projectors_src.mkdir(parents=True, exist_ok=True)
    (projectors_src / "__init__.py").write_text("def register():\n    pass\n", encoding="utf-8")
    (projectors_src / "blender_manifest.toml").write_text(
        'schema_version = "1.0.0"\n'
        'id = "projector"\n'
        'name = "Projector"\n'
        'version = "1.0.0"\n'
        'type = "add-on"\n'
        'blender_version_min = "4.2.0"\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "BLENDER_EXTENSIONS_USER": str(ext_repo_dir),
            "PROJECTORS_SRC": str(projectors_src),
            "AUTO_INSTALL_BLENDER": "0",
            "PYTHON_BIN": "python",
        }
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    installed_path = ext_repo_dir / "projector"
    assert installed_path.is_symlink()
    assert installed_path.resolve() == projectors_src.resolve()
    assert "BLENDER_EXTENSION_ID=projector" in result.stdout
