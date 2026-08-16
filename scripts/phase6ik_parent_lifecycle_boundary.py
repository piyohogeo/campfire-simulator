"""Durable parent/child lifecycle boundary evidence for Phase 6IK."""
from __future__ import annotations

import ctypes
import json
import math
import os
import time
from pathlib import Path

from phase6hu_atomic_report import append_durable_jsonl, atomic_write_json

SCHEMA = "campfire.phase6ik.parent-lifecycle-marker.v1"
RUNNER_SCHEMA = "campfire.phase6ik.runner-evidence.v1"
MAX_MARKERS_BYTES = 256 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024

ORDER = (
    "outer_guard_wait_started",
    "child_wait_started",
    "kit_app_ready",
    "operation_complete",
    "shutdown_complete",
    "child_process_exit",
    "child_wait_completed",
    "runner_evidence_write_started",
    "runner_evidence_write_completed",
    "parent_return",
    "guard_result_received",
    "canonical_evaluation_started",
    "canonical_evaluation_completed",
    "outer_guard_return",
)

ACTOR = {
    "outer_guard_wait_started": "outer_guard",
    "child_wait_started": "parent_powershell",
    "kit_app_ready": "child_kit",
    "operation_complete": "child_kit",
    "shutdown_complete": "child_kit",
    "child_process_exit": "parent_powershell",
    "child_wait_completed": "parent_powershell",
    "runner_evidence_write_started": "parent_powershell",
    "runner_evidence_write_completed": "parent_powershell",
    "parent_return": "parent_powershell",
    "guard_result_received": "outer_guard",
    "canonical_evaluation_started": "outer_guard",
    "canonical_evaluation_completed": "outer_guard",
    "outer_guard_return": "outer_guard",
}


