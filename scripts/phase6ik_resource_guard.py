"""Phase 6IK outer guard adapter with explicit post-parent boundaries."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import phase6eg_resource_guard as legacy
import phase6fu_resource_guard as phase6fu
from phase6hq_resource_guard import cleanup_observed_exact
from phase6hr_lifecycle_classification import attach_evaluation, build_evidence
from phase6hq_lifecycle_classification import read_jsonl
from phase6ik_parent_lifecycle_boundary import append_marker


def _write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > 1024 * 1024:
        raise RuntimeError("bounded_json_unavailable:" + str(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("bounded_json_root_invalid")
    return value


def main() -> int:
    parser = legacy._parser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--cleanup-suppression-lock", type=Path)
    parser.add_argument("--cleanup-suppression-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--cleanup-marker-path", type=Path)
    parser.add_argument("--runner-evidence-path", type=Path, required=True)
    parser.add_argument("--marker-path", type=Path, required=True)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke",), required=True)
    arguments = parser.parse_args()
    phase6fu.ATTEMPT_ID = arguments.attempt_id
    phase6fu.LOCK_PATH = arguments.cleanup_suppression_lock
    phase6fu.LOCK_DEADLINE = arguments.cleanup_suppression_deadline_seconds
    phase6fu.MARKER_PATH = arguments.cleanup_marker_path
    phase6fu.LAST_SUPPRESSION = None
    legacy._terminate_tree = phase6fu.terminate_exact_tree
    legacy._cleanup_observed_processes = cleanup_observed_exact
    started = time.monotonic()

    append_marker(arguments.marker_path, arguments.attempt_id, "outer_guard_wait_started", monotonic_elapsed_seconds=time.monotonic() - started)
    legacy_result = legacy.run(arguments)
    append_marker(arguments.marker_path, arguments.attempt_id, "guard_result_received", monotonic_elapsed_seconds=time.monotonic() - started, details={"legacy_result": legacy_result})
    try:
        append_marker(arguments.marker_path, arguments.attempt_id, "canonical_evaluation_started", monotonic_elapsed_seconds=time.monotonic() - started)
        raw = _read(arguments.summary)
        evidence = build_evidence(
            raw,
            _read(arguments.lifecycle_path),
            _read(arguments.runner_evidence_path),
            read_jsonl(arguments.marker_path, 1024 * 1024),
            read_jsonl(arguments.trace),
            attempt_id=arguments.attempt_id,
            mode=arguments.mode,
            policy=_read(arguments.contract_path),
        )
        report = attach_evaluation(raw, evidence, _read(arguments.contract_path))
        append_marker(arguments.marker_path, arguments.attempt_id, "canonical_evaluation_completed", monotonic_elapsed_seconds=time.monotonic() - started, details={"accepted": report["canonical_lifecycle_evaluation"]["accepted_for_phase6hr_boundary"]})
        _write(arguments.summary, report)
        append_marker(arguments.marker_path, arguments.attempt_id, "outer_guard_return", monotonic_elapsed_seconds=time.monotonic() - started, details={"exit_code": 0 if report["canonical_lifecycle_evaluation"]["accepted_for_phase6hr_boundary"] else 2})
        return 0 if report["canonical_lifecycle_evaluation"]["accepted_for_phase6hr_boundary"] else 2
    except Exception as error:
        raw = _read(arguments.summary) if arguments.summary.is_file() else {}
        raw.update({
            "schema": "campfire.phase6ik.resource-guard.v1",
            "status": "failed",
            "stop_reason": "canonical_evaluator_failure",
            "canonical_evaluator_error": f"{type(error).__name__}: {error}",
        })
        _write(arguments.summary, raw)
        return 2 if legacy_result in (0, 2) else legacy_result


if __name__ == "__main__":
    raise SystemExit(main())
