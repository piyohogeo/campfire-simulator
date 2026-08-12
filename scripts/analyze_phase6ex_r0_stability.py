"""Aggregate the frozen Phase 6EX extended stability-window qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .analyze_phase6ew_r0_lifecycle import (
        _case as _phase6ew_case,
        _json,
        _jsonl,
        _range_fraction,
        _time,
    )
except ImportError:
    from analyze_phase6ew_r0_lifecycle import (
        _case as _phase6ew_case,
        _json,
        _jsonl,
        _range_fraction,
        _time,
    )


def _slope(points: list[tuple[float, int]]) -> float | None:
    if len(points) < 2:
        return None
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    denominator = sum((point[0] - mean_x) ** 2 for point in points)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


def _kit_private_rows(trace: list[dict], start: float, end: float) -> list[tuple[float, int]]:
    result = []
    for row in trace:
        timestamp = float(row.get("timestamp_utc_epoch", 0.0))
        if not start <= timestamp <= end:
            continue
        process = next((item for item in row.get("processes", []) if item.get("role") == "kit"), None)
        if process is not None:
            result.append((timestamp, int(process["private_bytes"])))
    return result


def _case(root: Path, relative: str, prefix: str, contract: dict) -> dict:
    result = _phase6ew_case(root, relative, prefix, contract)
    case_dir = root / relative
    raw = _json(case_dir / "raw.json") or {}
    markers = _jsonl(case_dir / "resource_markers.jsonl")
    trace = _jsonl(root / "runner-logs" / f"{prefix}.resource.jsonl")
    marker = {row["marker"]: row for row in markers}
    start_row = marker.get("stability_observation_started")
    end_row = marker.get("stability_observation_ended")
    stability_rows: list[tuple[float, int]] = []
    start_epoch = end_epoch = None
    if start_row and end_row:
        start_epoch = _time(start_row["timestamp_utc"])
        end_epoch = _time(end_row["timestamp_utc"])
        stability_rows = _kit_private_rows(trace, start_epoch, end_epoch)

    private_values = [value for _, value in stability_rows]
    increases = sum(right > left for left, right in zip(private_values, private_values[1:]))
    decreases = sum(right < left for left, right in zip(private_values, private_values[1:]))
    unchanged = sum(right == left for left, right in zip(private_values, private_values[1:]))
    non_monotonic_or_flat = decreases > 0 or unchanged > 0
    slope = _slope(stability_rows)

    frame_blocks = {
        int(item["frame"]): int(item["active_blocks"])
        for item in raw.get("samples", []) if "frame" in item and "active_blocks" in item
    }
    stability = raw.get("stability_observation") or {}
    active_samples = [int(item["active_blocks"]) for item in stability.get("samples", [])]
    active_samples = [
        frame_blocks[frame] for frame in contract["plateau_contract"]["stability_frames"]
        if frame in frame_blocks
    ] + active_samples
    active_range = _range_fraction([float(value) for value in active_samples])
    thresholds = contract["plateau_contract"]
    minimum_samples = thresholds["minimum_resource_samples_in_stability_interval"]
    target_samples = thresholds["target_resource_samples_in_stability_interval"]
    plateau = bool(
        len(active_samples) >= len(thresholds["stability_frames"])
        and all(value > 0 for value in active_samples)
        and active_range is not None
        and active_range <= thresholds["maximum_active_block_range_fraction"]
        and len(stability_rows) >= minimum_samples
        and slope is not None
        and slope <= thresholds["maximum_private_growth_bytes_per_second"]
        and non_monotonic_or_flat
    )
    terminal_private = private_values[-1] if private_values else None
    result.update({
        "stability_window_start_utc_epoch": start_epoch,
        "stability_window_end_utc_epoch": end_epoch,
        "stability_window_seconds": None if start_epoch is None or end_epoch is None else end_epoch - start_epoch,
        "stability_resource_sample_count": len(stability_rows),
        "stability_resource_target_count": target_samples,
        "stability_resource_minimum_count": minimum_samples,
        "stability_resource_target_met": len(stability_rows) >= target_samples,
        "stability_private_slope_bytes_per_second": slope,
        "stability_private_increase_count": increases,
        "stability_private_decrease_count": decreases,
        "stability_private_unchanged_count": unchanged,
        "stability_private_non_monotonic_or_flat": non_monotonic_or_flat,
        "stability_active_block_sample_count": len(active_samples),
        "stability_active_block_minimum": min(active_samples) if active_samples else None,
        "stability_active_block_maximum": max(active_samples) if active_samples else None,
        "stability_active_block_range_fraction": active_range,
        "stability_extra_update_count": stability.get("extra_update_count"),
        "stability_timeline_playing_at_end": stability.get("timeline_playing_at_end"),
        "terminal_kit_private_bytes": terminal_private,
        "plateau": plateau,
    })
    return result


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
    r0_complete = all(item is not None for item in r0)
    peaks = [float(item["kit_peak_private_bytes"]) for item in r0 if item and item["kit_peak_private_bytes"] is not None]
    terminals = [float(item["terminal_kit_private_bytes"]) for item in r0 if item and item["terminal_kit_private_bytes"] is not None]
    close_times = [float(item["stage_close_seconds"]) for item in r0 if item and item["stage_close_seconds"] is not None]
    terminal_blocks = [float(item["active_blocks"][320]) for item in r0 if item and 320 in item["active_blocks"]]
    thresholds = contract["plateau_contract"]
    reproducibility = {
        "peak_private_range_fraction": _range_fraction(peaks),
        "terminal_private_range_fraction": _range_fraction(terminals),
        "terminal_active_block_range_fraction": _range_fraction(terminal_blocks),
        "stage_close_range_seconds": None if not close_times else max(close_times) - min(close_times),
        "maximum_stage_close_seconds": max(close_times) if close_times else None,
    }
    reproducibility["gate_pass"] = bool(
        len(peaks) == len(terminals) == len(terminal_blocks) == len(close_times) == 3
        and reproducibility["peak_private_range_fraction"] <= thresholds["maximum_cross_run_peak_private_range_fraction"]
        and reproducibility["terminal_private_range_fraction"] <= thresholds["maximum_cross_run_terminal_private_range_fraction"]
        and reproducibility["terminal_active_block_range_fraction"] <= thresholds["maximum_cross_run_active_block_range_fraction"]
        and reproducibility["stage_close_range_seconds"] <= thresholds["maximum_cross_run_stage_close_range_seconds"]
        and reproducibility["maximum_stage_close_seconds"] <= thresholds["maximum_stage_close_seconds"]
    )
    r0_gate = bool(
        r0_complete and reproducibility["gate_pass"]
        and all(
            item["normal_exit"] and item["probe_markers_complete"] and item["extension_markers_complete"]
            and item["runner_markers_complete"] and item["synchronous_memory_valid"] and item["plateau"]
            and item["stability_timeline_playing_at_end"] is True and not item["stage_close_timeout_marker"]
            for item in r0
        )
    )
    r1 = cases.get("R1_acquire_discard")
    r1_memory = {} if r1 is None else r1["acquire_private_bytes"]
    r1_gate = bool(
        r1 and r1["normal_exit"] and r1["probe_markers_complete"] and r1["extension_markers_complete"]
        and r1["runner_markers_complete"] and r1["synchronous_memory_valid"] and r1["plateau"]
        and r1["stability_timeline_playing_at_end"] is True and not r1["stage_close_timeout_marker"]
        and all(r1_memory.get(name) is not None for name in ("before", "after", "references_released", "next_frame"))
    )
    fixture = _json(args.root / "sampler-fixture" / "sampler_fixture_report.json")
    report = {
        "schema": "campfire.phase6ex.r0-stability-qualification-report.v1",
        "phase": "phase6ex",
        "sampler_fixture": fixture,
        "cases": cases,
        "r0_completed_runs": sum(item is not None for item in r0),
        "r0_normal_exit_runs": sum(bool(item and item["normal_exit"]) for item in r0),
        "r0_plateau_runs": sum(bool(item and item["plateau"]) for item in r0),
        "r0_target_sample_runs": sum(bool(item and item["stability_resource_target_met"]) for item in r0),
        "r0_cross_run_reproducibility": reproducibility,
        "r0_gate_pass": r0_gate,
        "r1_started": r1 is not None,
        "r1_gate_pass": r1_gate,
        "r1_vs_r0": {
            "r0_peak_private_bytes": peaks,
            "r0_terminal_private_bytes": terminals,
            "r0_stage_close_seconds": close_times,
            "r1_peak_private_bytes": None if r1 is None else r1["kit_peak_private_bytes"],
            "r1_terminal_private_bytes": None if r1 is None else r1["terminal_kit_private_bytes"],
            "r1_stage_close_seconds": None if r1 is None else r1["stage_close_seconds"],
            "r1_acquire_private_bytes": None if r1 is None else r1["acquire_private_bytes"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
