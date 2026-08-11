"""Fail-closed Kit shutdown classification, independent from Kit itself."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


INPUT_SCHEMA = "campfire.kit-shutdown-classification-input.v1"
OUTCOME_SCHEMA = "campfire.kit-shutdown-outcome.v1"
KNOWN_SIGNATURE = "ngx_telemetry_shutdown_wait_v1"
REQUIRED_COMPLETION_GATES = (
    "probe_complete",
    "results_saved",
    "timeline_stopped",
    "stage_closed",
    "renderer_drained",
    "shutdown_requested",
)
REQUIRED_SAFETY_GATES = (
    "production_app_unchanged",
    "no_fatal",
    "no_crash_dump",
    "no_windows_exception",
    "no_access_violation",
    "no_device_lost_or_tdr",
    "no_cuda_illegal_address",
    "no_upload_attempt",
)


def _failed(reason: str | list[str]) -> dict[str, Any]:
    reasons = [reason] if isinstance(reason, str) else reason
    return {
        "schema": OUTCOME_SCHEMA,
        "input_valid": not any(item.startswith("input:") for item in reasons),
        "functional_status": "fail",
        "lifecycle_status": "unknown_shutdown_failure",
        "performance_sample_accepted": False,
        "normal_exit_sample_accepted": False,
        "application_shutdown_marker": None,
        "shutdown_complete_reached": False,
        "os_process_normal_exit": False,
        "known_signature_name": None,
        "reasons": reasons,
    }


def classify(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _failed("input:not_object")
    if payload.get("schema") != INPUT_SCHEMA:
        return _failed("input:schema_mismatch")

    completion = payload.get("completion")
    safety = payload.get("safety")
    process = payload.get("process")
    if not isinstance(completion, dict):
        return _failed("input:completion_not_object")
    if not isinstance(safety, dict):
        return _failed("input:safety_not_object")
    if not isinstance(process, dict):
        return _failed("input:process_not_object")

    reasons = [
        f"completion:{name}"
        for name in REQUIRED_COMPLETION_GATES
        if completion.get(name) is not True
    ]
    reasons.extend(
        f"safety:{name}"
        for name in REQUIRED_SAFETY_GATES
        if safety.get(name) is not True
    )

    candidate = process.get("lifecycle_candidate")
    if candidate == "normal_exit":
        if process.get("exit_code") != 0:
            reasons.append("process:nonzero_exit")
        if process.get("shutdown_marker_observed") is not True:
            reasons.append("process:shutdown_marker_unobserved")
        if process.get("exited_within_shutdown_grace") is not True:
            reasons.append("process:not_within_shutdown_grace")
        if process.get("residual_process") is not False:
            reasons.append("process:unexpected_residual")
    elif candidate == "known_ngx_shutdown_residual":
        required_true = (
            ("pid_and_executable_verified", "pid_or_executable_unverified"),
            ("process_start_time_verified", "start_time_unverified"),
            ("shutdown_marker_observed", "shutdown_marker_unobserved"),
            ("diagnostic_capture_succeeded", "diagnostic_incomplete"),
            ("known_signature_matched", "known_signature_unmatched"),
            ("terminated_by_outer_runner", "not_terminated_by_outer_runner"),
            ("pid_absent_after_termination", "pid_remained_after_termination"),
            ("residual_process", "residual_not_observed"),
        )
        for field, reason in required_true:
            if process.get(field) is not True:
                reasons.append(f"process:{reason}")
        if process.get("known_signature_name") != KNOWN_SIGNATURE:
            reasons.append("process:signature_name_mismatch")
        if process.get("windows_exception_present") is not False:
            reasons.append("process:windows_exception_present_or_unknown")
        if process.get("fault_module") not in (None, ""):
            reasons.append("process:fault_module_present")
        if process.get("fault_offset") not in (None, ""):
            reasons.append("process:fault_offset_present")
        if process.get("dump_count") != 0:
            reasons.append("process:dump_present")
    else:
        reasons.append("process:unknown_shutdown_failure")

    if reasons:
        return _failed(reasons)

    if candidate == "known_ngx_shutdown_residual":
        return {
            "schema": OUTCOME_SCHEMA,
            "input_valid": True,
            "functional_status": "pass",
            "lifecycle_status": "known_ngx_shutdown_residual",
            "performance_sample_accepted": False,
            "normal_exit_sample_accepted": False,
            "application_shutdown_marker": process.get("last_lifecycle_marker"),
            "shutdown_complete_reached": process.get("last_lifecycle_marker") == "shutdown_complete",
            "os_process_normal_exit": False,
            "known_signature_name": KNOWN_SIGNATURE,
            "reasons": [],
        }

    return {
        "schema": OUTCOME_SCHEMA,
        "input_valid": True,
        "functional_status": "pass",
        "lifecycle_status": "normal_exit",
        "performance_sample_accepted": True,
        "normal_exit_sample_accepted": True,
        "application_shutdown_marker": process.get("last_lifecycle_marker"),
        "shutdown_complete_reached": process.get("last_lifecycle_marker") == "shutdown_complete",
        "os_process_normal_exit": True,
        "known_signature_name": None,
        "reasons": [],
    }


def _load_payload(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"_input_error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = _load_payload(args.input)
    if isinstance(payload, dict) and "_input_error" in payload:
        result = _failed("input:unreadable_or_invalid_json")
    else:
        result = classify(payload)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
