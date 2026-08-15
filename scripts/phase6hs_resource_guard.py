"""Phase 6HS resource guard using the same operation validator as its parent."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import phase6eg_resource_guard as legacy
import phase6fu_resource_guard as phase6fu
from phase6hq_lifecycle_classification import read_jsonl
from phase6hq_resource_guard import cleanup_observed_exact
from phase6hr_lifecycle_classification import build_evidence
from phase6hs_lifecycle_classification import attach_evaluation, consume_guard_report
from phase6hs_operation_report import sha256_bytes, validate_paths
from phase6hu_atomic_report import atomic_write_json


def _write(path: Path, payload: dict) -> None:
    atomic_write_json(path, payload)


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
    parser.add_argument("--schema-path", type=Path, required=True)
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
        operation_validation, operation, _, _ = validate_paths(
            arguments.lifecycle_path, arguments.marker_path,
            expected_attempt_id=arguments.attempt_id,
            expected_schema_sha256=sha256_bytes(arguments.schema_path.read_bytes()),
            expected_contract_sha256=sha256_bytes(arguments.contract_path.read_bytes()),
        )
        operation_for_lifecycle = copy.deepcopy(operation)
        if operation_validation.get("accepted") is not True:
            operation_for_lifecycle["status"] = "failed"
        policy = _read(arguments.contract_path)
        evidence = build_evidence(
            raw, operation_for_lifecycle, _read(arguments.runner_evidence_path),
            read_jsonl(arguments.marker_path, 1024 * 1024), read_jsonl(arguments.trace),
            attempt_id=arguments.attempt_id, mode="proxy", policy=policy,
        )
        report = attach_evaluation(raw, evidence, policy, operation_validation)
        _write(arguments.summary, report)
        final = consume_guard_report(report, policy, expected_attempt_id=arguments.attempt_id, operation_validation=operation_validation)
        return 0 if final["accepted"] else 2
    except Exception as error:
        raw = _read(arguments.summary) if arguments.summary.is_file() else {}
        raw.update({"schema":"campfire.phase6hs.resource-guard.v1","status":"failed","stop_reason":"canonical_evaluator_failure","canonical_evaluator_error":f"{type(error).__name__}: {error}"})
        _write(arguments.summary, raw)
        return 2 if legacy_result in (0, 2) else legacy_result


if __name__ == "__main__":
    raise SystemExit(main())
