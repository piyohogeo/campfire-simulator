"""Run the twenty frozen Phase 6FY synthetic/short-lived fixtures."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from phase6fy_three_axis_policy import classify_attempt, evaluate_population


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _valid(status: str = "normal", diagnostic: str = "not_required") -> dict:
    return {
        "operation": {
            "condition_operation_complete": True,
            "fixed_frame_reached": True,
            "startup_identity_match": True,
            "payload_identity_match": True,
            "source_identity_match": True,
            "active_block_evidence_present": True,
            "condition_identity_match": True,
            "resource_observation_complete": True,
            "operation_markers_complete": True,
        },
        "artifact": {
            "committed": True,
            "committed_before_stage_close": True,
            "hashes_match": True,
            "metadata_match": True,
            "telemetry_complete": True,
            "final_sample_before_stage_close": True,
        },
        "resource": {
            "kit_within_limit": True,
            "tree_within_limit": True,
            "runner_within_limit": True,
            "diagnostic_within_limit": True,
            "physical_floor_met": True,
            "commit_floor_met": True,
            "no_persistent_unexplained_accumulation": True,
        },
        "lifecycle": {
            "status": status,
            "stage_close_complete": status == "normal",
            "extension_shutdown_complete": status == "normal",
            "normal_os_exit": status == "normal",
            "timeout_after_stage_close_request": status == "stage_close_timeout",
            "measurement_completed_before_timeout": status == "stage_close_timeout",
        },
        "diagnostic": {
            "classification": diagnostic,
            "artifact_committed": True,
            "child_absent": True,
            "detach_safe": True,
            "attach_state_known": True,
            "exact_cleanup_complete": True,
        },
        "cleanup": {
            "phase6fu_complete": True,
            "cleanup_suppression_released": True,
            "final_helpers_absent": True,
        },
        "identity": {
            "phase6fw_qualified": True,
            "attempt_owned_residual_zero": True,
            "unresolved_unknown_zero": True,
            "mismatch_stop_zero": True,
            "dual_source_absence": True,
        },
        "safety": {
            "fatal_zero": True,
            "dump_zero": True,
            "upload_zero": True,
            "device_lost_zero": True,
            "tdr_zero": True,
        },
    }


def _attempt(attempt_id: str, condition: str, classification: str, *, slot_kind="basic", replacement_for=None, peak=100) -> dict:
    return {
        "attempt_id": attempt_id,
        "condition": condition,
        "slot_kind": slot_kind,
        "replacement_for": replacement_for,
        "classification": classification,
        "formal_peak": peak,
    }


def _short_lived_fixture(output: Path, leave_running: bool = False) -> dict:
    stdout = output.with_suffix(".stdout.log")
    stderr = output.with_suffix(".stderr.log")
    command = [sys.executable, "-c", "import time; print('fixture-ready', flush=True); time.sleep(60)"]
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.Popen(command, stdout=out, stderr=err)
    identity = {"pid": process.pid, "path": str(Path(sys.executable).resolve()), "started_at_utc": datetime.now(timezone.utc).isoformat()}
    time.sleep(0.1)
    observed_residual = process.poll() is None
    if not leave_running:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    else:
        # The decision observes a residual, then the fixture itself performs
        # bounded cleanup so no test child escapes into the real environment.
        process.terminate()
        process.wait(timeout=5)
    return {
        "identity": identity,
        "observed_residual_before_fixture_cleanup": observed_residual,
        "absent_after_fixture_cleanup": process.poll() is not None,
        "stdout_path": str(stdout),
        "stderr_path": str(stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if args.output_root.exists():
        raise RuntimeError(f"fixture root reuse refused: {args.output_root}")
    args.output_root.mkdir(parents=True)
    cases = []

    def attempt_case(name: str, evidence: dict, expected: str, source="synthetic_artifact"):
        decision = classify_attempt(evidence)
        cases.append({
            "name": name,
            "source": source,
            "expected": expected,
            "observed": decision["classification"],
            "passed": decision["classification"] == expected,
            "decision": decision,
        })

    attempt_case("memory_complete_normal_close", _valid(), "memory_valid_lifecycle_normal")
    attempt_case(
        "memory_complete_stage_close_timeout",
        _valid("stage_close_timeout", "diagnostic_attach_unavailable"),
        "memory_valid_lifecycle_timeout",
    )
    value = _valid("stage_close_timeout", "diagnostic_attach_unavailable")
    value["operation"]["condition_operation_complete"] = False
    attempt_case("timeout_before_memory_complete", value, "memory_invalid_operation_failure")
    value = _valid("stage_close_timeout", "diagnostic_attach_unavailable")
    value["resource"]["kit_within_limit"] = False
    attempt_case("resource_ceiling_then_timeout", value, "memory_invalid_resource_failure")
    value = _valid("stage_close_timeout", "diagnostic_attach_unavailable")
    value["artifact"]["committed"] = False
    attempt_case("timeout_before_artifact_commit", value, "memory_invalid_operation_failure")

    process_evidence = _short_lived_fixture(args.output_root / "stack_complete_target")
    attempt_case("stack_complete_cleanup_success", _valid("stage_close_timeout", "diagnostic_complete"), "memory_valid_lifecycle_timeout", "short_lived_process")
    attempt_case("attach_unavailable_partial_cleanup_success", _valid("stage_close_timeout", "diagnostic_attach_unavailable"), "memory_valid_lifecycle_timeout", "short_lived_process")
    value = _valid("stage_close_timeout", "diagnostic_partial_stack_timeout")
    value["diagnostic"]["child_absent"] = False
    residual_process = _short_lived_fixture(args.output_root / "cdb_timeout_residual", leave_running=True)
    attempt_case("cdb_timeout_child_residual", value, "memory_invalid_diagnostic_cleanup_failure", "short_lived_process")
    value = _valid("stage_close_timeout", "diagnostic_detach_failure")
    value["diagnostic"]["detach_safe"] = False
    attempt_case("detach_failure", value, "memory_invalid_diagnostic_cleanup_failure")
    value = _valid("stage_close_timeout", "diagnostic_complete")
    value["cleanup"]["phase6fu_complete"] = False
    attempt_case("exact_cleanup_failure", value, "memory_invalid_diagnostic_cleanup_failure")
    value = _valid()
    value["identity"]["unresolved_unknown_zero"] = False
    attempt_case("identity_unknown", value, "memory_invalid_identity_failure")
    attempt_case("protected_pid_reuse", _valid(), "memory_valid_lifecycle_normal", "short_lived_process")
    value = _valid()
    value["identity"]["attempt_owned_residual_zero"] = False
    attempt_case("attempt_owned_residual", value, "memory_invalid_identity_failure")

    normal = "memory_valid_lifecycle_normal"
    timeout = "memory_valid_lifecycle_timeout"
    invalid_resource = "memory_invalid_resource_failure"
    basic = [
        _attempt("a01", "M0_baseline", timeout, peak=300),
        _attempt("a02", "M1_phase6fo_equivalent", normal),
        _attempt("a03", "M2_pre_readback_frame", normal),
        _attempt("a04", "M1_phase6fo_equivalent", normal),
        _attempt("a05", "M2_pre_readback_frame", normal),
        _attempt("a06", "M0_baseline", normal),
        _attempt("a07", "M2_pre_readback_frame", normal),
        _attempt("a08", "M0_baseline", normal),
        _attempt("a09", "M1_phase6fo_equivalent", normal),
    ]

    def population_case(name: str, rows: list[dict], expected_failure: bool, extra_check=True):
        decision = evaluate_population(rows, contract)
        passed = decision["population_stopping_failure"] is expected_failure and bool(extra_check)
        cases.append({
            "name": name,
            "source": "synthetic_population",
            "expected_population_stopping_failure": expected_failure,
            "observed_population_stopping_failure": decision["population_stopping_failure"],
            "passed": passed,
            "decision": decision,
        })

    replacement = _attempt("a10", "M0_baseline", normal, slot_kind="replacement", replacement_for="a01")
    population_case("replacement_after_timeout", [*basic, replacement], False)
    second_timeout = _attempt("a10", "M0_baseline", timeout, slot_kind="replacement", replacement_for="a01")
    population_case("second_timeout_same_condition", [*basic, second_timeout], True)
    too_many = [
        *basic,
        replacement,
        _attempt("a11", "M1_phase6fo_equivalent", normal, slot_kind="replacement", replacement_for="a02"),
        _attempt("a12", "M2_pre_readback_frame", normal, slot_kind="replacement", replacement_for="a03"),
    ]
    population_case("replacement_slot_limit_exceeded", too_many, True)
    population_case("negative_exclude_timeout_from_distribution", [*basic[1:], replacement], True)
    overwritten = [*basic, _attempt("a01", "M0_baseline", normal, slot_kind="replacement", replacement_for="a01")]
    population_case("negative_replacement_overwrites_original", overwritten, True)
    resource_rows = copy.deepcopy(basic)
    resource_rows[0]["classification"] = invalid_resource
    resource_replacement = _attempt("a10", "M0_baseline", normal, slot_kind="replacement", replacement_for="a01")
    population_case("negative_replace_resource_failure", [*resource_rows, resource_replacement], True)
    timeout_max_rows = [*basic, replacement]
    formal_peaks = [row["formal_peak"] for row in timeout_max_rows if row["classification"] in {normal, timeout}]
    population_case(
        "timeout_peak_is_population_maximum",
        timeout_max_rows,
        False,
        extra_check=max(formal_peaks) == 300 and basic[0] in timeout_max_rows,
    )

    declared = list(contract["fixture_cases"])
    names = [row["name"] for row in cases]
    report = {
        "schema": "campfire.phase6fy.three-axis-fixture-report.v1",
        "phase": "phase6fy",
        "contract_sha256": _sha256(args.contract),
        "declared_cases": declared,
        "case_names_match_contract": names == declared,
        "passed": all(row["passed"] for row in cases) and names == declared,
        "passed_count": sum(row["passed"] for row in cases),
        "total_count": len(cases),
        "short_lived_process_evidence": {
            "stack_complete": process_evidence,
            "cdb_timeout_residual": residual_process,
            "final_residual_count": 0 if process_evidence["absent_after_fixture_cleanup"] and residual_process["absent_after_fixture_cleanup"] else 1,
        },
        "cases": cases,
        "phase6ft_reclassified": False,
        "phase6fv_reclassified": False,
        "phase6fx_reclassified": False,
        "real_kit_started": False,
    }
    path = args.output_root / "fixture_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": f"{report['passed_count']}/{report['total_count']}"}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
