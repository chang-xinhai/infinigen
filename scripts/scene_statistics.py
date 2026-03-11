import argparse
import csv
import json
import math
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt


def _read_csv_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", newline="") as handle:
        return list(csv.DictReader(handle))


def _safe_float(value, default=0.0):
    try:
        if value in (None, "", "nan"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _detect_scene_root(path: Path):
    candidate = path.resolve()
    if (candidate / "statistics").exists() or any(candidate.glob("pipeline_*.csv")):
        return candidate
    for child_name in ["coarse", "fine"]:
        child = candidate / child_name
        if child.exists() and any(child.glob("pipeline_*.csv")):
            return candidate
    return candidate


def _find_pipeline_files(scene_root: Path):
    files = []
    for subdir in [scene_root, scene_root / "coarse", scene_root / "fine"]:
        if subdir.exists():
            files.extend(sorted(subdir.glob("pipeline_*.csv")))
    return files


def _load_resource_rows(stat_dir: Path):
    resource_csv = stat_dir / "resource_usage.csv"
    return _read_csv_rows(resource_csv)


def _stage_records(scene_root: Path):
    records = []
    for pipeline_csv in _find_pipeline_files(scene_root):
        stage_group = pipeline_csv.stem
        for row in _read_csv_rows(pipeline_csv):
            records.append(
                {
                    "pipeline": stage_group,
                    "stage": row.get("name", "unknown"),
                    "ran": str(row.get("ran", "")).lower() == "true",
                    "duration_sec": _safe_float(row.get("duration_sec")),
                    "mem_at_finish": _safe_float(row.get("mem_at_finish")),
                    "obj_count": _safe_float(row.get("obj_count")),
                    "instance_count": _safe_float(row.get("instance_count")),
                    "started_at": row.get("started_at"),
                    "finished_at": row.get("finished_at"),
                }
            )
    return records


def _build_summary(scene_root: Path):
    scene_root = _detect_scene_root(scene_root)
    stat_dir = scene_root / "statistics"
    stat_dir.mkdir(parents=True, exist_ok=True)

    metadata = _read_json(stat_dir / "run_metadata.json") or {}
    stage_records = _stage_records(scene_root)
    resource_rows = _load_resource_rows(stat_dir)

    ran_records = [record for record in stage_records if record["ran"]]
    total_stage_time = sum(record["duration_sec"] for record in ran_records)

    stage_totals = {}
    for record in ran_records:
        stage_totals.setdefault(record["stage"], 0.0)
        stage_totals[record["stage"]] += record["duration_sec"]

    avg_cpu = None
    peak_cpu = None
    avg_rss_gb = None
    peak_rss_gb = None
    avg_gpu = None
    peak_gpu = None
    peak_gpu_mem_gb = None

    if resource_rows:
        cpu_values = [_safe_float(row.get("cpu_percent")) for row in resource_rows]
        rss_values = [_safe_float(row.get("rss_gb")) for row in resource_rows]
        gpu_values = [
            _safe_float(row.get("gpu_util_percent"), default=math.nan)
            for row in resource_rows
            if row.get("gpu_util_percent", "") not in ("", "nan")
        ]
        gpu_mem_values = [
            _safe_float(row.get("gpu_mem_used_gb"), default=math.nan)
            for row in resource_rows
            if row.get("gpu_mem_used_gb", "") not in ("", "nan")
        ]
        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else None
        peak_cpu = max(cpu_values) if cpu_values else None
        avg_rss_gb = sum(rss_values) / len(rss_values) if rss_values else None
        peak_rss_gb = max(rss_values) if rss_values else None
        avg_gpu = sum(gpu_values) / len(gpu_values) if gpu_values else None
        peak_gpu = max(gpu_values) if gpu_values else None
        peak_gpu_mem_gb = max(gpu_mem_values) if gpu_mem_values else None

    summary = {
        "scene_root": str(scene_root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata,
        "total_stage_time_sec": total_stage_time,
        "stage_count": len(ran_records),
        "stage_totals_sec": dict(sorted(stage_totals.items(), key=lambda item: item[1], reverse=True)),
        "resource_summary": {
            "avg_cpu_percent": avg_cpu,
            "peak_cpu_percent": peak_cpu,
            "avg_rss_gb": avg_rss_gb,
            "peak_rss_gb": peak_rss_gb,
            "avg_gpu_util_percent": avg_gpu,
            "peak_gpu_util_percent": peak_gpu,
            "peak_gpu_mem_used_gb": peak_gpu_mem_gb,
        },
        "pipeline_files": [str(path) for path in _find_pipeline_files(scene_root)],
    }

    (stat_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    _write_summary_text(stat_dir, summary, ran_records)
    _write_stage_charts(stat_dir, summary)
    _write_resource_chart(stat_dir, resource_rows)
    return summary


def _write_summary_text(stat_dir: Path, summary: dict, ran_records: list[dict]):
    lines = []
    lines.append(f"scene_root: {summary['scene_root']}")
    lines.append(f"generated_at: {summary['generated_at']}")
    if summary.get("metadata"):
        metadata = summary["metadata"]
        command = metadata.get("command")
        if command:
            lines.append(f"command: {command}")
        for key in ["label", "cwd", "conda_env", "exit_code", "start_time", "end_time"]:
            if metadata.get(key) is not None:
                lines.append(f"{key}: {metadata[key]}")
    lines.append(f"total_stage_time_sec: {summary['total_stage_time_sec']:.3f}")
    resource = summary["resource_summary"]
    for key, value in resource.items():
        if value is not None:
            lines.append(f"{key}: {value:.3f}")
    lines.append("")
    lines.append("stage_totals_sec:")
    for stage, duration in summary["stage_totals_sec"].items():
        lines.append(f"  {stage}: {duration:.3f}")
    lines.append("")
    lines.append("stage_records:")
    for record in ran_records:
        lines.append(
            "  {pipeline}::{stage} duration_sec={duration_sec:.3f} mem_at_finish={mem_at_finish:.0f} obj_count={obj_count:.0f} instance_count={instance_count:.0f}".format(
                **record
            )
        )
    (stat_dir / "summary.txt").write_text("\n".join(lines) + "\n")


def _write_stage_charts(stat_dir: Path, summary: dict):
    stage_totals = summary["stage_totals_sec"]
    if not stage_totals:
        return

    stages = list(stage_totals.keys())
    durations = [stage_totals[stage] for stage in stages]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(range(len(stages)), durations, color="#1f77b4")
    ax.set_xticks(range(len(stages)))
    ax.set_xticklabels(stages, rotation=60, ha="right")
    ax.set_ylabel("seconds")
    ax.set_title("Stage Duration Breakdown")
    fig.tight_layout()
    fig.savefig(stat_dir / "stage_durations.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(durations, labels=stages, autopct="%1.1f%%", startangle=90)
    ax.set_title("Stage Time Proportion")
    fig.tight_layout()
    fig.savefig(stat_dir / "stage_proportions.png", dpi=160)
    plt.close(fig)


def _write_resource_chart(stat_dir: Path, resource_rows: list[dict]):
    if not resource_rows:
        return

    time_axis = [_safe_float(row.get("elapsed_sec")) for row in resource_rows]
    cpu_values = [_safe_float(row.get("cpu_percent")) for row in resource_rows]
    rss_values = [_safe_float(row.get("rss_gb")) for row in resource_rows]
    gpu_values = [
        _safe_float(row.get("gpu_util_percent"), default=math.nan)
        if row.get("gpu_util_percent", "") not in ("", "nan")
        else math.nan
        for row in resource_rows
    ]
    gpu_mem_values = [
        _safe_float(row.get("gpu_mem_used_gb"), default=math.nan)
        if row.get("gpu_mem_used_gb", "") not in ("", "nan")
        else math.nan
        for row in resource_rows
    ]

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    axes[0].plot(time_axis, cpu_values, color="#d62728")
    axes[0].set_ylabel("CPU %")
    axes[0].set_title("Resource Usage Over Time")

    axes[1].plot(time_axis, rss_values, color="#2ca02c")
    axes[1].set_ylabel("RSS GB")

    axes[2].plot(time_axis, gpu_values, color="#1f77b4", label="GPU %")
    axes[2].plot(time_axis, gpu_mem_values, color="#9467bd", label="GPU Mem GB")
    axes[2].set_ylabel("GPU")
    axes[2].set_xlabel("elapsed seconds")
    axes[2].legend()

    fig.tight_layout()
    fig.savefig(stat_dir / "resource_usage.png", dpi=160)
    plt.close(fig)


def _write_resource_csv(stat_dir: Path, rows: list[dict]):
    fieldnames = [
        "timestamp",
        "elapsed_sec",
        "cpu_percent",
        "rss_gb",
        "vms_gb",
        "child_count",
        "gpu_name",
        "gpu_util_percent",
        "gpu_mem_used_gb",
    ]
    with (stat_dir / "resource_usage.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _aggregate_process_tree(proc):
    try:
        processes = [proc] + proc.children(recursive=True)
    except Exception:
        processes = [proc]

    rss = 0
    vms = 0
    cpu = 0
    alive = []
    for child in processes:
        try:
            mem_info = child.memory_info()
            rss += mem_info.rss
            vms += mem_info.vms
            cpu += child.cpu_percent(interval=None)
            alive.append(child)
        except Exception:
            continue
    return rss, vms, cpu, len(alive)


def _query_gpu():
    if shutil.which("nvidia-smi") is None:
        return None, None, None
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(cmd, text=True).strip().splitlines()
    except Exception:
        return None, None, None
    if not output:
        return None, None, None
    first = output[0]
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 3:
        return None, None, None
    gpu_name = parts[0]
    gpu_util = _safe_float(parts[1], default=math.nan)
    gpu_mem = _safe_float(parts[2], default=math.nan) / 1024.0
    return gpu_name, gpu_util, gpu_mem


def run_wrapped_command(scene_root: Path, label: str, command: list[str], sample_interval: float):
    scene_root = scene_root.resolve()
    stat_dir = scene_root / "statistics"
    stat_dir.mkdir(parents=True, exist_ok=True)

    shell_command = " ".join(shlex.quote(part) for part in command)
    metadata = {
        "label": label,
        "scene_root": str(scene_root),
        "cwd": str(Path.cwd()),
        "command": shell_command,
        "argv": command,
        "conda_env": Path(sys.prefix).name,
        "python_executable": sys.executable,
        "start_time": datetime.now().isoformat(timespec="seconds"),
        "sample_interval_sec": sample_interval,
    }
    (stat_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))

    process = subprocess.Popen(command, cwd=Path.cwd())
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("psutil is required for wrapped stats collection") from exc
    proc = psutil.Process(process.pid)
    proc.cpu_percent(interval=None)

    rows = []
    stop_event = threading.Event()
    start_time = time.time()

    def sample_loop():
        while not stop_event.is_set():
            rss, vms, cpu_percent, child_count = _aggregate_process_tree(proc)
            gpu_name, gpu_util, gpu_mem = _query_gpu()
            rows.append(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "elapsed_sec": round(time.time() - start_time, 3),
                    "cpu_percent": round(cpu_percent, 3),
                    "rss_gb": round(rss / (1024 ** 3), 3),
                    "vms_gb": round(vms / (1024 ** 3), 3),
                    "child_count": child_count,
                    "gpu_name": gpu_name,
                    "gpu_util_percent": None if gpu_util is None or math.isnan(gpu_util) else round(gpu_util, 3),
                    "gpu_mem_used_gb": None if gpu_mem is None or math.isnan(gpu_mem) else round(gpu_mem, 3),
                }
            )
            if process.poll() is not None:
                break
            time.sleep(sample_interval)

    thread = threading.Thread(target=sample_loop, daemon=True)
    thread.start()
    exit_code = process.wait()
    stop_event.set()
    thread.join(timeout=sample_interval + 1.0)

    metadata["end_time"] = datetime.now().isoformat(timespec="seconds")
    metadata["exit_code"] = exit_code
    metadata["duration_sec"] = round(time.time() - start_time, 3)
    (stat_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))
    _write_resource_csv(stat_dir, rows)
    _build_summary(scene_root)
    return exit_code


def aggregate_many(scene_roots: list[Path], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for scene_root in scene_roots:
        summary = _build_summary(scene_root)
        summaries.append(summary)

    aggregate_csv = output_dir / "aggregate_summary.csv"
    with aggregate_csv.open("w", newline="") as handle:
        fieldnames = [
            "scene_root",
            "label",
            "exit_code",
            "total_stage_time_sec",
            "peak_cpu_percent",
            "peak_rss_gb",
            "peak_gpu_util_percent",
            "peak_gpu_mem_used_gb",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            metadata = summary.get("metadata", {})
            resource = summary.get("resource_summary", {})
            writer.writerow(
                {
                    "scene_root": summary["scene_root"],
                    "label": metadata.get("label"),
                    "exit_code": metadata.get("exit_code"),
                    "total_stage_time_sec": round(summary.get("total_stage_time_sec", 0.0), 3),
                    "peak_cpu_percent": resource.get("peak_cpu_percent"),
                    "peak_rss_gb": resource.get("peak_rss_gb"),
                    "peak_gpu_util_percent": resource.get("peak_gpu_util_percent"),
                    "peak_gpu_mem_used_gb": resource.get("peak_gpu_mem_used_gb"),
                }
            )

    if summaries:
        labels = [summary.get("metadata", {}).get("label") or Path(summary["scene_root"]).name for summary in summaries]
        totals = [summary.get("total_stage_time_sec", 0.0) for summary in summaries]
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.bar(range(len(labels)), totals, color="#ff7f0e")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_ylabel("seconds")
        ax.set_title("Total Stage Time by Scene")
        fig.tight_layout()
        fig.savefig(output_dir / "aggregate_total_stage_time.png", dpi=160)
        plt.close(fig)

    return summaries


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)

    wrap_parser = subparsers.add_parser("wrap")
    wrap_parser.add_argument("--scene-root", type=Path, required=True)
    wrap_parser.add_argument("--label", type=str, default="scene_run")
    wrap_parser.add_argument("--sample-interval", type=float, default=1.0)
    wrap_parser.add_argument("command", nargs=argparse.REMAINDER)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--scene-root", type=Path, required=True)

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--output-dir", type=Path, required=True)
    aggregate_parser.add_argument("scene_roots", nargs="+", type=Path)

    args = parser.parse_args()

    if args.mode == "wrap":
        command = list(args.command)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise SystemExit("wrap mode requires a command after --")
        raise SystemExit(run_wrapped_command(args.scene_root, args.label, command, args.sample_interval))

    if args.mode == "summarize":
        _build_summary(args.scene_root)
        return

    if args.mode == "aggregate":
        aggregate_many(args.scene_roots, args.output_dir)


if __name__ == "__main__":
    main()