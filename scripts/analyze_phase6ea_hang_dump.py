"""Read public MINIDUMP streams from a Phase 6EA full hang capture.

The dump stays memory-mapped and is never copied into the repository.  This
records captured thread instruction pointers and their containing modules; it
does not claim to reconstruct native stacks without a debugger and symbols.
"""

from __future__ import annotations

import argparse
import json
import mmap
import struct
from pathlib import Path


STREAM_NAMES = {
    3: "ThreadListStream",
    4: "ModuleListStream",
    5: "MemoryListStream",
    6: "ExceptionStream",
    7: "SystemInfoStream",
    9: "Memory64ListStream",
    15: "MiscInfoStream",
    16: "MemoryInfoListStream",
    17: "ThreadInfoListStream",
    19: "HandleOperationListStream",
    21: "TokenStream",
}


def u32(data, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _utf16(data, rva: int) -> str:
    length = u32(data, rva)
    return bytes(data[rva + 4 : rva + 4 + length]).decode("utf-16-le", errors="replace")


def _streams(data) -> dict[int, dict]:
    if bytes(data[:4]) != b"MDMP":
        raise RuntimeError("Not a MINIDUMP")
    count = u32(data, 8)
    directory_rva = u32(data, 12)
    result = {}
    for index in range(count):
        entry = directory_rva + index * 12
        stream_type = u32(data, entry)
        result[stream_type] = {
            "type": stream_type,
            "name": STREAM_NAMES.get(stream_type, f"Stream{stream_type}"),
            "size": u32(data, entry + 4),
            "rva": u32(data, entry + 8),
        }
    return result


def _modules(data, stream: dict | None) -> list[dict]:
    if not stream:
        return []
    offset = stream["rva"]
    count = u32(data, offset)
    result = []
    for index in range(count):
        item = offset + 4 + index * 108
        result.append(
            {
                "base": u64(data, item),
                "size": u32(data, item + 8),
                "checksum": u32(data, item + 12),
                "timestamp": u32(data, item + 16),
                "name": _utf16(data, u32(data, item + 20)),
            }
        )
    return result


def _module_for(address: int, modules: list[dict]) -> dict | None:
    for module in modules:
        if module["base"] <= address < module["base"] + module["size"]:
            return {
                "name": module["name"],
                "base": f"0x{module['base']:016X}",
                "offset": f"0x{address - module['base']:X}",
            }
    return None


def _thread_info(data, stream: dict | None) -> dict[int, dict]:
    if not stream:
        return {}
    offset = stream["rva"]
    header_size = u32(data, offset)
    entry_size = u32(data, offset + 4)
    count = u32(data, offset + 8)
    result = {}
    for index in range(count):
        item = offset + header_size + index * entry_size
        tid = u32(data, item)
        result[tid] = {
            "dump_flags": u32(data, item + 4),
            "dump_error": u32(data, item + 8),
            "exit_status": u32(data, item + 12),
            "create_time_100ns": u64(data, item + 16),
            "exit_time_100ns": u64(data, item + 24),
            "kernel_time_100ns": u64(data, item + 32),
            "user_time_100ns": u64(data, item + 40),
            "start_address": f"0x{u64(data, item + 48):016X}",
            "affinity": f"0x{u64(data, item + 56):X}",
        }
    return result


def _memory64_ranges(data, stream: dict | None) -> list[dict]:
    if not stream:
        return []
    offset = stream["rva"]
    count = u64(data, offset)
    file_rva = u64(data, offset + 8)
    result = []
    for index in range(count):
        item = offset + 16 + index * 16
        start = u64(data, item)
        size = u64(data, item + 8)
        result.append({"start": start, "size": size, "file_rva": file_rva})
        file_rva += size
    return result


def _virtual_to_file(address: int, ranges: list[dict]) -> tuple[int, int] | None:
    for item in ranges:
        if item["start"] <= address < item["start"] + item["size"]:
            return item["file_rva"] + address - item["start"], item["start"] + item["size"] - address
    return None


def _threads(data, stream: dict | None, modules: list[dict], info: dict[int, dict], memory64: list[dict]) -> list[dict]:
    if not stream:
        return []
    offset = stream["rva"]
    count = u32(data, offset)
    result = []
    for index in range(count):
        item = offset + 4 + index * 48
        tid = u32(data, item)
        context_size = u32(data, item + 40)
        context_rva = u32(data, item + 44)
        row = {
            "thread_id": tid,
            "suspend_count": u32(data, item + 4),
            "priority_class": u32(data, item + 8),
            "priority": u32(data, item + 12),
            "teb": f"0x{u64(data, item + 16):016X}",
            "stack_start": f"0x{u64(data, item + 24):016X}",
            "stack_bytes": u32(data, item + 32),
            "context_bytes": context_size,
            "thread_info": info.get(tid),
        }
        if context_size >= 256:
            flags = u32(data, context_rva + 48)
            rip = u64(data, context_rva + 248)
            rsp = u64(data, context_rva + 152)
            row.update(
                {
                    "context_flags": f"0x{flags:08X}",
                    "instruction_pointer": f"0x{rip:016X}",
                    "stack_pointer": f"0x{rsp:016X}",
                    "instruction_module": _module_for(rip, modules),
                }
            )
            mapped = _virtual_to_file(rsp, memory64)
            candidates = []
            if mapped:
                stack_rva, remaining = mapped
                scan_bytes = min(65536, remaining)
                for stack_offset in range(0, max(0, scan_bytes - 7), 8):
                    address = u64(data, stack_rva + stack_offset)
                    module = _module_for(address, modules)
                    if module:
                        candidates.append(
                            {
                                "stack_offset": stack_offset,
                                "address": f"0x{address:016X}",
                                "module": module,
                            }
                        )
                        if len(candidates) >= 64:
                            break
            row["stack_module_candidates"] = candidates
        result.append(row)
    return result


def analyze(path: Path) -> dict:
    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        streams = _streams(data)
        modules = _modules(data, streams.get(4))
        info = _thread_info(data, streams.get(17))
        memory64 = _memory64_ranges(data, streams.get(9))
        threads = _threads(data, streams.get(3), modules, info, memory64)
        live_threads = [
            thread for thread in threads
            if thread.get("thread_info") and thread["thread_info"].get("create_time_100ns")
        ]
        earliest_thread_id = min(
            live_threads,
            key=lambda thread: thread["thread_info"]["create_time_100ns"],
            default={},
        ).get("thread_id")
        module_counts: dict[str, int] = {}
        for thread in threads:
            module = thread.get("instruction_module")
            name = Path(module["name"]).name if module else "unmapped"
            module_counts[name] = module_counts.get(name, 0) + 1
        misc = streams.get(15)
        process_id = None
        if misc and misc["size"] >= 12 and (u32(data, misc["rva"] + 4) & 1):
            process_id = u32(data, misc["rva"] + 8)
        return {
            "schema": "campfire.phase6ea.hang-dump-analysis.v1",
            "phase": "phase6ea",
            "dump_path": str(path),
            "dump_bytes": path.stat().st_size,
            "process_id": process_id,
            "streams": list(streams.values()),
            "module_count": len(modules),
            "modules": [
                {
                    **module,
                    "base": f"0x{module['base']:016X}",
                }
                for module in modules
            ],
            "full_memory_range_count": len(memory64),
            "thread_count": len(threads),
            "earliest_created_thread_id": earliest_thread_id,
            "instruction_module_counts": dict(sorted(module_counts.items(), key=lambda item: (-item[1], item[0]))),
            "threads": threads,
            "stack_analysis": {
                "available": False,
                "reason": "No WinDbg/CDB/ProcDump is installed; public MINIDUMP streams expose captured contexts but this parser does not unwind native stacks.",
            },
            "exception_stream_present": 6 in streams,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.dump.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("process_id", "module_count", "thread_count", "instruction_module_counts")}, indent=2))


if __name__ == "__main__":
    main()
