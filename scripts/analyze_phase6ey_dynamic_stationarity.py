"""Aggregate the frozen Phase 6EY dynamic-stationarity qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .analyze_phase6ew_r0_lifecycle import _case as _phase6ew_case, _json, _jsonl, _range_fraction, _time
    from .calibrate_phase6ey_dynamic_stationarity import aligned_rows
    from .phase6ey_dynamic_stationarity import evaluate
except ImportError:
    from analyze_phase6ew_r0_lifecycle import _case as _phase6ew_case, _json, _jsonl, _range_fraction, _time
    from calibrate_phase6ey_dynamic_stationarity import aligned_rows
    from phase6ey_dynamic_stationarity import evaluate


def _window_bounds(markers: list[dict]) -> tuple[float | None, float | None]:
    by_name = {row.get("marker"): row for row in markers}
    start = by_name.get("stability_observation_started")
    end = by_name.get("stability_observation_ended")
    return (
        _time(start["timestamp_utc"]) if start else None,
        _time(end["timestamp_utc"]) if end else None,
    )


def _outer_resource_count(trace: list[dict], start: float | None, end: float | None) -> int:
    if start is None or end is None:
        return 0
    return sum(
        start <= float(row.get("timestamp_utc_epoch", 0.0)) <= end
        and any(item.get("role") == "kit" for item in row.get("processes", []))
        for row in trace
    )


def _case(root: Path, relative: str, prefix: str, contract: dict) -> dict:
    # The shared lifecycle parser still derives obsolete Phase 6EV plateau
    # fields. Supply a permissive in-memory compatibility view only; Phase
    # 6EY qualification below exclusively uses its frozen stationarity gate.
    compatibility_contract = dict(contract)
    compatibility_contract["plateau_contract"] = {
        "stability_frames": [240, 280, 320],
        "maximum_active_block_range_fraction": 1.0e9,
        "minimum_resource_samples_in_stability_interval": 0,
        "maximum_private_growth_bytes_per_second": 1.0e30,
    }
    result = _phase6ew_case(root, relative, prefix, compatibility_contract)
    case_dir = root / relative
    log_dir = root / "runner-logs"
    marker_path = case_dir / "resource_markers.jsonl"
    trace_path = log_dir / f"{prefix}.resource.jsonl"
    gpu_path = log_dir / f"{prefix}.gpu.csv"
    markers = _jsonl(marker_path)
    trace = _jsonl(trace_path)
    raw = _json(case_dir / "raw.json") or {}
    stability = raw.get("stability_observation") or {}
    start, end = _window_bounds(markers)
    rows = aligned_rows(marker_path, trace_path, gpu_path)
    # The frozen 24-second contract concerns the fixed post-frame-320
    # observation. Earlier frame 240/280/320 anchors are retained in raw
    # artifacts but are not distributed across the four equal-time windows.
    rows = [
        row for row in rows
        if row.get("marker") == "stability_observation_sample"
        and start is not None and end is not None and start <= row["epoch"] <= end
    ]
    if rows:
        origin = rows[0]["epoch"]
        for index, row in enumerate(rows):
            row["wall_seconds"] = row["epoch"] - origin
            previous = rows[index - 1] if index else None
            row["active_block_delta"] = None if previous is None else row["active_blocks"] - previous["active_blocks"]
            row["kit_private_delta_bytes"] = None if previous is None else row["kit_private_bytes"] - previous["kit_private_bytes"]
    evaluation = evaluate(rows, contract["dynamic_stationarity_thresholds"])
    outer_count = _outer_resource_count(trace, start, end)
    observation = contract["observation"]
    result.update({
        "dynamic_window_start_utc_epoch": start,
        "dynamic_window_end_utc_epoch": end,
        "dynamic_window_seconds": None if start is None or end is None else end - start,
        "aligned_time_series": rows,
        "aligned_active_resource_sample_count": len(rows),
        "aligned_active_resource_target_count": observation["target_aligned_active_resource_samples"],
        "outer_resource_sample_count": outer_count,
        "outer_resource_target_count": observation["target_outer_resource_samples"],
        "stability_timeline_playing_at_end": stability.get("timeline_playing_at_end"),
        "dynamic_stationarity": evaluation,
        "dynamic_stationarity_pass": bool(
            evaluation["gate_pass"]
            and outer_count >= int(observation["minimum_outer_resource_samples"])
            and (stability.get("timeline_playing_at_end") is True)
        ),
    })
    return result


def _range(values: list[float]) -> float | None:
    return _range_fraction(values) if values else None


def _reproducibility(runs: list[dict], contract: dict) -> dict:
    metrics = [item["dynamic_stationarity"]["metrics"] for item in runs]
    active_mean = [item["active_blocks"]["mean"] for item in metrics]
    active_median = [item["active_blocks"]["median"] for item in metrics]
    active_p95 = [item["active_blocks"]["p95"] for item in metrics]
    active_max = [item["active_blocks"]["maximum"] for item in metrics]
    private_per_block = [item["private_bytes_per_active_block"]["mean"] for item in metrics]
    private_slopes = [item["private_slope_bytes_per_second"] for item in metrics]
    peaks = [float(item["kit_peak_private_bytes"]) for item in runs]
    terminals = [float(item["aligned_time_series"][-1]["kit_private_bytes"]) for item in runs]
    close_times = [float(item["stage_close_seconds"]) for item in runs]
    result = {
        "active_mean_range_fraction": _range(active_mean),
        "active_median_range_fraction": _range(active_median),
        "active_p95_range_fraction": _range(active_p95),
        "active_maximum_range_fraction": _range(active_max),
        "peak_private_range_fraction": _range(peaks),
        "terminal_private_range_fraction": _range(terminals),
        "private_per_block_mean_range_fraction": _range(private_per_block),
        "private_slope_range_bytes_per_second": max(private_slopes) - min(private_slopes),
        "stage_close_range_seconds": max(close_times) - min(close_times),
        "maximum_stage_close_seconds": max(close_times),
    }
    threshold = contract["reproducibility_thresholds"]
    result["gate_pass"] = bool(
        result["active_mean_range_fraction"] <= threshold["maximum_cross_run_active_mean_range_fraction"]
        and result["active_median_range_fraction"] <= threshold["maximum_cross_run_active_median_range_fraction"]
        and result["active_p95_range_fraction"] <= threshold["maximum_cross_run_active_p95_range_fraction"]
        and result["active_maximum_range_fraction"] <= threshold["maximum_cross_run_active_maximum_range_fraction"]
        and result["peak_private_range_fraction"] <= threshold["maximum_cross_run_peak_private_range_fraction"]
        and result["terminal_private_range_fraction"] <= threshold["maximum_cross_run_terminal_private_range_fraction"]
        and result["private_per_block_mean_range_fraction"] <= threshold["maximum_cross_run_private_per_block_mean_range_fraction"]
        and result["private_slope_range_bytes_per_second"] <= threshold["maximum_cross_run_private_slope_range_bytes_per_second"]
        and result["stage_close_range_seconds"] <= threshold["maximum_cross_run_stage_close_range_seconds"]
        and result["maximum_stage_close_seconds"] <= threshold["maximum_stage_close_seconds"]
    )
    return result


def _lifecycle_pass(item: dict) -> bool:
    return bool(
        item["normal_exit"] and item["probe_markers_complete"] and item["extension_markers_complete"]
        and item["runner_markers_complete"] and item["synchronous_memory_valid"]
        and not item["stage_close_timeout_marker"]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    entries = [
        (f"R0_run{run:02d}", f"calibration/run{run:02d}/R0_none", f"run{run:02d}_R0_none")
        for run in range(1, 4)
    ]
    entries.append(("R1_acquire_discard", "R1_acquire_discard", "R1_acquire_discard"))
    for key, relative, prefix in entries:
        if (args.root / relative).exists():
            cases[key] = _case(args.root, relative, prefix, contract)

    r0 = [cases.get(f"R0_run{run:02d}") for run in range(1, 4)]
    completed = [item for item in r0 if item is not None]
    reproducibility = _reproducibility(completed, contract) if len(completed) == 3 else {"gate_pass": False}
    r0_gate = bool(
        len(completed) == 3 and reproducibility["gate_pass"]
        and all(_lifecycle_pass(item) and item["dynamic_stationarity_pass"] for item in completed)
    )
    r1 = cases.get("R1_acquire_discard")
    acquire = {} if r1 is None else r1["acquire_private_bytes"]
    r1_gate = bool(
        r1 and _lifecycle_pass(r1) and r1["dynamic_stationarity_pass"]
        and all(acquire.get(name) is not None for name in ("before", "after", "references_released", "next_frame"))
    )
    r1_delta = None
    if r1 and acquire.get("before") is not None and acquire.get("after") is not None:
        r1_delta = acquire["after"] - acquire["before"]
    report = {
        "schema": "campfire.phase6ey.dynamic-stationarity-qualification-report.v1",
        "phase": "phase6ey",
        "synthetic_fixture": _json(args.root / "synthetic-fixture" / "synthetic_fixture_report.json"),
        "cases": cases,
        "r0_completed_runs": len(completed),
        "r0_normal_exit_runs": sum(bool(item and item["normal_exit"]) for item in r0),
        "r0_dynamic_stationarity_runs": sum(bool(item and item["dynamic_stationarity_pass"]) for item in r0),
        "r0_cross_run_reproducibility": reproducibility,
        "r0_gate_pass": r0_gate,
        "r1_started": r1 is not None,
        "r1_gate_pass": r1_gate,
        "r1_vs_r0": {
            "r0_active_block_means": [item["dynamic_stationarity"]["metrics"]["active_blocks"]["mean"] for item in completed],
            "r0_private_bytes_per_active_block_means": [item["dynamic_stationarity"]["metrics"]["private_bytes_per_active_block"]["mean"] for item in completed],
            "r0_peak_private_bytes": [item["kit_peak_private_bytes"] for item in completed],
            "r0_stage_close_seconds": [item["stage_close_seconds"] for item in completed],
            "r1_peak_private_bytes": None if r1 is None else r1["kit_peak_private_bytes"],
            "r1_stage_close_seconds": None if r1 is None else r1["stage_close_seconds"],
            "r1_acquire_private_bytes": None if r1 is None else acquire,
            "r1_acquire_immediate_delta_bytes": r1_delta,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
