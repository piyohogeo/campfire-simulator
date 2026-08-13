"""Analyze Phase 6FI bounded startup-replacement lifecycle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.analyze_phase6fh_lifecycle_qualification import case_for as phase6fh_case_for
    from scripts.analyze_phase6fh_lifecycle_qualification import jsonl, load, marker_map
except ModuleNotFoundError:
    from analyze_phase6fh_lifecycle_qualification import case_for as phase6fh_case_for
    from analyze_phase6fh_lifecycle_qualification import jsonl, load, marker_map


def scan_log(path: Path) -> dict:
    counts = {
        "shader_cache_lines": 0,
        "shader_compile_lines": 0,
        "device_lost_lines": 0,
        "tdr_lines": 0,
        "access_violation_lines": 0,
    }
    environment = []
    warnings = []
    if not path.is_file():
        return {"available": False, "counts": counts, "environment_lines": environment, "warning_error_count": 0}
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            lower = line.lower()
            if "shadercache" in lower or "shader cache" in lower:
                counts["shader_cache_lines"] += 1
            if "shader" in lower and ("compil" in lower or "ujitso" in lower):
                counts["shader_compile_lines"] += 1
            if "device lost" in lower or "device_removed" in lower:
                counts["device_lost_lines"] += 1
            if "tdr" in lower:
                counts["tdr_lines"] += 1
            if "access violation" in lower or "0xc0000005" in lower:
                counts["access_violation_lines"] += 1
            if len(environment) < 16 and (
                "driver version:" in lower
                or "nvidia geforce rtx" in lower
                or "kit sdk version" in lower
                or "omni.flowusd-" in lower
            ):
                environment.append({"line": line_number, "text": line.strip()[:512]})
            if len(warnings) < 32 and ("[warning]" in lower or "[error]" in lower):
                warnings.append({"line": line_number, "text": line.strip()[:512]})
    return {
        "available": True,
        "counts": counts,
        "environment_lines": environment,
        "warning_error_count": len(warnings),
        "first_warning_error_lines": warnings,
    }


def classify_attempt(root: Path, attempt: int, contract: dict) -> dict | None:
    base = phase6fh_case_for(root, attempt, {
        "startup": contract["startup"],
    })
    if base is None:
        return None

    label = f"run{attempt:02d}"
    run = root / label
    raw = load(run / "raw.json") or {}
    evidence = load(run / "runner_evidence.json") or {}
    guard = load(root / "runner-logs" / f"{label}.guard.json") or {}
    marker_rows = jsonl(run / "resource_markers.jsonl")
    markers = marker_map(marker_rows)
    extension_markers = marker_map(jsonl(run / "extension_lifecycle_markers.jsonl"))
    runner_marker_rows = jsonl(run / "runner_lifecycle_markers.jsonl")
    startup = raw.get("startup_liveness_gate") or {}
    source = raw.get("startup_live_point_emitter_contract") or {}
    completion = raw.get("completion_contract") or {}
    monitor = evidence.get("shutdown_monitor") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    log_evidence = scan_log(run / "kit.log")

    expected_payload = contract["startup"]["expected_payload_sha256"]
    payload = (raw.get("point_payload") or {}).get("payload_sha256")
    representative = bool(
        startup.get("classification") == "representative_ingestion"
        and startup.get("source_ok") is True
        and startup.get("telemetry_fresh") is True
        and (startup.get("identity_and_exact_source") or {}).get("pass") is True
        and payload == expected_payload
    )

    absolute_failures = []
    if guard.get("stop_reason"):
        absolute_failures.append(f"resource_guard:{guard.get('stop_reason')}")
    if evidence.get("fatal_lines"):
        absolute_failures.append("fatal")
    if evidence.get("dump_inventory"):
        absolute_failures.append("dump")
    if evidence.get("automatic_upload_attempt_lines"):
        absolute_failures.append("automatic_upload")
    if monitor.get("windows_exception_present") is True:
        absolute_failures.append("windows_exception")
    if any(log_evidence["counts"][name] for name in ("device_lost_lines", "tdr_lines", "access_violation_lines")):
        absolute_failures.append("native_safety_log_evidence")
    if cleanup.get("remaining") or cleanup.get("all_observed_absent") is not True:
        absolute_failures.append("cleanup_failure")

    stage_close_started = "stage_close_request_before" in markers
    stage_close_completed = "stage_close_request_after" in markers and completion.get("stage_closed") is True
    extension_complete = "extension_on_shutdown_begin" in extension_markers and "extension_on_shutdown_end" in extension_markers
    native_failures = []
    if stage_close_started and ("stage_close_timeout" in markers or not stage_close_completed):
        native_failures.append("stage_close_failure")
    if stage_close_completed and not extension_complete:
        native_failures.append("extension_shutdown_incomplete")
    if monitor.get("residual_process") is True:
        native_failures.append("shutdown_residual")
    if representative and not base.get("normal_os_exit"):
        native_failures.append("representative_normal_os_exit_missing")
    if not representative and stage_close_completed and extension_complete:
        prereq_exit_is_bounded = bool(
            monitor.get("lifecycle_candidate") == "normal_exit"
            and monitor.get("exit_code") == 1
            and monitor.get("pid_absent_after_termination") is True
            and monitor.get("terminated_by_outer_runner") is not True
        )
        if not prereq_exit_is_bounded:
            native_failures.append("prerequisite_process_exit_unbounded")

    required_markers = contract["operation"]["required_markers_for_representative_launch"]
    missing_operation_markers = [name for name in required_markers if name not in markers]
    forbidden_operation_markers = [
        name for name in markers
        if name in {
            "readback_acquire_started",
            "readback_acquire_complete",
            "fuel_numpy_conversion_started",
            "fuel_numpy_conversion_complete",
            "field_persistence_started",
            "field_persistence_complete",
        }
    ]
    operation_failures = []
    if representative and missing_operation_markers:
        operation_failures.append("missing_operation_markers")
    if forbidden_operation_markers:
        operation_failures.append("forbidden_operation_call")

    prerequisite_failures = []
    if not representative:
        prerequisite_failures.append(str(startup.get("classification") or "startup_evidence_missing"))
    if payload != expected_payload:
        prerequisite_failures.append("payload_hash")

    if absolute_failures:
        classification = "absolute_safety_failure"
    elif native_failures:
        classification = "native_lifecycle_failure"
    elif prerequisite_failures:
        classification = "startup_prerequisite_failure"
    elif operation_failures:
        classification = "operation_failure"
    else:
        classification = "representative_startup"

    startup_history = [
        {
            "frame": int(row.get("frame", -1)),
            "perf_counter_ns": row.get("perf_counter_ns"),
            "kit_update_number": row.get("kit_update_number"),
            "timeline_time": row.get("timeline_time"),
            "timeline_playing": row.get("timeline_playing"),
            "active_blocks": row.get("active_blocks"),
            "stage_identity": row.get("stage_identity"),
            "flow_identity": row.get("flow_identity"),
        }
        for row in raw.get("flow_liveness_history") or []
        if int(row.get("frame", -1)) <= int(contract["startup"]["final_frame"])
    ]
    first_marker = lambda name: markers.get(name, {}).get("timestamp_utc")
    return {
        **base,
        "attempt_id": f"attempt{attempt:02d}",
        "attempt_sequence": attempt,
        "classification": classification,
        "representative_startup": representative,
        "startup_prerequisite_failures": prerequisite_failures,
        "operation_failures": operation_failures,
        "native_lifecycle_failures": native_failures,
        "absolute_safety_failures": absolute_failures,
        "missing_operation_markers": missing_operation_markers,
        "forbidden_operation_markers": forbidden_operation_markers,
        "startup": {
            "classification": startup.get("classification"),
            "gate_frame": startup.get("gate_frame"),
            "sample_count": startup.get("sample_count"),
            "minimum_active_blocks": startup.get("minimum_active_blocks"),
            "maximum_active_blocks": startup.get("maximum_active_blocks"),
            "first_representative_frame": startup.get("first_representative_frame"),
            "telemetry_fresh": startup.get("telemetry_fresh"),
            "source_ok": startup.get("source_ok"),
            "identity_and_exact_source": startup.get("identity_and_exact_source"),
            "history": startup_history,
        },
        "source_contract": {
            "enabled": source.get("enabled"),
            "revision": source.get("revision"),
            "total_point_count": source.get("total_point_count"),
            "active_point_count": source.get("active_point_count"),
            "source_sums": source.get("source_sums"),
            "emitter_path": source.get("emitter_path"),
            "emitter_python_identity": source.get("emitter_python_identity"),
            "stage_python_identity": source.get("stage_python_identity"),
            "payload_sha256": payload,
        },
        "startup_timing": {
            "emitter_connection_complete_utc": first_marker("startup_live_point_emitter_contract_complete"),
            "flow_interface_acquire_complete_utc": first_marker("flow_interface_acquire_complete"),
            "renderer_readiness_complete_utc": first_marker("renderer_readiness_complete"),
            "pre_timeline_updates_complete_utc": first_marker("pre_timeline_updates_complete"),
            "timeline_playing_utc": first_marker("timeline_playing"),
            "previous_process_exit_utc": evidence.get("previous_process_exit_utc"),
            "previous_exit_to_start_seconds": evidence.get("previous_process_exit_to_process_start_seconds"),
        },
        "log_evidence": log_evidence,
        "stage_close_started": stage_close_started,
        "stage_close_completed": stage_close_completed,
        "extension_shutdown_complete": extension_complete,
        "cleanup_before_after": cleanup,
        "last_runner_marker": runner_marker_rows[-1].get("marker") if runner_marker_rows else None,
    }


def report_for(root: Path, contract: dict, contract_hash: str) -> dict:
    maximum = int(contract["population"]["maximum_launches"])
    attempts = [item for index in range(1, maximum + 1) if (item := classify_attempt(root, index, contract))]
    counts = {name: 0 for name in contract["launch_classifications"]}
    for attempt in attempts:
        counts[attempt["classification"]] += 1
    representative = counts["representative_startup"]
    prerequisite = counts["startup_prerequisite_failure"]
    target = int(contract["population"]["target_representative_processes"])
    budget = int(contract["population"]["startup_prerequisite_replacement_budget"])
    if counts["absolute_safety_failure"]:
        status = "absolute_safety_stop"
    elif counts["native_lifecycle_failure"]:
        status = "native_lifecycle_safe_stop"
    elif counts["operation_failure"]:
        status = "operation_safe_stop"
    elif representative >= target:
        status = "lifecycle_qualification_pass"
    elif prerequisite > budget or len(attempts) >= maximum:
        status = "prerequisite_population_incomplete"
    else:
        status = "incomplete"
    representative_closes = [item["stage_close_seconds"] for item in attempts if item["classification"] == "representative_startup" and item.get("stage_close_seconds") is not None]
    return {
        "schema": "campfire.phase6fi.lifecycle-replacement-report.v1",
        "phase": "phase6fi",
        "contract_sha256": contract_hash,
        "phase6fg_history_frozen": True,
        "phase6fh_history_frozen": True,
        "status": status,
        "target_representative_processes": target,
        "replacement_budget": budget,
        "maximum_launches": maximum,
        "total_launches": len(attempts),
        "representative_startup_count": representative,
        "startup_prerequisite_failure_count": prerequisite,
        "replacement_budget_used": min(prerequisite, budget),
        "startup_prerequisite_failure_rate": None if not attempts else prerequisite / len(attempts),
        "classification_counts": counts,
        "representative_stage_close_seconds": representative_closes,
        "attempts": attempts,
        "readback_calls": 0,
        "numpy_asarray_calls": 0,
        "field_persistence_calls": 0,
        "phase6fg_restart_candidate": status == "lifecycle_qualification_pass",
        "phase6fg_restart_authorized": False,
        "production_changed": any((load(root / f"run{i:02d}" / "runner_evidence.json") or {}).get("production_changed") is True for i in range(1, len(attempts) + 1)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load(args.contract)
    contract_hash = hashlib.sha256(args.contract.read_bytes()).hexdigest().upper()
    report = report_for(args.root, contract, contract_hash)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
