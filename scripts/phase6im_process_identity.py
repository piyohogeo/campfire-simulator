"""Exact, bounded Windows process identity evidence for Phase 6IM."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
import time
from pathlib import Path

from phase6hu_atomic_report import append_durable_jsonl, atomic_write_json

REPORT_SCHEMA = "campfire.phase6im.process-identity-report.v1"
MARKER_SCHEMA = "campfire.phase6im.process-identity-marker.v1"
MAX_JSON_BYTES = 1024 * 1024
MAX_MARKER_BYTES = 1024 * 1024
DWORD_MAX = 0xFFFFFFFF
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
STILL_ACTIVE = 259
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
WAIT_FAILED = 0xFFFFFFFF
WINDOWS_TO_UNIX_EPOCH_SECONDS = 11644473600.0


class ProcessIdentityError(RuntimeError):
    def __init__(self, reason: str, *, last_error: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.last_error = last_error


def validate_pid(pid: object) -> int:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or pid > DWORD_MAX:
        raise ProcessIdentityError("pid_invalid")
    return pid


def combine_filetime(high: int, low: int) -> int:
    if not all(isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= DWORD_MAX for value in (high, low)):
        raise ProcessIdentityError("filetime_component_invalid")
    return (high << 32) | low


def filetime_to_unix_epoch(high: int, low: int) -> tuple[int, float]:
    ticks = combine_filetime(high, low)
    epoch = ticks / 10_000_000.0 - WINDOWS_TO_UNIX_EPOCH_SECONDS
    if ticks <= 0 or not math.isfinite(epoch) or epoch <= 0:
        raise ProcessIdentityError("creation_time_invalid")
    return ticks, epoch


def normalize_executable_path(path: str | Path) -> str:
    if not isinstance(path, (str, Path)) or not str(path):
        raise ProcessIdentityError("executable_path_invalid")
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


class WindowsProcessApi:
    """Typed Kernel32 calls. Every real OpenProcess handle is tracked."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise ProcessIdentityError("windows_required")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = wintypes.HANDLE
        dword = wintypes.DWORD
        bool_type = wintypes.BOOL
        lp_filetime = ctypes.POINTER(wintypes.FILETIME)
        lp_dword = ctypes.POINTER(dword)

        self.kernel32.OpenProcess.argtypes = (dword, bool_type, dword)
        self.kernel32.OpenProcess.restype = handle
        self.kernel32.GetProcessTimes.argtypes = (handle, lp_filetime, lp_filetime, lp_filetime, lp_filetime)
        self.kernel32.GetProcessTimes.restype = bool_type
        self.kernel32.CloseHandle.argtypes = (handle,)
        self.kernel32.CloseHandle.restype = bool_type
        self.kernel32.GetCurrentProcess.argtypes = ()
        self.kernel32.GetCurrentProcess.restype = handle
        self.kernel32.GetCurrentProcessId.argtypes = ()
        self.kernel32.GetCurrentProcessId.restype = dword
        self.kernel32.GetExitCodeProcess.argtypes = (handle, lp_dword)
        self.kernel32.GetExitCodeProcess.restype = bool_type
        self.kernel32.WaitForSingleObject.argtypes = (handle, dword)
        self.kernel32.WaitForSingleObject.restype = dword
        self.kernel32.QueryFullProcessImageNameW.argtypes = (handle, dword, wintypes.LPWSTR, lp_dword)
        self.kernel32.QueryFullProcessImageNameW.restype = bool_type
        self._open_handles: set[int] = set()
        self.open_calls = 0
        self.close_calls = 0
        self.close_failures = 0

    @staticmethod
    def handle_value(handle: wintypes.HANDLE) -> int:
        value = ctypes.cast(handle, ctypes.c_void_p).value
        return int(value) if value is not None else 0

    def signature_evidence(self) -> dict:
        pseudo = self.kernel32.GetCurrentProcess()
        current_pid = int(self.kernel32.GetCurrentProcessId())
        return {
            "pointer_size_bytes": ctypes.sizeof(ctypes.c_void_p),
            "handle_size_bytes": ctypes.sizeof(wintypes.HANDLE),
            "dword_size_bytes": ctypes.sizeof(wintypes.DWORD),
            "bool_size_bytes": ctypes.sizeof(wintypes.BOOL),
            "filetime_size_bytes": ctypes.sizeof(wintypes.FILETIME),
            "current_process_pseudo_handle_value": self.handle_value(pseudo),
            "current_process_id": current_pid,
            "declared_apis": {
                name: {"argtypes": len(getattr(self.kernel32, name).argtypes or ()), "restype": str(getattr(self.kernel32, name).restype)}
                for name in (
                    "OpenProcess", "GetProcessTimes", "CloseHandle", "GetCurrentProcess",
                    "GetCurrentProcessId", "GetExitCodeProcess", "WaitForSingleObject",
                    "QueryFullProcessImageNameW",
                )
            },
        }

    def open_process(self, pid: int) -> wintypes.HANDLE:
        pid = validate_pid(pid)
        ctypes.set_last_error(0)
        handle = self.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
            False,
            pid,
        )
        value = self.handle_value(handle)
        if value == 0:
            raise ProcessIdentityError("open_process_failed", last_error=ctypes.get_last_error())
        self.open_calls += 1
        self._open_handles.add(value)
        return handle

    def close_process(self, handle: wintypes.HANDLE) -> tuple[bool, int]:
        value = self.handle_value(handle)
        self.close_calls += 1
        ctypes.set_last_error(0)
        success = bool(self.kernel32.CloseHandle(handle))
        error = 0 if success else ctypes.get_last_error()
        if success:
            self._open_handles.discard(value)
        else:
            self.close_failures += 1
        return success, error

    def get_process_times(self, handle: wintypes.HANDLE) -> tuple[wintypes.FILETIME, wintypes.FILETIME, wintypes.FILETIME, wintypes.FILETIME]:
        values = tuple(wintypes.FILETIME() for _ in range(4))
        ctypes.set_last_error(0)
        if not self.kernel32.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
            raise ProcessIdentityError("get_process_times_failed", last_error=ctypes.get_last_error())
        return values

    def get_exit_code(self, handle: wintypes.HANDLE) -> int:
        value = wintypes.DWORD()
        ctypes.set_last_error(0)
        if not self.kernel32.GetExitCodeProcess(handle, ctypes.byref(value)):
            raise ProcessIdentityError("get_exit_code_failed", last_error=ctypes.get_last_error())
        return int(value.value)

    def wait_zero(self, handle: wintypes.HANDLE) -> int:
        ctypes.set_last_error(0)
        result = int(self.kernel32.WaitForSingleObject(handle, 0))
        if result == WAIT_FAILED:
            raise ProcessIdentityError("wait_for_single_object_failed", last_error=ctypes.get_last_error())
        if result not in (WAIT_OBJECT_0, WAIT_TIMEOUT):
            raise ProcessIdentityError("wait_for_single_object_unknown")
        return result

    def executable_path(self, handle: wintypes.HANDLE) -> str:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        ctypes.set_last_error(0)
        if not self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            raise ProcessIdentityError("query_process_path_failed", last_error=ctypes.get_last_error())
        return normalize_executable_path(buffer.value)

    def tracker(self) -> dict:
        return {
            "open_calls": self.open_calls,
            "close_calls": self.close_calls,
            "close_failures": self.close_failures,
            "open_handle_residual_count": len(self._open_handles),
        }


