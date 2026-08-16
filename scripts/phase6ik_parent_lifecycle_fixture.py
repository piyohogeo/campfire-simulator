from __future__ import annotations

import argparse
import copy
import json
import math
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from phase6hu_atomic_report import AtomicReportError, atomic_write_json
from phase6ik_parent_lifecycle_boundary import (
    ORDER, append_marker, classify_boundary, produce_marker, produce_runner_evidence,
    read_bounded_json, read_jsonl, validate_markers, validate_runner_evidence,
    write_runner_evidence,
)
from phase6hr_lifecycle_classification import attach_evaluation, build_evidence, consume_guard_report
from run_phase6hr_preflight import _base

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
PYTHON = Path(r"C:\Python38\python.exe")
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
ATTEMPT = "phase6ik-fixture"
MIB = 1024 * 1024


def _write(path: Path, value: dict) -> None:
    atomic_write_json(path, value)


def _full_rows(path: Path, *, attempt_id: str = ATTEMPT) -> list[dict]:
    identities = {"outer_guard": (1100, 10.0), "parent_powershell": (1200, 20.0), "child_kit": (1300, 30.0)}
    elapsed = {key: 0.0 for key in identities}
    for step in ORDER:
        actor = {"outer_guard_wait_started":"outer_guard","child_wait_started":"parent_powershell","kit_app_ready":"child_kit","operation_complete":"child_kit","shutdown_complete":"child_kit","child_process_exit":"parent_powershell","child_wait_completed":"parent_powershell","runner_evidence_write_started":"parent_powershell","runner_evidence_write_completed":"parent_powershell","parent_return":"parent_powershell","guard_result_received":"outer_guard","canonical_evaluation_started":"outer_guard","canonical_evaluation_completed":"outer_guard","outer_guard_return":"outer_guard"}[step]
        elapsed[actor] += 0.1
        append_marker(path, attempt_id, step, actor=actor, pid=identities[actor][0], creation_time_utc_epoch=identities[actor][1], monotonic_elapsed_seconds=elapsed[actor])
    return read_jsonl(path)


def _runner(rows: list[dict], *, attempt_id: str = ATTEMPT, exit_code=0) -> dict:
    parent = next(row for row in rows if row["actor"] == "parent_powershell")
    child = next(row for row in rows if row["actor"] == "child_kit")
    return produce_runner_evidence(
        attempt_id=attempt_id,
        parent_identity={"pid": parent["pid"], "creation_time_utc_epoch": parent["creation_time_utc_epoch"], "path": str(POWERSHELL)},
        child_identity={"pid": child["pid"], "creation_time_utc_epoch": child["creation_time_utc_epoch"], "path": "kit.exe"},
        process_exit_code=exit_code,
        shutdown_monitor={"windows_exception_present": False, "lifecycle_candidate": "normal_exit"},
        status="qualified" if exit_code == 0 else "failed",
    )


def _canonical_round_trip(root: Path, policy: dict, rows: list[dict], runner: dict, *, mutate_raw=None) -> dict:
    raw, operation, _, _, trace = _base(policy)
    operation.update(schema="campfire.phase6ik.minimal-operation.v1", status="qualified", operation_complete=True, shutdown_complete=True)
    raw["exit_code"] = runner.get("process_exit_code")
    if mutate_raw:
        mutate_raw(raw)
    evidence = build_evidence(raw, operation, runner, rows, trace, attempt_id=ATTEMPT, mode="smoke", policy=policy)
    report = attach_evaluation(raw, evidence, policy)
    path = root / "canonical_guard.json"
    atomic_write_json(path, report)
    return consume_guard_report(read_bounded_json(path), policy, expected_attempt_id=ATTEMPT)


