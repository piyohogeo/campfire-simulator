"""No-Kit end-to-end fixture for Phase 6HU atomic report replacement."""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest import mock

from phase6hs_operation_report import (
    ReportError,
    atomic_write_json as actual_producer_writer,
    produce_report,
    read_bounded_json,
    sha256_bytes,
    validate_paths,
)
from phase6hu_atomic_report import AtomicReportError, atomic_write_json, writer_lease
from phase6hu_runtime_report import DurableOperationReporter


ATTEMPT = "phase6hu-fixture-attempt"


def _case(rows: list[dict], name: str, passed: bool, **detail) -> None:
    rows.append({"name": name, "passed": bool(passed), **detail})


def _completion_rows() -> list[dict]:
    return [
        {"name": "operation_complete", "attempt_id": ATTEMPT},
        {"name": "stage_close_complete", "attempt_id": ATTEMPT},
        {"name": "shutdown_complete", "attempt_id": ATTEMPT},
    ]


def _write_marker_rows(path: Path, rows: list[dict]) -> bytes:
    data = b"".join((json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return data


def _raw() -> dict:
    return {
        "schema": "campfire.phase6hu.fixture-raw.v1",
        "phase": "phase6hu",
        "status": "qualified",
        "last_marker": "shutdown_complete",
        "readback_calls": 0,
        "lifecycle": {"stage_close_complete": True, "shutdown_complete": True},
    }


def _locked_without_delete_share(path: Path):
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create_file.restype = wintypes.HANDLE
    handle = create_file(str(path), 0x80000000, 0x00000001 | 0x00000002, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateFileW fixture lock failed")
    return handle


def _close_handle(handle) -> None:
    if handle is None:
        return
    import ctypes
    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def run_fixture(root: Path, contract_path: Path, schema_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6HU atomic fixture refuses root reuse")
    root.mkdir(parents=True)
    cases: list[dict] = []
    contract_sha = sha256_bytes(contract_path.read_bytes())
    schema_sha = sha256_bytes(schema_path.read_bytes())

    # Actual producer -> actual serializer -> file -> actual bounded reader and validator.
    e2e = root / "producer_consumer"
    marker_rows = _completion_rows()
    marker_data = _write_marker_rows(e2e / "markers.jsonl", marker_rows)
    report = produce_report(
        _raw(), marker_rows, marker_data, attempt_id=ATTEMPT, kit_exit_code=0,
        schema_sha256=schema_sha, contract_sha256=contract_sha,
    )
    actual_producer_writer(e2e / "canonical.json", report)
    validation, consumed, consumed_rows, consumed_data = validate_paths(
        e2e / "canonical.json", e2e / "markers.jsonl",
        expected_attempt_id=ATTEMPT,
        expected_schema_sha256=schema_sha,
        expected_contract_sha256=contract_sha,
    )
    _case(cases, "actual_producer_to_consumer_unmodified", validation.get("accepted") is True and consumed == report and consumed_rows == marker_rows and consumed_data == marker_data, reason=validation.get("reason"))

    target = root / "atomic" / "report.json"
    first = {"sequence": 1, "status": "running"}
    second = {"sequence": 2, "status": "qualified"}
    one = atomic_write_json(target, first)
    _case(cases, "normal_create", read_bounded_json(target) == first and one["attempts"] == 1)
    two = atomic_write_json(target, second)
    _case(cases, "existing_file_replace", read_bounded_json(target) == second and two["attempts"] == 1)
    temp_one = one["temporary_name"]
    temp_two = two["temporary_name"]
    _case(cases, "unique_temporary_names", temp_one != temp_two and not list(target.parent.glob(target.name + ".partial.*")), first=temp_one, second=temp_two)
    for sequence in range(3, 13):
        atomic_write_json(target, {"sequence": sequence})
    _case(cases, "consecutive_updates", read_bounded_json(target).get("sequence") == 12)

    reader_errors: list[str] = []
    reader_busy = 0
    stop = threading.Event()

    def reader() -> None:
        nonlocal reader_busy
        while not stop.is_set():
            try:
                read_bounded_json(target)
            except ReportError as error:
                if str(error) == "report_writer_busy":
                    reader_busy += 1
                else:
                    reader_errors.append(type(error).__name__ + ":" + str(error))
            except Exception as error:  # fixture captures any transient invalid snapshot
                reader_errors.append(type(error).__name__ + ":" + str(error))

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()
    for sequence in range(13, 63):
        atomic_write_json(target, {"sequence": sequence})
    stop.set()
    reader_thread.join(timeout=2.0)
    _case(cases, "reader_concurrent_atomic_updates", not reader_errors and read_bounded_json(target).get("sequence") == 62, errors=reader_errors[:3], bounded_busy_classifications=reader_busy)

    # Reproduce the reader/guard share flags: read/write are shared, delete is not.
    atomic_write_json(target, {"sequence": 100})
    lock = _locked_without_delete_share(target)
    events: list[dict] = []
    release = threading.Thread(target=lambda: (time.sleep(0.055), _close_handle(lock)), daemon=True)
    release.start()
    shared = atomic_write_json(target, {"sequence": 101}, event=events.append)
    release.join(timeout=1.0)
    _case(cases, "temporary_sharing_violation_retried", read_bounded_json(target).get("sequence") == 101 and shared["attempts"] > 1 and any(row["event"] == "atomic_replace_retry" for row in events), attempts=shared["attempts"], events=events)

    lock = _locked_without_delete_share(target)
    exhausted = None
    try:
        atomic_write_json(target, {"sequence": 102})
    except AtomicReportError as error:
        exhausted = error
    finally:
        _close_handle(lock)
    _case(cases, "persistent_sharing_violation_fails_closed", exhausted is not None and exhausted.reason == "atomic_replace_retry_exhausted", attempts=getattr(exhausted, "attempts", None))

    with writer_lease(target):
        concurrent = None
        try:
            atomic_write_json(target, {"sequence": 103})
        except AtomicReportError as error:
            concurrent = error
    _case(cases, "multiple_writer_rejected", concurrent is not None and concurrent.reason == "concurrent_writer_rejected")

    denied = PermissionError("fixture write denied")
    denied.winerror = 5
    with mock.patch("phase6hu_atomic_report.os.replace", side_effect=denied):
        permission = None
        try:
            atomic_write_json(root / "atomic" / "denied.json", {"status": "x"})
        except AtomicReportError as error:
            permission = error
    _case(cases, "write_unavailable_fails_closed", permission is not None and permission.reason == "atomic_replace_retry_exhausted")

    nonretryable = FileNotFoundError("fixture nonretryable")
    with mock.patch("phase6hu_atomic_report.os.replace", side_effect=nonretryable):
        rejected = None
        try:
            atomic_write_json(root / "atomic" / "nonretryable.json", {"status": "x"})
        except AtomicReportError as error:
            rejected = error
    _case(cases, "nonretryable_error_not_hidden", rejected is not None and rejected.reason == "atomic_replace_nonretryable" and rejected.attempts == 1)

    missing_reason = None
    try:
        read_bounded_json(root / "missing.json")
    except ReportError as error:
        missing_reason = str(error)
    _case(cases, "missing_snapshot_rejected", missing_reason == "report_missing", reason=missing_reason)
    truncated = root / "atomic" / "truncated.json"
    truncated.write_text('{"status":', encoding="utf-8")
    truncated_reason = None
    try:
        read_bounded_json(truncated)
    except ReportError as error:
        truncated_reason = str(error)
    _case(cases, "truncated_snapshot_rejected", truncated_reason == "report_json_invalid", reason=truncated_reason)

    # The same runtime reporter must keep lifecycle cleanup markers durable when
    # raw snapshot replacement itself is unavailable.
    cleanup_root = root / "cleanup_after_report_failure"
    cleanup_report = {"status": "running", "readback_calls": 0, "lifecycle": {}}
    reporter = DurableOperationReporter(
        cleanup_root / "raw.json", cleanup_root / "markers.jsonl",
        cleanup_root / "atomic.jsonl", cleanup_report, ATTEMPT,
    )
    reporter.mark("contract_started")
    forced = AtomicReportError("atomic_replace_retry_exhausted", attempts=5, winerror=5)
    operation_raised = False
    with mock.patch("phase6hu_runtime_report.atomic_write_json", side_effect=forced):
        try:
            reporter.mark("operation_complete")
        except AtomicReportError:
            operation_raised = True
        reporter.enter_cleanup()
        reporter.mark("timeline_stop_complete")
        reporter.mark("stage_close_complete")
        reporter.mark("references_released")
        cleanup_report["lifecycle"] = {"stage_close_complete": True, "shutdown_complete": True}
        reporter.mark("shutdown_complete")
        final_write = reporter.try_final_write()
    durable_rows = [json.loads(line) for line in (cleanup_root / "markers.jsonl").read_text(encoding="utf-8").splitlines()]
    durable_names = [row["name"] for row in durable_rows]
    required_cleanup = ["timeline_stop_complete", "stage_close_complete", "references_released", "shutdown_complete"]
    _case(cases, "snapshot_failure_does_not_block_cleanup_markers", operation_raised and final_write is False and all(name in durable_names for name in required_cleanup), markers=durable_names)
    raw_after_failure = read_bounded_json(cleanup_root / "raw.json")
    _case(cases, "incomplete_snapshot_remains_fail_closed", raw_after_failure.get("last_marker") == "contract_started" and raw_after_failure.get("status") != "qualified", last_marker=raw_after_failure.get("last_marker"))

    return {
        "schema": "campfire.phase6hu.atomic-report-fixture.v1",
        "phase": "phase6hu",
        "status": "qualified" if all(case["passed"] for case in cases) else "failed",
        "kit_launch_count": 0,
        "case_count": len(cases),
        "cases": cases,
        "policy": {
            "maximum_bytes": 1024 * 1024,
            "maximum_attempts": 5,
            "maximum_elapsed_seconds": 0.25,
            "retryable_windows_errors": [5, 32, 33],
            "backoff_seconds": [0.01, 0.02, 0.04, 0.08],
            "durable_jsonl_source_of_truth": True,
        },
    }
