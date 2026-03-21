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
