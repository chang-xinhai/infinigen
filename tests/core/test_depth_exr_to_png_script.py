# Copyright (C) 2026.

from pathlib import Path
import sys

import numpy as np
import pytest

import infinigen

REPO_ROOT = infinigen.repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark import depth_exr_to_png


def test_convert_depth_exr_path_directory_preserves_relative_layout(tmp_path, monkeypatch):
    input_root = tmp_path / "depth_exr"
    nested = input_root / "scene_a" / "rgb" / "depth"
    nested.mkdir(parents=True)
    exr_a = nested / "frame_0001.exr"
    exr_b = nested / "frame_0002.exr"
    exr_a.write_bytes(b"")
    exr_b.write_bytes(b"")
    output_root = tmp_path / "depth_png"

    recorded_writes = []

    monkeypatch.setattr(
        depth_exr_to_png,
        "_load_depth_array",
        lambda path: np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
    )
    monkeypatch.setattr(
        depth_exr_to_png,
        "_colorize_depth_array",
        lambda depth: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    monkeypatch.setattr(
        depth_exr_to_png,
        "_write_png",
        lambda path, image: recorded_writes.append((Path(path), image.shape)),
    )

    outputs = depth_exr_to_png.convert_depth_exr_path(
        input_root,
        output_root=output_root,
        recursive=True,
    )

    assert outputs == [
        output_root / "scene_a" / "rgb" / "depth" / "frame_0001.png",
        output_root / "scene_a" / "rgb" / "depth" / "frame_0002.png",
    ]
    assert [path for path, _ in recorded_writes] == outputs


def test_convert_depth_exr_file_rejects_existing_output_without_overwrite(tmp_path, monkeypatch):
    exr_path = tmp_path / "frame_0001.exr"
    exr_path.write_bytes(b"")
    output_path = tmp_path / "frame_0001.png"
    output_path.write_bytes(b"existing")

    monkeypatch.setattr(
        depth_exr_to_png,
        "_load_depth_array",
        lambda path: np.array([[1.0]], dtype=np.float32),
    )
    monkeypatch.setattr(
        depth_exr_to_png,
        "_colorize_depth_array",
        lambda depth: np.zeros((1, 1, 3), dtype=np.uint8),
    )

    with pytest.raises(FileExistsError):
        depth_exr_to_png.convert_depth_exr_file(
            exr_path,
            output_path=output_path,
            overwrite=False,
        )
