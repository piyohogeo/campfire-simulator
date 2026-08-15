"""No-Kit producer-to-consumer fixture for the Phase 6II ladder."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import phase6ii_marker_contract as marker
import phase6ii_stage_composition_ladder as ladder
from phase6hu_atomic_report import AtomicReportError, atomic_write_json


def _successful(report: dict) -> dict:
    value = copy.deepcopy(report)
    value.update({
        "status": "stage_open_close_qualified",
        "operation_complete": True,
        "references_released": True,
        "context_empty": True,
        "shutdown_complete": True,
        "open_stage_async_calls": 1,
        "close_stage_async_calls": 1,
        "open_elapsed_seconds": 0.25,
        "close_elapsed_seconds": 0.05,
        "observed_identity": {
            **copy.deepcopy(value["expected_identity"]),
            "session_present": True,
            "session_identifier": "anon:fixture:" + value["expected_identity"]["session_suffix"],
            "runtime_empty": value["expected_identity"]["runtime_must_be_empty"],
        },
    })
    return value


def _prepare(root: Path, condition: str) -> tuple[dict, dict]:
    root.mkdir()
    protected = root / ladder.PROTECTED_FILENAME
    protected.write_text("#usda 1.0\ndef Xform \"World\" {}\n", encoding="utf-8")
    files = ladder.create_condition_files(root, condition)
    contract = {
        "protected_file_sha256": ladder.sha256_file(protected),
        "runtime_file_sha256": "28F84F705DAB5DC6D5BAAEE8EE94E59B93B71BCD708C048C71066E7A8956E2D1",
        "container_B_file_sha256": "C08CEF7649B8E1437F1753E8982C58E3DCD0AD8411BB04CE08D1AB49EACD0361",
        "container_C_file_sha256": "C556894E389C3E2AB49B53088460F2D2AFED46B6C0C4898C5758811288876250",
    }
    return files, contract


def run_fixture(output_root: Path) -> dict:
    output_root = Path(output_root)
    if output_root.exists():
        raise RuntimeError("Phase 6II fixture refuses root reuse")
    output_root.mkdir(parents=True)
    cases = []

    def record(name, passed, reason="pass"):
        cases.append({"name": name, "passed": bool(passed), "reason": reason})

    prepared = {}
    plan = []
    for condition in ladder.CONDITIONS:
        files, contract = _prepare(output_root / ("producer_" + condition), condition)
        prepared[condition] = (files, contract)
        validation = ladder.validate_composition_files(files, contract)
        plan.append({"condition": condition, "open_path": str(Path(files["open_path"]).resolve()), "protected_sha256": ladder.sha256_file(files["protected"]), "sublayer_roles": [] if condition == "A" else (["protected"] if condition == "B" else ["runtime", "protected"])})
        record("actual_producer_condition_" + condition, validation["accepted"], ";".join(validation["reasons"]))
    plan_hash = plan[0]["protected_sha256"]
    for row in plan:
        row["protected_sha256"] = plan_hash
    result = ladder.validate_plan(plan)
    record("A_B_C_one_variable_plan_and_D_equals_C", result["accepted"], ";".join(result["reasons"]))

    files, contract = prepared["C"]
    bad = copy.copy(contract); bad["protected_file_sha256"] = "0" * 64
    result = ladder.validate_composition_files(files, bad)
    record("protected_hash_mismatch", not result["accepted"] and "protected_hash_mismatch" in result["reasons"], ";".join(result["reasons"]))
    Path(files["runtime"]).write_text("#usda 1.0\ndef Xform \"Unexpected\" {}\n", encoding="utf-8")
    result = ladder.validate_composition_files(files, contract)
    record("runtime_layer_nonempty", not result["accepted"] and "runtime_layer_nonempty_or_invalid" in result["reasons"], ";".join(result["reasons"]))

    files_b, _ = prepared["B"]
    expected = ladder.expected_identity(files_b)
    positive = _successful(ladder.produce_operation_report("attempt-B", "B", expected))
    e2e_path = output_root / "producer_consumer" / "operation.json"
    atomic_write_json(e2e_path, positive)
    loaded = ladder.read_bounded(e2e_path)
    result = ladder.validate_operation(loaded, "attempt-B", "B")
    record("actual_producer_atomic_writer_reader_validator", result["accepted"], ";".join(result["reasons"]))

    def reject_identity(name, mutator, expected_reason):
        value = copy.deepcopy(positive)
        mutator(value["observed_identity"])
        result = ladder.validate_operation(value, "attempt-B", "B")
        reason = ";".join(result["reasons"])
        record(name, not result["accepted"] and expected_reason in reason, reason)

    reject_identity("layer_missing", lambda row: row.pop("session_identifier"), "layer_identity_mismatch")
    reject_identity("layer_duplicate", lambda row: row["sublayer_identifiers"].append(row["sublayer_identifiers"][0]), "layer_identity_mismatch")
    reject_identity("sublayer_order_swapped", lambda row: row.update({"sublayer_identifiers": list(reversed(row["sublayer_identifiers"])) + ["C:/unexpected"]}), "layer_identity_mismatch")
    reject_identity("unknown_path", lambda row: row.update({"root_identifier": "C:/outside/container.usda"}), "layer_identity_mismatch")

    for name, mutate in (
        ("open_before_failure", lambda value: value.update({"status": "failed", "operation_complete": False, "open_stage_async_calls": 0})),
        ("open_during_exception", lambda value: value.update({"status": "failed", "operation_complete": False, "open_stage_async_calls": 1, "close_stage_async_calls": 0})),
        ("open_after_close_failure", lambda value: value.update({"status": "failed", "operation_complete": False, "close_stage_async_calls": 1, "context_empty": False})),
    ):
        value = copy.deepcopy(positive); mutate(value)
        result = ladder.validate_operation(value, "attempt-B", "B")
        record(name, not result["accepted"], ";".join(result["reasons"]))
    value = copy.deepcopy(positive); value["open_elapsed_seconds"] = float("nan")
    try:
        atomic_write_json(output_root / "nonfinite.json", value)
        record("nonfinite", False, "unexpected_acceptance")
    except AtomicReportError as error:
        record("nonfinite", error.reason == "payload_json_invalid", error.reason)
    oversize = output_root / "oversize.json"; oversize.write_bytes(b"{" + b" " * ladder.MAX_DOCUMENT_BYTES + b"}")
    try:
        ladder.read_bounded(oversize); record("oversize", False, "unexpected_acceptance")
    except ValueError as error:
        record("oversize", "bounded_json_size_invalid" in str(error), str(error))

    marker_path = output_root / "markers.jsonl"
    payloads = {
        "process_started": {"attempt_id": "a", "condition": "A"},
        "kit_app_ready": {"attempt_id": "a", "condition": "A"},
        "stage_open_requested": {"condition": "A", "open_path": "C:/protected.usda"},
        "stage_open_completed": {"condition": "A", "elapsed_seconds": 0.1},
        "opened_stage_identity_recorded": {"condition": "A", "root_identifier": "C:/protected.usda"},
        "stage_close_requested": {"condition": "A"},
        "stage_close_completed": {"condition": "A", "elapsed_seconds": 0.1},
        "context_empty_confirmed": {"condition": "A"},
        "shutdown_requested": {"condition": "A"},
        "shutdown_complete": {"condition": "A"},
    }
    for event in marker.ORDER:
        produced, payload = marker.produce_marker(event, **payloads[event])
        marker.append_marker(marker_path, produced, payload)
    rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
    result = marker.validate_sequence(rows)
    record("actual_marker_producer_sequence", result["accepted"], ";".join(result["reasons"]))
    for name, rows_value in (
        ("marker_missing", rows[:-1]),
        ("marker_duplicate", rows + [rows[-1]]),
        ("marker_order", [rows[1], rows[0], *rows[2:]]),
    ):
        result = marker.validate_sequence(rows_value)
        record(name, not result["accepted"], ";".join(result["reasons"]))

    passed = sum(1 for row in cases if row["passed"])
    report = {"schema": "campfire.phase6ii.stage-open-composition-fixture.v1", "phase": "phase6ii", "status": "qualified" if passed == len(cases) else "failed", "case_count": [passed, len(cases)], "kit_launch_count": 0, "cases": cases}
    atomic_write_json(output_root / "fixture_report.json", report)
    return report
