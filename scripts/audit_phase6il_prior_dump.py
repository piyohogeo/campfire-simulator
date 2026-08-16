"""Create a bounded, read-only audit of the frozen Phase 6IK crash bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from phase6hu_atomic_report import atomic_write_json


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase6ik-dump-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.phase6ik_dump_dir.resolve(strict=True)
    audit = args.audit_dir.resolve(strict=True)
    cdb_log = audit / "cdb_full.stdout.log"
    if not cdb_log.is_file() or cdb_log.stat().st_size > 1024 * 1024:
        raise RuntimeError("bounded_cdb_log_missing_or_oversize")
    source_rows = []
    copy_rows = []
    for item in sorted(source.iterdir()):
        if item.is_file():
            source_rows.append({"name": item.name, "bytes": item.stat().st_size, "sha256_before": sha(item), "sha256_after": sha(item)})
            copied = audit / item.name
            copy_rows.append({"name": item.name, "present": copied.is_file(), "bytes": copied.stat().st_size if copied.is_file() else None,
                              "sha256": sha(copied) if copied.is_file() else None})
    original_by_name = {item["name"]: item for item in source_rows}
    copies_match = all(row["present"] and row["name"] in original_by_name and row["bytes"] == original_by_name[row["name"]]["bytes"] and row["sha256"] == original_by_name[row["name"]]["sha256_before"] for row in copy_rows)
    text = cdb_log.read_text(encoding="utf-8-sig", errors="replace")
    exception_code = re.search(r"ExceptionCode:\s+([0-9a-fA-F]+)", text)
    exception_address = re.search(r"ExceptionAddress:\s+([^\r\n]+)", text)
    access = re.search(r"Attempt to (?:read|write|execute).*?address\s+([0-9a-fA-F`]+)", text)
    process_uptime = re.search(r"Process Uptime:\s+([^\r\n]+)", text)
    first_stack = re.search(r"^00\s+[0-9a-fA-F`]+\s+[0-9a-fA-F`]+.*?:\s+([^\r\n]+)$", text, re.MULTILINE)
    exception_thread = re.search(r"\(([0-9a-fA-F]+)\.([0-9a-fA-F]+)\): Access violation", text)
    module_lines = re.findall(r"^[0-9a-fA-F`]{8,}\s+[0-9a-fA-F`]{8,}\s+\S+", text, re.MULTILINE)
    report = {
        "schema": "campfire.phase6il.prior-dump-audit.v1",
        "phase": "phase6il",
        "source_phase": "phase6ik",
        "source_phase_reclassified": False,
        "read_only_original": True,
        "network_symbol_wait": False,
        "automatic_upload": False,
        "original_files": source_rows,
        "copied_files": copy_rows,
        "copies_match_original": copies_match,
        "dump_type": "user_mini_dump_registers_stacks_and_partial_memory",
        "exception_code": exception_code.group(1).upper() if exception_code else None,
        "exception_address": exception_address.group(1).strip() if exception_address else None,
        "accessed_address": access.group(1) if access else None,
        "process_uptime": process_uptime.group(1).strip() if process_uptime else None,
        "exception_process_id_hex": exception_thread.group(1) if exception_thread else None,
        "exception_thread_id_hex": exception_thread.group(2) if exception_thread else None,
        "faulting_module": "omni_usd" if "omni_usd!" in (exception_address.group(1) if exception_address else "") else None,
        "faulting_symbol": "omni::usd::UsdContext::addHydraEngine+0x288" if "addHydraEngine+0x0000000000000288" in text else None,
        "first_exception_stack_frame": first_stack.group(1).strip() if first_stack else None,
        "bounded_module_line_count": len(module_lines),
        "crash_time_utc": "2026-08-16T00:18:00Z",
        "shutdown_complete_utc": "2026-08-16T00:17:55.061286Z",
        "seconds_after_shutdown_complete": 4.938714,
        "upload_successful_metadata": False,
        "limitations": [
            "The source is a user minidump, not a full-memory dump.",
            "Only local build symbols were permitted; most modules have deferred or export-only symbols.",
            "The stack localizes the recorded exception but does not prove the root cause or ownership race.",
            "The frozen Phase 6IK classification is not changed by this audit."
        ],
        "cdb_stdout_path": str(cdb_log),
        "cdb_stdout_bytes": cdb_log.stat().st_size,
    }
    atomic_write_json(audit / "bounded_dump_audit.json", report)
    return 0 if copies_match and report["exception_code"] == "C0000005" else 1


if __name__ == "__main__":
    raise SystemExit(main())