def capture_process_identity(
    pid: int,
    *,
    expected_path: str | Path | None = None,
    expected_creation_ticks: int | None = None,
    api: WindowsProcessApi | None = None,
) -> dict:
    pid = validate_pid(pid)
    api = api or WindowsProcessApi()
    handle = api.open_process(pid)
    handle_value = api.handle_value(handle)
    close_success = False
    close_error = 0
    result: dict | None = None
    primary_error: BaseException | None = None
    try:
        if api.wait_zero(handle) != WAIT_TIMEOUT:
            raise ProcessIdentityError("process_exit_race_before_identity")
        creation, exit_time, kernel_time, user_time = api.get_process_times(handle)
        ticks, epoch = filetime_to_unix_epoch(creation.dwHighDateTime, creation.dwLowDateTime)
        path = api.executable_path(handle)
        exit_code = api.get_exit_code(handle)
        if exit_code != STILL_ACTIVE or api.wait_zero(handle) != WAIT_TIMEOUT:
            raise ProcessIdentityError("process_exit_race_during_identity")
        if expected_path is not None and path != normalize_executable_path(expected_path):
            raise ProcessIdentityError("executable_path_mismatch")
        if expected_creation_ticks is not None and ticks != expected_creation_ticks:
            raise ProcessIdentityError("creation_time_mismatch")
        result = {
            "pid": pid,
            "creation_time_filetime_ticks": ticks,
            "creation_time_utc_epoch": epoch,
            "executable_path": path,
            "handle_value_hex": f"0x{handle_value:0{ctypes.sizeof(ctypes.c_void_p) * 2}X}",
            "handle_pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
            "wait_state": "alive_timeout",
            "exit_code": exit_code,
            "close_handle_success": None,
            "close_handle_last_error": None,
        }
    except BaseException as error:
        primary_error = error
    finally:
        close_success, close_error = api.close_process(handle)
    if not close_success:
        raise ProcessIdentityError("close_handle_failed", last_error=close_error) from primary_error
    if primary_error is not None:
        raise primary_error
    assert result is not None
    result["close_handle_success"] = True
    result["close_handle_last_error"] = 0
    result["tracker_after"] = api.tracker()
    return result


