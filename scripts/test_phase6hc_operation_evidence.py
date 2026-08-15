"""End-to-end no-Kit fixtures for Phase 6HC canonical operation evidence."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from phase6hc_operation_evidence import COMPLETE_MARKER, FAILURE_MARKER, SCHEMA, evaluate_operation_files
from run_phase6hc_candidate_lifecycle import build_command

CONDITION = "a_readback_release_control"


def normal_report() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "phase6hc",
        "condition": CONDITION,
        "attempt_identity": {"attempt_id": CONDITION, "condition": CONDITION, "mode": "R0"},
        "operation_result": "pass",
        "operation_complete": True,
        "last_operation_marker": COMPLETE_MARKER,
        "references_released": True,
        "weak_reference_alive_after_release_count": 0,
        "calls": {
            "array_metadata": 0,
            "non_temperature_buffer_to_volume": 0,
            "non_temperature_volume_metadata": 0,
            "non_temperature_save": 0,
            "non_temperature_typed_read": 0,
            "velocity_sampling": 0,
            "velocity_collector": 0,
            "temperature_buffer_to_volume": 0,
            "temperature_metadata": 0,
            "temperature_save": 0,
            "temperature_typed_read": 0,
            "temperature_sampling": 0,
            "temperature_collector": 0,
        },
        "checkpoints": [
            {"name": "phase6hc_readback_after"},
            {"name": "phase6hc_release_after"},
            {"name": COMPLETE_MARKER},
        ],
    }


def evaluate(root: Path, report, markers=(), *, resource_pass=True, cleanup_pass=True) -> dict:
    report_path = root / "post_readback_isolation.json"
    marker_path = root / "resource_markers.jsonl"
    if report == "invalid":
        report_path.write_text("{not-json", encoding="utf-8")
    elif report is not None:
        report_path.write_text(json.dumps(report), encoding="utf-8")
    if markers is not None:
        marker_path.write_text("".join(json.dumps({"marker": name}) + "\n" for name in markers), encoding="utf-8")
    return evaluate_operation_files(
        report_path, marker_path, expected_condition=CONDITION,
        expected_attempt_id=CONDITION, resource_pass=resource_pass, cleanup_pass=cleanup_pass,
    )


def main() -> int:
    results = []

    def case(name: str, mutate=None, markers=(), expected=True, report_seed=True,
             resource_pass=True, cleanup_pass=True) -> None:
        with tempfile.TemporaryDirectory(prefix=f"phase6hc-{name}-") as temporary:
            root = Path(temporary)
            report = normal_report() if report_seed is True else report_seed
            if mutate is not None and isinstance(report, dict):
                mutate(report)
            outcome = evaluate(root, report, markers, resource_pass=resource_pass, cleanup_pass=cleanup_pass)
            results.append({"name": name, "expected": expected, "actual": outcome["pass"],
                            "pass": outcome["pass"] is expected, "reasons": outcome["reasons"]})

    case("normal_phase6hb_a_shape", expected=True)
    case("operation_complete_missing", lambda row: row.update(operation_complete=False), expected=False)
    case("report_file_missing", report_seed=None, expected=False)
    case("json_corrupt", report_seed="invalid", expected=False)
    case("schema_mismatch", lambda row: row.update(schema="campfire.phase6hb.candidate-lifecycle-operation.v1"), expected=False)
    case("condition_mismatch", lambda row: row.update(condition="b_bounded_array_metadata"), expected=False)
    case("attempt_identity_mismatch", lambda row: row["attempt_identity"].update(attempt_id="wrong-attempt"), expected=False)
    case("resource_only_complete", lambda row: row.update(operation_complete=False), markers=(COMPLETE_MARKER,), expected=False)
    case("canonical_resource_agree", markers=(COMPLETE_MARKER,), expected=True)
    case("canonical_resource_conflict", markers=(FAILURE_MARKER,), expected=False)
    case("references_incomplete", lambda row: row.update(references_released=False), expected=False)
    case("forbidden_temperature_call", lambda row: row["calls"].update(temperature_buffer_to_volume=1), expected=False)
    case("resource_failure", resource_pass=False, expected=False)
    case("cleanup_failure", cleanup_pass=False, expected=False)
    case("legacy_name_only_not_accepted", lambda row: row.update(
        operation_complete=False,
        last_operation_marker="phase6hb_operation_complete",
        checkpoints=[{"name": "phase6hb_operation_complete"}],
    ), expected=False)
    case("weak_residual", lambda row: row.update(weak_reference_alive_after_release_count=1), expected=False)

    source = (Path(__file__).resolve().parent / "probe_phase6hc_candidate_lifecycle.py").read_text(encoding="utf-8")
    results.extend([
        {"name": "wrapper_sets_canonical_schema", "expected": True,
         "actual": "\"schema\": SCHEMA" in source, "pass": "\"schema\": SCHEMA" in source, "reasons": []},
        {"name": "wrapper_binds_attempt_identity", "expected": True,
         "actual": "ATTEMPT_ID != CONDITION" in source, "pass": "ATTEMPT_ID != CONDITION" in source, "reasons": []},
    ])
    contract_path = Path(__file__).resolve().parent / "phase6hc_candidate_lifecycle_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="phase6hc-command-") as temporary:
        command = " ".join(build_command(CONDITION, "R0", Path(temporary), contract))
        results.extend([
            {"name": "actual_command_uses_phase6hc_probe", "expected": True,
             "actual": "probe_phase6hc_candidate_lifecycle.py" in command,
             "pass": "probe_phase6hc_candidate_lifecycle.py" in command, "reasons": []},
            {"name": "actual_command_uses_phase6hc_report_phase", "expected": True,
             "actual": "-ReportPhase phase6hc" in command,
             "pass": "-ReportPhase phase6hc" in command, "reasons": []},
        ])
    report = {
        "schema": "campfire.phase6hc.operation-evidence-e2e-fixture.v1",
        "pass": all(row["pass"] for row in results), "count": len(results), "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
