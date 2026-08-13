"""Aggregate Phase 6FJ balanced single-readback attempts with bounded replacements."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

try:
    from scripts.analyze_phase6fg_paired_readback import LABELS, _case
    from scripts.analyze_phase6fh_lifecycle_qualification import jsonl, load, marker_map
except ModuleNotFoundError:
    from analyze_phase6fg_paired_readback import LABELS, _case
    from analyze_phase6fh_lifecycle_qualification import jsonl, load, marker_map


def _common(attempt_root: Path, metadata: dict, overlay: dict, base: dict) -> dict:
    condition = metadata["condition"]
    label = overlay["conditions"][condition]["label"]
    case_dir = attempt_root / label
    raw = load(case_dir / "raw.json") or {}
    evidence = load(case_dir / "runner_evidence.json") or {}
    guard = load(attempt_root / "runner-logs" / f"{label}.guard.json") or {}
    markers = marker_map(jsonl(case_dir / "resource_markers.jsonl"))
    extension = marker_map(jsonl(case_dir / "extension_lifecycle_markers.jsonl"))
    startup = raw.get("startup_liveness_gate") or {}
    payload = (raw.get("point_payload") or {}).get("payload_sha256")
    expected_payload = base["expected_stage"]["payload_sha256"]
    monitor = evidence.get("shutdown_monitor") or {}
    cleanup = guard.get("observed_process_cleanup") or {}

    representative = bool(
        startup.get("classification") == "representative_ingestion"
        and startup.get("source_ok") is True
        and startup.get("telemetry_fresh") is True
        and (startup.get("identity_and_exact_source") or {}).get("pass") is True
        and payload == expected_payload
    )

    absolute = []
    if guard.get("stop_reason"):
        absolute.append(f"resource_guard:{guard.get('stop_reason')}")
    if evidence.get("fatal_lines"):
        absolute.append("fatal")
    if evidence.get("dump_inventory"):
        absolute.append("dump")
    if evidence.get("automatic_upload_attempt_lines"):
        absolute.append("automatic_upload")
    if monitor.get("windows_exception_present") is True:
        absolute.append("windows_exception")
    if cleanup.get("remaining") or cleanup.get("all_observed_absent") is not True:
        absolute.append("cleanup_failure")

    completion = raw.get("completion_contract") or {}
    stage_started = "stage_close_request_before" in markers
    stage_complete = "stage_close_request_after" in markers and completion.get("stage_closed") is True
    extension_complete = "extension_on_shutdown_begin" in extension and "extension_on_shutdown_end" in extension
    native = []
    if stage_started and ("stage_close_timeout" in markers or not stage_complete):
        native.append("stage_close_failure")
    if stage_complete and not extension_complete:
        native.append("extension_shutdown_incomplete")
    if monitor.get("residual_process") is True:
        native.append("shutdown_residual")
    if representative and (monitor.get("lifecycle_candidate") != "normal_exit" or monitor.get("exit_code") != 0):
        native.append("representative_normal_os_exit_missing")
    if not representative and stage_complete and extension_complete:
        bounded_prerequisite_exit = bool(
            monitor.get("lifecycle_candidate") == "normal_exit"
            and monitor.get("exit_code") == 1
            and monitor.get("pid_absent_after_termination") is True
            and monitor.get("terminated_by_outer_runner") is not True
        )
        if not bounded_prerequisite_exit:
            native.append("prerequisite_process_exit_unbounded")

    operation_markers = {
        "readback_acquire_started", "readback_acquire_complete",
        "fuel_numpy_conversion_started", "fuel_numpy_conversion_complete",
        "measurement_complete",
    }
    operation_started = any(name in markers for name in operation_markers)
    prerequisite = []
    if not representative:
        prerequisite.append(str(startup.get("classification") or "startup_evidence_missing"))
    if payload != expected_payload:
        prerequisite.append("payload_hash")
    if operation_started and not representative:
        prerequisite.append("operation_started_before_prerequisite_stop")

    operation_case = None
    operation = []
    if representative and not absolute and not native:
        try:
            operation_case = _case(attempt_root, condition, base)
            if not operation_case.get("condition_gate_pass"):
                operation.extend(operation_case.get("condition_gate_failures") or ["condition_gate_failed"])
        except Exception as exc:  # fail closed and preserve the analyzer boundary
            operation.append(f"operation_analyzer:{type(exc).__name__}:{exc}")

    if absolute:
        classification = "absolute_safety_failure"
    elif native:
        classification = "native_lifecycle_failure"
    elif prerequisite:
        classification = "startup_prerequisite_failure" if not operation_started else "operation_failure"
    elif operation:
        classification = "operation_failure"
    else:
        classification = "representative_pass"

    return {
        "attempt_id": metadata["attempt_id"],
        "attempt_sequence": metadata["attempt_sequence"],
        "slot_id": metadata["slot_id"],
        "sequence": metadata["sequence"],
        "position": metadata["position"],
        "condition": condition,
        "classification": classification,
        "representative_startup": representative,
        "operation_started": operation_started,
        "startup_prerequisite_failures": prerequisite,
        "operation_failures": operation,
        "native_lifecycle_failures": native,
        "absolute_safety_failures": absolute,
        "startup": {
            "classification": startup.get("classification"),
            "sample_count": startup.get("sample_count"),
            "minimum_active_blocks": startup.get("minimum_active_blocks"),
            "maximum_active_blocks": startup.get("maximum_active_blocks"),
            "first_representative_frame": startup.get("first_representative_frame"),
            "telemetry_fresh": startup.get("telemetry_fresh"),
            "source_ok": startup.get("source_ok"),
            "identity_and_exact_source": startup.get("identity_and_exact_source"),
        },
        "stage_close_seconds": operation_case.get("stage_close_seconds") if operation_case else raw.get("stage_close_seconds"),
        "guard": {
            "status": guard.get("status"),
            "exit_code": guard.get("exit_code"),
            "process_absent": guard.get("process_absent"),
            "peaks": guard.get("peaks"),
            "machine_minima": guard.get("machine_minima"),
        },
        "operation_evidence": operation_case,
    }


def _finite(items):
    return [float(value) for value in items if isinstance(value, (int, float))]


def _distribution(items):
    values = _finite(items)
    return {
        "values": values,
        "minimum": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "mean": statistics.mean(values) if values else None,
        "maximum": max(values) if values else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--base-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    overlay = json.loads(args.contract.read_text(encoding="utf-8"))
    base = json.loads(args.base_contract.read_text(encoding="utf-8"))
    attempts = []
    for path in sorted(args.root.glob("attempt[0-9][0-9]")):
        metadata = load(path / "attempt_metadata.json")
        if metadata:
            attempts.append(_common(path, metadata, overlay, base))

    representative = [item for item in attempts if item["classification"] == "representative_pass"]
    by_condition = {name: [item for item in representative if item["condition"] == name] for name in LABELS}
    operation_cases = [item["operation_evidence"] for item in representative if item["operation_evidence"]]
    b_cases = [item["operation_evidence"] for item in by_condition["B_readback"] if item["operation_evidence"]]
    c_cases = [item["operation_evidence"] for item in by_condition["C_fuel_alias"] if item["operation_evidence"]]
    allocation = [((case.get("boundary") or {}).get("observable_copy_contract") or {}).get("allocation_classification") for case in c_cases]
    weak = [(case.get("boundary") or {}).get("weak_reference_alive_after_scope_count") for case in c_cases]
    c_consistent = len(c_cases) == 3 and len(set(allocation)) == 1 and allocation[0] == "same_object_zero_copy_alias" and weak == [0, 0, 0]
    counts = {name: len(items) for name, items in by_condition.items()}
    nonreplaceable = [item for item in attempts if item["classification"] in {"operation_failure", "native_lifecycle_failure", "absolute_safety_failure"}]
    prereq = [item for item in attempts if item["classification"] == "startup_prerequisite_failure"]
    qualified = len(representative) == 9 and all(value == 3 for value in counts.values()) and not nonreplaceable and c_consistent

    readback_increments = [case.get("memory_deltas_bytes", {}).get("readback_immediate") for case in b_cases + c_cases]
    next_residuals = [case.get("memory_deltas_bytes", {}).get("next_frame_residual") for case in b_cases + c_cases]
    settled_residuals = [case.get("memory_deltas_bytes", {}).get("observation_end_residual") for case in b_cases + c_cases]
    stage_closes = [item.get("stage_close_seconds") for item in representative]
    kit_peaks = [((item.get("guard") or {}).get("peaks") or {}).get("kit") for item in attempts]
    tree_peaks = [((item.get("guard") or {}).get("peaks") or {}).get("tree") for item in attempts]
    margins = [case.get("minimum_kit_ceiling_margin_bytes") for case in operation_cases]
    warnings = [case.get("waveform_telemetry", {}).get("warning_count", 0) for case in operation_cases]
    report = {
        "schema": "campfire.phase6fj.balanced-single-readback-report.v1",
        "phase": "phase6fj",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "base_operation_contract_sha256": hashlib.sha256(args.base_contract.read_bytes()).hexdigest().upper(),
        "history_frozen": overlay["history_frozen"],
        "total_launches": len(attempts),
        "representative_processes": len(representative),
        "startup_prerequisite_failures": len(prereq),
        "replacement_budget_used": len(prereq),
        "condition_counts": counts,
        "attempts": attempts,
        "nonreplaceable_failures": nonreplaceable,
        "operation_summary": {
            "readback_immediate_bytes": _distribution(readback_increments),
            "next_frame_residual_bytes": _distribution(next_residuals),
            "settling_end_residual_bytes": _distribution(settled_residuals),
            "c_allocation_classifications": allocation,
            "c_weak_reference_residuals": weak,
            "c_alias_contract_consistent": c_consistent,
            "fuel_logical_bytes": _distribution([(case.get("boundary") or {}).get("fuel_array", {}).get("nbytes") for case in c_cases]),
            "numpy_asarray_immediate_bytes": _distribution([case.get("memory_deltas_bytes", {}).get("fuel_conversion_immediate") for case in c_cases]),
        },
        "lifecycle_summary": {"stage_close_seconds": _distribution(stage_closes)},
        "resource_summary": {
            "kit_peak_bytes": max(_finite(kit_peaks), default=None),
            "tree_peak_bytes": max(_finite(tree_peaks), default=None),
            "minimum_kit_ceiling_margin_bytes": min(_finite(margins), default=None),
        },
        "waveform_telemetry": {"formal_gate": False, "warning_counts": warnings, "total_warnings": sum(warnings)},
        "qualified": qualified,
        "one_readback_qualified": qualified,
        "one_fuel_alias_lifetime_qualified": qualified,
        "repeated_readback_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
