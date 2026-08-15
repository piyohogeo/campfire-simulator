"""Single producer/consumer schema for Phase 6HE velocity isolation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from phase6hd_operation_schema import COUNTER_KEYS as PHASE6HD_COUNTER_KEYS

SCHEMA = "campfire.phase6he.operation-report.v1"
COMPLETE_MARKER = "phase6he_operation_complete"
FAILURE_MARKER = "phase6he_operation_failure"
MAX_REPORT_BYTES = 256 * 1024

VELOCITY_COUNTER_KEYS = (
    "velocity_alias_metadata",
    "velocity_second_conversion",
    "velocity_file_save",
    "velocity_file_durability_check",
    "velocity_file_read",
    "velocity_vector_grid_access",
    "velocity_basic_metadata",
    "velocity_roi_sampling",
    "velocity_profile",
    "velocity_temporary_file_deletion",
)
COUNTER_KEYS = PHASE6HD_COUNTER_KEYS + VELOCITY_COUNTER_KEYS

CONDITIONS = (
    {"name": "v0_condition_c_control", "mode": "V0", "stop_after": None, "adds": "none"},
    {"name": "v1_velocity_alias_metadata", "mode": "V1", "stop_after": None, "adds": "velocity_alias_metadata"},
    {"name": "v2_velocity_second_conversion", "mode": "V2", "stop_after": "conversion", "adds": "velocity_second_conversion"},
    {"name": "v3_velocity_save_durable", "mode": "V3", "stop_after": "durability", "adds": "velocity_file_save_and_durability"},
    {"name": "v4_velocity_file_read", "mode": "V4", "stop_after": "file_read", "adds": "velocity_file_read"},
    {"name": "v5_velocity_vector_basic_metadata", "mode": "V5", "stop_after": "basic_metadata", "adds": "velocity_vector_grid_and_basic_metadata"},
    {"name": "v6_velocity_roi_sampling", "mode": "V6", "stop_after": "roi_sampling", "adds": "five_roi_samples"},
    {"name": "v7_velocity_profile", "mode": "V7", "stop_after": "profile", "adds": "scene_profile"},
)
ROW_BY_NAME = {row["name"]: row for row in CONDITIONS}


def new_counter_values() -> dict[str, int]:
    return {key: 0 for key in COUNTER_KEYS}


def new_runtime_report(*, condition: str, attempt_id: str) -> dict:
    if condition not in ROW_BY_NAME or attempt_id != condition:
        raise ValueError("condition/attempt mismatch")
    return {
        "schema": SCHEMA,
        "phase": "phase6he",
        "condition": condition,
        "attempt_identity": {"attempt_id": attempt_id, "condition": condition},
        "mode": ROW_BY_NAME[condition]["mode"],
        "status": "running",
        "operation_result": "running",
        "operation_complete": False,
        "references_released": False,
        "weak_reference_alive_after_release_count": None,
        "calls": new_counter_values(),
        "checkpoints": [],
    }


def increment_counter(report: dict, key: str, amount: int = 1) -> None:
    if key not in COUNTER_KEYS:
        raise KeyError(f"unknown canonical operation counter: {key}")
    if type(amount) is not int or amount < 0:
        raise TypeError("counter increment must be a nonnegative integer")
    current = report["calls"].get(key)
    if type(current) is not int:
        raise TypeError(f"operation counter is not an integer: {key}")
    report["calls"][key] = current + amount


def append_checkpoint(report: dict, name: str, **values) -> None:
    report["last_operation_marker"] = name
    report["checkpoints"].append({
        "name": name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **values,
    })


def complete_operation(report: dict) -> None:
    report["status"] = "pass"
    report["operation_result"] = "pass"
    report["operation_complete"] = True
    append_checkpoint(report, COMPLETE_MARKER)


def write_operation_report(path: Path, report: dict) -> None:
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        raise RuntimeError("Phase 6HE operation report exceeded 256 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


def expected_counts(condition: str) -> dict[str, int]:
    if condition not in ROW_BY_NAME:
        raise ValueError("unknown condition")
    result = new_counter_values()
    result.update({
        "readback": 1,
        "array_metadata": 7,
        "schema_volume_conversion": 5,
        "schema_metadata": 5,
        "schema_temporary_save": 5,
        "schema_typed_read": 5,
    })
    level = int(ROW_BY_NAME[condition]["mode"][1:])
    if level >= 1:
        result["velocity_alias_metadata"] = 1
    if level >= 2:
        result["velocity_second_conversion"] = 1
    if level >= 3:
        result["velocity_file_save"] = 1
        result["velocity_file_durability_check"] = 1
        result["velocity_temporary_file_deletion"] = 1
    if level >= 4:
        result["velocity_file_read"] = 1
    if level >= 5:
        result["velocity_vector_grid_access"] = 1
        result["velocity_basic_metadata"] = 1
    if level >= 6:
        result["velocity_roi_sampling"] = 5
    if level >= 7:
        result["velocity_profile"] = 1
    return result


def read_operation_report(path: Path) -> tuple[dict | None, list[str]]:
    if not path.is_file():
        return None, ["canonical_report_missing"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, ["canonical_report_invalid_json"]
    if not isinstance(value, dict):
        return None, ["canonical_report_not_object"]
    return value, []


def normalize_operation_report(report: dict) -> tuple[dict, list[str]]:
    reasons = []
    normalized = dict(report)
    calls = report.get("calls")
    if not isinstance(calls, dict):
        reasons.append("call_counts_missing")
        normalized["calls"] = {}
        return normalized, reasons
    for key in COUNTER_KEYS:
        if key not in calls:
            reasons.append(f"forbidden_call_missing:{key}")
        elif type(calls[key]) is not int:
            reasons.append(f"call_count_type_invalid:{key}")
    for key in calls:
        if key not in COUNTER_KEYS:
            reasons.append(f"call_count_unknown:{key}")
    normalized["calls"] = {key: calls[key] for key in COUNTER_KEYS if key in calls}
    return normalized, reasons


def _resource_state(path: Path) -> dict:
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


def validate_operation_files(
    report_path: Path,
    resource_marker_path: Path,
    *,
    expected_condition: str,
    expected_attempt_id: str,
    resource_pass: bool,
    cleanup_pass: bool,
) -> dict:
    raw, reasons = read_operation_report(report_path)
    resource = _resource_state(resource_marker_path)
    canonical_complete = False
    if raw is not None:
        normalized, normalization_reasons = normalize_operation_report(raw)
        reasons.extend(normalization_reasons)
        if raw.get("schema") != SCHEMA:
            reasons.append("canonical_schema_mismatch")
        if raw.get("condition") != expected_condition:
            reasons.append("canonical_condition_mismatch")
        identity = raw.get("attempt_identity")
        if not isinstance(identity, dict):
            reasons.append("attempt_identity_missing")
        else:
            if identity.get("attempt_id") != expected_attempt_id:
                reasons.append("attempt_identity_mismatch")
            if identity.get("condition") != expected_condition:
                reasons.append("attempt_condition_mismatch")
        checkpoints = raw.get("checkpoints")
        names = [row.get("name") for row in checkpoints if isinstance(row, dict)] if isinstance(checkpoints, list) else []
        canonical_complete = (
            raw.get("operation_result") == "pass"
            and raw.get("operation_complete") is True
            and raw.get("last_operation_marker") == COMPLETE_MARKER
            and COMPLETE_MARKER in names
        )
        if not canonical_complete:
            reasons.append("canonical_operation_incomplete")
        if raw.get("references_released") is not True:
            reasons.append("references_not_released")
        if raw.get("weak_reference_alive_after_release_count") != 0:
            reasons.append("weak_reference_residual_nonzero")
        calls = normalized.get("calls", {})
        expected = expected_counts(expected_condition)
        for key, wanted in expected.items():
            if key not in calls or type(calls[key]) is not int:
                continue
            actual = calls[key]
            if wanted == 0 and actual != 0:
                reasons.append(f"forbidden_call_nonzero:{key}")
            elif wanted != 0 and actual != wanted:
                reasons.append(f"call_count_value_mismatch:{key}")
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
        "counter_schema": list(COUNTER_KEYS),
        "canonical_complete": canonical_complete,
        "resource_marker_role": "telemetry_and_consistency_only",
        "resource_operation_state": resource,
    }
