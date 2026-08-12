"""Summarize the Phase 6ET resource calibration without loading field arrays."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path


GIB = 1024 ** 3


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _guard(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _trace(path: Path, tail_seconds: float) -> dict:
    first = None
    last = None
    peak = None
    tail: list[tuple[float, int]] = []
    sample_count = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            sample_count += 1
            timestamp = float(record["timestamp_utc_epoch"])
            kit = max(
                (int(row["private_bytes"]) for row in record.get("processes", []) if row.get("role") == "kit"),
                default=0,
            )
            point = (timestamp, kit)
            first = first or point
            last = point
            if peak is None or kit > peak["private_bytes"]:
                peak = {
                    "private_bytes": kit,
                    "timestamp_utc_epoch": timestamp,
                    "execution_section": record.get("current_execution_section"),
                    "lifecycle_marker": record.get("lifecycle_marker"),
                    "diagnostic_marker": record.get("diagnostic_marker"),
                }
            section = str(record.get("current_execution_section") or "")
            if section not in {"measurement_complete", "timeline_stopping", "timeline_stopped", "renderer_drain_complete", "shutdown_complete"}:
                tail.append(point)
                while tail and timestamp - tail[0][0] > tail_seconds:
                    tail.pop(0)
    slope = None
    if len(tail) >= 2 and tail[-1][0] > tail[0][0]:
        slope = (tail[-1][1] - tail[0][1]) / (tail[-1][0] - tail[0][0])
    return {
        "sample_count": sample_count,
        "first_kit_private_bytes": None if first is None else first[1],
        "last_kit_private_bytes": None if last is None else last[1],
        "peak": peak,
        "tail_sample_count": len(tail),
        "tail_growth_bytes_per_second": slope,
    }


def _marker_memory(trace_path: Path, marker_path: Path) -> list[dict]:
    if not trace_path.is_file() or not marker_path.is_file():
        return []
    timestamps: list[float] = []
    samples: list[dict] = []
    with trace_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            kit = max((int(row["private_bytes"]) for row in record.get("processes", []) if row.get("role") == "kit"), default=0)
            timestamps.append(float(record["timestamp_utc_epoch"]))
            samples.append({"kit_private_bytes": kit, "tree_private_bytes": int(record.get("tree_private_bytes", 0))})
    output = []
    previous = None
    with marker_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            marker = json.loads(line)
            timestamp = datetime.fromisoformat(marker["timestamp_utc"]).timestamp()
            index = min(bisect.bisect_left(timestamps, timestamp), len(samples) - 1)
            if index < 0:
                continue
            row = {key: marker.get(key) for key in ("marker", "frame", "channel", "buffer_bytes", "raw_json_bytes", "readback") if key in marker}
            row.update(samples[index])
            row["sample_timestamp_utc_epoch"] = timestamps[index]
            row["kit_delta_from_previous_marker_bytes"] = None if previous is None else row["kit_private_bytes"] - previous
            previous = row["kit_private_bytes"]
            output.append(row)
    return output


def _raw_metrics(path: Path) -> dict:
    if not path.is_file():
        return {"available": False}
    raw = json.loads(path.read_text(encoding="utf-8"))
    per_frame = []
    for sample in raw.get("samples", []):
        channels = sample.get("channels", {})
        sizes = {name: int(value.get("buffer_bytes", value.get("word_count", 0) * 8)) for name, value in channels.items() if value.get("available")}
        per_frame.append({"frame": sample.get("frame"), "active_blocks": sample.get("active_blocks"), "channel_buffer_bytes": sizes, "total_buffer_bytes": sum(sizes.values())})
    npz_bytes = sum(item.stat().st_size for item in path.parent.rglob("*.npz"))
    return {
        "available": True,
        "status": raw.get("status"),
        "lifecycle_marker": raw.get("lifecycle_marker"),
        "frames": per_frame,
        "maximum_public_buffer_bytes_per_sample": max((item["total_buffer_bytes"] for item in per_frame), default=0),
        "spatial_npz_file_bytes": npz_bytes,
        "active_blocks": [item["active_blocks"] for item in per_frame],
    }


def _gpu(path: Path) -> dict:
    if not path.is_file():
        return {"available": False}
    per_adapter: dict[str, dict] = {}
    with path.open(encoding="utf-8", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 8:
                continue
            adapter = row[1].strip()
            try:
                used_mib = float(row[4].strip())
                utilization = float(row[5].strip())
                power = float(row[6].strip())
                temperature = float(row[7].strip())
            except ValueError:
                continue
            entry = per_adapter.setdefault(adapter, {"name": row[2].strip(), "pci_bus_id": row[3].strip(), "samples": 0, "peak_dedicated_mib": 0.0, "peak_utilization_percent": 0.0, "peak_power_w": 0.0, "peak_temperature_c": 0.0})
            entry["samples"] += 1
            entry["peak_dedicated_mib"] = max(entry["peak_dedicated_mib"], used_mib)
            entry["peak_utilization_percent"] = max(entry["peak_utilization_percent"], utilization)
            entry["peak_power_w"] = max(entry["peak_power_w"], power)
            entry["peak_temperature_c"] = max(entry["peak_temperature_c"], temperature)
    return {"available": bool(per_adapter), "adapters": per_adapter, "shared_memory": "unavailable; not estimated"}


def _baseline(root: Path) -> dict:
    rows = []
    for relative in (
        "artifacts/phase6er-formal-1/runner-logs/formal_run_1_lower_upper_allow_self_center.guard.json",
        "artifacts/phase6er-formal-2/runner-logs/formal_run_1_lower_upper_allow_self_center.guard.json",
        "artifacts/phase6es-calibration-1/runner-logs/emitterless_on.guard.json",
        "artifacts/phase6es-calibration-1/runner-logs/emitter_off.guard.json",
        "artifacts/phase6es-calibration-1/runner-logs/filtered_933_on.guard.json",
        "artifacts/phase6es-calibration-2/runner-logs/emitterless_on.guard.json",
        "artifacts/phase6es-calibration-2/runner-logs/emitter_off.guard.json",
        "artifacts/phase6es-calibration-2/runner-logs/filtered_933_on.guard.json",
    ):
        path = root / relative
        if not path.is_file():
            continue
        guard = _guard(path)
        peak = int(guard.get("peaks", {}).get("kit", 0))
        rows.append({"artifact": relative, "status": guard.get("status"), "stop_reason": guard.get("stop_reason"), "kit_peak_bytes": peak, "kit_peak_gib": peak / GIB, "tree_peak_bytes": int(guard.get("peaks", {}).get("tree", 0)), "duration_seconds": guard.get("duration_seconds"), "peak_section": (guard.get("peak_evidence", {}).get("kit") or {}).get("timestamp_utc_epoch")})
    return {
        "rows": rows,
        "phase6er_four_log_runtime": "not reached; Phase 6ER production_four evidence is offline geometry only",
        "phase6es_root1_failed_peak_bytes": 15100735488,
        "phase6es_root1_failed_peak_gib": 15100735488 / GIB,
        "phase6es_root2_failed_peak_bytes": 15722414080,
        "phase6es_root2_failed_peak_gib": 15722414080 / GIB,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    completed = []
    by_condition: dict[str, list[dict]] = defaultdict(list)
    tail_seconds = float(contract["plateau_contract"]["tail_window_seconds"])
    slope_limit = float(contract["plateau_contract"]["maximum_tail_growth_bytes_per_second"])
    min_tail = int(contract["plateau_contract"]["minimum_tail_samples"])
    for summary_path in sorted((args.root / "runner-logs").glob("run??_*.guard.json")):
        if summary_path.name.endswith(".transport.guard.json"):
            continue
        stem = summary_path.name[: -len(".guard.json")]
        run_index = int(stem[3:5])
        condition_id = stem[6:]
        condition_dir = args.root / "calibration" / f"run{run_index:02d}" / condition_id
        guard = _guard(summary_path)
        trace = _trace(summary_path.with_name(stem + ".resource.jsonl"), tail_seconds)
        raw = _raw_metrics(condition_dir / "raw.json")
        marker_memory = _marker_memory(
            summary_path.with_name(stem + ".resource.jsonl"),
            condition_dir / "resource_markers.jsonl",
        )
        peak = int(guard.get("peaks", {}).get("kit", 0))
        slope = trace["tail_growth_bytes_per_second"]
        plateau = guard.get("status") == "ok" and trace["tail_sample_count"] >= min_tail and slope is not None and slope <= slope_limit
        row = {
            "run_index": run_index,
            "condition": condition_id,
            "guard_status": guard.get("status"),
            "stop_reason": guard.get("stop_reason"),
            "exit_code": guard.get("exit_code"),
            "kit_peak_bytes": peak,
            "kit_peak_gib": peak / GIB,
            "tree_peak_bytes": int(guard.get("peaks", {}).get("tree", 0)),
            "runner_peak_bytes": int(guard.get("peaks", {}).get("runner", 0)),
            "diagnostic_peak_bytes": int(guard.get("peaks", {}).get("diagnostic", 0)),
            "machine_minima": guard.get("machine_minima"),
            "trace": trace,
            "plateau": plateau,
            "raw": raw,
            "marker_memory": marker_memory,
            "gpu": _gpu(summary_path.with_name(stem + ".gpu.csv")),
        }
        completed.append(row)
        by_condition[condition_id].append(row)
    aggregate = {}
    for condition_id, rows in by_condition.items():
        peaks = [row["kit_peak_bytes"] for row in rows]
        aggregate[condition_id] = {
            "completed_runs": len(rows),
            "kit_peak_min_bytes": min(peaks),
            "kit_peak_max_bytes": max(peaks),
            "kit_peak_mean_bytes": sum(peaks) / len(peaks),
            "all_normal_exit": all(row["guard_status"] == "ok" and row["exit_code"] == 0 for row in rows),
            "all_plateau": all(row["plateau"] for row in rows),
        }
    expected = int(contract["formal_process_count"])
    first_rows = {row["condition"]: row for row in completed if row["run_index"] == 1}
    cause_classification = "insufficient formal evidence"
    if "A_flow_only" in first_rows and "B_minimal_fuel" in first_rows:
        a = first_rows["A_flow_only"]
        b = first_rows["B_minimal_fuel"]
        if a["guard_status"] == "ok" and b["stop_reason"] == "kit_private_limit":
            cause_classification = (
                "four-log Flow without readback already approaches the fixed limit; the first public fuel readback is sufficient "
                "to cross it. Directional aggregation and temperature/smoke collection occur later and are excluded as the "
                "trigger for this safe stop; readback resource lifetime versus Flow allocator high-water remains unresolved."
            )
    report = {
        "schema": "campfire.phase6et.four-log-memory-calibration-report.v1",
        "phase": "phase6et",
        "status": "qualified" if len(completed) == expected and all(row["plateau"] and row["guard_status"] == "ok" for row in completed) else "safe_stop_or_incomplete",
        "contract_sha256": _sha(args.contract),
        "phase6es_frozen": True,
        "phase6es_reclassified": False,
        "baseline_read_only": _baseline(repo),
        "attempted_processes": len(completed),
        "completed_processes": sum(row["guard_status"] == "ok" and row["exit_code"] == 0 for row in completed),
        "expected_processes": expected,
        "rows": completed,
        "by_condition": aggregate,
        "cause_classification": cause_classification,
        "return_gate_satisfied": len(completed) == expected and all(row["plateau"] and row["guard_status"] == "ok" for row in completed),
        "array_interpretation": "get_latest_nanovdb_readback returns the public channel tuple as one acquisition. The selected-channel byte count is a lower bound; the earlier Phase 6ES frame-90 available buffers total 294,940,224 bytes. Public buffer bytes and compressed NPZ bytes are reported separately, and an unexplained GiB increase is not attributed to Python arrays without matching byte evidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
