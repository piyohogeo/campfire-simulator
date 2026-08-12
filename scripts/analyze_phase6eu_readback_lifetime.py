from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


GIB = 1024 ** 3


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path):
    if not path.is_file():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _slope(points):
    if len(points) < 2:
        return None
    xs = [float(row[0]) for row in points]
    ys = [float(row[1]) for row in points]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator <= 0.0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))]


def _marker_summary(markers, contract, resource_trace):
    sample_rows = {}
    for row in markers:
        if row.get("marker") == "sample_started" and "frame" in row:
            sample_rows[int(row["frame"])] = row
    stability_frames = list(contract["plateau_contract"]["stability_frames"])
    stability = [sample_rows[frame] for frame in stability_frames if frame in sample_rows]
    active = [int(row.get("active_blocks", 0)) for row in stability]
    active_mean = statistics.fmean(active) if active else None
    active_range_fraction = (
        (max(active) - min(active)) / active_mean if active and active_mean and active_mean > 0 else None
    )
    private_points = []
    private_values = []
    marker_memory_source = "synchronous_process_snapshot"
    for row in stability:
        memory = row.get("process_memory") or {}
        if memory.get("available") and memory.get("private_bytes") is not None:
            private_points.append((float(row["perf_counter_ns"]) / 1_000_000_000.0, int(memory["private_bytes"])))
            private_values.append(int(memory["private_bytes"]))
    if len(private_values) != len(stability_frames) and resource_trace:
        marker_memory_source = "nearest_outer_guard_sample"
        private_points = []
        private_values = []
        for marker in stability:
            marker_epoch = datetime.fromisoformat(marker["timestamp_utc"]).timestamp()
            candidates = []
            for trace_row in resource_trace:
                for process in trace_row.get("processes", []):
                    if process.get("role") == "kit":
                        candidates.append((abs(float(trace_row["timestamp_utc_epoch"]) - marker_epoch), trace_row, process))
            if not candidates:
                continue
            _distance, trace_row, process = min(candidates, key=lambda item: item[0])
            private_points.append((float(trace_row["timestamp_utc_epoch"]), int(process["private_bytes"])))
            private_values.append(int(process["private_bytes"]))
    private_slope = _slope(private_points)
    decreases = sum(right < left for left, right in zip(private_values, private_values[1:]))
    stability_resource_samples = 0
    if len(stability) == len(stability_frames):
        start_epoch = datetime.fromisoformat(stability[0]["timestamp_utc"]).timestamp()
        end_epoch = datetime.fromisoformat(stability[-1]["timestamp_utc"]).timestamp()
        stability_resource_samples = sum(
            start_epoch <= float(row.get("timestamp_utc_epoch", -1.0)) <= end_epoch for row in resource_trace
        )
    plateau = contract["plateau_contract"]
    active_stable = (
        len(active) == len(stability_frames)
        and active_range_fraction is not None
        and active_range_fraction <= float(plateau["maximum_active_block_range_fraction"])
    )
    memory_stable = (
        len(private_values) == len(stability_frames)
        and private_slope is not None
        and private_slope <= int(plateau["maximum_private_growth_bytes_per_second"])
        and (decreases > 0 or abs(private_slope) <= int(plateau["maximum_private_growth_bytes_per_second"]))
    )
    return {
        "sample_frames_present": sorted(sample_rows),
        "stability_frames": stability_frames,
        "stability_active_blocks": active,
        "active_block_range_fraction": active_range_fraction,
        "active_blocks_stable": active_stable,
        "stability_private_bytes": private_values,
        "marker_memory_source": marker_memory_source,
        "private_growth_bytes_per_second": private_slope,
        "private_decrease_interval_count": decreases,
        "stability_resource_sample_count": stability_resource_samples,
        "private_memory_stable": memory_stable,
        "plateau_pass": bool(
            active_stable and memory_stable
            and stability_resource_samples >= int(plateau["minimum_resource_samples_in_stability_interval"])
        ),
    }


def _boundary_deltas(markers):
    by_frame = defaultdict(dict)
    for row in markers:
        frame = row.get("frame")
        memory = row.get("process_memory") or {}
        if frame is None or not memory.get("available"):
            continue
        by_frame[int(frame)][row.get("marker")] = int(memory["private_bytes"])
    pairs = [
        ("acquire", "readback_call_before", "readback_call_after"),
        ("tuple_check", "readback_call_after", "tuple_elements_checked"),
        ("fuel_conversion", "fuel_conversion_before", "fuel_conversion_after"),
        ("numpy_aggregate", "numpy_aggregate_before", "numpy_aggregate_after"),
        ("reference_release", "tuple_elements_checked", "python_references_released"),
        ("jsonl_write", "jsonl_write_before", "jsonl_write_after"),
    ]
    result = []
    for frame, values in sorted(by_frame.items()):
        row = {"frame": frame}
        for label, before, after in pairs:
            if before in values and after in values:
                row[f"{label}_private_delta_bytes"] = values[after] - values[before]
        result.append(row)
    return result