def identity_equal(first: dict, second: dict) -> bool:
    return all(first.get(key) == second.get(key) for key in ("pid", "creation_time_filetime_ticks", "executable_path"))


def produce_helper_report(*, attempt_id: str, pid: int, expected_path: str | Path) -> dict:
    """The single report producer used by both the real probe and fixture."""
    api = WindowsProcessApi()
    signature = api.signature_evidence()
    first = capture_process_identity(pid, expected_path=expected_path, api=api)
    second = capture_process_identity(
        pid,
        expected_path=expected_path,
        expected_creation_ticks=first["creation_time_filetime_ticks"],
        api=api,
    )
    tracker = api.tracker()
    if not identity_equal(first, second):
        raise ProcessIdentityError("identity_unstable")
    if tracker["open_calls"] != 2 or tracker["close_calls"] != 2 or tracker["close_failures"] != 0 or tracker["open_handle_residual_count"] != 0:
        raise ProcessIdentityError("handle_balance_invalid")
    return {
        "schema": REPORT_SCHEMA,
        "phase": "phase6im",
        "attempt_id": attempt_id,
        "helper_complete": True,
        "operation_complete": False,
        "shutdown_complete": False,
        "identities": [first, second],
        "identity_stable": True,
        "signature_evidence": signature,
        "handle_tracker_final": tracker,
        "forbidden_calls": {
            "stage": 0,
            "layer": 0,
            "timeline_play": 0,
            "flow": 0,
            "renderer_update": 0,
            "readback": 0,
            "capture": 0,
            "cdb_attach": 0,
            "dump_analysis": 0,
            "post_shutdown_schedule_samples": 0,
        },
    }


