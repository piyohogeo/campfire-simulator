"""Read public MINIDUMP streams without installing a debugger.

The stack-address list is deliberately labelled heuristic: optimized native
frames cannot be unwound reliably without DbgEng/WinDbg and matching symbols.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def minidump_string(data: bytes, rva: int) -> str:
    length = u32(data, rva)
    return data[rva + 4 : rva + 4 + length].decode("utf-16-le", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive = args.zip.resolve()
    with zipfile.ZipFile(archive) as bundle:
        dmp_name = next(name for name in bundle.namelist() if name.lower().endswith(".dmp"))
        data = bundle.read(dmp_name)

    if data[:4] != b"MDMP":
        raise RuntimeError("not a MINIDUMP file")
    stream_count = u32(data, 8)
    directory_rva = u32(data, 12)
    streams: dict[int, tuple[int, int]] = {}
    for index in range(stream_count):
        entry = directory_rva + index * 12
        streams[u32(data, entry)] = (u32(data, entry + 4), u32(data, entry + 8))

    module_size, module_rva = streams[4]
    module_count = u32(data, module_rva)
    modules = []
    cursor = module_rva + 4
    for _ in range(module_count):
        base = u64(data, cursor)
        size = u32(data, cursor + 8)
        name = minidump_string(data, u32(data, cursor + 20))
        modules.append({"base": base, "size": size, "end": base + size, "name": name})
        cursor += 108
    modules.sort(key=lambda item: item["base"])

    def locate(address: int):
        for module in modules:
            if module["base"] <= address < module["end"]:
                return {
                    "module": module["name"],
                    "module_base": f"0x{module['base']:016X}",
                    "offset": f"0x{address - module['base']:X}",
                    "address": f"0x{address:016X}",
                }
        return {"module": None, "module_base": None, "offset": None, "address": f"0x{address:016X}"}

    exception_size, exception_rva = streams[6]
    thread_id = u32(data, exception_rva)
    exception_code = u32(data, exception_rva + 8)
    exception_flags = u32(data, exception_rva + 12)
    exception_address = u64(data, exception_rva + 24)
    parameter_count = u32(data, exception_rva + 32)
    parameters = [u64(data, exception_rva + 40 + i * 8) for i in range(min(parameter_count, 15))]
    context_size = u32(data, exception_rva + 160)
    context_rva = u32(data, exception_rva + 164)
    context = data[context_rva : context_rva + context_size]
    if len(context) < 256:
        raise RuntimeError("AMD64 context is unavailable")
    rsp = u64(context, 152)
    rbp = u64(context, 160)
    rip = u64(context, 248)

    thread_size, thread_rva = streams[3]
    thread_count = u32(data, thread_rva)
    stack = None
    cursor = thread_rva + 4
    for _ in range(thread_count):
        current_id = u32(data, cursor)
        if current_id == thread_id:
            stack_start = u64(data, cursor + 24)
            stack_size = u32(data, cursor + 32)
            stack_rva = u32(data, cursor + 36)
            stack = (stack_start, stack_size, stack_rva)
            break
        cursor += 48

    candidates = [dict(index=0, source="instruction_pointer", **locate(rip))]
    if stack is not None:
        stack_start, stack_size, stack_rva = stack
        start_offset = max(0, min(stack_size, rsp - stack_start))
        raw = data[stack_rva + start_offset : stack_rva + stack_size]
        seen = {rip}
        for offset in range(0, len(raw) - 7, 8):
            address = u64(raw, offset)
            located = locate(address)
            if located["module"] and address not in seen:
                seen.add(address)
                candidates.append(dict(index=len(candidates), source=f"stack_scan_rsp+0x{offset:X}", **located))
                if len(candidates) >= 64:
                    break

    report = {
        "schema": "campfire.phasev3tl.native-crash-analysis.v1",
        "status": "ok",
        "archive": str(archive),
        "archive_size": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest().upper(),
        "minidump_member": dmp_name,
        "minidump_size": len(data),
        "stream_types": sorted(streams),
        "exception": {
            "thread_id": thread_id,
            "code": f"0x{exception_code:08X}",
            "flags": f"0x{exception_flags:08X}",
            "address": f"0x{exception_address:016X}",
            "parameters": [f"0x{value:016X}" for value in parameters],
            "fault_location": locate(exception_address),
            "rip_location": locate(rip),
            "rsp": f"0x{rsp:016X}",
            "rbp": f"0x{rbp:016X}",
        },
        "native_stack": {
            "status": "heuristic_module_address_scan_only",
            "reason": "WinDbg/CDB/DumpChk and matching private symbols are unavailable; optimized frames cannot be authoritatively unwound",
            "candidates": candidates,
        },
        "module_count": len(modules),
        "limitations": [
            "Stack candidates after RIP are aligned pointer-like values found above RSP, not an authoritative unwind.",
            "A module/offset match does not establish root cause without symbols and a debugger unwind.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["exception"], indent=2))


if __name__ == "__main__":
    main()
