"""No-Kit producer-to-consumer fixture for Phase 6IJ."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import phase6ii_marker_contract as marker
import phase6ij_stage_composition_ladder as ladder
from phase6hu_atomic_report import AtomicReportError, atomic_write_json


class FakeLayer:
    def __init__(self, identifier: str, *, anonymous: bool = False, real_path: str = ""):
        self.identifier = identifier
        self.anonymous = anonymous
        self.realPath = real_path


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


def _positive_report(files: dict, runtime_id: str = "00000371B6101780") -> dict:
    expected = ladder.expected_identity(files)
    report = ladder.produce_operation_report("attempt-B", "B", expected)
    session = FakeLayer("anon:" + runtime_id, anonymous=True)
    root = FakeLayer(expected["root_identifier"], real_path=expected["root_identifier"])
    protected = FakeLayer(expected["protected_sha256"])
    evidence = ladder.produce_session_evidence(
        session_layer=session, session_layer_at_close_request=session,
        root_layer=root, runtime_layer=None, protected_layer=protected,
        layer_stack=[session, root, protected], raw_identifier=session.identifier,
        close_request_identifier=session.identifier, real_path="", resolved_path="",
    )
    report.update({
        "status": "stage_open_close_qualified", "operation_complete": True,
        "references_released": True, "context_empty": True, "shutdown_complete": True,
        "open_stage_async_calls": 1, "close_stage_async_calls": 1,
        "open_elapsed_seconds": 0.25, "close_elapsed_seconds": 0.05,
        "observed_identity": {
            "condition": "B", "open_path": expected["open_path"],
            "open_sha256": expected["open_sha256"], "root_identifier": expected["root_identifier"],
            "sublayer_identifiers": expected["sublayer_identifiers"],
            "edit_target_identifier": expected["edit_target_identifier"],
            "protected_sha256": expected["protected_sha256"], "runtime_empty": False,
            **evidence,
        },
    })
    return report


def _marker_rows(root: Path, report: dict) -> list[dict]:
    path = root / "markers.jsonl"
    payloads = {
        "process_started": {"attempt_id": report["attempt_id"], "condition": report["condition"]},
        "kit_app_ready": {"attempt_id": report["attempt_id"], "condition": report["condition"]},
        "stage_open_requested": {"condition": report["condition"], "open_path": report["expected_identity"]["open_path"]},
        "stage_open_completed": {"condition": report["condition"], "elapsed_seconds": 0.25},
        "opened_stage_identity_recorded": {"condition": report["condition"], "root_identifier": report["observed_identity"]["root_identifier"]},
        "stage_close_requested": {"condition": report["condition"]},
        "stage_close_completed": {"condition": report["condition"], "elapsed_seconds": 0.05},
        "context_empty_confirmed": {"condition": report["condition"]},
        "shutdown_requested": {"condition": report["condition"]},
        "shutdown_complete": {"condition": report["condition"]},
    }
    for event in marker.ORDER:
        name, payload = marker.produce_marker(event, **payloads[event])
        marker.append_marker(path, name, payload)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_fixture(output_root: Path) -> dict:
    output_root = Path(output_root)
    if output_root.exists():
        raise RuntimeError("Phase 6IJ fixture refuses root reuse")
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
        plan.append({
            "condition": condition, "open_path": str(Path(files["open_path"]).resolve()),
            "protected_sha256": ladder.sha256_file(files["protected"]),
            "sublayer_roles": [] if condition == "A" else (["protected"] if condition == "B" else ["runtime", "protected"]),
        })
        record("actual_producer_condition_" + condition, validation["accepted"], ";".join(validation["reasons"]))
    common_hash = plan[0]["protected_sha256"]
    for row in plan:
        row["protected_sha256"] = common_hash
    result = ladder.validate_plan(plan)
    record("A_B_C_one_variable_plan_and_D_equals_C", result["accepted"], ";".join(result["reasons"]))

    files = prepared["B"][0]
    for runtime_id in ("00000371B6101780", "ABCDEF1234"):
        report = _positive_report(files, runtime_id)
        path = output_root / ("e2e_" + runtime_id + ".json")
        atomic_write_json(path, report)
        loaded = ladder.read_bounded(path)
        result = ladder.validate_operation(loaded, "attempt-B", "B")
        record("producer_writer_reader_validator_valid_" + runtime_id, result["accepted"], ";".join(result["reasons"]))

    positive = _positive_report(files)
    rows = _marker_rows(output_root / "marker_e2e", positive)
    result = ladder.validate_marker_identity_consistency(rows, positive)
    record("marker_and_layer_evidence_consistent", result["accepted"], ";".join(result["reasons"]))

    def reject(name, mutate, required_fragment):
        value = copy.deepcopy(positive)
        mutate(value)
        result = ladder.validate_operation(value, "attempt-B", "B")
        reason = ";".join(result["reasons"])
        record(name, not result["accepted"] and required_fragment in reason, reason)

    for name, raw in (
        ("empty_runtime_id", "anon:"),
        ("legacy_filename_suffix", "anon:ABC:protected_diagnostic-session.usda"),
        ("path_separator_forward", "anon:ABC/DEF"),
        ("path_separator_back", "anon:ABC\\DEF"),
        ("uri", "anon:https://example"),
        ("traversal", "anon:.."),
        ("control_character", "anon:ABC\nDEF"),
        ("additional_suffix", "anon:ABC:extra"),
    ):
        reject(name, lambda value, raw=raw: (
            value["observed_identity"].update({"session_identifier_raw": raw, "session_identifier_normalized": ladder.normalize_session_identifier(raw)}),
            value["observed_identity"].update({"session_identifier_at_close_request_raw": raw, "session_identifier_at_close_request_normalized": ladder.normalize_session_identifier(raw)})
        ), "session_identifier_invalid")

    reject("file_backed_session", lambda value: value["observed_identity"].update({"session_real_path": "C:/session.usda", "session_resolved_path": "C:/session.usda"}), "session_real_path_file_backed")
    reject("session_not_anonymous", lambda value: value["observed_identity"].update({"session_anonymous": False}), "session_anonymous_invalid")
    reject("session_root_identity_collision", lambda value: value["observed_identity"].update({"session_distinct_from_root": False}), "session_distinct_from_root_invalid")
    reject("session_runtime_identity_collision", lambda value: value["observed_identity"].update({"session_distinct_from_runtime": False}), "session_distinct_from_runtime_invalid")
    reject("session_protected_identity_collision", lambda value: value["observed_identity"].update({"session_distinct_from_protected": False}), "session_distinct_from_protected_invalid")
    reject("session_layer_multiple", lambda value: value["observed_identity"].update({"session_layer_count": 2}), "session_layer_count_invalid")
    reject("identifier_changed_in_process", lambda value: value["observed_identity"].update({
        "session_identifier_at_close_request_raw": "anon:BBBB",
        "session_identifier_at_close_request_normalized": ladder.normalize_session_identifier("anon:BBBB"),
        "session_identifier_stable_until_close_request": False,
    }), "session_identifier_stable_until_close_request_invalid")
    reject("layer_object_changed_in_process", lambda value: value["observed_identity"].update({
        "session_is_get_session_layer": False, "session_python_identity_stable": False,
        "session_object_stable_until_close_request": False,
    }), "session_is_get_session_layer_invalid")
    reject("session_evidence_missing", lambda value: value["observed_identity"].pop("session_identifier_normalized"), "session_identifier_invalid")
    reject("session_evidence_type_invalid", lambda value: value["observed_identity"].update({"session_layer_count": "1"}), "session_layer_count_invalid")

    bad_rows = copy.deepcopy(rows)
    bad_rows[4]["root_identifier"] = "C:/conflict.usda"
    result = ladder.validate_marker_identity_consistency(bad_rows, positive)
    record("marker_layer_evidence_conflict", not result["accepted"] and "marker_root_identity_evidence_conflict" in result["reasons"], ";".join(result["reasons"]))
    for name, marker_rows in (("marker_missing", rows[:-1]), ("marker_duplicate", rows + [rows[-1]])):
        result = marker.validate_sequence(marker_rows)
        record(name, not result["accepted"], ";".join(result["reasons"]))

    value = copy.deepcopy(positive)
    value["open_elapsed_seconds"] = float("nan")
    try:
        atomic_write_json(output_root / "nonfinite.json", value)
        record("nonfinite", False, "unexpected_acceptance")
    except AtomicReportError as error:
        record("nonfinite", error.reason == "payload_json_invalid", error.reason)
    oversize = output_root / "oversize.json"
    oversize.write_bytes(b"{" + b" " * ladder.MAX_DOCUMENT_BYTES + b"}")
    try:
        ladder.read_bounded(oversize)
        record("oversize", False, "unexpected_acceptance")
    except ValueError as error:
        record("oversize", "bounded_json_size_invalid" in str(error), str(error))

    passed = sum(1 for row in cases if row["passed"])
    report = {
        "schema": "campfire.phase6ij.stage-open-composition-fixture.v1",
        "phase": "phase6ij", "status": "qualified" if passed == len(cases) else "failed",
        "case_count": [passed, len(cases)], "kit_launch_count": 0, "cases": cases,
    }
    atomic_write_json(output_root / "fixture_report.json", report)
    return report
