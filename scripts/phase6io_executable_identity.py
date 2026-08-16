"""Handle-resolved executable identity boundary for Phase 6IO.

Phase 6IM remains the sole authority for a running process' PID, creation time,
and executable path.  This module only proves that a predeclared lexical launch
path and that authoritative process path name the same regular Windows file.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from phase6hu_atomic_report import atomic_write_json

SCHEMA = "campfire.phase6io.executable-path-identity.v1"
MAX_JSON_BYTES = 1024 * 1024
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_NAME_NORMALIZED = 0
VOLUME_NAME_DOS = 0
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PathIdentityError(RuntimeError):
    def __init__(self, reason: str, *, last_error: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.last_error = last_error


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


def _strip_extended_prefix(value: str) -> str:
    normalized = value.replace("/", "\\")
    if normalized.lower().startswith("\\\\?\\unc\\"):
        return "\\\\" + normalized[8:]
    if normalized.lower().startswith("\\\\?\\"):
        return normalized[4:]
    return normalized


def normalize_path_text(value: str | Path) -> str:
    if not isinstance(value, (str, Path)) or not str(value) or "\x00" in str(value):
        raise PathIdentityError("path_text_invalid")
    text = _strip_extended_prefix(str(value))
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


class WindowsFileIdentityApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise PathIdentityError("windows_required")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.GetFinalPathNameByHandleW.argtypes = (
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        )
        kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        kernel.GetFileInformationByHandle.argtypes = (
            wintypes.HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION),
        )
        kernel.GetFileInformationByHandle.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel32 = kernel
        self.open_count = 0
        self.close_count = 0
        self.close_failures = 0
        self._open: set[int] = set()

    @staticmethod
    def _value(handle: wintypes.HANDLE) -> int:
        value = ctypes.cast(handle, ctypes.c_void_p).value
        return int(value) if value is not None else 0

    def open_file(self, path: str) -> wintypes.HANDLE:
        ctypes.set_last_error(0)
        handle = self.kernel32.CreateFileW(
            path, FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None,
        )
        value = self._value(handle)
        if value in (0, INVALID_HANDLE_VALUE):
            raise PathIdentityError("path_open_failed", last_error=ctypes.get_last_error())
        self.open_count += 1
        self._open.add(value)
        return handle

    def final_path(self, handle: wintypes.HANDLE) -> str:
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        ctypes.set_last_error(0)
        size = int(self.kernel32.GetFinalPathNameByHandleW(
            handle, buffer, capacity, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS,
        ))
        if size == 0 or size >= capacity:
            raise PathIdentityError("final_path_query_failed", last_error=ctypes.get_last_error())
        return normalize_path_text(buffer.value)

    def file_information(self, handle: wintypes.HANDLE) -> BY_HANDLE_FILE_INFORMATION:
        info = BY_HANDLE_FILE_INFORMATION()
        ctypes.set_last_error(0)
        if not self.kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise PathIdentityError("file_information_failed", last_error=ctypes.get_last_error())
        if int(info.dwFileAttributes) & FILE_ATTRIBUTE_DIRECTORY:
            raise PathIdentityError("path_not_regular_file")
        return info

    def close(self, handle: wintypes.HANDLE) -> None:
        value = self._value(handle)
        self.close_count += 1
        ctypes.set_last_error(0)
        if not self.kernel32.CloseHandle(handle):
            self.close_failures += 1
            raise PathIdentityError("file_handle_close_failed", last_error=ctypes.get_last_error())
        self._open.discard(value)

    def tracker(self) -> dict[str, int]:
        return {
            "open_count": self.open_count,
            "close_count": self.close_count,
            "close_failures": self.close_failures,
            "open_handle_residual_count": len(self._open),
            "pointer_size_bytes": ctypes.sizeof(ctypes.c_void_p),
            "handle_size_bytes": ctypes.sizeof(wintypes.HANDLE),
        }


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest().upper()


def resolve_file_identity(path: str | Path, *, api: WindowsFileIdentityApi | None = None) -> dict[str, Any]:
    api = api or WindowsFileIdentityApi()
    lexical = normalize_path_text(path)
    handle = api.open_file(lexical)
    primary: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        final = api.final_path(handle)
        info = api.file_information(handle)
        final_path = Path(final)
        if not final_path.is_file():
            raise PathIdentityError("resolved_path_not_regular_file")
        size = (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)
        result = {
            "lexical_path": lexical,
            "canonical_path": final,
            "volume_serial": int(info.dwVolumeSerialNumber),
            "file_index": (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
            "file_size_bytes": size,
            "sha256": _sha256(final_path),
            "regular_file": True,
        }
    except BaseException as error:
        primary = error
    try:
        api.close(handle)
    except BaseException as close_error:
        raise close_error from primary
    if primary is not None:
        raise primary
    assert result is not None
    result["handle_closed"] = True
    return result


def same_file(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("canonical_path", "volume_serial", "file_index", "file_size_bytes", "sha256")
    return all(left.get(key) == right.get(key) for key in keys)


def produce_path_identity_report(
    *, attempt_id: str, lexical_launch_path: str | Path,
    expected_lexical_launch_path: str | Path, process_identity: dict[str, Any],
    launch_pid: int, launch_creation_ticks: int,
) -> dict[str, Any]:
    if normalize_path_text(lexical_launch_path) != normalize_path_text(expected_lexical_launch_path):
        raise PathIdentityError("launch_lexical_boundary_mismatch")
    if type(launch_pid) is not int or launch_pid <= 0:
        raise PathIdentityError("launch_pid_invalid")
    if type(launch_creation_ticks) is not int or launch_creation_ticks <= 0:
        raise PathIdentityError("launch_creation_time_invalid")
    required = {"pid", "creation_time_filetime_ticks", "executable_path"}
    if not isinstance(process_identity, dict) or not required.issubset(process_identity):
        raise PathIdentityError("process_identity_incomplete")
    api = WindowsFileIdentityApi()
    launch_file = resolve_file_identity(lexical_launch_path, api=api)
    process_file = resolve_file_identity(process_identity["executable_path"], api=api)
    pid_match = process_identity["pid"] == launch_pid
    creation_match = process_identity["creation_time_filetime_ticks"] == launch_creation_ticks
    path_match = same_file(launch_file, process_file)
    tracker = api.tracker()
    accepted = pid_match and creation_match and path_match and tracker["open_handle_residual_count"] == 0 and tracker["close_failures"] == 0
    reasons = []
    if not pid_match:
        reasons.append("pid_mismatch")
    if not creation_match:
        reasons.append("creation_time_mismatch")
    if not path_match:
        reasons.append("canonical_file_identity_mismatch")
    if tracker["open_handle_residual_count"] or tracker["close_failures"]:
        reasons.append("file_handle_cleanup_failure")
    return {
        "schema": SCHEMA, "phase": "phase6io", "attempt_id": attempt_id,
        "accepted": accepted, "reasons": reasons,
        "authority": "phase6im_process_identity",
        "launch_pid": launch_pid, "launch_creation_time_filetime_ticks": launch_creation_ticks,
        "process_identity": {key: process_identity[key] for key in sorted(required)},
        "lexical_launch_file": launch_file, "process_executable_file": process_file,
        "checks": {"pid_match": pid_match, "creation_time_match": creation_match, "canonical_file_match": path_match},
        "handle_tracker": tracker,
    }


def validate_path_identity_report(report: dict[str, Any], *, attempt_id: str) -> dict[str, Any]:
    reasons: list[str] = []
    exact = {
        "schema", "phase", "attempt_id", "accepted", "reasons", "authority",
        "launch_pid", "launch_creation_time_filetime_ticks", "process_identity",
        "lexical_launch_file", "process_executable_file", "checks", "handle_tracker",
    }
    if not isinstance(report, dict):
        return {"accepted": False, "reasons": ["report_type_invalid"]}
    missing = exact - set(report)
    unknown = set(report) - exact
    reasons.extend("required_key_missing:" + key for key in sorted(missing))
    reasons.extend("unknown_key:" + key for key in sorted(unknown))
    if report.get("schema") != SCHEMA:
        reasons.append("schema_invalid")
    if report.get("phase") != "phase6io" or report.get("attempt_id") != attempt_id:
        reasons.append("attempt_identity_invalid")
    if report.get("authority") != "phase6im_process_identity":
        reasons.append("authority_invalid")
    process = report.get("process_identity")
    launch = report.get("lexical_launch_file")
    resolved = report.get("process_executable_file")
    checks = report.get("checks")
    tracker = report.get("handle_tracker")
    if not all(isinstance(value, dict) for value in (process, launch, resolved, checks, tracker)):
        reasons.append("evidence_type_invalid")
    else:
        for label, value in (("launch", launch), ("process", resolved)):
            required_file = {"lexical_path", "canonical_path", "volume_serial", "file_index", "file_size_bytes", "sha256", "regular_file", "handle_closed"}
            if set(value) != required_file:
                reasons.append(label + "_file_keys_invalid")
            if value.get("regular_file") is not True or value.get("handle_closed") is not True:
                reasons.append(label + "_file_invalid")
        if process.get("pid") != report.get("launch_pid") or checks.get("pid_match") is not True:
            reasons.append("pid_mismatch")
        if process.get("creation_time_filetime_ticks") != report.get("launch_creation_time_filetime_ticks") or checks.get("creation_time_match") is not True:
            reasons.append("creation_time_mismatch")
        if not same_file(launch, resolved) or checks.get("canonical_file_match") is not True:
            reasons.append("canonical_file_identity_mismatch")
        if tracker.get("open_count") != 2 or tracker.get("close_count") != 2 or tracker.get("close_failures") != 0 or tracker.get("open_handle_residual_count") != 0:
            reasons.append("file_handle_balance_invalid")
        if tracker.get("pointer_size_bytes") != 8 or tracker.get("handle_size_bytes") != 8:
            reasons.append("pointer_handle_size_invalid")
    if report.get("accepted") is not True or report.get("reasons") != []:
        reasons.append("producer_not_accepted")
    return {"accepted": not reasons, "reasons": reasons}


def write_report(path: Path, report: dict[str, Any]) -> None:
    atomic_write_json(path, report)


def read_report(path: Path, maximum: int = MAX_JSON_BYTES) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > maximum:
        raise PathIdentityError("bounded_json_missing_or_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PathIdentityError("bounded_json_root_invalid")
    return value
