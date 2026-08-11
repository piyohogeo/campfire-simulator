"""Analyze preserved Phase 6DT/6DU minidumps without extracting them.

This is intentionally a small, read-only MINIDUMP parser.  It records the
exception stream and module-relative instruction address even when WinDbg/CDB
and private NVIDIA symbols are unavailable.  It does not upload, modify, or
copy the sensitive dump payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath


MINIDUMP_SIGNATURE = b"MDMP"
MODULE_LIST_STREAM = 4
EXCEPTION_STREAM = 6
ACCESS_KIND = {0: "read", 1: "write", 8: "execute"}


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _utf16_string(data: bytes, rva: int) -> str:
    size = _u32(data, rva)
    return data[rva + 4 : rva + 4 + size].decode("utf-16-le", errors="replace")


def _directory(data: bytes) -> dict[int, tuple[int, int]]:
    if data[:4] != MINIDUMP_SIGNATURE:
        raise ValueError("Not a Windows minidump")
    count = _u32(data, 8)
    rva = _u32(data, 12)
    result = {}
    for index in range(count):
        offset = rva + index * 12
        stream_type, size, stream_rva = struct.unpack_from("<III", data, offset)
        result[stream_type] = (stream_rva, size)
    return result


def _modules(data: bytes, streams: dict[int, tuple[int, int]]) -> list[dict]:
    rva, _ = streams[MODULE_LIST_STREAM]
    count = _u32(data, rva)
    result = []
    cursor = rva + 4
    for _ in range(count):
        base = _u64(data, cursor)
        size = _u32(data, cursor + 8)
        timestamp = _u32(data, cursor + 16)
        name = _utf16_string(data, _u32(data, cursor + 20))
        result.append(
            {
                "name": str(PureWindowsPath(name).name),
                "path": name,
                "base": base,
                "size": size,
                "timestamp": timestamp,
            }
        )
        cursor += 108
    return result


def _exception(data: bytes, streams: dict[int, tuple[int, int]], modules: list[dict]) -> dict:
    rva, _ = streams[EXCEPTION_STREAM]
    thread_id = _u32(data, rva)
    record = rva + 8
    code = _u32(data, record)
    flags = _u32(data, record + 4)
    address = _u64(data, record + 16)
    parameter_count = min(_u32(data, record + 24), 15)
    parameters = [_u64(data, record + 32 + 8 * index) for index in range(parameter_count)]
    module = next(
        (item for item in modules if item["base"] <= address < item["base"] + item["size"]),
        None,
    )
    result = {
        "thread_id": thread_id,
        "exception_code": f"0x{code:08X}",
        "exception_flags": flags,
        "instruction_address": f"0x{address:016X}",
        "parameters": [f"0x{value:X}" for value in parameters],
        "fault_module": module["name"] if module else None,
        "fault_module_offset": f"0x{address - module['base']:X}" if module else None,
    }
    if code == 0xC0000005 and len(parameters) >= 2:
        result["access_kind"] = ACCESS_KIND.get(parameters[0], f"unknown({parameters[0]})")
        result["access_target"] = f"0x{parameters[1]:X}"
    return result


def analyze(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        dump_names = [name for name in archive.namelist() if name.lower().endswith(".dmp")]
        if len(dump_names) != 1:
            raise ValueError(f"Expected one .dmp in {path}, found {len(dump_names)}")
        data = archive.read(dump_names[0])
    streams = _directory(data)
    modules = _modules(data, streams)
    return {
        "path": str(path),
        "zip_size_bytes": path.stat().st_size,
        "zip_sha256": _sha256(path),
        "embedded_dump_name": dump_names[0],
        "embedded_dump_size_bytes": len(data),
        "stream_types": sorted(streams),
        "exception": _exception(data, streams, modules),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    results = [analyze(path.resolve()) for path in args.dump]
    signatures = {
        (
            item["exception"]["exception_code"],
            item["exception"]["fault_module"],
            item["exception"]["fault_module_offset"],
            item["exception"].get("access_kind"),
            item["exception"].get("access_target"),
        )
        for item in results
    }
    payload = {
        "schema": "campfire.phase6dv.stage-open-crash-analysis.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_method": "public MINIDUMP ExceptionStream and ModuleListStream; no symbols",
        "debugger_available": False,
        "symbol_limit": "Function names and native locals are not qualified without WinDbg/CDB symbols.",
        "same_fault_signature": len(signatures) == 1,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
