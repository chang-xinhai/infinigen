#!/usr/bin/env python

import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt


def _is_primary_depth_file(path: Path, capture_root: Path | None = None) -> bool:
    if path.suffix.lower() not in {".npy", ".exr"}:
        return False
    rel = path.relative_to(capture_root).as_posix() if capture_root is not None else path.as_posix()
    name = path.name.lower()
    if "/left/" in rel or "/right/" in rel:
        return False
    if "_l_depth" in name or "_r_depth" in name:
        return False
    if "depth" in name:
        return True
    return "/rgb/depth/" in rel


def _iter_depth_files(capture_root: Path) -> list[Path]:
    candidates = sorted(
        path for path in capture_root.rglob("*") if _is_primary_depth_file(path, capture_root)
    )
    preferred = []
    fallback = []
    for path in candidates:
        rel = path.relative_to(capture_root).as_posix()
        if rel.startswith("output/rgb/depth/"):
            preferred.append(path)
        elif rel.startswith("structured_light/frames/") or rel.startswith("structured_light/task/structured_light/"):
            preferred.append(path)
        else:
            fallback.append(path)
    return preferred or fallback


def _load_depth_array(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        array = np.load(path)
    else:
        from infinigen.core.rendering.post_render import load_depth

        array = load_depth(path)
    array = np.asarray(array, dtype=np.float32)
    if array.ndim > 2:
        array = np.squeeze(array[..., 0])
    return array


def _downsample(values: np.ndarray, limit: int) -> np.ndarray:
    if values.size <= limit:
        return values
    step = max(1, values.size // limit)
    return values[::step][:limit]


def build_depth_histogram(
    capture_root: Path,
    output_json: Path,
    output_png: Path,
    bins: int,
    min_depth_m: float,
    max_depth_m: float,
    quantile_sample_limit: int,
) -> dict:
    depth_files = _iter_depth_files(capture_root)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    if not depth_files:
        payload = {
            "status": "no_depth_files_found",
            "capture_root": str(capture_root),
            "bins": bins,
            "min_depth_m": min_depth_m,
            "max_depth_m": max_depth_m,
            "depth_files": [],
        }
        output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    edges = np.linspace(min_depth_m, max_depth_m, bins + 1, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.int64)
    sample_chunks = []
    sample_budget_left = quantile_sample_limit
    valid_pixel_count = 0
    below_range_count = 0
    above_range_count = 0
    total_sum = 0.0
    min_seen = None
    max_seen = None

    for path in depth_files:
        depth = _load_depth_array(path)
        finite = depth[np.isfinite(depth)]
        if finite.size == 0:
            continue

        positive = finite[finite > 0.0]
        if positive.size == 0:
            continue

        min_local = float(positive.min())
        max_local = float(positive.max())
        min_seen = min_local if min_seen is None else min(min_seen, min_local)
        max_seen = max_local if max_seen is None else max(max_seen, max_local)
        below_range_count += int(np.count_nonzero(positive < min_depth_m))
        above_range_count += int(np.count_nonzero(positive > max_depth_m))

        in_range = positive[(positive >= min_depth_m) & (positive <= max_depth_m)]
        if in_range.size == 0:
            continue

        counts += np.histogram(in_range, bins=edges)[0]
        valid_pixel_count += int(in_range.size)
        total_sum += float(in_range.sum())

        if sample_budget_left > 0:
            sample = _downsample(in_range, sample_budget_left)
            sample_budget_left -= sample.size
            sample_chunks.append(sample)

    if valid_pixel_count == 0:
        payload = {
            "status": "no_valid_depth_pixels",
            "capture_root": str(capture_root),
            "bins": bins,
            "min_depth_m": min_depth_m,
            "max_depth_m": max_depth_m,
            "depth_files": [str(path.relative_to(capture_root)) for path in depth_files],
        }
        output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    sample_values = np.concatenate(sample_chunks) if sample_chunks else np.array([], dtype=np.float32)
    summary = {
        "mean_depth_m": total_sum / valid_pixel_count,
        "median_depth_m": float(np.median(sample_values)) if sample_values.size else None,
        "p05_depth_m": float(np.quantile(sample_values, 0.05)) if sample_values.size else None,
        "p95_depth_m": float(np.quantile(sample_values, 0.95)) if sample_values.size else None,
        "min_depth_m_observed": min_seen,
        "max_depth_m_observed": max_seen,
    }
    payload = {
        "status": "ok",
        "capture_root": str(capture_root),
        "depth_files": [str(path.relative_to(capture_root)) for path in depth_files],
        "depth_file_count": len(depth_files),
        "bins": bins,
        "histogram_min_depth_m": min_depth_m,
        "histogram_max_depth_m": max_depth_m,
        "valid_pixel_count": valid_pixel_count,
        "below_range_count": below_range_count,
        "above_range_count": above_range_count,
        "summary": summary,
        "bin_edges_m": [float(edge) for edge in edges],
        "counts": counts.astype(int).tolist(),
    }
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    centers = 0.5 * (edges[:-1] + edges[1:])
    widths = np.diff(edges)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(centers, counts, width=widths, align="center", color="#2f6f5e", edgecolor="#1e463b", linewidth=0.4)
    ax.set_title("Scene Depth Distribution")
    ax.set_xlabel("Depth (m)")
    ax.set_ylabel("Pixel Count")
    ax.set_xlim(min_depth_m, max_depth_m)
    fig.tight_layout()
    fig.savefig(output_png, dpi=160)
    plt.close(fig)
    return payload


def main():
    parser = argparse.ArgumentParser(description="Build a scene-level depth histogram from capture outputs.")
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-png", type=Path, required=True)
    parser.add_argument("--bins", type=int, default=80)
    parser.add_argument("--min-depth-m", type=float, default=0.0)
    parser.add_argument("--max-depth-m", type=float, default=10.0)
    parser.add_argument("--quantile-sample-limit", type=int, default=200000)
    args = parser.parse_args()

    build_depth_histogram(
        capture_root=args.capture_root,
        output_json=args.output_json,
        output_png=args.output_png,
        bins=args.bins,
        min_depth_m=args.min_depth_m,
        max_depth_m=args.max_depth_m,
        quantile_sample_limit=args.quantile_sample_limit,
    )


if __name__ == "__main__":
    main()
