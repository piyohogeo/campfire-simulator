"""No-Kit producer-to-consumer fixture for the Phase 6IM identity helper."""
from __future__ import annotations

import argparse
import copy
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time

from phase6im_process_identity import (
    DWORD_MAX,
    ProcessIdentityError,
    WindowsProcessApi,
    append_marker,
    capture_process_identity,
    combine_filetime,
    identity_equal,
    normalize_executable_path,
    produce_helper_report,
    read_bounded_json,
    read_bounded_jsonl,
    validate_pid,
    validate_report,
    write_report,
)

PYTHON = Path(r"C:\Python38\python.exe")


def _case(results: list[dict], name: str, passed: bool, evidence: object = None) -> None:
    results.append({"name": name, "passed": bool(passed), "evidence": evidence})


def _expect_reason(call, reason: str) -> tuple[bool, dict]:
    try:
        call()
    except ProcessIdentityError as error:
        return error.reason == reason, {"reason": error.reason, "last_error": error.last_error}
    except Exception as error:  # bounded unexpected-type evidence
        return False, {"unexpected": type(error).__name__, "message": str(error)[:256]}
    return False, {"reason": "no_exception"}


class FailTimesApi(WindowsProcessApi):
    def get_process_times(self, handle):
        raise ProcessIdentityError("get_process_times_failed", last_error=6)


class FailCloseEvidenceApi(WindowsProcessApi):
    def close_process(self, handle):
        success, _ = super().close_process(handle)
        assert success
        self.close_failures += 1
        return False, 6


def _write_rows(path: Path, attempt: str, identity: dict, steps: list[str]) -> None:
    started = time.monotonic()
    for step in steps:
        append_marker(path, attempt_id=attempt, step_id=step, identity=identity, elapsed=time.monotonic() - started)


