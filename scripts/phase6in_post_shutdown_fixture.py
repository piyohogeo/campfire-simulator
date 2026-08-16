from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess

from phase6in_post_shutdown_boundary import (
    MAX_JSON_BYTES, classify, read_json, read_jsonl, validate_markers,
    validate_operation, validate_runner, write_json,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
CASE = SCRIPTS / "run_phase6in_fixture_case.ps1"


def run_case(root: Path, mode: str) -> tuple[dict, list[dict], dict]:
    target = root / mode
    command = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(CASE), "-Mode", mode, "-OutputDir", str(target)]
    with (root / f"{mode}.stdout.log").open("wb", buffering=0) as stdout, (root / f"{mode}.stderr.log").open("wb", buffering=0) as stderr:
        result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=15)
    if result.returncode:
        raise RuntimeError(f"phase6in_actual_fixture_failed:{mode}:{result.returncode}")
    evidence = read_json(target / "case.json")
    parent = read_jsonl(target / "parent.jsonl")
    child = read_jsonl(target / "child.jsonl")
    rows = parent[:2] + child + parent[2:]
    return evidence, rows, evidence["operation"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise RuntimeError("Phase 6IN fixture refuses root reuse")
    root.mkdir(parents=True)
    results: list[dict] = []

    def check(name: str, passed: bool, details=None) -> None:
        results.append({"name": name, "passed": bool(passed), "details": details})

    actual = {mode: run_case(root, mode) for mode in ("exit0", "delay0", "hang", "exit5")}
    normal, normal_rows, operation = actual["exit0"]
    identity = operation["process_identity"]
    operation_validation = validate_operation(operation, attempt_id=normal["attempt_id"], helper_contract_sha256="FIXTURE")
    marker_validation = validate_markers(normal_rows, attempt_id=normal["attempt_id"], identity=identity)
    runner_validation = validate_runner(normal, attempt_id=normal["attempt_id"], identity=identity)
    check("actual_producer_atomic_writer_reader_validator", operation_validation["accepted"] and marker_validation["accepted"] and runner_validation["accepted"], {"operation": operation_validation, "markers": marker_validation, "runner": runner_validation})
    check("phase6im_helper_reused", operation["phase6im_helper_evidence"]["schema"] == "campfire.phase6im.process-identity-report.v1" and operation["phase6im_helper_evidence"]["handle_tracker_final"]["open_handle_residual_count"] == 0)
    check("immediate_exit_zero_observed", normal["monitor"]["exit_observed"] and normal["monitor"]["exit_code"] == 0)
    delayed = actual["delay0"][0]
    check("delayed_exit_zero_observed", delayed["monitor"]["exit_observed"] and delayed["monitor"]["exit_code"] == 0 and len(delayed["samples"]) >= 2)
    hang = actual["hang"][0]
    check("post_shutdown_timeout_observed", hang["monitor"]["timeout"] and hang["assisted_cleanup"] and hang["residual_process_count"] == 0)
    abnormal = actual["exit5"][0]
    check("post_shutdown_nonzero_exit_observed", abnormal["monitor"]["exit_observed"] and abnormal["monitor"]["exit_code"] == 5)
    check("stdout_stderr_streamed_to_bounded_files", all((root / f"{mode}.stdout.log").stat().st_size < MAX_JSON_BYTES and (root / f"{mode}.stderr.log").stat().st_size < MAX_JSON_BYTES for mode in actual))

    normal_axes = classify(operation_valid=True, monitor_valid=True, identity_reuse=False, exit_observed=True, exit_code=0, exit_seconds=1.0, post_shutdown_exception=False, resource_pass=True, cleanup_pass=True, cleanup_assisted=False)
    delayed_axes = classify(operation_valid=True, monitor_valid=True, identity_reuse=False, exit_observed=True, exit_code=0, exit_seconds=20.0, post_shutdown_exception=False, resource_pass=True, cleanup_pass=True, cleanup_assisted=False)
    timeout_axes = classify(operation_valid=True, monitor_valid=True, identity_reuse=False, exit_observed=False, exit_code=None, exit_seconds=None, post_shutdown_exception=False, resource_pass=True, cleanup_pass=True, cleanup_assisted=True)
    exception_axes = classify(operation_valid=True, monitor_valid=True, identity_reuse=False, exit_observed=True, exit_code=0xC0000005, exit_seconds=4.94, post_shutdown_exception=True, resource_pass=True, cleanup_pass=True, cleanup_assisted=True)
    check("normal_exit_axis", normal_axes["lifecycle"] == "normal_exit")
    check("delayed_exit_axis", delayed_axes["lifecycle"] == "delayed_exit")
    check("timeout_axis_independent_from_operation", timeout_axes["monitor"] == "qualified" and timeout_axes["operation"] == "complete" and timeout_axes["lifecycle"] == "post_shutdown_timeout")
    check("exception_axis_independent_from_operation", exception_axes["monitor"] == "qualified" and exception_axes["operation"] == "complete" and exception_axes["lifecycle"] == "post_shutdown_exception")
    check("natural_cleanup_axis", normal_axes["cleanup"] == "natural")
    check("assisted_cleanup_axis", timeout_axes["cleanup"] == "assisted_known_auxiliary")
    check("resource_failure_axis", classify(operation_valid=True, monitor_valid=True, identity_reuse=False, exit_observed=True, exit_code=0, exit_seconds=1.0, post_shutdown_exception=False, resource_pass=False, cleanup_pass=True, cleanup_assisted=False)["resource"] == "failed")

    def invalid_marker(name: str, mutate, reason: str) -> None:
        rows = copy.deepcopy(normal_rows); mutate(rows)
        outcome = validate_markers(rows, attempt_id=normal["attempt_id"], identity=identity)
        check(name, not outcome["accepted"] and any(reason in item for item in outcome["reasons"]), outcome)

    invalid_marker("marker_missing", lambda rows: rows.pop(2), "marker_missing")
    invalid_marker("marker_duplicate", lambda rows: rows.insert(3, copy.deepcopy(rows[2])), "marker_missing_or_duplicate")
    invalid_marker("marker_order_invalid", lambda rows: rows.insert(2, rows.pop(4)), "marker_order_invalid")
    invalid_marker("marker_identity_mismatch", lambda rows: rows[2].update(pid=rows[2]["pid"] + 1), "marker_identity_mismatch")

    reused = copy.deepcopy(normal)
    reused["samples"][0]["identity_state"] = "pid_reused"
    check("pid_reuse_fail_closed_without_stop_authority", classify(operation_valid=True, monitor_valid=True, identity_reuse=True, exit_observed=False, exit_code=None, exit_seconds=None, post_shutdown_exception=False, resource_pass=True, cleanup_pass=True, cleanup_assisted=False)["monitor"] == "failed")
    mismatch_runner = copy.deepcopy(normal); mismatch_runner["samples"][0]["creation_time_filetime_ticks"] += 1
    check("sample_identity_mismatch", not validate_runner(mismatch_runner, attempt_id=normal["attempt_id"], identity=identity)["accepted"])

    corrupt = root / "corrupt.json"; corrupt.write_text("{", encoding="utf-8")
    try: read_json(corrupt); rejected = False
    except (ValueError, TypeError, json.JSONDecodeError): rejected = True
    check("corrupt_json_rejected", rejected)
    oversize = root / "oversize.json"
    with oversize.open("wb") as stream: stream.truncate(MAX_JSON_BYTES + 1)
    try: read_json(oversize); rejected = False
    except ValueError: rejected = True
    check("oversize_json_rejected", rejected)
    missing_operation = copy.deepcopy(operation); missing_operation.pop("operation_complete")
    check("operation_missing_rejected", not validate_operation(missing_operation, attempt_id=normal["attempt_id"], helper_contract_sha256="FIXTURE")["accepted"])
    conflict = copy.deepcopy(operation); conflict["phase6im_helper_contract_sha256"] = "CONFLICT"
    check("helper_contract_conflict_rejected", not validate_operation(conflict, attempt_id=normal["attempt_id"], helper_contract_sha256="FIXTURE")["accepted"])
    check("all_actual_fixture_residuals_zero", all(value[0]["residual_process_count"] == 0 for value in actual.values()))
    check("cdb_and_dump_analysis_zero", all(value[0]["cdb_attempted"] is False and not value[0]["dump_inventory"] for value in actual.values()))

    summary = {
        "schema": "campfire.phase6in.fixture.v1", "phase": "phase6in",
        "status": "qualified" if all(item["passed"] for item in results) else "failed",
        "case_count": len(results), "passed_count": sum(item["passed"] for item in results),
        "actual_process_case_count": len(actual), "kit_launch_count": 0,
        "results": results,
    }
    write_json(root / "fixture_summary.json", summary)
    return 0 if summary["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