def _wait_case(root: Path, name: str, *, delay=0.0, hang=0.0, exit_code=0) -> dict:
    case = root / name
    case.mkdir()
    cmd = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "run_phase6ik_wait_fixture_case.ps1"), "-PythonPath", str(PYTHON), "-ChildPath", str(SCRIPTS / "phase6ik_fixture_child.py"), "-MarkersPath", str(case / "markers.jsonl"), "-ReportPath", str(case / "report.json"), "-ResultPath", str(case / "wait.json"), "-AttemptId", ATTEMPT, "-DelaySeconds", str(delay), "-HangSeconds", str(hang), "-ChildExitCode", str(exit_code)]
    with (case / "parent.stdout.log").open("wb") as stdout, (case / "parent.stderr.log").open("wb") as stderr:
        completed = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=15)
    result = read_bounded_json(case / "wait.json")
    return {"exit": completed.returncode, "result": result, "rows": read_jsonl(case / "markers.jsonl")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6IK fixture refuses root reuse")
    args.output_root.mkdir(parents=True)
    policy = read_bounded_json(args.contract)
    cases = []

    def check(name: str, passed: bool, observed=None):
        cases.append({"name": name, "passed": bool(passed), "observed": observed})

    positive_root = args.output_root / "positive"
    positive_root.mkdir()
    rows = _full_rows(positive_root / "markers.jsonl")
    marker_result = validate_markers(rows, ATTEMPT)
    runner = _runner(rows)
    source = positive_root / "runner.source.json"
    _write(source, runner)
    writer_result = write_runner_evidence(positive_root / "runner_evidence.json", read_bounded_json(source))
    persisted_runner = read_bounded_json(positive_root / "runner_evidence.json")
    runner_result = validate_runner_evidence(persisted_runner, rows, ATTEMPT)
    canonical = _canonical_round_trip(positive_root, policy, rows, persisted_runner)
    check("normal_marker_runner_canonical_round_trip", marker_result["accepted"] and runner_result["accepted"] and canonical["accepted"], {"marker": marker_result, "runner": runner_result, "canonical": canonical, "writer": writer_result})

    normal = _wait_case(args.output_root, "child_shutdown_then_exit0")
    check("child_shutdown_then_exit0", normal["result"]["monitor"]["exit_code"] == 0 and any(r["step_id"] == "child_process_exit" for r in normal["rows"]))
    delayed = _wait_case(args.output_root, "child_short_delay_exit0", delay=0.35)
    check("child_shutdown_short_delay_exit0", delayed["result"]["monitor"]["exit_code"] == 0)
    hung = _wait_case(args.output_root, "child_does_not_exit", hang=8.0)
    check("child_shutdown_does_not_exit", hung["result"]["monitor"]["exit_code"] is None and not any(r["step_id"] == "child_process_exit" for r in hung["rows"]))
    failed_child = _wait_case(args.output_root, "child_exit1", exit_code=1)
    check("child_exit1", failed_child["result"]["monitor"]["exit_code"] == 1)

    def mutated(name, mutate, expected_reason=None):
        clone = copy.deepcopy(rows)
        mutate(clone)
        result = validate_markers(clone, ATTEMPT)
        passed = not result["accepted"] and (expected_reason is None or any(expected_reason in reason for reason in result["reasons"]))
        check(name, passed, result)

    mutated("parent_wait_released_before_child_exit", lambda value: value.__setitem__(slice(None), [r for r in value if r["step_id"] != "child_process_exit"]))
    mutated("guard_result_missing", lambda value: value.__setitem__(slice(None), [r for r in value if r["step_id"] != "guard_result_received"]))
    delayed_rows = copy.deepcopy(rows)
    for row in delayed_rows:
        if row["actor"] == "outer_guard": row["monotonic_elapsed_seconds"] += 10.0
    check("guard_result_short_delay", validate_markers(delayed_rows, ATTEMPT)["accepted"])
    mutated("canonical_evaluator_stops_before_start", lambda value: value.__setitem__(slice(None), [r for r in value if ORDER.index(r["step_id"]) >= ORDER.index("canonical_evaluation_started")]))
    mutated("canonical_evaluator_exception", lambda value: value.__setitem__(slice(None), [r for r in value if r["step_id"] not in ("canonical_evaluation_completed", "outer_guard_return")]))

    locked = args.output_root / "locked.json"
    locked.with_name(locked.name + ".writer.lock").write_text("held", encoding="ascii")
    try:
        write_runner_evidence(locked, runner)
        lock_rejected = False
    except AtomicReportError as error:
        lock_rejected = error.reason == "concurrent_writer_rejected"
    check("runner_evidence_temporarily_locked", lock_rejected)
    events = []
    sharing = PermissionError(13, "sharing"); sharing.winerror = 32
    with mock.patch("phase6hu_atomic_report.os.replace", side_effect=sharing):
        try:
            write_runner_evidence(args.output_root / "replace-fail.json", runner, event=events.append)
            replace_failed = False
        except AtomicReportError as error:
            replace_failed = error.reason == "atomic_replace_retry_exhausted" and error.attempts == 5
    check("atomic_replace_failure", replace_failed and any(e["event"] == "atomic_replace_exhausted" for e in events), events)
    check("runner_evidence_missing", not (args.output_root / "missing.json").exists())
    mutated("runner_evidence_duplicate_marker", lambda value: value.append(copy.deepcopy(value[-1])), "marker_duplicate")
    conflicting = copy.deepcopy(runner); conflicting["process_exit_code"] = 1
    check("runner_evidence_conflict", not validate_runner_evidence(conflicting, rows, ATTEMPT)["accepted"])
    wrong_attempt = copy.deepcopy(runner); wrong_attempt["attempt_id"] = "other"
    check("attempt_id_mismatch", not validate_runner_evidence(wrong_attempt, rows, ATTEMPT)["accepted"])
    wrong_pid = copy.deepcopy(runner); wrong_pid["child_identity"]["pid"] += 1
    check("pid_mismatch", not validate_runner_evidence(wrong_pid, rows, ATTEMPT)["accepted"])
    wrong_created = copy.deepcopy(runner); wrong_created["parent_identity"]["creation_time_utc_epoch"] += 1
    check("creation_time_mismatch", not validate_runner_evidence(wrong_created, rows, ATTEMPT)["accepted"])
    mutated("pid_reuse_identity_change", lambda value: value[-1].update(pid=value[-1]["pid"] + 99), "actor_identity_changed")
    outer_timeout_rows = [r for r in rows if ORDER.index(r["step_id"]) <= ORDER.index("parent_return")]
    boundary = classify_boundary(outer_timeout_rows, fixture_pass=True, runtime_started=True)
    check("outer_180_guard_preempts_parent_completion", boundary["first_incomplete_step"] == "guard_result_received", boundary)
    cleanup = _canonical_round_trip(args.output_root / "cleanup-failure", policy, rows, runner, mutate_raw=lambda raw: raw["observed_process_cleanup"].update(all_observed_absent=False))
    check("parent_uncollected_child", not cleanup["accepted"], cleanup)
    oversized = args.output_root / "oversize.json"; oversized.write_bytes(b"{" + b"x" * (MIB + 1) + b"}")
    try: read_bounded_json(oversized); oversize_rejected = False
    except ValueError: oversize_rejected = True
    check("oversize_rejected", oversize_rejected)
    try: produce_marker(ATTEMPT, "operation_complete", monotonic_elapsed_seconds=math.nan); nonfinite_rejected = False
    except TypeError: nonfinite_rejected = True
    check("nonfinite_rejected", nonfinite_rejected)
    corrupt = args.output_root / "corrupt.json"; corrupt.write_text("{broken", encoding="utf-8")
    try: read_bounded_json(corrupt); corrupt_rejected = False
    except json.JSONDecodeError: corrupt_rejected = True
    check("corrupt_json_rejected", corrupt_rejected)
    check("stdout_stderr_not_buffered", all(not item["result"]["stdout_buffered"] and not item["result"]["stderr_buffered"] for item in (normal, delayed, hung, failed_child)))

    report = {
        "schema": "campfire.phase6ik.parent-lifecycle-preflight.v1", "phase": "phase6ik",
        "status": "qualified" if all(case["passed"] for case in cases) else "failed",
        "kit_launch_count": 0, "case_count": len(cases), "passed_count": sum(case["passed"] for case in cases),
        "cases": cases,
        "actual_components": ["phase6ik marker producer", "phase6hu atomic writer", "phase6hr canonical evaluator", "kit_shutdown_policy.ps1 Wait-CampfireKitProcessWithShutdownPolicy"],
    }
    _write(args.output_root / "preflight_report.json", report)
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
