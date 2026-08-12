"""Offline historical audit and synthetic calibration for Phase 6EY."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from .analyze_phase6ew_r0_lifecycle import _time
    from .phase6ey_dynamic_stationarity import MIB, correlation, evaluate, slope
except ImportError:
    from analyze_phase6ew_r0_lifecycle import _time
    from phase6ey_dynamic_stationarity import MIB, correlation, evaluate, slope


CALIBRATED_THRESHOLDS = {
    "window_count": 4,
    "minimum_aligned_samples": 40,
    "minimum_observation_seconds": 20.0,
    "minimum_samples_per_window": 8,
    "maximum_active_blocks": 1800,
    "maximum_active_projected_drift_fraction": 0.20,
    "maximum_private_slope_bytes_per_second": 8 * MIB,
    "maximum_private_projected_drift_fraction": 0.05,
    "maximum_private_per_block_projected_drift_fraction": 0.25,
    "active_half_ratio_range": [0.80, 1.25],
    "private_half_ratio_range": [0.95, 1.05],
    "maximum_window_active_ratio": 1.30,
    "active_final_window_ratio_range": [0.80, 1.25],
    "minimum_increase_transition_fraction": 0.15,
    "minimum_decrease_transition_fraction": 0.15,
    "maximum_final_half_new_high_fraction": 0.30,
    "maximum_consecutive_new_highs": 5,
    "maximum_active_drop_private_increase_fraction": 0.75,
    "private_high_water_recovery_bytes": 64 * MIB,
    "maximum_last_half_private_slope_bytes_per_second": 4 * MIB,
    "maximum_autocorrelation_lag_samples": 12,
    "maximum_memory_lag_samples": 4,
}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _nearest_trace(trace: list[dict], epoch: float) -> dict | None:
    return min(trace, key=lambda row: abs(float(row["timestamp_utc_epoch"]) - epoch)) if trace else None


def _gpu_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    tokyo = timezone(timedelta(hours=9))
    with path.open(encoding="utf-8", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 8 or row[1].strip() != "0":
                continue
            try:
                stamp = datetime.strptime(row[0].strip(), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=tokyo).timestamp()
                rows.append({"epoch": stamp, "dedicated_mib": float(row[4].strip())})
            except ValueError:
                continue
    return rows


def _nearest_gpu(rows: list[dict], epoch: float) -> float | None:
    return min(rows, key=lambda row: abs(row["epoch"] - epoch))["dedicated_mib"] if rows else None


def aligned_rows(marker_path: Path, trace_path: Path, gpu_path: Path) -> list[dict]:
    markers = _jsonl(marker_path)
    trace = _jsonl(trace_path)
    gpu = _gpu_rows(gpu_path)
    selected = [
        row for row in markers
        if row.get("marker") in ("sample_started", "stability_observation_sample") and "active_blocks" in row
    ]
    result = []
    seen = set()
    for marker in selected:
        epoch = _time(marker["timestamp_utc"])
        identity = (round(epoch, 6), int(marker["active_blocks"]))
        if identity in seen:
            continue
        seen.add(identity)
        resource = _nearest_trace(trace, epoch)
        if resource is None:
            continue
        kit = next((item for item in resource.get("processes", []) if item.get("role") == "kit"), None)
        if kit is None:
            continue
        timeline_time = marker.get("timeline_time")
        frame = marker.get("frame")
        result.append({
            "timestamp_utc": marker["timestamp_utc"],
            "epoch": epoch,
            "wall_seconds": 0.0,
            "timeline_frame": int(frame) if frame is not None else (
                int(round(float(timeline_time) * 60.0)) if timeline_time is not None else None
            ),
            "timeline_frame_source": "explicit" if frame is not None else "timeline_time_x_60",
            "active_blocks": int(marker["active_blocks"]),
            "kit_private_bytes": int(kit["private_bytes"]),
            "kit_working_set_bytes": int(kit["working_set_bytes"]),
            "tree_private_bytes": sum(int(item["private_bytes"]) for item in resource.get("processes", [])),
            "gpu_dedicated_memory_mib": _nearest_gpu(gpu, epoch),
        })
    if result:
        origin = result[0]["epoch"]
        for index, row in enumerate(result):
            row["wall_seconds"] = row["epoch"] - origin
            previous = result[index - 1] if index else None
            row["active_block_delta"] = None if previous is None else row["active_blocks"] - previous["active_blocks"]
            row["kit_private_delta_bytes"] = None if previous is None else row["kit_private_bytes"] - previous["kit_private_bytes"]
            row["private_bytes_per_active_block"] = row["kit_private_bytes"] / row["active_blocks"]
    return result


def _duration(markers: list[dict], start: str, end: str) -> float | None:
    by_name = {row.get("marker"): row for row in markers}
    if start not in by_name or end not in by_name:
        return None
    return _time(by_name[end]["timestamp_utc"]) - _time(by_name[start]["timestamp_utc"])


def _historical_case(repo: Path, spec: dict) -> dict:
    root = repo / "artifacts" / spec["root"]
    case = root / spec["relative"]
    logs = root / "runner-logs"
    rows = aligned_rows(case / "resource_markers.jsonl", logs / f"{spec['prefix']}.resource.jsonl", logs / f"{spec['prefix']}.gpu.csv")
    markers = _jsonl(case / "resource_markers.jsonl")
    raw = _json(case / "raw.json") or {}
    evidence = _json(case / "runner_evidence.json") or {}
    guard = _json(logs / f"{spec['prefix']}.guard.json") or {}
    active = [float(row["active_blocks"]) for row in rows]
    private = [float(row["kit_private_bytes"]) for row in rows]
    by_name = {row.get("marker"): row for row in markers}
    stability_start = by_name.get("stability_observation_started")
    stability_end = by_name.get("stability_observation_ended")
    stability_rows = []
    if stability_start and stability_end:
        start_epoch = _time(stability_start["timestamp_utc"])
        end_epoch = _time(stability_end["timestamp_utc"])
        stability_rows = [row for row in rows if start_epoch <= row["epoch"] <= end_epoch]
        if stability_rows:
            origin = stability_rows[0]["epoch"]
            for index, row in enumerate(stability_rows):
                row["stability_wall_seconds"] = row["epoch"] - origin
                previous = stability_rows[index - 1] if index else None
                row["stability_active_block_delta"] = None if previous is None else row["active_blocks"] - previous["active_blocks"]
                row["stability_private_delta_bytes"] = None if previous is None else row["kit_private_bytes"] - previous["kit_private_bytes"]
    stability_active = [float(row["active_blocks"]) for row in stability_rows]
    stability_private = [float(row["kit_private_bytes"]) for row in stability_rows]
    stability_active_deltas = [right - left for left, right in zip(stability_active, stability_active[1:])]
    result = {
        "phase": spec["phase"],
        "condition": spec["condition"],
        "source_root": spec["root"],
        "formal_population_reuse": False,
        "rows": rows,
        "stability_rows": stability_rows,
        "summary": {
            "sample_count": len(rows),
            "active_minimum": min(active) if active else None,
            "active_mean": sum(active) / len(active) if active else None,
            "active_maximum": max(active) if active else None,
            "active_slope_blocks_per_second": slope([row["wall_seconds"] for row in rows], active),
            "private_slope_bytes_per_second": slope([row["wall_seconds"] for row in rows], private),
            "active_private_correlation": correlation(active, private),
            "stage_close_seconds": _duration(markers, "stage_close_request_before", "stage_close_request_after"),
            "raw_status": raw.get("status"),
            "lifecycle_marker": raw.get("lifecycle_marker"),
            "lifecycle_status": (evidence.get("outcome") or {}).get("lifecycle_status"),
            "guard_status": guard.get("status"),
            "guard_stop_reason": guard.get("stop_reason"),
            "stability_sample_count": len(stability_rows),
            "stability_active_minimum": min(stability_active) if stability_active else None,
            "stability_active_mean": sum(stability_active) / len(stability_active) if stability_active else None,
            "stability_active_maximum": max(stability_active) if stability_active else None,
            "stability_active_slope_blocks_per_second": slope(
                [row["stability_wall_seconds"] for row in stability_rows], stability_active
            ),
            "stability_private_slope_bytes_per_second": slope(
                [row["stability_wall_seconds"] for row in stability_rows], stability_private
            ),
            "stability_active_private_correlation": correlation(stability_active, stability_private),
            "stability_active_increase_count": sum(value > 0 for value in stability_active_deltas),
            "stability_active_decrease_count": sum(value < 0 for value in stability_active_deltas),
        },
    }
    return result


def _synthetic_rows(kind: str, count: int = 80, dt: float = 0.5) -> list[dict]:
    rows = []
    for index in range(count):
        t = index * dt
        noise = 8.0 * math.sin(index * 1.73) + 4.0 * math.cos(index * 0.61)
        if kind == "constant_noise":
            active = 1300.0 + noise
            private = 13.0 * 1024**3 + active * 0.2 * MIB + 8 * MIB * math.sin(index * 0.4)
        elif kind == "periodic":
            active = 1300.0 + 170.0 * math.sin(2.0 * math.pi * index / 16.0) + noise
            private = 12.8 * 1024**3 + active * 0.25 * MIB + 12 * MIB * math.sin(index * 0.25)
        elif kind == "drop_recovery":
            drop = -260.0 * math.exp(-((index - 42.0) / 6.0) ** 2)
            active = 1320.0 + drop + noise
            private = 12.9 * 1024**3 + active * 0.2 * MIB + 10 * MIB * math.sin(index * 0.3)
        elif kind == "linear_growth":
            active = 1150.0 + 7.0 * index + noise
            private = 12.5 * 1024**3 + active * 0.3 * MIB
        elif kind == "accelerating_growth":
            active = 1150.0 + 0.12 * index * index + noise
            private = 12.5 * 1024**3 + active * 0.35 * MIB
        elif kind == "memory_only_growth":
            active = 1300.0 + noise
            private = 12.4 * 1024**3 + index * 7.0 * MIB
        elif kind == "bounded_correlated_growth":
            active = 1280.0 + 0.35 * index + noise
            private = 12.8 * 1024**3 + active * 0.8 * MIB + 5 * MIB * math.sin(index * 0.4)
        elif kind == "cache_after_drop":
            active = 1350.0 - (180.0 if 25 <= index < 50 else 0.0) + noise
            private = 12.8 * 1024**3 + index * 3.0 * MIB
        else:
            raise ValueError(kind)
        rows.append({
            "wall_seconds": t,
            "active_blocks": max(1.0, active),
            "kit_private_bytes": private,
            "kit_working_set_bytes": private * 0.62,
            "tree_private_bytes": private + 150 * MIB,
            "gpu_dedicated_memory_mib": 6800.0 + active * 0.02,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Phase 6EY offline calibration refuses output reuse: {output}")
    output.mkdir(parents=True)
    specs = [
        {"phase": "6EU", "condition": "R0_none_run01", "root": "phase6eu-readback-lifetime-1", "relative": "calibration/run01/R0_none", "prefix": "run01_R0_none"},
        {"phase": "6EV", "condition": "L0_short_control", "root": "phase6ev-r0-lifecycle-1", "relative": "L0_short", "prefix": "L0_short"},
        {"phase": "6EW", "condition": "R0_none_run01", "root": "phase6ew-r0-lifecycle-1", "relative": "calibration/run01/R0_none", "prefix": "run01_R0_none"},
        {"phase": "6EX", "condition": "R0_none_run01", "root": "phase6ex-r0-stability-1", "relative": "calibration/run01/R0_none", "prefix": "run01_R0_none"},
    ]
    historical = [_historical_case(repo, spec) for spec in specs]
    synthetic_expectations = {
        "constant_noise": True,
        "periodic": True,
        "drop_recovery": True,
        "linear_growth": False,
        "accelerating_growth": False,
        "memory_only_growth": False,
        "bounded_correlated_growth": True,
        "cache_after_drop": False,
    }
    synthetic = {}
    for name, expected in synthetic_expectations.items():
        evaluation = evaluate(_synthetic_rows(name), CALIBRATED_THRESHOLDS)
        evaluation["expected_gate_pass"] = expected
        evaluation["expectation_met"] = evaluation["gate_pass"] is expected
        synthetic[name] = evaluation
    report = {
        "schema": "campfire.phase6ey.offline-dynamic-stationarity-calibration.v1",
        "phase": "phase6ey",
        "status": "pass" if all(item["expectation_met"] for item in synthetic.values()) else "fail",
        "purpose": "read-only metric design; no historical sample is eligible for the Phase 6EY formal population",
        "calibrated_thresholds": CALIBRATED_THRESHOLDS,
        "historical": historical,
        "synthetic": synthetic,
    }
    (output / "offline_calibration.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
