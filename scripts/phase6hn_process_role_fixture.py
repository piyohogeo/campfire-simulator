"""No-Kit Phase 6HN projection and process-role end-to-end fixtures."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

import phase6eg_resource_guard as legacy_guard
from phase6hl_guard_preflight import _write, validate_guard_summary
from phase6hm_process_role_fixture import _run_guarded_powershell_case
from phase6hn_process_role_projection import (
    EXPECTED_ATTEMPT_IDS,
    FZ_ROOT,
    PROJECTION_MAX_BYTES,
    ProjectionError,
    read_projection,
    validate_projection,
    write_projection,
)
from phase6hn_process_tree_topology import (
    KIT,
    ROOT,
    build_formal_target,
    norm_path,
    validate_formal_target,
)


MIB = 1024 * 1024


class _FakeProcess:
    def __init__(self, pid: int, name: str):
        self.pid = pid
        self._name = name

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list:
        return []


def _negative_projection(root: Path, name: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    path = root / (name + ".json")
    _write(path, payload)
    try:
        loaded = read_projection(path)
    except ProjectionError as exc:
        return False, str(exc)
    return validate_projection(loaded)


def _guard_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    summary = result.get("guard_summary") or {}
    return {
        "guard_exit_code": result.get("guard_exit_code"),
        "summary_status": summary.get("status"),
        "child_exit_code": summary.get("exit_code"),
        "root": summary.get("root"),
        "peaks": summary.get("peaks"),
        "process_absent": summary.get("process_absent"),
        "all_observed_absent": (summary.get("observed_process_cleanup") or {}).get("all_observed_absent"),
        "child_stdout_path": result.get("paths", {}).get("child_stdout"),
        "child_stderr_path": result.get("paths", {}).get("child_stderr"),
        "large_output_buffered_in_parent": summary.get("large_output_buffered_in_parent"),
        "guard_absent": result.get("guard_absent"),
    }


def run_fixture_suite(contract: Dict[str, Any], output_root: Path) -> Dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    projection_path = output_root / "phase6fz_process_role_projection.json"
    write_projection(FZ_ROOT, projection_path)
    projection_size = projection_path.stat().st_size
    projection = read_projection(projection_path)
    projection_ok, projection_reason = validate_projection(projection)

    negative_root = output_root / "projection-negatives"
    negative_root.mkdir()
    missing = copy.deepcopy(projection)
    missing["attempts"] = missing["attempts"][:-1]
    missing["attempt_count"] = 8
    missing_ok, missing_reason = _negative_projection(negative_root, "missing-attempt", missing)

    duplicate = copy.deepcopy(projection)
    duplicate["attempts"][-1] = copy.deepcopy(duplicate["attempts"][0])
    duplicate_ok, duplicate_reason = _negative_projection(negative_root, "duplicate-attempt", duplicate)

    wrong_type = copy.deepcopy(projection)
    wrong_type["attempt_count"] = "9"
    type_ok, type_reason = _negative_projection(negative_root, "type-invalid", wrong_type)

    role_conflict = copy.deepcopy(projection)
    role_conflict["attempts"][0]["guarded_root"]["role"] = "kit"
    role_ok, role_reason = _negative_projection(negative_root, "role-conflict", role_conflict)

    unknown_role = copy.deepcopy(projection)
    unknown_role["attempts"][0]["roles"]["mystery"] = unknown_role["attempts"][0]["roles"].pop("unknown_child")
    unknown_ok, unknown_reason = _negative_projection(negative_root, "unknown-role", unknown_role)

    oversize_path = negative_root / "oversize.json"
    oversize_payload = dict(projection)
    oversize_payload["forbidden_padding"] = "x" * (PROJECTION_MAX_BYTES + 1)
    _write(oversize_path, oversize_payload)
    try:
        read_projection(oversize_path)
        oversize_ok, oversize_reason = True, "unexpected_pass"
    except ProjectionError as exc:
        oversize_ok, oversize_reason = False, str(exc)

    positive = _run_guarded_powershell_case(contract, output_root / "guard-positive", 0)
    nonzero = _run_guarded_powershell_case(contract, output_root / "guard-nonzero", 7)
    positive_summary = positive.get("guard_summary") or {}
    positive_runner = positive.get("runner_report") or {}
    positive_child = positive.get("child_report") or {}
    nonzero_summary = nonzero.get("guard_summary") or {}
    nonzero_runner = nonzero.get("runner_report") or {}

    formal_paths = {
        "output": output_root / "formal-shape" / "run.json",
        "markers": output_root / "formal-shape" / "markers.jsonl",
        "runner_evidence": output_root / "formal-shape" / "runner.json",
        "kit_log": output_root / "formal-shape" / "kit.log",
        "kit_stdout": output_root / "formal-shape" / "kit.stdout.log",
        "kit_stderr": output_root / "formal-shape" / "kit.stderr.log",
    }
    formal_target = build_formal_target(formal_paths, contract["safety"]["stage_close_timeout_seconds"])
    formal_ok, formal_reason = validate_formal_target(formal_target)
    direct_ok, direct_reason = validate_formal_target([str(KIT.resolve()), "--bad-root"])
    mismatch_target = list(formal_target)
    mismatch_target[mismatch_target.index("-KitPath") + 1] = str(ROOT / "wrong" / "kit.exe")
    mismatch_ok, mismatch_reason = validate_formal_target(mismatch_target)
    missing_summary_ok, missing_summary_reason = validate_guard_summary(None, [])

    sample_kit_role = legacy_guard._role(_FakeProcess(200, "kit.exe"), 100)
    sample_unknown_role = legacy_guard._role(_FakeProcess(201, "unlisted-helper.exe"), 100)
    stdout_paths = [positive["paths"]["child_stdout"], positive["paths"]["child_stderr"]]
    cases = {
        "actual_producer_to_bounded_consumer": projection_ok and projection_reason == "pass",
        "nine_attempts_complete_unique": projection["attempt_count"] == 9 and [row["attempt_id"] for row in projection["attempts"]] == EXPECTED_ATTEMPT_IDS,
        "projection_below_prefrozen_limit": projection_size <= contract["projection"]["maximum_bytes"] == PROJECTION_MAX_BYTES,
        "projection_has_one_mib_reader_margin": projection_size <= PROJECTION_MAX_BYTES < MIB,
        "full_samples_and_logs_not_embedded": all(projection["projection_contract"][key] is False for key in ("full_samples_embedded", "stdout_stderr_embedded", "gpu_timeseries_embedded")),
        "powershell_guarded_root_is_runner_9_of_9": all(Path(row["guarded_root"]["normalized_executable_path"]).name.lower() == "powershell.exe" and row["guarded_root"]["role"] == "runner" for row in projection["attempts"]),
        "kit_is_direct_child_9_of_9": all(row["kit_direct_child"]["verified"] and row["kit_direct_child"]["identity"]["role"] == "kit" for row in projection["attempts"]),
        "diagnostic_and_unknown_child_roles_recorded": all(row["roles"]["diagnostic"]["identity_count"] > 0 and row["roles"]["unknown_child"]["identity_count"] >= 0 for row in projection["attempts"]),
        "pid_creation_dedup_9_of_9": all(row["deduplication"]["duplicate_identity_within_sample_count"] == 0 for row in projection["attempts"]),
        "pid_reuse_protection_9_of_9": all(row["pid_reuse_protection"]["identity_key_includes_creation_time"] and row["pid_reuse_protection"]["unknown_identity_count"] == 0 for row in projection["attempts"]),
        "cleanup_and_residual_zero_9_of_9": all(row["cleanup"]["all_observed_absent"] and row["cleanup"]["residual_process_count"] == 0 for row in projection["attempts"]),
        "normal_exit_classification_9_of_9": all(row["exit_state"]["normal_os_exit"] and row["final_classification"] == "memory_valid_lifecycle_normal" for row in projection["attempts"]),
        "missing_attempt_rejected": not missing_ok and missing_reason == "projection_attempt_count_mismatch",
        "duplicate_attempt_rejected": not duplicate_ok and duplicate_reason == "projection_attempt_identity_mismatch",
        "oversize_rejected": not oversize_ok and oversize_reason == "projection_oversize",
        "type_mismatch_rejected": not type_ok and type_reason == "projection_attempts_type_invalid",
        "contradictory_role_rejected": not role_ok and role_reason == "role_contradiction:runner",
        "unknown_role_label_rejected": not unknown_ok and unknown_reason == "role_set_mismatch",
        "formal_powershell_root_shape": formal_ok and formal_reason == "pass",
        "direct_kit_root_rejected": not direct_ok and direct_reason == "direct_kit_guarded_root_forbidden",
        "kit_path_mismatch_rejected": not mismatch_ok and mismatch_reason == "kit_child_path_mismatch",
        "missing_guard_summary_rejected": not missing_summary_ok and missing_summary_reason == "guard_summary_missing",
        "mock_kit_child_classified_kit": sample_kit_role == "kit",
        "unknown_executable_classified_bounded_child": sample_unknown_role == "child",
        "actual_powershell_child_exit_zero_propagates": positive["guard_exit_code"] == 0 and positive_runner.get("child_exit_code") == 0 and positive_summary.get("exit_code") == 0,
        "actual_nonzero_child_exit_propagates": nonzero["guard_exit_code"] == 2 and nonzero_runner.get("child_exit_code") == 7 and nonzero_summary.get("exit_code") == 7,
        "stdout_stderr_streamed_to_bounded_files": all(Path(path).is_file() and Path(path).stat().st_size <= 2 * MIB for path in stdout_paths),
        "parent_did_not_buffer_full_output": positive_summary.get("large_output_buffered_in_parent") is False,
        "actual_guard_runner_child_residual_zero": all((positive.get("guard_absent"), positive_summary.get("process_absent"), (positive_summary.get("observed_process_cleanup") or {}).get("all_observed_absent"), nonzero.get("guard_absent"), (nonzero_summary.get("observed_process_cleanup") or {}).get("all_observed_absent"))),
        "actual_child_identity_bound_to_runner": positive_child.get("parent_pid") == positive_summary.get("root", {}).get("pid"),
        "runner_budget_separate": contract["safety"]["runner_private_limit_bytes"] == 512 * MIB,
        "kit_budget_separate": contract["safety"]["kit_private_limit_bytes"] == 16 * 1024 * MIB,
        "diagnostic_budget_separate": contract["safety"]["diagnostic_private_limit_bytes"] == 512 * MIB,
        "tree_budget_separate": contract["safety"]["unique_tree_private_limit_bytes"] == 17 * 1024 * MIB,
    }
    report = {
        "schema": "campfire.phase6hn.process-role-fixture-suite.v1",
        "phase": "phase6hn",
        "status": "pass" if all(cases.values()) else "fail",
        "kit_launch_count": 0,
        "cases": cases,
        "projection": {
            "path": str(projection_path),
            "size_bytes": projection_size,
            "maximum_bytes": PROJECTION_MAX_BYTES,
            "source_aggregate_size_bytes": projection["source"]["aggregate_size_bytes"],
            "attempt_count": projection["attempt_count"],
            "validation_reason": projection_reason,
        },
        "negative_reasons": {
            "missing": missing_reason,
            "duplicate": duplicate_reason,
            "oversize": oversize_reason,
            "type": type_reason,
            "role_conflict": role_reason,
            "unknown_role": unknown_reason,
            "direct_kit_root": direct_reason,
            "kit_path_mismatch": mismatch_reason,
            "missing_summary": missing_summary_reason,
        },
        "guard_positive": _guard_summary(positive),
        "guard_nonzero": _guard_summary(nonzero),
        "formal_target_command": formal_target,
        "residual_process_count": 0 if cases["actual_guard_runner_child_residual_zero"] else None,
        "source_modified": False,
        "phase6fz_reclassified": False,
        "phase6hm_reclassified": False,
    }
    _write(output_root / "fixture_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HN fixture refuses root reuse: %s" % args.output_root)
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    report = run_fixture_suite(contract, args.output_root.resolve())
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
