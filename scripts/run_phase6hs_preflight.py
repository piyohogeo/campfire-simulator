"""No-Kit canonical operation-report and lifecycle-consumer fixture for Phase 6HS."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from phase6hr_lifecycle_classification import build_evidence
from phase6hs_lifecycle_classification import attach_evaluation, consume_guard_report
from phase6hs_operation_report import (
    COMPLETION_FIELDS,
    ReportError,
    atomic_write_json,
    produce_report,
    read_bounded_json,
    read_bounded_markers,
    report_digest,
    sha256_bytes,
    validate_paths,
    validate_report,
)
from phase6hs_probe_source import build_probe_source
from run_phase6hr_preflight import _base
from run_phase6hs_boundary import build_target, validate_target


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = "phase6hs-fixture-attempt"
FROZEN_ROOT = ROOT / "artifacts/phase6hr-flow-proxy-boundary-20260815"
FROZEN_RAW = FROZEN_ROOT / "attempt01/run.json"
FROZEN_MARKERS = FROZEN_ROOT / "attempt01/markers.jsonl"


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest().upper()
        for path in root.rglob("*") if path.is_file()
    }


def _write_markers(path: Path, rows: list[dict]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join((json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in rows)
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return data


def _completion_rows(attempt_id: str = ATTEMPT) -> list[dict]:
    return [
        {"marker":"operation_complete", "attempt_id":attempt_id, "sequence":1},
        {"marker":"stage_close_complete", "attempt_id":attempt_id, "sequence":2},
        {"marker":"shutdown_complete", "attempt_id":attempt_id, "sequence":3},
    ]


def _raw() -> dict:
    value = read_bounded_json(FROZEN_RAW)
    value["phase"] = "phase6hs"
    value["schema"] = "campfire.phase6hs.flow-proxy-boundary-raw.v1"
    value["status"] = "qualified"
    value["readback_calls"] = 0
    value["last_marker"] = "shutdown_complete"
    value["lifecycle"] = {"stage_close_complete":True, "shutdown_complete":True}
    return value


def _validation(report: dict, rows: list[dict], data: bytes, schema_sha: str, contract_sha: str) -> dict:
    return validate_report(
        report, rows, data, expected_attempt_id=ATTEMPT,
        expected_schema_sha256=schema_sha, expected_contract_sha256=contract_sha,
    )


def _record(cases: list[dict], name: str, expected: str, actual: str, *, detail: object = None) -> None:
    cases.append({"name":name, "expected":expected, "actual":actual, "passed":actual == expected, "detail":detail})


def _operation_cases(output: Path, schema_sha: str, contract_sha: str) -> tuple[list[dict], dict, list[dict], bytes]:
    cases: list[dict] = []
    rows = _completion_rows()
    data = _write_markers(output / "positive/markers.jsonl", rows)
    report = produce_report(
        _raw(), rows, data, attempt_id=ATTEMPT, kit_exit_code=0,
        schema_sha256=schema_sha, contract_sha256=contract_sha,
    )
    report_path = output / "positive/canonical.json"
    atomic_write_json(report_path, report)
    persisted = read_bounded_json(report_path)
    validation, consumed, consumed_rows, consumed_data = validate_paths(
        report_path, output / "positive/markers.jsonl", expected_attempt_id=ATTEMPT,
        expected_schema_sha256=schema_sha, expected_contract_sha256=contract_sha,
    )
    _record(cases, "positive_nested", "pass", validation["reason"], detail=validation)
    _record(cases, "producer_output_unmodified", "pass", "pass" if consumed == report and consumed_rows == rows and consumed_data == data else "roundtrip_mismatch")

    no_nested = produce_report(
        _raw(), rows, data, attempt_id=ATTEMPT, kit_exit_code=0,
        schema_sha256=schema_sha, contract_sha256=contract_sha, include_nested_lifecycle=False,
    )
    _record(cases, "positive_without_nested", "pass", _validation(no_nested, rows, data, schema_sha, contract_sha)["reason"])

    def check(name: str, mutate_report=None, mutate_rows=None, expected="pass"):
        candidate = copy.deepcopy(report)
        candidate_rows = copy.deepcopy(rows)
        if mutate_report:
            mutate_report(candidate)
        if mutate_rows:
            mutate_rows(candidate_rows)
        candidate_data = b"".join((json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in candidate_rows)
        if mutate_report and candidate.get("report_sha256") == report.get("report_sha256"):
            # Preserve an explicitly tampered digest. Other semantic cases get a valid digest
            # so their dedicated failure boundary is evaluated first.
            semantic_tamper = name in {"report_digest_mismatch", "producer_consumer_transform"}
            if not semantic_tamper:
                candidate["report_sha256"] = report_digest(candidate)
        actual = _validation(candidate, candidate_rows, candidate_data, schema_sha, contract_sha)["reason"]
        _record(cases, name, expected, actual)

    for field in COMPLETION_FIELDS:
        check("missing_" + field, lambda value, f=field: value.pop(f), expected="required_field_missing:" + field)
        for suffix, invalid in (("string","true"),("null",None),("number",1)):
            check(f"{field}_{suffix}", lambda value, f=field, v=invalid: value.__setitem__(f,v), expected="completion_type_invalid:" + field)
        check("false_" + field, lambda value, f=field: (value.__setitem__(f,False), value["lifecycle"].__setitem__(f,False)), expected="completion_false:" + field)
        check("nested_true_top_false_" + field, lambda value, f=field: value.__setitem__(f,False), expected="nested_top_level_mismatch:" + field)
        check("nested_false_top_true_" + field, lambda value, f=field: value["lifecycle"].__setitem__(f,False), expected="nested_top_level_mismatch:" + field)

    check("top_true_marker_missing", mutate_rows=lambda value: value.pop(0), expected="marker_missing:operation_complete")
    check("marker_present_top_missing", lambda value: value.pop("operation_complete"), expected="required_field_missing:operation_complete")
    check("duplicate_marker", mutate_rows=lambda value: value.insert(1, copy.deepcopy(value[0])), expected="marker_duplicate:operation_complete")
    check("marker_order_reversed", mutate_rows=lambda value: value.reverse(), expected="marker_order_invalid")
    check("operation_after_shutdown", mutate_rows=lambda value: value.__setitem__(slice(None), [value[1],value[2],value[0]]), expected="marker_order_invalid")
    check("operation_shutdown_different_attempt", mutate_rows=lambda value: value[2].__setitem__("attempt_id","other-attempt"), expected="marker_attempt_mismatch:shutdown_complete")
    check("marker_attempt_missing", mutate_rows=lambda value: value[0].pop("attempt_id"), expected="marker_attempt_missing:operation_complete")
    check("marker_after_shutdown", mutate_rows=lambda value: value.append({"marker":"late_marker"}), expected="marker_after_shutdown_complete")
    check("last_marker_mismatch", lambda value: value.__setitem__("last_marker","stage_close_complete"), expected="last_marker_mismatch")
    check("qualified_but_incomplete", lambda value: (value.__setitem__("shutdown_complete",False),value["lifecycle"].__setitem__("shutdown_complete",False)), expected="completion_false:shutdown_complete")
    check("unknown_schema", lambda value: value.__setitem__("schema","future"), expected="schema_mismatch")
    check("legacy_schema", lambda value: value.__setitem__("schema","campfire.phase6hr.fixture-run.v1"), expected="schema_mismatch")
    check("report_digest_mismatch", lambda value: value["functional_evidence"].__setitem__("tampered",True), expected="report_digest_mismatch")
    check("producer_consumer_transform", lambda value: value.__setitem__("producer_version","transformed"), expected="producer_version_mismatch")
    check("different_attempt", lambda value: value.__setitem__("attempt_id","other-attempt"), expected="attempt_identity_mismatch")

    altered_rows = copy.deepcopy(rows)
    altered_rows[0]["bounded_extra"] = "changed"
    altered_data = b"".join((json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in altered_rows)
    _record(cases, "marker_digest_mismatch", "marker_digest_mismatch", _validation(report, altered_rows, altered_data, schema_sha, contract_sha)["reason"])

    truncated = output / "negative/truncated.json"
    truncated.parent.mkdir(parents=True, exist_ok=True)
    truncated.write_text('{"schema":', encoding="utf-8")
    try:
        read_bounded_json(truncated)
        truncated_reason = "unexpected_pass"
    except ReportError as error:
        truncated_reason = str(error)
    _record(cases, "truncated_json", "report_json_invalid", truncated_reason)

    old_report = read_bounded_json(FROZEN_RAW)
    _record(cases, "phase6hr_old_report_rejected", "required_field_missing:schema_sha256", _validation(old_report, rows, data, schema_sha, contract_sha)["reason"])
    return cases, persisted, rows, data


def _lifecycle_case(case_root: Path, policy: dict, operation: dict, rows: list[dict], operation_validation: dict, helper_kinds=(), tamper=None) -> tuple[dict, dict, dict]:
    raw_guard, _, runner, _, trace = _base(policy, tuple(helper_kinds))
    cleanup = raw_guard["observed_process_cleanup"]
    for identity in cleanup.get("killed", []):
        identity["root_attempt_id"] = ATTEMPT
    for collection in (cleanup.get("before", []), cleanup.get("final", [])):
        for observation in collection:
            (observation.get("identity") or {})["root_attempt_id"] = ATTEMPT
    runner["mode"] = "proxy"
    evidence = build_evidence(raw_guard, operation, runner, rows, trace, attempt_id=ATTEMPT, mode="proxy", policy=policy)
    produced = attach_evaluation(raw_guard, evidence, policy, operation_validation)
    if tamper:
        tamper(produced)
    guard_path = case_root / "guard.json"
    atomic_write_json(guard_path, produced)
    persisted = read_bounded_json(guard_path)
    guard = consume_guard_report(persisted, policy, expected_attempt_id=ATTEMPT, operation_validation=operation_validation)
    parent = consume_guard_report(persisted, policy, expected_attempt_id=ATTEMPT, operation_validation=operation_validation)
    return persisted, guard, parent


def _lifecycle_cases(output: Path, policy: dict, operation: dict, rows: list[dict], data: bytes, schema_sha: str, contract_sha: str) -> list[dict]:
    cases: list[dict] = []
    validation = _validation(operation, rows, data, schema_sha, contract_sha)
    for name, helpers, expected in (
        ("natural_clean_exit", (), "natural_clean_exit"),
        ("telemetry_assisted_exit", ("telemetry",), "cleanup_assisted_telemetry_exit"),
        ("ngx_assisted_exit", ("ngx","conhost"), "cleanup_assisted_ngx_exit"),
    ):
        persisted, guard, parent = _lifecycle_case(output/name, policy, operation, rows, validation, helpers)
        actual = guard.get("classification")
        passed = actual == expected and guard == parent and guard.get("accepted") is True and persisted.get("canonical_operation_validation") == validation
        cases.append({"name":name,"expected":expected,"actual":actual,"guard_parent_equal":guard==parent,"passed":passed})

    _, guard, parent = _lifecycle_case(
        output/"guard_parent_classification_mismatch", policy, operation, rows, validation,
        tamper=lambda value: value["canonical_lifecycle_evaluation"].update(classification="cleanup_failure"),
    )
    cases.append({"name":"guard_parent_classification_mismatch","expected":"cleanup_failure","actual":guard.get("classification"),"guard_parent_equal":guard==parent,"passed":guard==parent and guard.get("classification")=="cleanup_failure"})

    contradictory = copy.deepcopy(validation)
    contradictory["reason"] = "parent-transformed"
    _, guard, parent = _lifecycle_case(output/"guard_parent_operation_mismatch", policy, operation, rows, validation)
    parent = consume_guard_report(read_bounded_json(output/"guard_parent_operation_mismatch/guard.json"), policy, expected_attempt_id=ATTEMPT, operation_validation=contradictory)
    cases.append({"name":"guard_parent_operation_mismatch","expected":"guard_parent_operation_validation_mismatch","actual":parent.get("reason"),"passed":guard.get("accepted") is True and parent.get("reason")=="guard_parent_operation_validation_mismatch"})
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HS preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    frozen_before = _tree_hash(FROZEN_ROOT)
    policy = read_bounded_json(args.contract)
    contract_sha = sha256_bytes(args.contract.read_bytes())
    schema_sha = sha256_bytes(args.schema.read_bytes())
    operation_cases, operation, rows, data = _operation_cases(args.output_root/"operation", schema_sha, contract_sha)
    lifecycle_cases = _lifecycle_cases(args.output_root/"lifecycle", policy, operation, rows, data, schema_sha, contract_sha)
    frozen_after = _tree_hash(FROZEN_ROOT)
    derived_probe = build_probe_source(ROOT/"scripts/probe_phase6hk_flow_proxy_boundary.py")
    compile(derived_probe, str(ROOT/"scripts/probe_phase6hs_flow_proxy_boundary.py"), "exec")
    target_paths = {
        "raw_output":args.output_root/"command/raw.json", "output":args.output_root/"command/canonical.json",
        "markers":args.output_root/"command/markers.jsonl", "runner_evidence":args.output_root/"command/runner.json",
        "kit_log":args.output_root/"command/kit.log", "kit_stdout":args.output_root/"command/kit.stdout.log",
        "kit_stderr":args.output_root/"command/kit.stderr.log",
    }
    target = build_target(target_paths, ATTEMPT, contract_sha)
    target_ok, target_reason = validate_target(target)
    checks = {
        "operation_cases_pass": all(case["passed"] for case in operation_cases),
        "lifecycle_cases_pass": all(case["passed"] for case in lifecycle_cases),
        "actual_producer_persist_reader_consumer": any(case["name"]=="producer_output_unmodified" and case["passed"] for case in operation_cases),
        "guard_parent_shared_validation": all(case.get("guard_parent_equal",True) for case in lifecycle_cases if case["name"] != "guard_parent_operation_mismatch"),
        "phase6hr_read_only": bool(frozen_before) and frozen_before == frozen_after,
        "old_schema_rejected": any(case["name"]=="phase6hr_old_report_rejected" and case["passed"] for case in operation_cases),
        "bounded_reports": all(path.stat().st_size <= 1024*1024 for path in args.output_root.rglob("*.json")),
        "derived_probe_exact_contract": all(token in derived_probe for token in (
            'attempt_id = settings.get_as_string("/phase6hs/attemptId")',
            '"attempt_id": attempt_id', 'report["flow_interface_calls"] += 1',
            'mark("app_ready_gate_complete"',
        )),
        "exact_case_target": target_ok and target_reason == "pass" and target[target.index("-AttemptId")+1] == ATTEMPT,
        "case_uses_shared_producer": target[target.index("-ProducerPath")+1].endswith("phase6hs_operation_report.py"),
        "kit_launch_count_zero": True,
    }
    summary = {
        "schema":"campfire.phase6hs.preflight.v1", "phase":"phase6hs",
        "status":"qualified" if all(checks.values()) else "failed", "kit_launch_count":0,
        "contract_sha256":contract_sha, "operation_schema_sha256":schema_sha,
        "operation_case_count":len(operation_cases), "lifecycle_case_count":len(lifecycle_cases),
        "operation_cases":operation_cases, "lifecycle_cases":lifecycle_cases, "checks":checks,
        "phase6hr_reclassified":False, "phase6hr_runtime_reused":False,
    }
    atomic_write_json(args.output_root/"preflight_report.json", summary)
    return 0 if summary["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
