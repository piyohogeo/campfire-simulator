"""Aggregate the bounded Phase 6FP pre-readback allocation calibration."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def epoch(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def summarize_trace(path: Path, marker_times: dict):
    peaks = {"kit_private_bytes": 0, "kit_working_set_bytes": 0, "tree_private_bytes": 0,
             "runner_private_bytes": 0, "diagnostic_private_bytes": 0}
    kit_samples = []
    nearest = {name: None for name in marker_times}
    minimum_physical = None
    minimum_commit = None
    for sample in jsonl(path):
        timestamp = float(sample.get("timestamp_utc_epoch", 0.0))
        tree = int(sample.get("tree_private_bytes", 0) or 0)
        peaks["tree_private_bytes"] = max(peaks["tree_private_bytes"], tree)
        machine = sample.get("machine") or {}
        physical = machine.get("available_physical_bytes")
        commit = machine.get("estimated_commit_headroom_bytes")
        minimum_physical = physical if minimum_physical is None else min(minimum_physical, physical)
        minimum_commit = commit if minimum_commit is None else min(minimum_commit, commit)
        kit = None
        for process in sample.get("processes", []):
            role = process.get("role")
            private = int(process.get("private_bytes", 0) or 0)
            if role == "kit":
                kit = process
                peaks["kit_private_bytes"] = max(peaks["kit_private_bytes"], private)
                peaks["kit_working_set_bytes"] = max(peaks["kit_working_set_bytes"], int(process.get("working_set_bytes", 0) or 0))
            elif role == "runner":
                peaks["runner_private_bytes"] = max(peaks["runner_private_bytes"], private)
            elif role == "diagnostic":
                peaks["diagnostic_private_bytes"] = max(peaks["diagnostic_private_bytes"], private)
        if kit is not None:
            row = {
                "timestamp_utc_epoch": timestamp,
                "kit_private_bytes": int(kit.get("private_bytes", 0) or 0),
                "kit_working_set_bytes": int(kit.get("working_set_bytes", 0) or 0),
                "tree_private_bytes": tree,
                "active_marker": sample.get("diagnostic_marker") or sample.get("lifecycle_marker"),
            }
            kit_samples.append(row)
            for name, target in marker_times.items():
                if target is None:
                    continue
                current = nearest[name]
                distance = abs(timestamp - target)
                if current is None or distance < current[0]:
                    nearest[name] = (distance, row)
    return {
        "peaks": peaks,
        "minimum_available_physical_bytes": minimum_physical,
        "minimum_commit_headroom_bytes": minimum_commit,
        "kit_sample_count": len(kit_samples),
        "first_kit_sample": kit_samples[0] if kit_samples else None,
        "last_kit_sample": kit_samples[-1] if kit_samples else None,
        "nearest_markers": {key: value[1] if value else None for key, value in nearest.items()},
    }


def summarize_gpu(path: Path):
    dedicated = defaultdict(list)
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            for row in csv.reader(stream):
                if len(row) < 5:
                    continue
                try:
                    dedicated[row[1].strip()].append(float(row[4].strip()))
                except ValueError:
                    continue
    return {
        "dedicated_memory_mib_by_gpu": {
            key: {"sample_count": len(values), "minimum": min(values), "maximum": max(values)}
            for key, values in dedicated.items()
        },
        "shared_memory": {"available": False, "reason": "existing bounded nvidia-smi CSV does not expose shared memory"},
    }


def condition_lookup(contract):
    return {item["id"]: item for item in contract["conditions"]}


def classify_attempt(attempt_dir: Path, contract):
    metadata = load(attempt_dir / "attempt_metadata.json") or {}
    case_dir = attempt_dir / "case"
    logs = attempt_dir / "runner-logs"
    raw = load(case_dir / "raw.json") or {}
    evidence = load(case_dir / "runner_evidence.json") or {}
    guard = load(logs / "guard.json") or {}
    markers = list(jsonl(case_dir / "resource_markers.jsonl"))
    frames = {}
    marker_times = {}
    for marker in markers:
        name = marker.get("marker")
        if name in ("offline_stage_complete", "allocation_calibration_prepared", "timeline_playing", "final_sample_complete"):
            marker_times[name] = epoch(marker.get("timestamp_utc"))
        if name == "startup_frame_sample" and marker.get("frame") in (60, 96):
            frame = int(marker["frame"])
            frames[str(frame)] = {
                "active_blocks": marker.get("active_blocks"),
                "kit_private_bytes": (marker.get("process_memory") or {}).get("private_bytes"),
                "kit_working_set_bytes": (marker.get("process_memory") or {}).get("working_set_bytes"),
                "timestamp_utc": marker.get("timestamp_utc"),
            }
            marker_times[f"frame_{frame}"] = epoch(marker.get("timestamp_utc"))
    trace = summarize_trace(logs / "resource.jsonl", marker_times)
    gpu = summarize_gpu(logs / "gpu.csv")
    failures = []
    startup = raw.get("startup_liveness_gate") or {}
    if guard.get("status") != "ok":
        failures.append(f"guard:{guard.get('stop_reason') or guard.get('status') or 'missing'}")
    if raw.get("status") != "ok" or raw.get("lifecycle_marker") != "shutdown_complete":
        failures.append("probe_or_shutdown_incomplete")
    outcome = evidence.get("outcome") or {}
    if outcome.get("functional_status") != "pass" or outcome.get("lifecycle_status") != "normal_exit":
        failures.append("normal_exit_not_confirmed")
    if startup.get("classification") != "representative_ingestion":
        failures.append(f"startup:{startup.get('classification') or 'missing'}")
    if len(frames) != 2:
        failures.append("frame_60_96_marker_missing")
    if evidence.get("fatal_lines") or evidence.get("dump_inventory") or evidence.get("automatic_upload_attempt_lines"):
        failures.append("fatal_dump_or_upload")
    if evidence.get("production_changed"):
        failures.append("production_hash_changed")
    expected = condition_lookup(contract).get(metadata.get("condition"), {})
    allocation = raw.get("allocation_calibration") or {}
    if allocation.get("level") != expected.get("level"):
        failures.append("allocation_level_mismatch")
    if allocation.get("logical_buffer_bytes") != 0:
        failures.append("unexpected_pre_readback_field_body")
    startup_only = bool(failures) and all(value.startswith("startup:") for value in failures)
    classification = "representative_pass" if not failures else ("startup_prerequisite_failure" if startup_only else "nonreplaceable_failure")
    return {
        "attempt_id": metadata.get("attempt_id"),
        "slot_id": metadata.get("slot_id"),
        "sequence": metadata.get("sequence"),
        "position": metadata.get("position"),
        "condition": metadata.get("condition"),
        "level": expected.get("level"),
        "classification": classification,
        "failures": failures,
        "startup": startup,
        "stage_sha256": raw.get("stage_sha256"),
        "payload_sha256": (raw.get("point_payload") or {}).get("payload_sha256"),
        "allocation": allocation,
        "frames": frames,
        "resource": trace,
        "gpu": gpu,
        "guard_status": guard.get("status"),
        "guard_stop_reason": guard.get("stop_reason"),
        "process_exit_code": evidence.get("process_exit_code"),
        "normal_exit": outcome.get("lifecycle_status") == "normal_exit",
        "fatal_count": len(evidence.get("fatal_lines") or []),
        "dump_count": len(evidence.get("dump_inventory") or []),
        "upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines") or []),
    }


def distribution(values):
    values = [int(value) for value in values if value is not None]
    return None if not values else {
        "count": len(values), "minimum": min(values), "median": statistics.median(values),
        "maximum": max(values), "mean": statistics.mean(values),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = load(args.contract)
    attempts = [classify_attempt(path, contract) for path in sorted((args.root / "attempts").glob("attempt*"))]
    grouped = defaultdict(list)
    for attempt in attempts:
        if attempt["classification"] == "representative_pass":
            grouped[attempt["condition"]].append(attempt)
    baseline = grouped.get("C0_baseline", [])
    baseline_peaks = [item["resource"]["peaks"]["kit_private_bytes"] for item in baseline]
    baseline_median = statistics.median(baseline_peaks) if baseline_peaks else None
    summaries = {}
    for condition in [item["id"] for item in contract["conditions"]]:
        values = grouped.get(condition, [])
        peaks = [item["resource"]["peaks"]["kit_private_bytes"] for item in values]
        summary = {
            "representative_count": len(values),
            "kit_private_peak_bytes": distribution(peaks),
            "kit_private_frame60_bytes": distribution((item["frames"].get("60") or {}).get("kit_private_bytes") for item in values),
            "kit_private_frame96_bytes": distribution((item["frames"].get("96") or {}).get("kit_private_bytes") for item in values),
            "active_blocks_frame60": distribution((item["frames"].get("60") or {}).get("active_blocks") for item in values),
            "active_blocks_frame96": distribution((item["frames"].get("96") or {}).get("active_blocks") for item in values),
        }
        current_median = (summary["kit_private_peak_bytes"] or {}).get("median")
        summary["kit_peak_median_delta_from_baseline_bytes"] = (
            None if baseline_median is None or current_median is None else current_median - baseline_median
        )
        summaries[condition] = summary
    nonreplaceable = [item for item in attempts if item["classification"] == "nonreplaceable_failure"]
    required = int(contract["population"]["required_representative_processes"])
    report = {
        "schema": "campfire.phase6fp.pre-readback-allocation-report.v1",
        "phase": "phase6fp",
        "attempt_count": len(attempts),
        "representative_count": sum(item["classification"] == "representative_pass" for item in attempts),
        "startup_prerequisite_failure_count": sum(item["classification"] == "startup_prerequisite_failure" for item in attempts),
        "nonreplaceable_failure_count": len(nonreplaceable),
        "attempts": attempts,
        "condition_summaries": summaries,
        "population_complete": sum(item["classification"] == "representative_pass" for item in attempts) == required,
        "calibration_qualified": sum(item["classification"] == "representative_pass" for item in attempts) == required and not nonreplaceable,
        "gpu_shared_memory_contract": "unavailable is explicit and is not estimated",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
