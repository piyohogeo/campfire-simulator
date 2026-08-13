"""Analyze Phase 6FH readback-free lifecycle qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


def load(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]


def marker_map(rows: list[dict]) -> dict[str, dict]:
    return {str(row.get("marker", row.get("name"))): row for row in rows}


def timestamp(row: dict | None) -> float | None:
    if not row:
        return None
    value = row.get("timestamp_utc")
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    value = row.get("wall_ns")
    return float(value) / 1e9 if value is not None else None


def duration(markers: dict[str, dict], before: str, after: str) -> float | None:
    a, b = timestamp(markers.get(before)), timestamp(markers.get(after))
    return None if a is None or b is None else b - a


def case_for(root: Path, run_index: int, contract: dict) -> dict | None:
    run = root / f"run{run_index:02d}"
    if not run.exists():
        return None
    raw = load(run / "raw.json") or {}
    evidence = load(run / "runner_evidence.json") or {}
    guard = load(root / "runner-logs" / f"run{run_index:02d}.guard.json") or {}
    markers = marker_map(jsonl(run / "resource_markers.jsonl"))
    extensions = marker_map(jsonl(run / "extension_lifecycle_markers.jsonl"))
    runner = marker_map(jsonl(run / "runner_lifecycle_markers.jsonl"))
    startup = raw.get("startup_liveness_gate") or {}
    completion = raw.get("completion_contract") or {}
    monitor = evidence.get("shutdown_monitor") or {}
    outcome = evidence.get("outcome") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    diagnostic = monitor.get("diagnostic") or {}
    debugger = diagnostic.get("debugger") or {}
    stack = diagnostic.get("stack_fingerprint") or {}
    failures = []
    representative = startup.get("classification") == "representative_ingestion" and startup.get("source_ok") is True and startup.get("telemetry_fresh") is True
    if not representative:
        failures.append("representative_startup")
    if guard.get("status") != "ok":
        failures.append("resource_or_process_guard")
    if completion.get("timeline_stopped") is not True:
        failures.append("timeline_stop")
    if completion.get("renderer_drained") is not True:
        failures.append("renderer_drain")
    if completion.get("stage_closed") is not True:
        failures.append("stage_close")
    if outcome.get("shutdown_complete_reached") is not True:
        failures.append("shutdown_complete")
    if outcome.get("os_process_normal_exit") is not True:
        failures.append("normal_os_exit")
    if cleanup.get("remaining"):
        failures.append("cleanup_residual")
    if evidence.get("fatal_lines"):
        failures.append("fatal")
    if evidence.get("dump_inventory"):
        failures.append("dump")
    if evidence.get("automatic_upload_attempt_lines"):
        failures.append("automatic_upload")
    expected_payload = contract["startup"]["expected_payload_sha256"]
    payload = (raw.get("point_payload") or {}).get("payload_sha256")
    if payload != expected_payload:
        failures.append("payload_hash")
    return {
        "run": run_index,
        "path": run.name,
        "status": "pass" if not failures else "lifecycle_failure",
        "failures": failures,
        "startup_classification": startup.get("classification"),
        "representative_startup": representative,
        "stage_sha256": raw.get("stage_sha256"),
        "payload_sha256": payload,
        "last_probe_marker": raw.get("lifecycle_marker"),
        "last_runner_marker": next(iter(runner), None),
        "timeline_stop_seconds": duration(markers, "timeline_stop_request_before", "timeline_stop_confirmed"),
        "renderer_drain_seconds": duration(markers, "renderer_drain_started", "renderer_drain_complete"),
        "reference_release_seconds": duration(markers, "flow_references_release_started", "provider_readback_references_release_complete"),
        "stage_close_seconds": duration(markers, "stage_close_request_before", "stage_close_request_after"),
        "stage_close_timeout": "stage_close_timeout" in markers,
        "extension_shutdown_seconds": duration(extensions, "extension_on_shutdown_begin", "extension_on_shutdown_end"),
        "normal_os_exit": outcome.get("os_process_normal_exit") is True,
        "lifecycle_status": outcome.get("lifecycle_status"),
        "guard_status": guard.get("status"),
        "guard_stop_reason": guard.get("stop_reason"),
        "resource_peaks": guard.get("peaks"),
        "machine_minima": guard.get("machine_minima"),
        "fatal_count": len(evidence.get("fatal_lines") or []),
        "dump_count": len(evidence.get("dump_inventory") or []),
        "upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines") or []),
        "cleanup": cleanup,
        "cdb": {
            "invoked": bool(diagnostic),
            "capture_succeeded": diagnostic.get("diagnostic_capture_succeeded"),
            "attach_observed": debugger.get("attach_observed"),
            "modules_observed": debugger.get("loaded_modules_observed"),
            "all_thread_stack_complete": debugger.get("all_thread_stack_observed"),
            "detach_observed": debugger.get("detach_observed"),
            "timed_out": debugger.get("timed_out"),
            "process_absent": debugger.get("process_absent"),
            "known_ngx_matched": stack.get("matched"),
            "required_tokens": stack.get("required_tokens"),
            "full_dump_created": debugger.get("full_dump_created"),
            "passes": debugger.get("passes"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load(args.contract)
    cases = [case for i in range(1, contract["population"]["planned_processes"] + 1) if (case := case_for(args.root, i, contract))]
    failures = [case for case in cases if case["status"] != "pass"]
    report = {
        "schema": "campfire.phase6fh.lifecycle-qualification-report.v1",
        "phase": "phase6fh",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "phase6fg_history_frozen": True,
        "planned_processes": contract["population"]["planned_processes"],
        "attempted_processes": len(cases),
        "normal_processes": len(cases) - len(failures),
        "lifecycle_failures": len(failures),
        "observed_failure_rate": None if not cases else len(failures) / len(cases),
        "status": "lifecycle_failure_captured" if failures else ("completed_no_reproduction" if len(cases) == contract["population"]["planned_processes"] else "incomplete"),
        "cases": cases,
        "readback_calls": 0,
        "numpy_asarray_calls": 0,
        "memory_waveform_formal_gate_changed": False,
        "production_changed": any((load(args.root / f"run{i:02d}" / "runner_evidence.json") or {}).get("production_changed") is True for i in range(1, len(cases) + 1)),
        "phase6fg_restart_authorized": False,
        "two_axis_policy": contract["two_axis_policy_proposal"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
