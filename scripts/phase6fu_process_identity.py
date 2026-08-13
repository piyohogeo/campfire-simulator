"""Fail-closed Windows process identity and exact-cleanup helpers.

This module deliberately keeps process observation separate from cleanup
authority.  A PID is never enough to authorize termination: creation time and
the absolute executable path must also match the identity captured by the
owning attempt.  psutil and a native Win32 query are used independently so an
exception from either path cannot be translated into "process absent".
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import time
from pathlib import Path
from typing import Callable, Iterable

import psutil


ALIVE_IDENTITY_MATCH = "alive_identity_match"
ALIVE_IDENTITY_MISMATCH = "alive_identity_mismatch"
CONFIRMED_EXITED = "confirmed_exited"
QUERY_FAILED_UNKNOWN = "query_failed_unknown"
ACCESS_DENIED_UNKNOWN = "access_denied_unknown"
CREATION_TIME_UNAVAILABLE_UNKNOWN = "creation_time_unavailable_unknown"
PATH_UNAVAILABLE_UNKNOWN = "path_unavailable_unknown"

UNKNOWN_STATES = {
    QUERY_FAILED_UNKNOWN,
    ACCESS_DENIED_UNKNOWN,
    CREATION_TIME_UNAVAILABLE_UNKNOWN,
    PATH_UNAVAILABLE_UNKNOWN,
}

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.abspath(value))


def make_identity(
    *,
    pid: int,
    create_time_utc_epoch: float,
    path: str,
    parent_pid: int | None,
    role: str,
    attempt_id: str,
    observed_at_utc_epoch: float | None = None,
) -> dict:
    return {
        "pid": int(pid),
        "create_time_utc_epoch": float(create_time_utc_epoch),
        "path": os.path.abspath(path),
        "parent_pid": None if parent_pid is None else int(parent_pid),
        "observed_at_utc_epoch": float(observed_at_utc_epoch or time.time()),
        "role": str(role),
        "root_attempt_id": str(attempt_id),
    }


def identity_from_psutil(process: psutil.Process, *, role: str, attempt_id: str) -> dict:
    return make_identity(
        pid=process.pid,
        create_time_utc_epoch=process.create_time(),
        path=process.exe(),
        parent_pid=process.ppid(),
        role=role,
        attempt_id=attempt_id,
    )


def _compare(identity: dict, create_time: float, path: str) -> str:
    if abs(float(identity["create_time_utc_epoch"]) - float(create_time)) > 1.0:
        return ALIVE_IDENTITY_MISMATCH
    if _path_key(str(identity["path"])) != _path_key(path):
        return ALIVE_IDENTITY_MISMATCH
    return ALIVE_IDENTITY_MATCH


def query_psutil(identity: dict) -> dict:
    try:
        process = psutil.Process(int(identity["pid"]))
        try:
            create_time = process.create_time()
        except psutil.AccessDenied as error:
            return {"state": ACCESS_DENIED_UNKNOWN, "error": str(error), "source": "psutil"}
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return {"state": CONFIRMED_EXITED, "source": "psutil"}
        try:
            path = process.exe()
        except psutil.AccessDenied as error:
            return {"state": PATH_UNAVAILABLE_UNKNOWN, "error": str(error), "source": "psutil"}
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return {"state": CONFIRMED_EXITED, "source": "psutil"}
        return {
            "state": _compare(identity, create_time, path),
            "source": "psutil",
            "pid": process.pid,
            "create_time_utc_epoch": create_time,
            "path": os.path.abspath(path),
            "parent_pid": process.ppid(),
        }
    except psutil.NoSuchProcess:
        return {"state": CONFIRMED_EXITED, "source": "psutil"}
    except psutil.AccessDenied as error:
        return {"state": ACCESS_DENIED_UNKNOWN, "error": str(error), "source": "psutil"}
    except (psutil.ZombieProcess, OSError, ValueError) as error:
        return {"state": QUERY_FAILED_UNKNOWN, "error": str(error), "source": "psutil"}


def _filetime_to_epoch(value: wintypes.FILETIME) -> float:
    ticks = (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)
    return ticks / 10_000_000.0 - 11_644_473_600.0


def query_native(identity: dict) -> dict:
    if os.name != "nt":
        return {"state": QUERY_FAILED_UNKNOWN, "source": "win32", "error": "not_windows"}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(identity["pid"]))
    if not handle:
        error = ctypes.get_last_error()
        if error == ERROR_INVALID_PARAMETER:
            return {"state": CONFIRMED_EXITED, "source": "win32", "win32_error": error}
        if error == ERROR_ACCESS_DENIED:
            return {"state": ACCESS_DENIED_UNKNOWN, "source": "win32", "win32_error": error}
        return {"state": QUERY_FAILED_UNKNOWN, "source": "win32", "win32_error": error}
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return {"state": QUERY_FAILED_UNKNOWN, "source": "win32", "win32_error": ctypes.get_last_error()}
        if exit_code.value != STILL_ACTIVE:
            return {"state": CONFIRMED_EXITED, "source": "win32", "exit_code": int(exit_code.value)}

        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)):
            return {"state": CREATION_TIME_UNAVAILABLE_UNKNOWN, "source": "win32", "win32_error": ctypes.get_last_error()}
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return {"state": PATH_UNAVAILABLE_UNKNOWN, "source": "win32", "win32_error": ctypes.get_last_error()}
        create_time = _filetime_to_epoch(creation)
        path = buffer.value
        return {
            "state": _compare(identity, create_time, path),
            "source": "win32",
            "pid": int(identity["pid"]),
            "create_time_utc_epoch": create_time,
            "path": os.path.abspath(path),
        }
    finally:
        kernel32.CloseHandle(handle)


def combine_query_results(primary: dict, independent: dict) -> str:
    states = {str(primary["state"]), str(independent["state"])}
    if ALIVE_IDENTITY_MISMATCH in states:
        return ALIVE_IDENTITY_MISMATCH
    if ALIVE_IDENTITY_MATCH in states:
        # One exact live match is enough to prove the process is not absent;
        # an unknown second path remains evidence but cannot suppress cleanup.
        return ALIVE_IDENTITY_MATCH
    if states == {CONFIRMED_EXITED}:
        return CONFIRMED_EXITED
    for state in (
        ACCESS_DENIED_UNKNOWN,
        CREATION_TIME_UNAVAILABLE_UNKNOWN,
        PATH_UNAVAILABLE_UNKNOWN,
        QUERY_FAILED_UNKNOWN,
    ):
        if state in states:
            return state
    return QUERY_FAILED_UNKNOWN


def query_identity(
    identity: dict,
    *,
    primary_query: Callable[[dict], dict] = query_psutil,
    independent_query: Callable[[dict], dict] = query_native,
) -> dict:
    primary = primary_query(identity)
    independent = independent_query(identity)
    return {
        "state": combine_query_results(primary, independent),
        "identity": identity,
        "queries": [primary, independent],
        "observed_at_utc_epoch": time.time(),
    }


def append_jsonl(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", buffering=1) as stream:
        stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def wait_for_cleanup_suppression(
    lock_path: Path | None,
    *,
    deadline_seconds: float,
    marker_path: Path | None = None,
) -> dict:
    started = time.monotonic()
    observed = False
    while lock_path is not None and lock_path.exists():
        observed = True
        if time.monotonic() - started >= deadline_seconds:
            result = {"observed": observed, "released": False, "timed_out": True, "wait_seconds": time.monotonic() - started}
            append_jsonl(marker_path, {"marker": "cleanup_suppression_deadline", **result})
            return result
        time.sleep(0.05)
    result = {"observed": observed, "released": True, "timed_out": False, "wait_seconds": time.monotonic() - started}
    append_jsonl(marker_path, {"marker": "cleanup_suppression_released", **result})
    return result


def exact_cleanup(
    identities: Iterable[dict],
    *,
    marker_path: Path | None = None,
    retry_count: int = 3,
    retry_seconds: float = 0.2,
    kill: Callable[[int], None] | None = None,
    primary_query: Callable[[dict], dict] = query_psutil,
    independent_query: Callable[[dict], dict] = query_native,
) -> dict:
    records = list(identities)
    kill = kill or (lambda pid: psutil.Process(pid).kill())
    before: list[dict] = []
    killed: list[dict] = []
    protected: list[dict] = []
    unknown: list[dict] = []
    append_jsonl(marker_path, {"marker": "exact_cleanup_started", "identity_count": len(records)})

    for identity in reversed(records):
        result = query_identity(identity, primary_query=primary_query, independent_query=independent_query)
        before.append(result)
        state = result["state"]
        if state == ALIVE_IDENTITY_MATCH:
            try:
                kill(int(identity["pid"]))
                killed.append(identity)
                append_jsonl(marker_path, {"marker": "exact_identity_stop_requested", "identity": identity})
            except (psutil.NoSuchProcess, ProcessLookupError):
                pass
            except (psutil.AccessDenied, PermissionError, OSError) as error:
                unknown.append({"identity": identity, "state": ACCESS_DENIED_UNKNOWN, "error": str(error)})
        elif state == ALIVE_IDENTITY_MISMATCH:
            protected.append(result)
        elif state in UNKNOWN_STATES:
            unknown.append(result)

    final: list[dict] = []
    for attempt in range(max(1, retry_count)):
        final = [query_identity(item, primary_query=primary_query, independent_query=independent_query) for item in records]
        if all(item["state"] in {CONFIRMED_EXITED, ALIVE_IDENTITY_MISMATCH} for item in final):
            break
        if attempt + 1 < retry_count:
            time.sleep(retry_seconds)

    matching_remaining = [item for item in final if item["state"] == ALIVE_IDENTITY_MATCH]
    final_unknown = [item for item in final if item["state"] in UNKNOWN_STATES]
    summary = {
        "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
        "observed_identity_count": len(records),
        "before": before,
        "killed": killed,
        "protected_identity_mismatch": protected,
        "query_unknown": unknown,
        "final": final,
        "matching_remaining": matching_remaining,
        "final_unknown": final_unknown,
        "all_matching_absent": not matching_remaining and not final_unknown,
        # Compatibility aliases keep existing analyzers fail-closed while the
        # richer state model is adopted.  Unknown is therefore never reported
        # as an empty/absent set.
        "cleanup_required": bool(killed or matching_remaining or final_unknown),
        "killed_pids": [int(item["pid"]) for item in killed],
        "remaining": [item["identity"] for item in matching_remaining + final_unknown],
        "all_observed_absent": not matching_remaining and not final_unknown,
        "absence_confirmation_sources": ["psutil", "win32"],
        "completed_at_utc_epoch": time.time(),
    }
    append_jsonl(marker_path, {"marker": "exact_cleanup_complete", "all_matching_absent": summary["all_matching_absent"]})
    return summary
