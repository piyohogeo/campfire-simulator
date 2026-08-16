"""Bounded producer/consumer contract for the Phase 6IN monitor."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from phase6hu_atomic_report import append_durable_jsonl, atomic_write_json

MARKER_SCHEMA = "campfire.phase6in.post-shutdown-marker.v1"
OPERATION_SCHEMA = "campfire.phase6in.operation.v1"
RUNNER_SCHEMA = "campfire.phase6in.runner-evidence.v1"
SUMMARY_SCHEMA = "campfire.phase6in.summary.v1"
MAX_JSON_BYTES = 1024 * 1024
MAX_JSONL_BYTES = 1024 * 1024
SCHEDULE_SECONDS = (0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0)
NORMAL_EXIT_MAX_SECONDS = 15.0
MONITOR_TIMEOUT_SECONDS = 30.0

ORDER = (
    "runner_started", "kit_process_launched", "kit_app_ready",
    "operation_complete", "shutdown_requested", "shutdown_complete",
    "post_shutdown_monitor_started", "post_shutdown_sample",
    "process_exit_detected", "crash_reporter_detected", "post_shutdown_timeout",
    "post_shutdown_monitor_complete", "cleanup_started", "cleanup_complete",
    "final_residual_confirmed",
)
TERMINALS = {"process_exit_detected", "post_shutdown_timeout"}


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def append_marker(path: Path, *, attempt_id: str, step_id: str, actor: str,
                  pid: int, creation_ticks: int, executable_path: str,
                  elapsed: float, details: dict | None = None) -> dict:
    if step_id not in ORDER:
        raise ValueError("marker_step_unknown:" + step_id)
    if type(pid) is not int or pid <= 0 or type(creation_ticks) is not int or creation_ticks <= 0:
        raise ValueError("marker_identity_invalid")
    if not isinstance(executable_path, str) or not executable_path or not _finite(elapsed):
        raise ValueError("marker_payload_invalid")
    row = {
        "schema": MARKER_SCHEMA, "attempt_id": attempt_id, "step_id": step_id,
        "actor": actor, "pid": pid, "creation_time_filetime_ticks": creation_ticks,
        "executable_path": executable_path, "timestamp_utc_epoch": time.time(),
        "monotonic_elapsed_seconds": float(elapsed), "details": details or {},
    }
    if path.is_file() and path.stat().st_size >= MAX_JSONL_BYTES:
        raise ValueError("marker_file_oversize")
    append_durable_jsonl(path, row)
    return row


def write_json(path: Path, value: dict) -> None:
    atomic_write_json(path, value)


def read_json(path: Path, maximum: int = MAX_JSON_BYTES) -> dict:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > maximum:
        raise ValueError("bounded_json_missing_or_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("bounded_json_root_invalid")
    return value


def read_jsonl(path: Path, maximum: int = MAX_JSONL_BYTES) -> list[dict]:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > maximum:
        raise ValueError("bounded_jsonl_missing_or_size_invalid")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise TypeError("bounded_jsonl_rows_invalid")
    return rows


def validate_operation(report: dict, *, attempt_id: str, helper_contract_sha256: str) -> dict:
    reasons: list[str] = []
    if report.get("schema") != OPERATION_SCHEMA:
        reasons.append("operation_schema_invalid")
    if report.get("attempt_id") != attempt_id:
        reasons.append("operation_attempt_invalid")
    if report.get("phase6im_helper_contract_sha256") != helper_contract_sha256:
        reasons.append("helper_contract_identity_invalid")
    if report.get("operation_complete") is not True:
        reasons.append("operation_incomplete")
    if report.get("shutdown_complete") is not True:
        reasons.append("shutdown_incomplete")
    identity = report.get("process_identity")
    required = {"pid", "creation_time_filetime_ticks", "executable_path"}
    if not isinstance(identity, dict) or not required.issubset(identity):
        reasons.append("process_identity_incomplete")
    helper = report.get("phase6im_helper_evidence")
    if not isinstance(helper, dict) or helper.get("schema") != "campfire.phase6im.process-identity-report.v1" or helper.get("identity_stable") is not True:
        reasons.append("phase6im_helper_evidence_invalid")
    forbidden = report.get("forbidden_calls")
    if not isinstance(forbidden, dict) or any(type(value) is not int or value != 0 for value in forbidden.values()):
        reasons.append("forbidden_call_nonzero_or_invalid")
    return {"accepted": not reasons, "reasons": reasons}


def validate_markers(rows: list[dict], *, attempt_id: str, identity: dict,
                     require_cleanup: bool = True) -> dict:
    reasons: list[str] = []
    steps: list[str] = []
    last_index = -1
    terminal_count = 0
    for index, row in enumerate(rows):
        step = row.get("step_id")
        steps.append(step)
        if row.get("schema") != MARKER_SCHEMA or row.get("attempt_id") != attempt_id:
            reasons.append(f"marker_envelope_invalid:{index}")
        if step not in ORDER:
            reasons.append(f"marker_step_unknown:{index}")
            continue
        order_index = ORDER.index(step)
        if step == "post_shutdown_sample":
            if order_index < last_index:
                reasons.append("marker_order_invalid")
        elif step == "crash_reporter_detected":
            if order_index < ORDER.index("post_shutdown_monitor_started"):
                reasons.append("marker_order_invalid")
        elif order_index < last_index:
            reasons.append("marker_order_invalid")
        last_index = max(last_index, order_index if step not in {"crash_reporter_detected"} else last_index)
        if step in TERMINALS:
            terminal_count += 1
        if step not in {"runner_started", "cleanup_started", "cleanup_complete", "final_residual_confirmed"}:
            for key in ("pid", "creation_time_filetime_ticks", "executable_path"):
                if row.get(key) != identity.get(key):
                    reasons.append(f"marker_identity_mismatch:{index}:{key}")
        if not _finite(row.get("timestamp_utc_epoch")) or not _finite(row.get("monotonic_elapsed_seconds")):
            reasons.append(f"marker_time_invalid:{index}")
        if not isinstance(row.get("details"), dict):
            reasons.append(f"marker_details_invalid:{index}")
    for required in ("runner_started", "kit_process_launched", "kit_app_ready", "operation_complete",
                     "shutdown_requested", "shutdown_complete", "post_shutdown_monitor_started",
                     "post_shutdown_sample", "post_shutdown_monitor_complete"):
        if steps.count(required) != 1 and required != "post_shutdown_sample":
            reasons.append("marker_missing_or_duplicate:" + required)
        if required == "post_shutdown_sample" and steps.count(required) < 1:
            reasons.append("marker_missing:post_shutdown_sample")
    if terminal_count != 1:
        reasons.append("terminal_marker_count_invalid")
    if require_cleanup:
        for required in ("cleanup_started", "cleanup_complete", "final_residual_confirmed"):
            if steps.count(required) != 1:
                reasons.append("marker_missing_or_duplicate:" + required)
    return {"accepted": not reasons, "reasons": sorted(set(reasons)), "steps": steps}


def validate_sample(sample: dict, identity: dict) -> list[str]:
    reasons: list[str] = []
    required = {
        "sample_index", "scheduled_offset_seconds", "observed_offset_seconds", "pid",
        "creation_time_filetime_ticks", "executable_path", "identity_state", "alive",
        "exit_code", "cpu_total_seconds", "cpu_delta_seconds", "private_bytes",
        "working_set_bytes", "thread_count", "auxiliary_processes", "crash_reporters",
        "dump_inventory", "file_progress",
    }
    reasons.extend("sample_missing:" + key for key in sorted(required - set(sample)))
    for key in ("pid", "creation_time_filetime_ticks", "executable_path"):
        if sample.get(key) != identity.get(key):
            reasons.append("sample_identity_mismatch:" + key)
    if sample.get("identity_state") not in {"exact_alive", "exact_exited", "pid_reused", "query_failed"}:
        reasons.append("sample_identity_state_invalid")
    if not isinstance(sample.get("alive"), bool):
        reasons.append("sample_alive_invalid")
    for key in ("scheduled_offset_seconds", "observed_offset_seconds"):
        if not _finite(sample.get(key)):
            reasons.append("sample_time_invalid:" + key)
    for key in ("auxiliary_processes", "crash_reporters", "dump_inventory"):
        if not isinstance(sample.get(key), list) or len(sample.get(key, [])) > 64:
            reasons.append("sample_list_invalid:" + key)
    return reasons


def validate_runner(evidence: dict, *, attempt_id: str, identity: dict) -> dict:
    reasons: list[str] = []
    if evidence.get("schema") != RUNNER_SCHEMA or evidence.get("attempt_id") != attempt_id:
        reasons.append("runner_envelope_invalid")
    if evidence.get("large_output_buffered_in_parent") is not False:
        reasons.append("large_output_buffered")
    samples = evidence.get("samples")
    if not isinstance(samples, list) or not samples:
        reasons.append("samples_missing")
    else:
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict):
                reasons.append(f"sample_type_invalid:{index}")
            else:
                reasons.extend(f"{reason}:{index}" for reason in validate_sample(sample, identity))
    if evidence.get("monitor_complete") is not True:
        reasons.append("monitor_incomplete")
    return {"accepted": not reasons, "reasons": reasons}


def classify(*, operation_valid: bool, monitor_valid: bool, identity_reuse: bool,
             exit_observed: bool, exit_code: int | None, exit_seconds: float | None,
             post_shutdown_exception: bool, resource_pass: bool, cleanup_pass: bool,
             cleanup_assisted: bool) -> dict:
    operation = "complete" if operation_valid else "incomplete"
    monitor = "qualified" if monitor_valid and not identity_reuse else ("failed" if identity_reuse else "incomplete")
    if post_shutdown_exception:
        lifecycle = "post_shutdown_exception"
    elif exit_observed and exit_code == 0 and exit_seconds is not None:
        lifecycle = "normal_exit" if exit_seconds <= NORMAL_EXIT_MAX_SECONDS else "delayed_exit"
    elif not exit_observed:
        lifecycle = "post_shutdown_timeout"
    else:
        lifecycle = "unknown"
    cleanup = "failure" if not cleanup_pass else ("assisted_known_auxiliary" if cleanup_assisted else "natural")
    resource = "qualified" if resource_pass else "failed"
    qualified = monitor == "qualified" and operation == "complete" and cleanup_pass and resource_pass
    return {"monitor": monitor, "operation": operation, "lifecycle": lifecycle,
            "cleanup": cleanup, "resource": resource, "monitor_boundary_qualified": qualified}