def append_marker(path: Path, *, attempt_id: str, step_id: str, identity: dict, elapsed: float, details: dict | None = None) -> None:
    if path.is_file() and path.stat().st_size >= MAX_MARKER_BYTES:
        raise ProcessIdentityError("marker_oversize")
    row = {
        "schema": MARKER_SCHEMA,
        "attempt_id": attempt_id,
        "step_id": step_id,
        "pid": identity["pid"],
        "creation_time_filetime_ticks": identity["creation_time_filetime_ticks"],
        "executable_path": identity["executable_path"],
        "timestamp_utc_epoch": time.time(),
        "monotonic_elapsed_seconds": elapsed,
        "details": details or {},
    }
    append_durable_jsonl(path, row)


def write_report(path: Path, report: dict) -> dict:
    return atomic_write_json(path, report)


def read_bounded_json(path: Path, maximum: int = MAX_JSON_BYTES) -> dict:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > maximum:
        raise ProcessIdentityError("bounded_json_missing_or_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ProcessIdentityError("bounded_json_root_invalid")
    return value


def read_bounded_jsonl(path: Path, maximum: int = MAX_MARKER_BYTES) -> list[dict]:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > maximum:
        raise ProcessIdentityError("bounded_jsonl_missing_or_size_invalid")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ProcessIdentityError("bounded_jsonl_rows_invalid")
    return rows


def validate_report(report: dict, rows: list[dict], *, attempt_id: str) -> dict:
    reasons: list[str] = []
    if report.get("schema") != REPORT_SCHEMA:
        reasons.append("report_schema_invalid")
    if report.get("attempt_id") != attempt_id:
        reasons.append("attempt_id_invalid")
    identities = report.get("identities")
    if not isinstance(identities, list) or len(identities) != 2:
        reasons.append("identity_count_invalid")
    else:
        required = {
            "pid", "creation_time_filetime_ticks", "creation_time_utc_epoch",
            "executable_path", "handle_value_hex", "handle_pointer_bits",
            "wait_state", "exit_code", "close_handle_success",
            "close_handle_last_error", "tracker_after",
        }
        for index, identity in enumerate(identities):
            if not isinstance(identity, dict):
                reasons.append(f"identity_type_invalid:{index}")
                continue
            for key in sorted(required - set(identity)):
                reasons.append(f"identity_key_missing:{index}:{key}")
            if identity.get("close_handle_success") is not True:
                reasons.append(f"handle_close_incomplete:{index}")
            tracker = identity.get("tracker_after")
            if not isinstance(tracker, dict) or tracker.get("open_handle_residual_count") != 0:
                reasons.append(f"handle_residual:{index}")
        if all(isinstance(value, dict) for value in identities) and not identity_equal(identities[0], identities[1]):
            reasons.append("identity_unstable")
    signatures = report.get("signature_evidence")
    if not isinstance(signatures, dict) or signatures.get("pointer_size_bytes") != signatures.get("handle_size_bytes") or signatures.get("pointer_size_bytes") != 8:
        reasons.append("pointer_handle_size_invalid")
    if report.get("helper_complete") is not True:
        reasons.append("helper_incomplete")
    if report.get("operation_complete") is not True:
        reasons.append("operation_incomplete")
    expected_steps = ["kit_app_ready", "process_started", "identity_helper_complete", "operation_complete", "shutdown_complete"]
    steps = [row.get("step_id") for row in rows]
    if steps != expected_steps:
        reasons.append("marker_order_or_completeness_invalid")
    for index, row in enumerate(rows):
        if row.get("schema") != MARKER_SCHEMA or row.get("attempt_id") != attempt_id:
            reasons.append(f"marker_identity_invalid:{index}")
        if identities and isinstance(identities, list) and isinstance(identities[0], dict):
            if row.get("pid") != identities[0].get("pid") or row.get("creation_time_filetime_ticks") != identities[0].get("creation_time_filetime_ticks") or row.get("executable_path") != identities[0].get("executable_path"):
                reasons.append(f"marker_process_identity_conflict:{index}")
    return {"accepted": not reasons, "reasons": reasons, "steps": steps}
