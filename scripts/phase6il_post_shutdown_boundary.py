"""Bounded evidence and classification for the Phase 6IL post-shutdown boundary."""
from __future__ import annotations

import json
import math
import os
import time
import hashlib
from pathlib import Path

from phase6hu_atomic_report import append_durable_jsonl, atomic_write_json

MARKER_SCHEMA = "campfire.phase6il.post-shutdown-marker.v1"
REPORT_SCHEMA = "campfire.phase6il.post-shutdown-report.v1"
SUMMARY_SCHEMA = "campfire.phase6il.summary.v1"
MAX_JSON_BYTES = 1024 * 1024
MAX_JSONL_BYTES = 1024 * 1024
STILL_ACTIVE = 259
ACCESS_VIOLATION = 0xC0000005

REQUIRED_PREFIX = (
    "process_started",
    "kit_app_ready",
    "operation_complete",
    "shutdown_complete",
    "post_shutdown_monitor_started",
)
TERMINAL_MARKERS = (
    "child_process_exit",
    "post_shutdown_boundary_reached",
)
CLASSIFICATIONS = {
    "qualified": "post_shutdown_child_exit_qualified",
    "native_wait": "safe_stop_post_shutdown_native_wait_localized",
    "crash_reporter": "safe_stop_post_shutdown_crash_reporter_boundary",
    "stale": "safe_stop_stale_process_object_proven",
    "unresolved": "safe_stop_post_shutdown_exit_unresolved",
    "harness": "safe_stop_post_shutdown_harness_failure",
}


def process_creation_time_utc_epoch() -> float:
    if os.name != "nt":
        return time.time()
    class FILETIME(__import__("ctypes").Structure):
        _fields_ = (("low", __import__("ctypes").c_uint32), ("high", __import__("ctypes").c_uint32))
    ctypes = __import__("ctypes")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    values = [FILETIME() for _ in range(4)]
    if not kernel32.GetProcessTimes(kernel32.GetCurrentProcess(), *(ctypes.byref(value) for value in values)):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = (values[0].high << 32) | values[0].low
    return ticks / 10_000_000.0 - 11644473600.0


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def read_bounded_json(path: Path, maximum: int = MAX_JSON_BYTES) -> dict:
    if not path.is_file():
        raise ValueError("bounded_json_missing")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise ValueError("bounded_json_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("bounded_json_root_invalid")
    return value


def read_bounded_jsonl(path: Path, maximum: int = MAX_JSONL_BYTES) -> list[dict]:
    if not path.is_file():
        raise ValueError("bounded_jsonl_missing")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise ValueError("bounded_jsonl_size_invalid")
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError("bounded_jsonl_row_invalid")
        rows.append(value)
    return rows


def append_marker(path: Path, *, attempt_id: str, step_id: str, actor: str,
                  pid: int, creation_time_utc_epoch: float,
                  monotonic_elapsed_seconds: float, details: dict | None = None) -> dict:
    row = {
        "schema": MARKER_SCHEMA,
        "attempt_id": attempt_id,
        "step_id": step_id,
        "marker": step_id,
        "actor": actor,
        "pid": int(pid),
        "creation_time_utc_epoch": float(creation_time_utc_epoch),
        "timestamp_utc_epoch": time.time(),
        "monotonic_elapsed_seconds": float(monotonic_elapsed_seconds),
        "details": details or {},
    }
    if path.is_file() and path.stat().st_size >= MAX_JSONL_BYTES:
        raise ValueError("bounded_jsonl_oversize")
    append_durable_jsonl(path, row)
    return row


def validate_marker_rows(rows: list[dict], attempt_id: str) -> dict:
    reasons: list[str] = []
    steps: list[str] = []
    last_elapsed = -1.0
    for index, row in enumerate(rows):
        if row.get("schema") != MARKER_SCHEMA:
            reasons.append(f"marker_schema_invalid:{index}")
        if row.get("attempt_id") != attempt_id:
            reasons.append(f"marker_attempt_invalid:{index}")
        step = row.get("step_id")
        if not isinstance(step, str) or not step:
            reasons.append(f"marker_step_invalid:{index}")
        else:
            steps.append(step)
        if not isinstance(row.get("pid"), int) or isinstance(row.get("pid"), bool):
            reasons.append(f"marker_pid_invalid:{index}")
        for key in ("creation_time_utc_epoch", "timestamp_utc_epoch", "monotonic_elapsed_seconds"):
            if not _finite_number(row.get(key)):
                reasons.append(f"marker_number_invalid:{index}:{key}")
        elapsed = row.get("monotonic_elapsed_seconds")
        if _finite_number(elapsed):
            if float(elapsed) < last_elapsed:
                reasons.append(f"marker_elapsed_regression:{index}")
            last_elapsed = float(elapsed)
    cursor = -1
    for required in REQUIRED_PREFIX:
        try:
            found = steps.index(required, cursor + 1)
        except ValueError:
            reasons.append("marker_missing:" + required)
            continue
        if steps.count(required) != 1:
            reasons.append("marker_duplicate:" + required)
        cursor = found
    for terminal in TERMINAL_MARKERS:
        if steps.count(terminal) > 1:
            reasons.append("marker_duplicate:" + terminal)
    if not any(step in steps for step in TERMINAL_MARKERS):
        reasons.append("terminal_marker_missing")
    return {"accepted": not reasons, "reasons": reasons, "steps": steps}


def validate_sample(sample: dict) -> list[str]:
    reasons: list[str] = []
    required = {
        "sample_offset_seconds", "process_object_has_exited", "native_wait_state",
        "native_exit_code", "os_identity_state", "same_exact_kit_alive",
        "private_bytes", "working_set_bytes", "thread_count", "handle_count",
        "tree", "dump_state", "kit_log",
    }
    missing = sorted(required - set(sample))
    reasons.extend("sample_missing:" + key for key in missing)
    if not _finite_number(sample.get("sample_offset_seconds")):
        reasons.append("sample_offset_invalid")
    for key in ("process_object_has_exited", "same_exact_kit_alive"):
        if not isinstance(sample.get(key), bool):
            reasons.append("sample_bool_invalid:" + key)
    if sample.get("native_wait_state") not in {"signaled", "timeout", "failed"}:
        reasons.append("native_wait_state_invalid")
    exit_code = sample.get("native_exit_code")
    if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
        reasons.append("native_exit_code_invalid")
    for key in ("private_bytes", "working_set_bytes", "thread_count", "handle_count"):
        value = sample.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            reasons.append("sample_count_invalid:" + key)
    for key in ("tree", "dump_state", "kit_log"):
        if not isinstance(sample.get(key), dict):
            reasons.append("sample_object_invalid:" + key)
    return reasons


def validate_report(report: dict, rows: list[dict], *, attempt_id: str) -> dict:
    reasons: list[str] = []
    if report.get("schema") != REPORT_SCHEMA:
        reasons.append("report_schema_invalid")
    if report.get("attempt_id") != attempt_id:
        reasons.append("report_attempt_invalid")
    if report.get("operation_complete") is not True:
        reasons.append("operation_incomplete")
    if report.get("shutdown_complete") is not True:
        reasons.append("shutdown_incomplete")
    samples = report.get("samples")
    if not isinstance(samples, list) or not samples:
        reasons.append("samples_missing")
    else:
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict):
                reasons.append(f"sample_invalid:{index}")
                continue
            reasons.extend(f"{reason}:{index}" for reason in validate_sample(sample))
    markers = validate_marker_rows(rows, attempt_id)
    reasons.extend(markers["reasons"])
    return {"accepted": not reasons, "reasons": reasons, "marker_validation": markers}


