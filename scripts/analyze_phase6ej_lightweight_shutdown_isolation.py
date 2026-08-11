"""Summarize Phase 6EJ shutdown-diagnostic isolation and CPU telemetry."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime
from pathlib import Path


MIB = 1024 * 1024


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def trace(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def markers(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return trace(path)


def cpu_summary(records: list[dict], role: str, shutdown_only: bool = False) -> dict:
    values = []
    user_start = None
    user_end = None
    kernel_start = None
    kernel_end = None
    for sample in records:
        if shutdown_only and sample.get("lifecycle_marker") not in {"timeline_stopped", "shutdown_requested", "shutdown_complete"}:
            continue
        for process in sample.get("processes", []):
            if process.get("role") != role:
                continue
            value = process.get("cpu_percent_of_logical_total")
            if value is not None:
                values.append(float(value))
            user = process.get("cpu_user_seconds")
            kernel = process.get("cpu_kernel_seconds")
            if user is not None:
                user_start = float(user) if user_start is None else user_start
                user_end = float(user)
            if kernel is not None:
                kernel_start = float(kernel) if kernel_start is None else kernel_start
                kernel_end = float(kernel)
    return {
        "sample_count": len(values),
        "mean_percent_of_logical_total": statistics.fmean(values) if values else None,
        "maximum_percent_of_logical_total": max(values) if values else None,
        "cumulative_user_delta_seconds": None if user_start is None else max(0.0, user_end - user_start),
        "cumulative_kernel_delta_seconds": None if kernel_start is None else max(0.0, kernel_end - kernel_start),
    }


def cpu_by_section(records: list[dict], role: str) -> dict:
    sections: dict[str, list[float]] = {}
    for sample in records:
        section = str(sample.get("current_execution_section") or "unknown")
        for process in sample.get("processes", []):
            value = process.get("cpu_percent_of_logical_total")
            if process.get("role") == role and value is not None:
                sections.setdefault(section, []).append(float(value))
    return {
        section: {
            "sample_count": len(values),
            "mean_percent_of_logical_total": statistics.fmean(values),
            "maximum_percent_of_logical_total": max(values),
        }
        for section, values in sections.items()
    }


def top_thread_evidence(records: list[dict]) -> list[dict]:
    evidence = []
    for sample in records:
        for process in sample.get("processes", []):
            thread = process.get("top_cpu_thread")
            if process.get("role") == "kit" and thread is not None:
                evidence.append({
                    "sample_index": sample.get("sample_index"),
                    "section": sample.get("current_execution_section"),
                    "kit_cpu_percent_of_logical_total": process.get("cpu_percent_of_logical_total"),
                    **thread,
                })
    return evidence


def memory_at_markers(records: list[dict], marker_records: list[dict]) -> list[dict]:
    evidence = []
    if not records:
        return evidence
    for marker in marker_records:
        text = re.sub(r"(\.\d{6})\d+", r"\1", marker["timestamp_utc"].replace("Z", "+00:00"))
        timestamp = datetime.fromisoformat(text).timestamp()
        nearest = min(records, key=lambda item: abs(float(item["timestamp_utc_epoch"]) - timestamp))
        roles: dict[str, int] = {}
        for process in nearest.get("processes", []):
            role = str(process.get("role"))
            roles[role] = max(roles.get(role, 0), int(process.get("private_bytes", 0)))
        evidence.append({
            "marker": marker.get("marker"),
            "marker_process_id": marker.get("process_id"),
            "marker_timestamp_utc": marker.get("timestamp_utc"),
            "nearest_sample_index": nearest.get("sample_index"),
            "nearest_sample_offset_seconds": abs(float(nearest["timestamp_utc_epoch"]) - timestamp),
            "runner_private_bytes": roles.get("runner"),
            "diagnostic_private_bytes": roles.get("diagnostic"),
            "kit_private_bytes": roles.get("kit"),
            "unique_tree_private_bytes": nearest.get("tree_private_bytes"),
        })
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = load(root / "run_manifest.json")
    fixture = load(root / "diagnostic-fixtures" / "report.json")
    fixture_diagnostic = load(root / "diagnostic-fixtures" / "isolated-child" / "diagnostic" / "lightweight_shutdown_diagnostic.json")
    fixture_trace = trace(root / "diagnostic-fixture-guard" / "memory.jsonl")
    fixture_markers = markers(root / "diagnostic-fixtures" / "isolated-child" / "diagnostic.markers.jsonl")
    normal_evidence = load(root / "known-normal-kit" / "case" / "runner_evidence.json")
    p0_evidence = load(root / "p0-equivalent" / "case" / "runner_evidence.json")
    p0_raw = load(root / "p0-equivalent" / "case" / "raw.json")
    p0_spatial = load(root / "p0-equivalent" / "spatial" / "manifest.json")
    p0_trace = trace(root / "p0-equivalent-guard" / "memory.jsonl")
    p0_markers_path = root / "p0-equivalent" / "case" / "sensitive-shutdown-diagnostics.markers.jsonl"
    p0_markers = markers(p0_markers_path)

    off = [item["summary"] for item in manifest["telemetry_comparison"] if not item["enabled"]]
    on = [item["summary"] for item in manifest["telemetry_comparison"] if item["enabled"]]
    off_duration = statistics.fmean(float(item["duration_seconds"]) for item in off)
    on_duration = statistics.fmean(float(item["duration_seconds"]) for item in on)
    off_peak = max(int(item["peaks"]["runner"]) for item in off)
    on_peak = max(int(item["peaks"]["runner"]) for item in on)
    telemetry_memory_delta = on_peak - off_peak
    telemetry_duration_delta = on_duration - off_duration
    telemetry_nonperturbing = telemetry_memory_delta <= 64 * MIB and telemetry_duration_delta <= 1.5

    marker_names = [item.get("marker") for item in p0_markers]
    required_markers = [
        "diagnostic_child_process_started",
        "process_identity_complete",
        "capture_lock_acquired",
        "gpu_inventory_started",
        "gpu_inventory_complete",
        "kit_log_parse_started",
        "kit_log_parse_complete",
        "dump_cdb_decision",
        "diagnostic_json_write_started",
        "diagnostic_json_write_complete",
        "cleanup_started",
        "cleanup_complete",
        "diagnostic_child_process_normal_exit",
        "parent_process_returned",
    ]
    diagnostic_invoked = bool(p0_markers)
    marker_gate = (not diagnostic_invoked) or all(name in marker_names for name in required_markers)
    diagnostic_result = root / "p0-equivalent" / "case" / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json"
    p0_guard = manifest["p0_guard"]
    p0_outcome = p0_evidence.get("outcome") or {}
    p0_safety = (
        not p0_evidence.get("timed_out")
        and not p0_evidence.get("fatal_lines")
        and not p0_evidence.get("dump_inventory")
        and not p0_evidence.get("automatic_upload_attempt_lines")
        and not p0_evidence.get("production_changed")
        and p0_evidence.get("relevant_crash_registry_unchanged") is True
    )
    cleanup = bool(p0_guard["process_absent"])
    parent_bounded = int(p0_guard["peaks"]["runner"]) < int(p0_guard["limits"]["runner_private_bytes"])
    diagnostic_bounded = int(p0_guard["peaks"]["diagnostic"]) < int(p0_guard["limits"]["diagnostic_private_bytes"])
    boundary_persisted = (
        p0_outcome.get("lifecycle_status") == "normal_exit"
        or diagnostic_result.is_file()
        or (diagnostic_invoked and marker_names[-1:] == ["parent_process_returned"])
    )
    contract_unchanged = manifest["frozen_contract_sha256"] == manifest["contract_sha256_after"]
    production_unchanged = manifest["production_app_sha256_before"] == manifest["production_app_sha256_after"]
    p0_gate = all((
        fixture["status"] == "ok",
        normal_evidence.get("outcome", {}).get("lifecycle_status") == "normal_exit",
        telemetry_nonperturbing,
        parent_bounded,
        diagnostic_bounded,
        boundary_persisted,
        marker_gate,
        cleanup,
        p0_safety,
        p0_outcome.get("functional_status") == "pass",
        p0_raw.get("status") == "ok",
        p0_raw.get("lifecycle_marker") == "shutdown_complete",
        int(p0_spatial.get("file_count", 0)) == 4,
        abs(float(p0_raw.get("stage_audit", {}).get("emitter", {}).get("fuel", 0.0)) - 0.8) <= 1e-6,
        contract_unchanged,
        production_unchanged,
    ))

    shutdown_cpu = cpu_summary(p0_trace, "kit", shutdown_only=True)
    if shutdown_cpu["sample_count"] == 0:
        cpu_mode = "not_observed_after_shutdown_marker"
    elif (shutdown_cpu["mean_percent_of_logical_total"] or 0.0) < 1.0 and (shutdown_cpu["maximum_percent_of_logical_total"] or 0.0) < 5.0:
        cpu_mode = "mostly_waiting"
    elif (shutdown_cpu["mean_percent_of_logical_total"] or 0.0) < 2.5 and (shutdown_cpu["maximum_percent_of_logical_total"] or 0.0) < 5.0:
        cpu_mode = "low_cpu_teardown_activity"
    else:
        cpu_mode = "cpu_active"

    report = {
        "schema": "campfire.phase6ej.lightweight-shutdown-isolation.v1",
        "phase": "phase6ej",
        "status": "pass" if p0_gate else "safe_stop",
        "phase6eg_formal_restarted": False,
        "restart_recommendation": "eligible_for_new_explicitly_approved_root" if p0_gate else "blocked",
        "fixtures": fixture,
        "fixture_diagnostic": {
            "diagnostic_capture_succeeded": fixture_diagnostic.get("diagnostic_capture_succeeded"),
            "cdb_available": fixture_diagnostic.get("debugger", {}).get("cdb_path") is not None,
            "cdb_error": fixture_diagnostic.get("debugger", {}).get("error"),
            "gpu_inventory_succeeded": fixture_diagnostic.get("gpu_inventory_capture", {}).get("succeeded"),
        },
        "diagnostic_boundary_memory": memory_at_markers(fixture_trace, fixture_markers),
        "known_normal_kit": {
            "functional_status": normal_evidence.get("outcome", {}).get("functional_status"),
            "lifecycle_status": normal_evidence.get("outcome", {}).get("lifecycle_status"),
            "exit_code": normal_evidence.get("process_exit_code"),
        },
        "telemetry_off_on": {
            "runs_per_mode": 3,
            "off_mean_duration_seconds": off_duration,
            "on_mean_duration_seconds": on_duration,
            "duration_delta_seconds": telemetry_duration_delta,
            "off_runner_peak_private_bytes": off_peak,
            "on_runner_peak_private_bytes": on_peak,
            "runner_peak_delta_bytes": telemetry_memory_delta,
            "nonperturbing_gate": telemetry_nonperturbing,
            "duration_delta_limit_seconds": 1.5,
            "memory_delta_limit_bytes": 64 * MIB,
        },
        "p0_equivalent": {
            "functional_status": p0_outcome.get("functional_status"),
            "lifecycle_status": p0_outcome.get("lifecycle_status"),
            "probe_status": p0_raw.get("status"),
            "lifecycle_marker": p0_raw.get("lifecycle_marker"),
            "active_blocks_final": p0_raw.get("active_blocks_final"),
            "source_fuel": p0_raw.get("stage_audit", {}).get("emitter", {}).get("fuel"),
            "velocity_sample_count": p0_spatial.get("file_count"),
            "runner_peak_private_bytes": p0_guard["peaks"]["runner"],
            "diagnostic_peak_private_bytes": p0_guard["peaks"]["diagnostic"],
            "kit_peak_private_bytes": p0_guard["peaks"]["kit"],
            "tree_peak_private_bytes": p0_guard["peaks"]["tree"],
            "diagnostic_invoked": diagnostic_invoked,
            "diagnostic_result_exists": diagnostic_result.is_file(),
            "durable_markers": marker_names,
            "cpu": {
                "all_kit": cpu_summary(p0_trace, "kit"),
                "all_runner": cpu_summary(p0_trace, "runner"),
                "shutdown_interval": shutdown_cpu,
                "runner_shutdown_interval": cpu_summary(p0_trace, "runner", shutdown_only=True),
                "shutdown_mode": cpu_mode,
                "by_lifecycle_section": cpu_by_section(p0_trace, "kit"),
                "high_cpu_top_thread_samples": top_thread_evidence(p0_trace),
                "normalization": "100 percent equals all logical CPUs busy",
                "sample_interval_seconds": p0_guard["cpu_telemetry"]["sample_interval_seconds"],
            },
        },
        "gates": {
            "fixture_pass": fixture["status"] == "ok",
            "known_normal_exit": normal_evidence.get("outcome", {}).get("lifecycle_status") == "normal_exit",
            "telemetry_nonperturbing": telemetry_nonperturbing,
            "parent_below_512_mib": parent_bounded,
            "diagnostic_child_below_limit": diagnostic_bounded,
            "diagnostic_boundary_persisted": boundary_persisted,
            "required_markers_complete_when_invoked": marker_gate,
            "process_tree_absent": cleanup,
            "no_fatal_dump_upload_device_failure": p0_safety,
            "functional_pass": p0_outcome.get("functional_status") == "pass",
            "four_velocity_samples": int(p0_spatial.get("file_count", 0)) == 4,
            "frozen_contract_unchanged": contract_unchanged,
            "production_unchanged": production_unchanged,
        },
        "cause_classification": {
            "observed": [
                "the full lightweight diagnostic now executes in a bounded child process",
                "the parent receives only a bounded JSON file and helper exit evidence",
            ],
            "strong_inference": [],
            "unconfirmed": [],
        },
    }
    if diagnostic_invoked and p0_gate:
        report["cause_classification"]["strong_inference"].append(
            "the Phase 6EI parent growth belonged to the former in-process diagnostic host boundary rather than the isolated GPU inventory process"
        )
        report["cause_classification"]["unconfirmed"].append(
            "the exact native or PowerShell allocator retained by the former in-process path"
        )
    elif not diagnostic_invoked:
        report["cause_classification"]["unconfirmed"].append(
            "P0 exited normally, so the exact Phase 6EI residual path was not reproduced in this probe"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if p0_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