def _run_row(root: Path, contract, run_index: int, condition):
    condition_id = condition["id"]
    prefix = f"run{run_index:02d}_{condition_id}"
    guard_path = root / "runner-logs" / f"{prefix}.guard.json"
    case_dir = root / "calibration" / f"run{run_index:02d}" / condition_id
    if not guard_path.is_file():
        return None
    guard = _load(guard_path)
    raw_path = case_dir / "raw.json"
    raw = _load(raw_path) if raw_path.is_file() else None
    markers = _jsonl(case_dir / "resource_markers.jsonl")
    resource_trace = _jsonl(root / "runner-logs" / f"{prefix}.resource.jsonl")
    object_rows = []
    if raw:
        for sample in raw.get("samples", []):
            boundary = sample.get("readback_boundary")
            if boundary:
                object_rows.append({"frame": sample.get("frame"), **boundary})
    row = {
        "run_index": run_index,
        "condition": condition_id,
        "mode": condition["readback_mode"],
        "readback_frames": condition["readback_frames"],
        "guard_status": guard.get("status"),
        "stop_reason": guard.get("stop_reason"),
        "exit_code": guard.get("exit_code"),
        "process_absent": guard.get("process_absent"),
        "kit_peak_bytes": (guard.get("peaks") or {}).get("kit"),
        "kit_peak_gib": ((guard.get("peaks") or {}).get("kit") or 0) / GIB,
        "tree_peak_bytes": (guard.get("peaks") or {}).get("tree"),
        "runner_peak_bytes": (guard.get("peaks") or {}).get("runner"),
        "diagnostic_peak_bytes": (guard.get("peaks") or {}).get("diagnostic"),
        "raw_status": raw.get("status") if raw else "missing",
        "lifecycle_marker": raw.get("lifecycle_marker") if raw else None,
        "samples": [
            {"frame": sample.get("frame"), "active_blocks": sample.get("active_blocks")}
            for sample in (raw or {}).get("samples", [])
        ],
        "object_lifetime": object_rows,
        "boundary_private_deltas": _boundary_deltas(markers),
        "marker_summary": _marker_summary(markers, contract, resource_trace),
    }
    row["normal_exit"] = bool(
        row["guard_status"] == "ok" and row["exit_code"] == 0 and row["process_absent"]
        and row["raw_status"] == "ok" and row["lifecycle_marker"] == "shutdown_complete"
    )
    return row


def analyze(root: Path, contract):
    conditions = []
    condition_to_group = {}
    for group in contract["condition_groups"]:
        for condition in group["conditions"]:
            conditions.append(condition)
            condition_to_group[condition["id"]] = group["id"]
    rows = []
    for condition in conditions:
        for run_index in range(1, int(contract["runs_per_condition"]) + 1):
            row = _run_row(root, contract, run_index, condition)
            if row is not None:
                rows.append(row)
    grouped = {}
    for group in contract["condition_groups"]:
        ids = {condition["id"] for condition in group["conditions"]}
        expected = len(ids) * int(contract["runs_per_condition"])
        group_rows = [row for row in rows if row["condition"] in ids]
        grouped[group["id"]] = {
            "expected_processes": expected,
            "observed_processes": len(group_rows),
            "normal_exit_processes": sum(bool(row["normal_exit"]) for row in group_rows),
            "plateau_processes": sum(bool(row["marker_summary"]["plateau_pass"]) for row in group_rows),
            "gate_pass": bool(
                len(group_rows) == expected
                and all(row["normal_exit"] for row in group_rows)
                and (not group.get("requires_group_plateau") or all(row["marker_summary"]["plateau_pass"] for row in group_rows))
            ),
        }
    completed = sum(bool(row["normal_exit"]) for row in rows)
    return {
        "schema": "campfire.phase6eu.nanovdb-readback-lifetime-report.v1",
        "phase": "phase6eu",
        "status": "qualified" if completed == int(contract["formal_process_count"]) and all(value["gate_pass"] for value in grouped.values()) else "safe_stop_or_incomplete",
        "contract_sha256": None,
        "phase6es_frozen": True,
        "phase6et_frozen": True,
        "attempted_processes": len(rows),
        "completed_processes": completed,
        "expected_processes": int(contract["formal_process_count"]),
        "rows": rows,
        "groups": grouped,
        "condition_group": condition_to_group,
        "return_gate_satisfied": bool(
            all(grouped[name]["gate_pass"] for name in ("baseline", "acquisition", "conversion_and_aggregation"))
        ),
        "classification": "unclassified until staged conditions complete; a safe stop preserves all completed rows without retrospective acceptance",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _load(args.contract)
    report = analyze(args.root, contract)
    import hashlib
    report["contract_sha256"] = hashlib.sha256(args.contract.read_bytes()).hexdigest().upper()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "attempted": report["attempted_processes"], "completed": report["completed_processes"], "groups": report["groups"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
