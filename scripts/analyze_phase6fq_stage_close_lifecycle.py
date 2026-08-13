"""Aggregate bounded Phase 6FQ stage-close lifecycle evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path


def _json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _duration(markers: list[dict], first: str, last: str):
    start = next((row for row in markers if row.get("marker") == first), None)
    end = next((row for row in markers if row.get("marker") == last), None)
    if not start or not end:
        return None
    if start.get("perf_counter_ns") is not None and end.get("perf_counter_ns") is not None:
        return (int(end["perf_counter_ns"]) - int(start["perf_counter_ns"])) / 1e9
    try:
        return (datetime.fromisoformat(end["timestamp_utc"]) - datetime.fromisoformat(start["timestamp_utc"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None


def _attempt(path: Path, contract: dict) -> dict:
    metadata = _json(path / "attempt_metadata.json") or {}
    case = path / "case"
    raw = _json(case / "raw.json") or {}
    guard = _json(path / "runner-logs" / "guard.json") or {}
    markers = _jsonl(case / "resource_markers.jsonl")
    marker_names = [str(row.get("marker")) for row in markers]
    diagnostic = _json(case / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json") or {}
    debugger = diagnostic.get("debugger") or {}
    stack = diagnostic.get("stack_fingerprint") or {}
    completion = raw.get("completion_contract") or {}
    startup = raw.get("startup_liveness_gate") or {}
    capture = raw.get("capture_lifecycle_preparation") or {}
    required = list(contract["required_markers"])
    missing = [value for value in required if value not in marker_names]
    readback_calls = int((raw.get("readback_operation_count") or 0))
    captures = len(raw.get("captures") or [])
    failures = []
    if guard.get("status") != "ok":
        failures.append(f"guard:{guard.get('stop_reason') or guard.get('status') or 'missing'}")
    if raw.get("status") != "ok":
        failures.append(f"probe:{raw.get('status') or 'missing'}")
    if startup.get("classification") != "representative_ingestion" or not startup.get("readback_permitted"):
        failures.append(f"startup:{startup.get('classification') or 'missing'}")
    for key in ("results_saved", "timeline_stopped", "stage_closed", "renderer_drained", "shutdown_requested"):
        if completion.get(key) is not True:
            failures.append(f"completion:{key}")
    if missing:
        failures.append("markers:" + ",".join(missing))
    if readback_calls or captures:
        failures.append("forbidden_runtime_operation")
    if capture.get("capture_calls", 0) or capture.get("pixel_buffer_bytes", 0) or capture.get("video_generation_calls", 0):
        failures.append("capture_body_created")
    cleanup = guard.get("observed_process_cleanup") or {}
    if cleanup.get("all_observed_absent") is not True:
        failures.append("cleanup_residual")
    classification = "representative_pass" if not failures else "nonreplaceable_failure"
    if failures and all(value.startswith("startup:") for value in failures):
        classification = "startup_prerequisite_failure"
    return {
        "attempt_id": metadata.get("attempt_id", path.name),
        "slot_id": metadata.get("slot_id"),
        "sequence": metadata.get("sequence"),
        "position": metadata.get("position"),
        "condition": metadata.get("condition"),
        "settings": metadata.get("settings"),
        "classification": classification,
        "failures": failures,
        "last_marker": marker_names[-1] if marker_names else diagnostic.get("lifecycle_marker"),
        "marker_count": len(markers),
        "missing_markers": missing,
        "stage_close_seconds": _duration(markers, "stage_close_request_before", "stage_close_request_after"),
        "stage_close_timeout_seconds": _duration(markers, "stage_close_request_before", "stage_close_timeout"),
        "renderer_drain_seconds": _duration(markers, "renderer_drain_started", "renderer_drain_complete"),
        "extension_shutdown_markers": [
            row.get("marker") or row.get("name") for row in _jsonl(case / "extension_lifecycle_markers.jsonl")
        ],
        "capture_preparation": capture,
        "active_blocks_final": raw.get("active_blocks_final"),
        "readback_calls": readback_calls,
        "guard_status": guard.get("status"),
        "guard_stop_reason": guard.get("stop_reason"),
        "process_exit_code": guard.get("exit_code"),
        "resource_peaks_bytes": guard.get("peaks"),
        "machine_minima_bytes": guard.get("machine_minima"),
        "cleanup": cleanup,
        "diagnostic": {
            "started": bool(diagnostic),
            "lifecycle_marker": diagnostic.get("lifecycle_marker"),
            "capture_succeeded": diagnostic.get("diagnostic_capture_succeeded"),
            "cdb_timed_out": debugger.get("timed_out"),
            "modules_observed": debugger.get("loaded_modules_observed"),
            "all_thread_stack_observed": debugger.get("all_thread_stack_observed"),
            "detach_observed": debugger.get("detach_observed"),
            "attach_observed": debugger.get("attach_observed"),
            "module_pass": (debugger.get("passes") or {}).get("attach_and_modules"),
            "all_thread_stack_pass": (debugger.get("passes") or {}).get("all_thread_stacks"),
            "detach_recovery_pass": (debugger.get("passes") or {}).get("detach_recovery"),
            "known_ngx_signature": stack.get("matched"),
        },
    }


def build(root: Path, contract_path: Path) -> dict:
    contract = _json(contract_path)
    if not contract:
        raise ValueError("invalid contract")
    attempts_root = root / "attempts"
    attempts = [_attempt(path, contract) for path in sorted(attempts_root.glob("attempt*")) if path.is_dir()]
    failures = [value for value in attempts if value["classification"] == "nonreplaceable_failure"]
    startup = [value for value in attempts if value["classification"] == "startup_prerequisite_failure"]
    passes = [value for value in attempts if value["classification"] == "representative_pass"]
    planned = sum(len(value) for value in contract["population"]["orders"])
    by_condition = {}
    for row in attempts:
        by_condition.setdefault(str(row["condition"]), []).append(row)
    return {
        "schema": "campfire.phase6fq.stage-close-lifecycle-report.v1",
        "phase": "phase6fq",
        "contract_sha256": (root / "frozen_contract.sha256").read_text(encoding="utf-8").split()[0],
        "population": {
            "planned": planned,
            "launched": len(attempts),
            "representative_pass": len(passes),
            "startup_prerequisite_failure": len(startup),
            "nonreplaceable_failure": len(failures),
        },
        "qualification_complete": len(passes) == planned and not failures,
        "safe_stop": failures[0] if failures else None,
        "attempts": attempts,
        "conditions": {
            key: {
                "runs": len(rows),
                "passes": sum(row["classification"] == "representative_pass" for row in rows),
                "stage_close_seconds": [row["stage_close_seconds"] for row in rows],
            }
            for key, rows in by_condition.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root.resolve(), args.contract.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
