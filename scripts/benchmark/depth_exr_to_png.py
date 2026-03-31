#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert depth EXR files to colorized PNG previews."
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="A single .exr file or a directory containing .exr files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to writing PNGs next to the source EXRs.",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.exr",
        help="Glob pattern used when input_path is a directory.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan input directories for matching EXR files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing PNG outputs.",
    )
    return parser.parse_args()


def _iter_exr_files(input_path: Path, *, pattern: str, recursive: bool) -> list[Path]:
    input_path = Path(input_path)
    if input_path.is_file():
        if input_path.suffix.lower() != ".exr":
            raise ValueError(f"Expected a .exr file, got {input_path}")
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    iterator = input_path.rglob(pattern) if recursive else input_path.glob(pattern)
    files = sorted(path for path in iterator if path.is_file() and path.suffix.lower() == ".exr")
    if not files:
        raise FileNotFoundError(f"No .exr files found under {input_path} with pattern {pattern!r}")
    return files


def _output_path_for(exr_path: Path, *, input_root: Path | None, output_root: Path | None) -> Path:
    if output_root is None:
        return exr_path.with_suffix(".png")
    if input_root is None:
        return Path(output_root) / exr_path.with_suffix(".png").name
    rel = exr_path.relative_to(input_root)
    return Path(output_root) / rel.with_suffix(".png")


def _load_depth_array(exr_path: Path):
    from infinigen.core.rendering.post_render import load_depth, sanitize_depth

    return sanitize_depth(load_depth(exr_path))


def _colorize_depth_array(depth):
    from infinigen.core.rendering.post_render import colorize_depth

    return colorize_depth(depth)


def _write_png(output_path: Path, image) -> None:
    from imageio import imwrite

    imwrite(output_path, image)


def convert_depth_exr_file(
    exr_path: Path,
    *,
    output_path: Path,
    overwrite: bool = False,
) -> Path:
    exr_path = Path(exr_path)
    output_path = Path(output_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    depth = _load_depth_array(exr_path)
    colorized = _colorize_depth_array(depth)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(output_path, colorized)
    return output_path


def convert_depth_exr_path(
    input_path: Path,
    *,
    output_root: Path | None = None,
    pattern: str = "*.exr",
    recursive: bool = False,
    overwrite: bool = False,
) -> list[Path]:
    input_path = Path(input_path)
    exr_files = _iter_exr_files(input_path, pattern=pattern, recursive=recursive)
    input_root = input_path if input_path.is_dir() else None
    outputs = []
    for exr_path in exr_files:
        output_path = _output_path_for(
            exr_path,
            input_root=input_root,
            output_root=output_root,
        )
        outputs.append(
            convert_depth_exr_file(
                exr_path,
                output_path=output_path,
                overwrite=overwrite,
            )
        )
    return outputs


def main() -> None:
    args = _parse_args()
    outputs = convert_depth_exr_path(
        args.input_path,
        output_root=args.output_root,
        pattern=args.pattern,
        recursive=args.recursive,
        overwrite=args.overwrite,
    )
    for output in outputs:
        print(f"Wrote {output}")


if __name__ == "__main__":
    main()
