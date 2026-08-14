"""Finalize a stopped Phase 6GY population without launching Kit.

This utility is intentionally specific to the user-requested safe boundary.  It
summarizes the one completed attempt that the suspended outer runner could not
commit, appends it once, and makes the population heartbeat terminal.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import run_phase6gv_repetition as repetition


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--condition", required=True, choices=("A", "B"))
    parser.add_argument("--deleted-temporary-relative-path")
    parser.add_argument("--deleted-temporary-bytes", type=int)
    args = parser.parse_args()

    output = Path(args.output_root).resolve()
    contract = repetition.read_json(output / "frozen_contract.json")
    if not contract or contract.get("phase") != "phase6gy":
        raise SystemExit("not a frozen Phase 6GY artifact root")
    if repetition.existing_campfire_kit():
        raise SystemExit("Kit is still running")

    attempt_id = f"launch{args.sequence:02d}_{args.condition}"
    root = output / "runs" / attempt_id
    attempt = repetition.read_json(root / "attempt.json")
    if not attempt or attempt.get("attempt_id") != attempt_id:
        raise SystemExit("attempt identity mismatch")
    summary_path = root / "run_summary.json"

    aggregate_path = output / "aggregate.jsonl"
    rows = []
    if aggregate_path.exists():
        for line in aggregate_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    existing_sequences = {row["sequence"] for row in rows}

    if args.sequence in existing_sequences:
        summary = next(row for row in rows if row["sequence"] == args.sequence)
    else:
        case = root / "case"
        logs = root / "runner-logs"
        guard = repetition.read_json(logs / "guard.json")
        runner = repetition.read_json(case / "runner_evidence.json")
        raw = repetition.read_json(case / "raw.json")
        operation = repetition.read_json(case / "post_readback_isolation.json") if args.condition == "A" else None
        markers = repetition.marker_digest(case / "resource_markers.jsonl")
        stderr_path = logs / "stderr.log"
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-4096:] if stderr_path.exists() else ""
        guard_exit = 0 if (guard or {}).get("status") == "passed" else 2
        classification, signature = repetition.classify(guard, runner, raw, markers, guard_exit, stderr_text)
        peaks = (guard or {}).get("peaks") or {}
        cleanup = (guard or {}).get("observed_process_cleanup") or {}
        remaining = list(root.rglob("*.nvdb"))
        if remaining:
            raise SystemExit(f"temporary NVDB remains: {remaining}")
        observed = []
        if args.deleted_temporary_relative_path:
            relative = Path(args.deleted_temporary_relative_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise SystemExit("unsafe deleted temporary relative path")
            if not repetition.ALLOWED_TEMPORARY_NVDB.fullmatch(relative.name):
                raise SystemExit("deleted temporary filename is not allowlisted")
            if args.deleted_temporary_bytes is None or args.deleted_temporary_bytes < 0:
                raise SystemExit("deleted temporary byte count missing")
            observed.append({"relative_path": str(relative), "bytes": args.deleted_temporary_bytes,
                             "allowlisted": True, "deleted": True})
        temporary_cleanup = {"observed": observed, "failures": [], "residual_count": 0, "pass": True,
                             "performed_by": "user_requested_safe_boundary_finalizer"}

        start = parse_utc(attempt["start_utc"])
        guard_mtime = datetime.fromtimestamp((logs / "guard.json").stat().st_mtime, timezone.utc)
        first_start = parse_utc(rows[0]["start_utc"]) if rows else start
        counts = markers.get("counts", {})
        summary = {
            "schema": "campfire.phase6gv.run-summary.v1", "sequence": args.sequence,
            "condition": args.condition, "phase": "phase6gy", "attempt_id": attempt_id,
            "start_utc": attempt["start_utc"], "end_utc": guard_mtime.isoformat(),
            "elapsed_seconds": max(0.0, (guard_mtime - start).total_seconds()),
            "elapsed_from_population_start_seconds": max(0.0, (guard_mtime - first_start).total_seconds()),
            "classification": classification, "failure_signature": signature,
            "representative": classification != "startup_prerequisite_not_met",
            "last_operation_marker": markers.get("last_operation_marker"),
            "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
            "process_exit_code": (runner or {}).get("process_exit_code"),
            "stage_close_seconds": markers.get("stage_close_seconds"),
            "peaks": {key: peaks.get(key) for key in ("kit", "tree", "runner", "diagnostic")},
            "active_blocks": markers.get("active_blocks"),
            "calls": {
                "readback": sum(v for k, v in counts.items() if "readback_call_before" in k or k.endswith("readback_before")),
                "conversion": sum(v for k, v in counts.items() if "volume_conversion_before" in k or "buffer_to_volume_before" in k),
                "metadata": sum(v for k, v in counts.items() if "metadata" in k and k.endswith("before")),
                "save": sum(v for k, v in counts.items() if "save_volume_before" in k),
                "sampling": sum(v for k, v in counts.items() if "sampling_before" in k),
            },
            "temporary_file_cleanup": temporary_cleanup, "temporary_files_remaining": 0,
            "residual_process_count": 0 if cleanup.get("all_observed_absent") else None,
            "guard_exit_code": guard_exit, "guard_stop_reason": (guard or {}).get("stop_reason"),
            "operation_status": (operation or {}).get("operation_result") if operation else (raw or {}).get("status"),
            "finalized_after_user_requested_safe_boundary": True,
        }
        repetition.atomic_json(summary_path, summary)
        with aggregate_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(summary, separators=(",", ":"), allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        rows.append(summary)

    elapsed = max((row.get("elapsed_from_population_start_seconds", 0.0) for row in rows), default=0.0)
    report = repetition.aggregate(rows, 0.0, "user_requested_safe_boundary", "phase6gy")
    report["elapsed_seconds"] = elapsed
    report["population_truncated_by_user_request"] = True
    repetition.atomic_json(output / "aggregate_report.json", report)
    repetition.atomic_json(output / "heartbeat.json", {
        "schema": "campfire.phase6gv.heartbeat.v1", "status": "terminal",
        "stop_reason": "user_requested_safe_boundary", "launches": len(rows),
        "elapsed_seconds": elapsed, "updated_utc": repetition.utc_now(),
    })
    print(json.dumps({"passed": True, "launches": len(rows), "last": summary,
                      "aggregate_report": report}, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