def _process_creation_time_utc_epoch() -> float:
    if os.name != "nt":
        return time.time()
    class FILETIME(ctypes.Structure):
        _fields_ = (("low", ctypes.c_uint32), ("high", ctypes.c_uint32))
    creation, exit_time, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetProcessTimes.argtypes = (ctypes.c_void_p, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME))
    handle = kernel32.GetCurrentProcess()
    ok = kernel32.GetProcessTimes(
        handle, ctypes.byref(creation), ctypes.byref(exit_time),
        ctypes.byref(kernel), ctypes.byref(user),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = (creation.high << 32) | creation.low
    return ticks / 10_000_000.0 - 11644473600.0


def produce_marker(attempt_id: str, step_id: str, *, actor: str | None = None,
                   pid: int | None = None, creation_time_utc_epoch: float | None = None,
                   monotonic_elapsed_seconds: float = 0.0, details: dict | None = None) -> dict:
    if step_id not in ORDER:
        raise ValueError("step_id_unknown:" + str(step_id))
    expected_actor = ACTOR[step_id]
    actor = expected_actor if actor is None else actor
    if actor != expected_actor:
        raise ValueError("step_actor_mismatch:" + step_id)
    if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 128:
        raise ValueError("attempt_id_invalid")
    pid = os.getpid() if pid is None else pid
    created = _process_creation_time_utc_epoch() if creation_time_utc_epoch is None else creation_time_utc_epoch
    if type(pid) is not int or pid <= 0:
        raise TypeError("pid_invalid")
    for name, value in (("creation_time_utc_epoch", created), ("monotonic_elapsed_seconds", monotonic_elapsed_seconds)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise TypeError(name + "_invalid")
    if details is not None and not isinstance(details, dict):
        raise TypeError("details_invalid")
    return {
        "schema": SCHEMA,
        "attempt_id": attempt_id,
        "marker": step_id,
        "step_id": step_id,
        "actor": actor,
        "pid": pid,
        "creation_time_utc_epoch": float(created),
        "timestamp_utc_epoch": time.time(),
        "monotonic_elapsed_seconds": float(monotonic_elapsed_seconds),
        "details": details or {},
    }


def append_marker(path: Path, attempt_id: str, step_id: str, **kwargs) -> dict:
    row = produce_marker(attempt_id, step_id, **kwargs)
    append_durable_jsonl(Path(path), row)
    return row


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > MAX_MARKERS_BYTES:
        raise ValueError("marker_file_size_invalid")
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError("marker_row_invalid")
        rows.append(value)
    return rows


def read_bounded_json(path: Path) -> dict:
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise ValueError("bounded_json_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("bounded_json_root_invalid")
    return value


def validate_markers(rows: list[dict], attempt_id: str, *, require_complete: bool = True) -> dict:
    reasons = []
    names = []
    actor_identities = {}
    last_elapsed = {}
    for index, row in enumerate(rows):
        step = row.get("step_id")
        names.append(step)
        if row.get("schema") != SCHEMA:
            reasons.append(f"marker_schema_mismatch:{index}")
        if row.get("attempt_id") != attempt_id:
            reasons.append(f"marker_attempt_mismatch:{index}")
        if step not in ORDER:
            reasons.append(f"marker_step_unknown:{index}")
            continue
        if row.get("actor") != ACTOR[step]:
            reasons.append("marker_actor_mismatch:" + step)
        pid, created = row.get("pid"), row.get("creation_time_utc_epoch")
        if type(pid) is not int or pid <= 0:
            reasons.append("marker_pid_invalid:" + step)
        if not isinstance(created, (int, float)) or isinstance(created, bool) or not math.isfinite(created):
            reasons.append("marker_creation_time_invalid:" + step)
        timestamp = row.get("timestamp_utc_epoch")
        if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool) or not math.isfinite(timestamp) or timestamp < 0:
            reasons.append("marker_timestamp_invalid:" + step)
        elapsed = row.get("monotonic_elapsed_seconds")
        if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0:
            reasons.append("marker_monotonic_invalid:" + step)
        actor = row.get("actor")
        identity = (pid, created)
        if actor in actor_identities and actor_identities[actor] != identity:
            reasons.append("actor_identity_changed:" + str(actor))
        actor_identities.setdefault(actor, identity)
        if actor in last_elapsed and isinstance(elapsed, (int, float)) and elapsed < last_elapsed[actor]:
            reasons.append("actor_monotonic_regressed:" + str(actor))
        if isinstance(elapsed, (int, float)):
            last_elapsed[actor] = elapsed
        if not isinstance(row.get("details"), dict):
            reasons.append("marker_details_invalid:" + step)
    if len(names) != len(set(names)):
        reasons.append("marker_duplicate")
    indices = [ORDER.index(name) for name in names if name in ORDER]
    if indices != sorted(indices):
        reasons.append("marker_order_invalid")
    if require_complete and names != list(ORDER):
        reasons.append("marker_missing_or_extra")
    return {"accepted": not reasons, "reasons": sorted(set(reasons)), "steps": names}


def produce_runner_evidence(*, attempt_id: str, parent_identity: dict,
                            child_identity: dict, process_exit_code,
                            shutdown_monitor: dict, status: str = "qualified") -> dict:
    return {
        "schema": RUNNER_SCHEMA,
        "attempt_id": attempt_id,
        "status": status,
        "mode": "smoke",
        "parent_identity": parent_identity,
        "child_identity": child_identity,
        "process_exit_code": process_exit_code,
        "shutdown_monitor": shutdown_monitor,
        "fatal_lines": [],
        "dump_inventory": [],
        "automatic_upload_attempt_lines": [],
        "large_output_buffered_in_parent": False,
    }


def write_runner_evidence(path: Path, evidence: dict, *, event=None) -> dict:
    return atomic_write_json(Path(path), evidence, event=event)


def validate_runner_evidence(evidence: dict, rows: list[dict], attempt_id: str) -> dict:
    reasons = []
    if evidence.get("schema") != RUNNER_SCHEMA:
        reasons.append("runner_schema_mismatch")
    if evidence.get("attempt_id") != attempt_id:
        reasons.append("runner_attempt_mismatch")
    if evidence.get("status") != "qualified":
        reasons.append("runner_status_not_qualified")
    if evidence.get("process_exit_code") != 0:
        reasons.append("child_exit_nonzero")
    parent = evidence.get("parent_identity")
    child = evidence.get("child_identity")
    if not isinstance(parent, dict) or not isinstance(child, dict):
        reasons.append("runner_identity_missing")
    else:
        for role, identity in (("parent_powershell", parent), ("child_kit", child)):
            matching = [row for row in rows if row.get("actor") == role]
            if not matching:
                reasons.append("marker_identity_missing:" + role)
            elif any((row.get("pid"), row.get("creation_time_utc_epoch")) != (identity.get("pid"), identity.get("creation_time_utc_epoch")) for row in matching):
                reasons.append("marker_runner_identity_mismatch:" + role)
    if evidence.get("large_output_buffered_in_parent") is not False:
        reasons.append("large_output_buffered")
    return {"accepted": not reasons, "reasons": reasons}


def first_incomplete_boundary(rows: list[dict]) -> dict:
    names = [row.get("step_id") for row in rows]
    last = None
    for step in ORDER:
        if step not in names:
            return {"last_completed_step": last, "first_incomplete_step": step}
        last = step
    return {"last_completed_step": last, "first_incomplete_step": None}


def classify_boundary(rows: list[dict], *, fixture_pass: bool, runtime_started: bool,
                      resource_pass: bool = True, cleanup_pass: bool = True,
                      fatal_or_dump: bool = False) -> dict:
    boundary = first_incomplete_boundary(rows)
    names = set(row.get("step_id") for row in rows)
    if not fixture_pass or not runtime_started:
        status = "safe_stop_parent_lifecycle_harness_failure"
    elif boundary["first_incomplete_step"] is None and resource_pass and cleanup_pass and not fatal_or_dump:
        status = "parent_lifecycle_evidence_boundary_qualified"
    elif boundary["first_incomplete_step"] is not None and boundary["last_completed_step"] is not None:
        status = "safe_stop_parent_lifecycle_boundary_localized"
    else:
        status = "safe_stop_parent_lifecycle_boundary_unresolved"
    cause = "complete"
    missing = boundary["first_incomplete_step"]
    if missing in {"child_process_exit", "child_wait_completed"} and "shutdown_complete" in names:
        cause = "child_did_not_naturally_exit_or_parent_wait_did_not_return"
    elif missing == "runner_evidence_write_completed":
        cause = "runner_evidence_atomic_write_failed_or_stopped"
    elif missing == "parent_return":
        cause = "parent_return_incomplete"
    elif missing == "guard_result_received":
        cause = "outer_guard_result_not_returned"
    elif missing == "canonical_evaluation_completed":
        cause = "canonical_evaluator_stopped_or_failed"
    elif missing == "outer_guard_return":
        cause = "outer_guard_return_incomplete"
    elif missing is None and (not resource_pass or not cleanup_pass or fatal_or_dump):
        cause = "resource_cleanup_or_native_gate_failed"
    return {"status": status, **boundary, "cause_boundary": cause}
