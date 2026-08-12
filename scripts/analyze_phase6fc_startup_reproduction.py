"""Aggregate bounded Phase 6FC startup-reproduction probes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from phase6fc_startup_contract import classify_startup


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_utc(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def log_evidence(path: Path):
    counts = Counter()
    bounded = []
    digest = hashlib.sha256()
    if not path.exists():
        return {"available": False, "sha256": None, "counts": {}, "bounded_lines": []}
    with path.open("rb") as raw:
        for chunk in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(chunk)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for number, line in enumerate(stream, 1):
            lower = line.lower()
            if "[warning]" in lower:
                counts["warning"] += 1
            if "[error]" in lower:
                counts["error"] += 1
            if "shader" in lower and ("compil" in lower or "cache" in lower):
                counts["shader_or_cache"] += 1
            if "cache hit" in lower:
                counts["cache_hit"] += 1
            if "cache miss" in lower:
                counts["cache_miss"] += 1
            if "adapter" in lower or "gpu foundation" in lower:
                counts["gpu_initialization"] += 1
            if len(bounded) < 40 and any(token in lower for token in ("[warning]", "[error]", "shader", "cache", "adapter", "gpu foundation")):
                bounded.append({"line": number, "text": line.rstrip()[:1000]})
    return {"available": True, "sha256": digest.hexdigest().upper(), "counts": dict(counts), "bounded_lines": bounded}


def marker_duration(markers, start, end):
    left = next((item for item in markers if item.get("marker") == start), None)
    right = next((item for item in markers if item.get("marker") == end), None)
    if left is None or right is None:
        return None
    return (int(right["perf_counter_ns"]) - int(left["perf_counter_ns"])) / 1e9


def analyze_case(root: Path, condition: dict, contract: dict, sequence_index: int) -> dict:
    label = condition["id"]
    directory = root / label
    raw = load(directory / "raw.json") or {}
    evidence = load(directory / "runner_evidence.json") or {}
    guard = load(root / "runner-logs" / f"{label}.guard.json") or {}
    markers = jsonl(directory / "resource_markers.jsonl")
    marker_names = [item.get("marker") for item in markers]
    source = raw.get("startup_live_point_emitter_contract") or {}
    history = (raw.get("startup_probe") or {}).get("history") or raw.get("flow_liveness_history") or []
    physical = classify_startup(history, source, contract["classification"])
    missing = [name for name in contract["required_startup_markers"] if name not in marker_names]
    outcome = evidence.get("outcome") or {}
    lifecycle_pass = bool(
        raw.get("status") == "ok" and raw.get("lifecycle_marker") == "shutdown_complete"
        and outcome.get("functional_status") == "pass" and outcome.get("lifecycle_status") == "normal_exit"
        and guard.get("status") == "ok" and guard.get("exit_code") == 0 and guard.get("process_absent") is True
        and not missing
    )
    classification = physical["classification"] if lifecycle_pass else "lifecycle_failure"
    by_frame = {int(item["frame"]): int(item["active_blocks"]) for item in history}
    source_arrays = source.get("arrays") or {}
    identity_fields = (
        "stage_identity", "stage_python_identity", "flow_identity", "emitter_python_identity",
        "points_prim_python_identity", "stage_sha256", "payload_sha256",
    )
    identities_stable = {
        field: len({json.dumps(item.get(field), sort_keys=True) for item in history}) <= 1
        for field in identity_fields
    }
    os_exit = next((item for item in jsonl(directory / "runner_lifecycle_markers.jsonl") if item.get("marker") == "os_process_exit_observed"), None)
    return {
        "id": label,
        "sequence_index": sequence_index,
        "declared_condition": condition,
        "classification": classification,
        "physical_classification": physical,
        "frame_values": {str(frame): by_frame.get(frame) for frame in (1, 30, 60, 120)},
        "active_block_history": [{"frame": int(item["frame"]), "active_blocks": int(item["active_blocks"])} for item in history],
        "source_contract": source,
        "source_array_hashes": {name: item.get("sha256") for name, item in source_arrays.items()},
        "stage_sha256": raw.get("stage_sha256"),
        "payload_sha256": (raw.get("point_payload") or {}).get("payload_sha256"),
        "identities_stable": identities_stable,
        "startup_markers_complete": not missing,
        "missing_startup_markers": missing,
        "lifecycle_pass": lifecycle_pass,
        "last_lifecycle_marker": raw.get("lifecycle_marker"),
        "stage_connection_seconds": marker_duration(markers, "usd_context_connection_started", "usd_context_connection_complete"),
        "viewport_readiness_seconds": marker_duration(markers, "renderer_readiness_started", "renderer_readiness_complete"),
        "flow_interface_acquire_seconds": marker_duration(markers, "flow_interface_acquire_started", "flow_interface_acquire_complete"),
        "stopped_update_seconds": marker_duration(markers, "pre_timeline_updates_started", "pre_timeline_updates_complete"),
        "extra_update_seconds": marker_duration(markers, "extra_updates_before_play_started", "extra_updates_before_play_complete"),
        "stage_close_seconds": marker_duration(markers, "stage_close_request_before", "stage_close_request_after"),
        "process_start_utc": evidence.get("process_start_utc"),
        "previous_process_exit_utc": evidence.get("previous_process_exit_utc"),
        "previous_process_exit_to_process_start_seconds": evidence.get("previous_process_exit_to_process_start_seconds"),
        "os_exit_utc": os_exit.get("timestamp_utc") if os_exit else None,
        "sequence_cache_state": "cold_first_process_in_empty_root" if sequence_index == 0 else "subsequent_process_in_same_sequence",
        "cache_state_publicly_confirmed": False,
        "log_evidence": log_evidence(directory / "kit.log"),
        "resource_guard": guard,
        "shutdown_outcome": outcome,
        "fatal_count": len(evidence.get("fatal_lines") or []),
        "dump_count": len(evidence.get("dump_inventory") or []),
        "upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines") or []),
        "cdb_invoked": (evidence.get("shutdown_monitor") or {}).get("diagnostic") is not None,
        "production_app_sha256_before": evidence.get("production_app_sha256_before"),
        "production_app_sha256_after": evidence.get("production_app_sha256_after"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load(args.contract)
    declared = contract["baseline_conditions"] + contract["ablation_conditions"]
    cases = {}
    for index, condition in enumerate(declared):
        if (args.root / condition["id"]).exists():
            cases[condition["id"]] = analyze_case(args.root, condition, contract, index)
    baseline_ids = [item["id"] for item in contract["baseline_conditions"]]
    baseline = [cases[label] for label in baseline_ids if label in cases]
    baseline_classes = Counter(item["classification"] for item in baseline)
    report = {
        "schema": "campfire.phase6fc.startup-reproduction-report.v1",
        "phase": "phase6fc",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": True,
        "cases": cases,
        "baseline_completed": len(baseline),
        "baseline_classification_counts": dict(baseline_classes),
        "small_field_reproduction_rate": (
            baseline_classes.get("small_field_ingestion", 0) / len(baseline) if baseline else None
        ),
        "all_six_baselines_representative": bool(
            len(baseline) == 6 and all(item["classification"] == "representative_ingestion" for item in baseline)
        ),
        "ablations_eligible": bool(
            len(baseline) == 6 and all(item["classification"] == "representative_ingestion" for item in baseline)
        ),
        "stage_hash_equal": len({item["stage_sha256"] for item in cases.values()}) <= 1,
        "payload_hash_equal": len({item["payload_sha256"] for item in cases.values()}) <= 1,
        "public_field_checked": False,
        "long_population_started": False,
        "production_changed": any(
            item["production_app_sha256_before"] != item["production_app_sha256_after"] for item in cases.values()
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
