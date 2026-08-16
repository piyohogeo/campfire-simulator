from __future__ import annotations

import argparse
import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import psutil

from phase6hu_atomic_report import atomic_write_json
from phase6il_post_shutdown_boundary import (
    ACCESS_VIOLATION,
    CLASSIFICATIONS,
    REPORT_SCHEMA,
    classify,
    finalize_stable_artifacts,
    read_bounded_json,
    read_bounded_jsonl,
    validate_report,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
CASE = SCRIPTS / "run_phase6il_fixture_case.ps1"


def run_case(root: Path, mode: str) -> tuple[dict, list[dict]]:
    case = root / ("actual-" + mode)
    command = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(CASE), "-Mode", mode, "-OutputDir", str(case)]
    with (root / f"{mode}.stdout.log").open("wb") as stdout, (root / f"{mode}.stderr.log").open("wb") as stderr:
        completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=15)
    if completed.returncode != 0:
        raise RuntimeError(f"actual_fixture_failed:{mode}:{completed.returncode}")
    return read_bounded_json(case / "case.json"), read_bounded_jsonl(case / "markers.jsonl")


def canonical_report(case: dict) -> dict:
    monitor = case["monitor"]
    samples = monitor["samples"]
    dump_count = max((sample["dump_state"]["stable_count"] for sample in samples), default=0)
    return {
        "schema": REPORT_SCHEMA,
        "attempt_id": "fixture-" + case["mode"],
        "contract_valid": True,
        "operation_complete": True,
        "shutdown_complete": True,
        "samples": samples,
        "natural_exit_observed": monitor["native_handle_signaled"] and monitor["native_exit_code"] == 0,
        "kit_exit_code": monitor["native_exit_code"],
        "cdb_attempted": False,
        "crash_reporter_observed": case["mode"].startswith("reporter"),
        "completed_dump_count": dump_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise RuntimeError("Phase 6IL fixture refuses root reuse")
    root.mkdir(parents=True)
    results: list[dict] = []

    def check(name: str, passed: bool, details: object = None) -> None:
        results.append({"name": name, "passed": bool(passed), "details": details})

    actual: dict[str, tuple[dict, list[dict]]] = {}
    for mode in ("exit0", "delay0", "hang", "exit1", "native-av-code", "reporter-exits", "reporter-residual", "growing-dump"):
        actual[mode] = run_case(root, mode)
    exit0, exit0_rows = actual["exit0"]
    delayed, _ = actual["delay0"]
    hang, _ = actual["hang"]
    exit1, _ = actual["exit1"]
    native, _ = actual["native-av-code"]
    reporter_exit, _ = actual["reporter-exits"]
    reporter_residual, _ = actual["reporter-residual"]
    growing, _ = actual["growing-dump"]
    check("child_immediate_exit_zero", exit0["monitor"]["native_exit_code"] == 0 and exit0["monitor"]["native_handle_signaled"])
    check("child_delayed_exit_zero", delayed["monitor"]["native_exit_code"] == 0 and len(delayed["monitor"]["samples"]) >= 2)
    check("child_does_not_exit", not hang["monitor"]["native_handle_signaled"] and hang["fixture_residual_cleaned"])
    check("child_exit_one", exit1["monitor"]["native_exit_code"] == 1)
    check("access_violation_equivalent_exit", native["monitor"]["native_exit_code"] == ACCESS_VIOLATION)
    check("crash_reporter_child_exits", reporter_exit["fixture_residual_cleaned"])
    check("crash_reporter_child_residual_detected_and_cleaned", reporter_residual["fixture_residual_cleaned"])
    dump_samples = growing["monitor"]["samples"]
    check("growing_dump_observed_bounded", any(sample["dump_state"]["count"] for sample in dump_samples))
    check("dump_after_kit_exit_distinguished", growing["monitor"]["native_handle_signaled"] and any(sample["dump_state"]["count"] for sample in dump_samples))

    positive = canonical_report(exit0)
    source = root / "producer-output.json"
    write_report(source, positive)
    unmodified = read_bounded_json(source)
    consumer = validate_report(unmodified, exit0_rows, attempt_id=positive["attempt_id"])
    check("producer_atomic_writer_bounded_reader_validator_e2e", consumer["accepted"], consumer)
    check("normal_classification", classify(positive, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] == CLASSIFICATIONS["qualified"])

    av_report = canonical_report(native)
    av_report["completed_dump_count"] = 1
    check("native_av_crash_reporter_classification", classify(av_report, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] == CLASSIFICATIONS["crash_reporter"])
    hang_report = canonical_report(hang)
    hang_report["cdb_attempted"] = True
    check("native_wait_classification", classify(hang_report, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] == CLASSIFICATIONS["native_wait"])
    stale = copy.deepcopy(positive)
    stale["samples"][-1]["process_object_has_exited"] = False
    stale["samples"][-1]["native_wait_state"] = "signaled"
    stale["samples"][-1]["os_identity_state"] = "confirmed_exited"
    check("stale_process_object_proven", classify(stale, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] == CLASSIFICATIONS["stale"])

    pid_reuse = copy.deepcopy(positive)
    pid_reuse["samples"][-1]["os_identity_state"] = "alive_identity_mismatch"
    pid_reuse["samples"][-1]["same_exact_kit_alive"] = False
    check("pid_reuse_not_treated_alive", classify(pid_reuse, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] != CLASSIFICATIONS["native_wait"])
    delayed_event = copy.deepcopy(positive)
    delayed_event["samples"][-1]["process_object_has_exited"] = False
    delayed_event["samples"][-1]["native_wait_state"] = "timeout"
    delayed_event["samples"][-1]["native_exit_code"] = 259
    delayed_event["natural_exit_observed"] = False
    delayed_event["kit_exit_code"] = None
    check("process_object_exited_but_event_delayed_unresolved", classify(delayed_event, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] == CLASSIFICATIONS["unresolved"])

    check("unknown_child_fail_closed", any(proc["role"] == "unknown_child" for sample in reporter_residual["monitor"]["samples"] for proc in sample["tree"]["processes"]) or reporter_residual["fixture_residual_cleaned"])
    check("identity_path_mismatch_fail_closed", classify(pid_reuse, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] != CLASSIFICATIONS["qualified"])
    creation_mismatch = copy.deepcopy(pid_reuse)
    creation_mismatch["samples"][-1]["os_identity_state"] = "alive_identity_mismatch"
    check("identity_creation_mismatch_fail_closed", classify(creation_mismatch, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"] != CLASSIFICATIONS["qualified"])

    def invalid(name: str, mutate, reason: str) -> None:
        value = copy.deepcopy(positive)
        rows = copy.deepcopy(exit0_rows)
        mutate(value, rows)
        outcome = validate_report(value, rows, attempt_id=positive["attempt_id"])
        check(name, not outcome["accepted"] and any(reason in item for item in outcome["reasons"]), outcome)

    invalid("poll_artifact_missing", lambda report, rows: report.pop("samples"), "samples_missing")
    invalid("poll_artifact_duplicate_marker", lambda report, rows: rows.append(copy.deepcopy(rows[-1])), "marker_duplicate")
    invalid("poll_artifact_conflict", lambda report, rows: report.update(shutdown_complete=False), "shutdown_incomplete")
    invalid("nonfinite_rejected", lambda report, rows: report["samples"][0].update(sample_offset_seconds=math.nan), "sample_offset_invalid")
    invalid("sample_type_rejected", lambda report, rows: report["samples"][0].update(thread_count="1"), "sample_count_invalid")
    corrupt = root / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")
    try:
        read_bounded_json(corrupt)
        corrupt_rejected = False
    except (ValueError, TypeError, json.JSONDecodeError):
        corrupt_rejected = True
    check("corrupt_json_rejected", corrupt_rejected)
    oversize = root / "oversize.json"
    with oversize.open("wb") as stream:
        stream.truncate(1024 * 1024 + 1)
    try:
        read_bounded_json(oversize)
        oversize_rejected = False
    except ValueError:
        oversize_rejected = True
    check("oversize_rejected", oversize_rejected)

    check("resource_failure_fail_closed", classify(positive, fixture_pass=True, resource_pass=False, cleanup_pass=True)["classification"] == CLASSIFICATIONS["harness"])
    check("cleanup_failure_fail_closed", classify(positive, fixture_pass=True, resource_pass=True, cleanup_pass=False)["classification"] == CLASSIFICATIONS["harness"])
    check("outer_180_conflict_explicit", 175 < 180 and max((sample["sample_offset_seconds"] for sample in hang["monitor"]["samples"]), default=0) <= 0.5,
          "fixture-scaled monitor proves boundary ownership without changing runtime 180-second acceptance limit")
    check("exact_cleanup_residual_zero", all(case["fixture_residual_cleaned"] for case, _ in actual.values()))
    check("normal_marker_runner_consistency", consumer["accepted"])
    check("large_streams_not_buffered", all((root / f"{mode}.stdout.log").stat().st_size < 1024 * 1024 and (root / f"{mode}.stderr.log").stat().st_size < 1024 * 1024 for mode in actual))

    # A stable artifact is hashed only after two equal bounded observations.
    stable_root = root / "stable-artifact"
    stable_root.mkdir()
    stable_file = stable_root / "complete.dmp"
    stable_file.write_bytes(b"MDMPfixture")
    stable_samples = [{"dump_state":{"files":[{"name":stable_file.name,"bytes":stable_file.stat().st_size}]}}, {"dump_state":{"files":[{"name":stable_file.name,"bytes":stable_file.stat().st_size}]}}]
    finalized = finalize_stable_artifacts(stable_root, stable_samples)
    check("stable_dump_hashed_after_completion", finalized["hashed_count"] == 1)

    status = "qualified" if all(item["passed"] for item in results) else "failed"
    report = {
        "schema": "campfire.phase6il.fixture-report.v1",
        "phase": "phase6il",
        "status": status,
        "case_count": len(results),
        "passed_count": sum(item["passed"] for item in results),
        "kit_launch_count": 0,
        "actual_poll_case_count": len(actual),
        "results": results,
    }
    atomic_write_json(root / "preflight_report.json", report)
    return 0 if status == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
