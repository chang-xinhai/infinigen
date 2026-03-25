from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class FrameComparison:
    frame: int
    image_index: int
    reference_path: str
    rendered_path: str
    mae: float
    mse: float
    psnr: float
    max_abs_diff: int
    exact_match: bool


def _load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def compare_rgb_pair(
    *,
    frame: int,
    image_index: int,
    reference_path: Path,
    rendered_path: Path,
) -> FrameComparison:
    reference = _load_rgb(reference_path)
    rendered = _load_rgb(rendered_path)
    if reference.shape != rendered.shape:
        raise ValueError(
            f"Image size mismatch for frame {frame}: {reference.shape} vs {rendered.shape}"
        )

    diff = rendered.astype(np.int16) - reference.astype(np.int16)
    abs_diff = np.abs(diff)
    mse = float(np.mean(np.square(diff, dtype=np.float64)))
    psnr = math.inf if mse == 0.0 else float(20.0 * math.log10(255.0) - 10.0 * math.log10(mse))
    return FrameComparison(
        frame=int(frame),
        image_index=int(image_index),
        reference_path=str(Path(reference_path)),
        rendered_path=str(Path(rendered_path)),
        mae=float(np.mean(abs_diff)),
        mse=mse,
        psnr=psnr,
        max_abs_diff=int(abs_diff.max()),
        exact_match=bool(np.array_equal(reference, rendered)),
    )


def summarize_frame_comparisons(frame_reports: list[FrameComparison]) -> dict:
    if not frame_reports:
        raise ValueError("Cannot summarize an empty comparison report")

    finite_psnr = [report.psnr for report in frame_reports if math.isfinite(report.psnr)]
    return {
        "frame_count": len(frame_reports),
        "exact_match_count": sum(1 for report in frame_reports if report.exact_match),
        "mean_mae": float(np.mean([report.mae for report in frame_reports])),
        "mean_mse": float(np.mean([report.mse for report in frame_reports])),
        "mean_psnr": float(np.mean(finite_psnr)) if finite_psnr else math.inf,
        "max_abs_diff": int(max(report.max_abs_diff for report in frame_reports)),
    }


def write_comparison_reports(output_dir: Path, frame_reports: list[FrameComparison]) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = summarize_frame_comparisons(frame_reports)
    summary_path = output_dir / "summary.json"
    frames_path = output_dir / "frames.jsonl"
    tsv_path = output_dir / "frames.tsv"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with frames_path.open("w", encoding="utf-8") as handle:
        for report in frame_reports:
            handle.write(json.dumps(asdict(report)) + "\n")

    with tsv_path.open("w", encoding="utf-8") as handle:
        handle.write("frame\timage_index\tmae\tmse\tpsnr\tmax_abs_diff\texact_match\n")
        for report in frame_reports:
            psnr = "inf" if math.isinf(report.psnr) else f"{report.psnr:.6f}"
            handle.write(
                f"{report.frame}\t{report.image_index}\t{report.mae:.6f}\t{report.mse:.6f}\t{psnr}\t{report.max_abs_diff}\t{int(report.exact_match)}\n"
            )

    return summary
