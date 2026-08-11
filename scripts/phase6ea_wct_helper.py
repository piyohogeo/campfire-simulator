from __future__ import annotations

import argparse
import ctypes
import json
import os
import struct
import time
from ctypes import wintypes
from pathlib import Path


MAX_NODE_COUNT = 16
WAIT_CHAIN_NODE_SIZE = 280
UNION_OFFSET = 8
OBJECT_NAME_CHARACTERS = 128
OBJECT_NAME_BYTES = OBJECT_NAME_CHARACTERS * 2
WCT_THREAD_TYPE = 8
TH32CS_SNAPTHREAD = 0x00000004
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _write_marker(path: Path | None, name: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.time_ns()}\t{name}\tpid={os.getpid()}\n".encode("utf-8")
    with path.open("ab", buffering=0) as stream:
        stream.write(line)
        os.fsync(stream.fileno())


def read_bounded_object_name(node: bytes | bytearray | memoryview) -> str:
    if len(node) < WAIT_CHAIN_NODE_SIZE:
        raise ValueError("WCT node buffer is smaller than the fixed structure size")
    encoded = bytes(node[UNION_OFFSET : UNION_OFFSET + OBJECT_NAME_BYTES])
    length = OBJECT_NAME_BYTES
    for offset in range(0, OBJECT_NAME_BYTES, 2):
        if encoded[offset : offset + 2] == b"\0\0":
            length = offset
            break
    return encoded[:length].decode("utf-16-le", errors="strict")


def decode_boundary_fixture(marker_path: Path | None) -> str:
    _write_marker(marker_path, "decode_boundary_fixture_started")
    node = bytearray([0x5A]) * WAIT_CHAIN_NODE_SIZE
    _write_marker(marker_path, "fixture_allocation_complete")
    encoded = ("X" * OBJECT_NAME_CHARACTERS).encode("utf-16-le")
    node[UNION_OFFSET : UNION_OFFSET + len(encoded)] = encoded
    _write_marker(marker_path, "bounded_copy_complete")
    value = read_bounded_object_name(node)
    _write_marker(marker_path, "read_bounded_object_name_complete")
    return value


def _thread_ids(process_id: int) -> list[int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    result: list[int] = []
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
            return result
        while True:
            if int(entry.th32OwnerProcessID) == process_id:
                result.append(int(entry.th32ThreadID))
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def collect_wait_chains(process_id: int) -> list[dict[str, object]]:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.OpenThreadWaitChainSession.argtypes = [wintypes.DWORD, ctypes.c_void_p]
    advapi32.OpenThreadWaitChainSession.restype = wintypes.HANDLE
    advapi32.GetThreadWaitChain.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetThreadWaitChain.restype = wintypes.BOOL
    advapi32.CloseThreadWaitChainSession.argtypes = [wintypes.HANDLE]
    advapi32.CloseThreadWaitChainSession.restype = None

    session = advapi32.OpenThreadWaitChainSession(0, None)
    if not session:
        raise ctypes.WinError(ctypes.get_last_error())
    chains: list[dict[str, object]] = []
    try:
        for thread_id in _thread_ids(process_id):
            count = wintypes.DWORD(MAX_NODE_COUNT)
            is_cycle = wintypes.BOOL(False)
            nodes = (ctypes.c_ubyte * (WAIT_CHAIN_NODE_SIZE * MAX_NODE_COUNT))()
            ok = bool(
                advapi32.GetThreadWaitChain(
                    session,
                    None,
                    0,
                    thread_id,
                    ctypes.byref(count),
                    ctypes.byref(nodes),
                    ctypes.byref(is_cycle),
                )
            )
            if count.value > MAX_NODE_COUNT:
                raise RuntimeError("WCT returned a node count beyond the allocated maximum")
            error_code = 0 if ok else ctypes.get_last_error()
            chain: dict[str, object] = {
                "thread_id": thread_id,
                "call_succeeded": ok,
                "is_cycle": bool(is_cycle.value),
                "error_code": error_code,
                "nodes": [],
            }
            if ok:
                raw = bytes(nodes)
                decoded_nodes: list[dict[str, object]] = []
                for index in range(count.value):
                    start = index * WAIT_CHAIN_NODE_SIZE
                    node = raw[start : start + WAIT_CHAIN_NODE_SIZE]
                    object_type, object_status = struct.unpack_from("<II", node, 0)
                    thread_node = object_type == WCT_THREAD_TYPE
                    process_node_id, node_thread_id, wait_time_ms, context_switches = (
                        struct.unpack_from("<IIII", node, UNION_OFFSET) if thread_node else (0, 0, 0, 0)
                    )
                    decoded_nodes.append(
                        {
                            "object_type": object_type,
                            "object_status": object_status,
                            "object_name": None if thread_node else read_bounded_object_name(node),
                            "process_id": process_node_id,
                            "thread_id": node_thread_id,
                            "wait_time_ms": wait_time_ms,
                            "context_switches": context_switches,
                        }
                    )
                chain["nodes"] = decoded_nodes
            chains.append(chain)
    finally:
        advapi32.CloseThreadWaitChainSession(session)
    return chains


def _write_json(path: Path, payload: dict[str, object], marker_path: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _write_marker(marker_path, "json_serialization_complete")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())
    _write_marker(marker_path, "json_write_complete")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Phase 6EA WCT helper")
    parser.add_argument("--target-process-id", type=int, default=0)
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--object-name-boundary-fixture", action="store_true")
    parser.add_argument("--fixture-hang-seconds", type=int, default=0)
    parser.add_argument("--durable-marker-path", type=Path)
    args = parser.parse_args()

    _write_marker(args.durable_marker_path, "python_process_entry")
    _write_marker(args.durable_marker_path, "parameter_binding_complete")
    _write_marker(args.durable_marker_path, "dynamic_add_type_not_used")
    if args.fixture_hang_seconds > 0:
        time.sleep(args.fixture_hang_seconds)

    constants = {
        "max_node_count": MAX_NODE_COUNT,
        "node_size": WAIT_CHAIN_NODE_SIZE,
        "union_offset": UNION_OFFSET,
        "object_name_characters": OBJECT_NAME_CHARACTERS,
    }
    if args.object_name_boundary_fixture:
        value = decode_boundary_fixture(args.durable_marker_path)
        payload: dict[str, object] = {
            "schema": "campfire.phase6ea.wct-boundary-fixture.v1",
            "value": value,
            "length": len(value),
            "constants": constants,
        }
    else:
        if args.target_process_id <= 0:
            parser.error("--target-process-id is required outside fixture mode")
        payload = {
            "schema": "campfire.phase6ea.wct-helper.v1",
            "target_pid": args.target_process_id,
            "status": "ok",
            "chains": collect_wait_chains(args.target_process_id),
            "constants": constants,
        }
    _write_json(args.output_path.resolve(), payload, args.durable_marker_path)
    _write_marker(args.durable_marker_path, "python_process_exit_imminent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
