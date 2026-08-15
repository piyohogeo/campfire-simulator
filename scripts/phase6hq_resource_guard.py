"""Phase 6HQ guard adapter with canonical lifecycle classification."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil

import phase6eg_resource_guard as legacy
import phase6fu_resource_guard as phase6fu
from phase6fu_process_identity import (
    ACCESS_DENIED_UNKNOWN,
    ALIVE_IDENTITY_MATCH,
    ALIVE_IDENTITY_MISMATCH,
    CONFIRMED_EXITED,
    UNKNOWN_STATES,
    append_jsonl,
    make_identity,
    query_identity,
)
from phase6hq_lifecycle_classification import (
    attach_evaluation,
    build_evidence,
    read_jsonl,
)


def _write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def exact_cleanup_with_times(identities, *, marker_path=None, retry_count=4, retry_seconds=0.25) -> dict:
    records = list(identities)
    before, killed, protected, unknown = [], [], [], []
    append_jsonl(marker_path, {"marker": "exact_cleanup_started", "identity_count": len(records), "timestamp_utc_epoch": time.time()})
    for identity in reversed(records):
        result = query_identity(identity)
        before.append(result)
        state = result["state"]
        if state == ALIVE_IDENTITY_MATCH:
            requested = time.time()
            try:
                psutil.Process(int(identity["pid"])).kill()
                killed_identity = dict(identity)
                killed_identity["termination_requested_at_utc_epoch"] = requested
                identity["termination_requested_at_utc_epoch"] = requested
                killed.append(killed_identity)
                append_jsonl(marker_path, {"marker": "exact_identity_stop_requested", "identity": killed_identity, "timestamp_utc_epoch": requested})
            except (psutil.NoSuchProcess, ProcessLookupError):
                pass
            except (psutil.AccessDenied, PermissionError, OSError) as error:
                unknown.append({"identity": identity, "state": ACCESS_DENIED_UNKNOWN, "error": str(error)})
        elif state == ALIVE_IDENTITY_MISMATCH:
            protected.append(result)
        elif state in UNKNOWN_STATES:
            unknown.append(result)
    final = []
    for attempt in range(max(1, retry_count)):
        final = [query_identity(item) for item in records]
        if all(item["state"] in {CONFIRMED_EXITED, ALIVE_IDENTITY_MISMATCH} for item in final):
            break
        if attempt + 1 < retry_count:
            time.sleep(retry_seconds)
    matching = [item for item in final if item["state"] == ALIVE_IDENTITY_MATCH]
    final_unknown = [item for item in final if item["state"] in UNKNOWN_STATES]
    summary = {
        "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
        "observed_identity_count": len(records),
        "before": before,
        "killed": killed,
        "protected_identity_mismatch": protected,
        "query_unknown": unknown,
        "final": final,
        "matching_remaining": matching,
        "final_unknown": final_unknown,
        "all_matching_absent": not matching and not final_unknown,
        "cleanup_required": bool(killed or matching or final_unknown),
        "killed_pids": [int(item["pid"]) for item in killed],
        "remaining": [item["identity"] for item in matching + final_unknown],
        "all_observed_absent": not matching and not final_unknown,
        "absence_confirmation_sources": ["psutil", "win32"],
        "completed_at_utc_epoch": time.time(),
    }
    append_jsonl(marker_path, {"marker": "exact_cleanup_complete", "all_matching_absent": summary["all_matching_absent"], "timestamp_utc_epoch": time.time()})
    return summary


def cleanup_observed_exact(observed, root_pid):
    suppression = phase6fu._suppression()
    identities = []
    for record in observed.values():
        parent_pid = None
        try:
            parent_pid = psutil.Process(int(record["pid"])).ppid()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            pass
        identities.append(make_identity(
            pid=int(record["pid"]), create_time_utc_epoch=float(record["create_time_utc_epoch"]),
            path=str(record["path"]), parent_pid=parent_pid, role=str(record.get("role", "child")),
            attempt_id=phase6fu.ATTEMPT_ID,
        ))
    summary = exact_cleanup_with_times(identities, marker_path=phase6fu.MARKER_PATH)
    summary["root_pid"] = root_pid
    summary["cleanup_suppression"] = suppression
    return summary


def _read(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise RuntimeError("bounded_json_unavailable:" + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = legacy._parser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--cleanup-suppression-lock", type=Path)
    parser.add_argument("--cleanup-suppression-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--cleanup-marker-path", type=Path)
    parser.add_argument("--runner-evidence-path", type=Path, required=True)
    parser.add_argument("--marker-path", type=Path, required=True)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "proxy"), required=True)
    arguments = parser.parse_args()
    phase6fu.ATTEMPT_ID = arguments.attempt_id
    phase6fu.LOCK_PATH = arguments.cleanup_suppression_lock
    phase6fu.LOCK_DEADLINE = arguments.cleanup_suppression_deadline_seconds
    phase6fu.MARKER_PATH = arguments.cleanup_marker_path
    phase6fu.LAST_SUPPRESSION = None
    legacy._terminate_tree = phase6fu.terminate_exact_tree
    legacy._cleanup_observed_processes = cleanup_observed_exact
    legacy_result = legacy.run(arguments)
    try:
        raw = _read(arguments.summary)
        operation = _read(arguments.lifecycle_path)
        runner = _read(arguments.runner_evidence_path)
        markers = read_jsonl(arguments.marker_path, 1024 * 1024)
        trace = read_jsonl(arguments.trace)
        policy = _read(arguments.contract_path)
        evidence = build_evidence(
            raw, operation, runner, markers, trace,
            attempt_id=arguments.attempt_id, mode=arguments.mode, policy=policy,
        )
        report = attach_evaluation(raw, evidence, policy)
        _write(arguments.summary, report)
        return 0 if report["canonical_lifecycle_evaluation"]["accepted_for_phase6hq_boundary"] else 2
    except Exception as error:
        raw = _read(arguments.summary) if arguments.summary.is_file() else {}
        raw["schema"] = "campfire.phase6hq.resource-guard.v1"
        raw["status"] = "failed"
        raw["stop_reason"] = "canonical_evaluator_failure"
        raw["canonical_evaluator_error"] = f"{type(error).__name__}: {error}"
        _write(arguments.summary, raw)
        return 2 if legacy_result in (0, 2) else legacy_result


if __name__ == "__main__":
    raise SystemExit(main())