def run(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6IM fixture refuses root reuse")
    output_root.mkdir(parents=True)
    results: list[dict] = []
    attempt = "phase6im-fixture-positive"

    api = WindowsProcessApi()
    signature = api.signature_evidence()
    current = capture_process_identity(os.getpid(), expected_path=PYTHON, api=api)
    _case(results, "real_current_process_handle", current["pid"] == os.getpid() and current["close_handle_success"] and api.tracker()["open_handle_residual_count"] == 0, current)
    repeated = capture_process_identity(os.getpid(), expected_path=PYTHON, expected_creation_ticks=current["creation_time_filetime_ticks"], api=api)
    _case(results, "same_process_creation_time_stable", identity_equal(current, repeated), {"first": current["creation_time_filetime_ticks"], "second": repeated["creation_time_filetime_ticks"]})

    child = subprocess.Popen([str(PYTHON), "-c", "import time; time.sleep(1.0)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        child_live = capture_process_identity(child.pid, expected_path=PYTHON)
        _case(results, "real_short_lived_child_before_exit", child_live["pid"] == child.pid and child_live["close_handle_success"], child_live)
        child.wait(timeout=5)
        try:
            capture_process_identity(child.pid, expected_path=PYTHON)
            passed, evidence = False, {"reason": "unexpected_identity_success"}
        except ProcessIdentityError as error:
            passed = error.reason in {"open_process_failed", "process_exit_race_before_identity", "process_exit_race_during_identity"}
            evidence = {"reason": error.reason, "last_error": error.last_error}
        _case(results, "child_exit_race_fail_closed", passed, evidence)
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=5)

    for name, value in (("pid_zero", 0), ("pid_negative", -1), ("pid_dword_overflow", DWORD_MAX + 1), ("pid_bool", True)):
        passed, evidence = _expect_reason(lambda value=value: validate_pid(value), "pid_invalid")
        _case(results, name, passed, evidence)
    passed, evidence = _expect_reason(lambda: capture_process_identity(99999999), "open_process_failed")
    _case(results, "invalid_pid_open_failure", passed, evidence)

    closed_api = WindowsProcessApi()
    closed_handle = closed_api.open_process(os.getpid())
    close_success, close_error = closed_api.close_process(closed_handle)
    passed, evidence = _expect_reason(lambda: closed_api.get_process_times(closed_handle), "get_process_times_failed")
    _case(results, "closed_handle_rejected", close_success and close_error == 0 and passed, evidence)
    invalid_handle = wintypes.HANDLE(0)
    passed, evidence = _expect_reason(lambda: closed_api.get_process_times(invalid_handle), "get_process_times_failed")
    _case(results, "invalid_handle_rejected", passed, evidence)

    failure_api = FailTimesApi()
    passed, evidence = _expect_reason(lambda: capture_process_identity(os.getpid(), expected_path=PYTHON, api=failure_api), "get_process_times_failed")
    _case(results, "get_process_times_failure_closes_handle", passed and failure_api.close_calls == 1 and failure_api.tracker()["open_handle_residual_count"] == 0, {"error": evidence, "tracker": failure_api.tracker()})
    close_api = FailCloseEvidenceApi()
    passed, evidence = _expect_reason(lambda: capture_process_identity(os.getpid(), expected_path=PYTHON, api=close_api), "close_handle_failed")
    _case(results, "close_handle_failure_is_evidence", passed and close_api.close_calls == 1 and close_api.tracker()["open_handle_residual_count"] == 0, {"error": evidence, "tracker": close_api.tracker()})

    synthetic = wintypes.HANDLE(0x1234567887654321)
    _case(results, "pointer_sized_handle_not_truncated", WindowsProcessApi.handle_value(synthetic) == 0x1234567887654321 and ctypes.sizeof(wintypes.HANDLE) == 8, {"value": WindowsProcessApi.handle_value(synthetic), "sizes": signature})
    _case(results, "filetime_high_low_combination", combine_filetime(0x12345678, 0x9ABCDEF0) == 0x123456789ABCDEF0)

    passed, evidence = _expect_reason(lambda: capture_process_identity(os.getpid(), expected_path=output_root / "not-python.exe"), "executable_path_mismatch")
    _case(results, "exact_path_mismatch", passed, evidence)
    passed, evidence = _expect_reason(lambda: capture_process_identity(os.getpid(), expected_path=PYTHON, expected_creation_ticks=current["creation_time_filetime_ticks"] + 1), "creation_time_mismatch")
    _case(results, "creation_time_mismatch", passed, evidence)
    reused = dict(current); reused["creation_time_filetime_ticks"] += 1
    _case(results, "pid_reuse_identity_distinguished", not identity_equal(current, reused))

    report = produce_helper_report(attempt_id=attempt, pid=os.getpid(), expected_path=PYTHON)
    report["operation_complete"] = True
    report["shutdown_complete"] = True
    report_path = output_root / "positive_report.json"
    marker_path = output_root / "positive_markers.jsonl"
    steps = ["kit_app_ready", "process_started", "identity_helper_complete", "operation_complete", "shutdown_complete"]
    _write_rows(marker_path, attempt, report["identities"][0], steps)
    write_result = write_report(report_path, report)
    consumed = read_bounded_json(report_path)
    rows = read_bounded_jsonl(marker_path)
    validation = validate_report(consumed, rows, attempt_id=attempt)
    _case(results, "producer_atomic_writer_reader_validator", validation["accepted"] and consumed == report, {"write": write_result, "validation": validation})

    missing_rows = rows[:-1]
    _case(results, "marker_missing", not validate_report(consumed, missing_rows, attempt_id=attempt)["accepted"])
    conflict_rows = copy.deepcopy(rows); conflict_rows[1]["executable_path"] = normalize_executable_path(output_root / "wrong.exe")
    _case(results, "marker_identity_conflict", "marker_process_identity_conflict:1" in validate_report(consumed, conflict_rows, attempt_id=attempt)["reasons"])
    duplicate_rows = rows[:2] + [copy.deepcopy(rows[1])] + rows[2:]
    _case(results, "marker_duplicate_or_order", "marker_order_or_completeness_invalid" in validate_report(consumed, duplicate_rows, attempt_id=attempt)["reasons"])
    corrupt = output_root / "corrupt.json"; corrupt.write_text("{", encoding="utf-8")
    try:
        read_bounded_json(corrupt); corrupt_rejected = False
    except (json.JSONDecodeError, ProcessIdentityError):
        corrupt_rejected = True
    _case(results, "corrupt_json_rejected", corrupt_rejected)
    oversize = output_root / "oversize.json"; oversize.write_bytes(b"x" * (1024 * 1024 + 1))
    passed, evidence = _expect_reason(lambda: read_bounded_json(oversize), "bounded_json_missing_or_size_invalid")
    _case(results, "oversize_rejected", passed, evidence)

    summary = {
        "schema": "campfire.phase6im.process-identity-fixture.v1",
        "phase": "phase6im",
        "status": "qualified" if all(item["passed"] for item in results) else "failed",
        "case_count": len(results),
        "passed_count": sum(item["passed"] for item in results),
        "kit_launch_count": 0,
        "real_windows_handle_used": True,
        "signature_evidence": signature,
        "cases": results,
    }
    write_report(output_root / "fixture_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_root.resolve())
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
