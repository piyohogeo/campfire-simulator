"""Canonical bounded-operation evidence normalization for Phase 6HC."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "campfire.phase6hc.operation-report.v1"
COMPLETE_MARKER = "phase6hc_operation_complete"
FAILURE_MARKER = "phase6hc_operation_failure"
FORBIDDEN_CALLS = (
    "temperature_buffer_to_volume",
    "temperature_metadata",
    "temperature_save",
    "temperature_typed_read",
    "temperature_sampling",
    "temperature_collector",
)


def _read_report(path: Path) -> tuple[dict | None, list[str]]:
    if not path.is_file():
        return None, ["canonical_report_missing"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, ["canonical_report_invalid_json"]
    if not isinstance(value, dict):
        return None, ["canonical_report_not_object"]
    return value, []


def _resource_operation_state(path: Path) -> dict:
    if not path.is_file():
        return {"present": False, "complete": False, "failure": False, "invalid_lines": 0}
    complete = failure = False
    invalid = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        marker = row.get("marker") if isinstance(row, dict) else None
        complete = complete or marker == COMPLETE_MARKER
        failure = failure or marker == FAILURE_MARKER
    return {"present": True, "complete": complete, "failure": failure, "invalid_lines": invalid}


def evaluate_operation_files(
    report_path: Path,
    resource_marker_path: Path,
    *,
    expected_condition: str,
    expected_attempt_id: str,
    resource_pass: bool,
    cleanup_pass: bool,
) -> dict:
    report, reasons = _read_report(report_path)
    resource = _resource_operation_state(resource_marker_path)
    if report is not None:
        if report.get("schema") != SCHEMA:
            reasons.append("canonical_schema_mismatch")
        if report.get("condition") != expected_condition:
            reasons.append("canonical_condition_mismatch")
        identity = report.get("attempt_identity")
        if not isinstance(identity, dict):
            reasons.append("attempt_identity_missing")
        else:
            if identity.get("attempt_id") != expected_attempt_id:
                reasons.append("attempt_identity_mismatch")
            if identity.get("condition") != expected_condition:
                reasons.append("attempt_condition_mismatch")
        checkpoints = report.get("checkpoints")
        checkpoint_names = [row.get("name") for row in checkpoints if isinstance(row, dict)] \
            if isinstance(checkpoints, list) else []
        canonical_complete = (
            report.get("operation_result") == "pass"
            and report.get("operation_complete") is True
            and report.get("last_operation_marker") == COMPLETE_MARKER
            and COMPLETE_MARKER in checkpoint_names
        )
        if not canonical_complete:
            reasons.append("canonical_operation_incomplete")
        if report.get("references_released") is not True:
            reasons.append("references_not_released")
        if report.get("weak_reference_alive_after_release_count") != 0:
            reasons.append("weak_reference_residual_nonzero")
        calls = report.get("calls")
        if not isinstance(calls, dict):
            reasons.append("call_counts_missing")
        else:
            for name in FORBIDDEN_CALLS:
                if calls.get(name) != 0:
                    reasons.append(f"forbidden_call_nonzero:{name}")
    else:
        canonical_complete = False

    if resource["complete"] and resource["failure"]:
        reasons.append("resource_operation_markers_conflict")
    elif resource["failure"] and canonical_complete:
        reasons.append("canonical_resource_operation_conflict")
    elif resource["complete"] and not canonical_complete:
        reasons.append("resource_complete_without_canonical_complete")
    if not resource_pass:
        reasons.append("resource_gate_failed")
    if not cleanup_pass:
        reasons.append("cleanup_gate_failed")
    return {
        "pass": not reasons,
        "reasons": reasons,
        "canonical_source": str(report_path),
        "canonical_schema": SCHEMA,
        "canonical_complete": canonical_complete,
        "resource_marker_role": "telemetry_and_consistency_only",
        "resource_operation_state": resource,
    }