def classify(report: dict, *, fixture_pass: bool, resource_pass: bool, cleanup_pass: bool) -> dict:
    if not fixture_pass or report.get("contract_valid") is not True:
        return {"classification": CLASSIFICATIONS["harness"], "reason": "pre_runtime_contract_or_fixture_failure"}
    if not resource_pass or not cleanup_pass:
        return {"classification": CLASSIFICATIONS["harness"], "reason": "resource_or_cleanup_failure"}
    samples = report.get("samples") or []
    if not samples or report.get("operation_complete") is not True or report.get("shutdown_complete") is not True:
        return {"classification": CLASSIFICATIONS["harness"], "reason": "required_evidence_incomplete"}
    if any(sample.get("os_identity_state") == "alive_identity_mismatch" for sample in samples):
        return {"classification": CLASSIFICATIONS["harness"], "reason": "pid_reuse_or_identity_mismatch"}
    stale = any(
        sample.get("process_object_has_exited") is False
        and sample.get("native_wait_state") == "signaled"
        and sample.get("os_identity_state") == "confirmed_exited"
        for sample in samples
    )
    if stale:
        return {"classification": CLASSIFICATIONS["stale"], "reason": "process_object_disagreed_with_native_handle_and_os"}
    exit_code = report.get("kit_exit_code")
    reporter = report.get("crash_reporter_observed") is True
    dump = report.get("completed_dump_count", 0)
    if exit_code == 0 and report.get("natural_exit_observed") is True and not reporter and dump == 0:
        return {"classification": CLASSIFICATIONS["qualified"], "reason": "exact_child_exit_zero_observed"}
    if exit_code not in (None, 0) and (reporter or dump):
        return {"classification": CLASSIFICATIONS["crash_reporter"], "reason": "abnormal_exit_with_crash_reporter_or_dump"}
    if exit_code not in (None, 0) or report.get("cdb_attempted") is True:
        return {"classification": CLASSIFICATIONS["native_wait"], "reason": "native_exit_or_live_wait_boundary_observed"}
    return {"classification": CLASSIFICATIONS["unresolved"], "reason": "post_shutdown_exit_not_resolved"}


def write_report(path: Path, report: dict) -> None:
    atomic_write_json(path, report)


def finalize_stable_artifacts(root: Path, samples: list[dict], *, maximum_files: int = 64,
                              maximum_file_bytes: int = 512 * 1024 * 1024) -> dict:
    root = root.resolve()
    observations: dict[str, list[int]] = {}
    for sample in samples:
        state = sample.get("dump_state") if isinstance(sample, dict) else None
        for item in state.get("files", []) if isinstance(state, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("bytes"), int):
                observations.setdefault(item["name"], []).append(item["bytes"])
    files: list[dict] = []
    for path in sorted(root.glob("*"))[:maximum_files]:
        resolved = path.resolve(strict=True)
        if resolved.parent != root or not resolved.is_file():
            raise ValueError("artifact_root_or_type_invalid")
        size = resolved.stat().st_size
        prior = observations.get(resolved.name, [])
        stable = len(prior) >= 2 and prior[-1] == prior[-2] == size
        digest = None
        if stable and 0 < size <= maximum_file_bytes:
            value = hashlib.sha256()
            with resolved.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(chunk)
            digest = value.hexdigest().upper()
        files.append({"name": resolved.name, "bytes": size, "stable": stable, "sha256": digest})
    return {
        "count": len(files),
        "stable_count": sum(item["stable"] for item in files),
        "hashed_count": sum(item["sha256"] is not None for item in files),
        "files": files,
    }
