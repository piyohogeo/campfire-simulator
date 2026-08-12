"""Bounded, Windows-only synchronous process-memory snapshot for Phase 6EU."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("page_fault_count", wintypes.DWORD),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
        ("private_usage", ctypes.c_size_t),
    ]


def process_memory_snapshot():
    if os.name != "nt":
        return {"available": False, "reason": "Windows PROCESS_MEMORY_COUNTERS_EX only"}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCountersEx),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    success = psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    )
    if not success:
        return {
            "available": False,
            "reason": f"GetProcessMemoryInfo error {ctypes.get_last_error()}",
            "structure_bytes": ctypes.sizeof(counters),
        }
    return {
        "available": True,
        "private_bytes": int(counters.private_usage),
        "working_set_bytes": int(counters.working_set_size),
        "peak_working_set_bytes": int(counters.peak_working_set_size),
        "structure_bytes": ctypes.sizeof(counters),
    }
