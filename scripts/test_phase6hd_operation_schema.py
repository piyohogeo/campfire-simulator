"""Producer-to-consumer no-Kit fixture for Phase 6HD."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from phase6hd_operation_schema import (
    COMPLETE_MARKER,
    COUNTER_KEYS,
    FAILURE_MARKER,
    SCHEMA,
    complete_operation,
    increment_counter,
    new_counter_values,
    new_runtime_report,
    validate_operation_files,
    write_operation_report,
)
from run_phase6hd_candidate_lifecycle import build_command

CONDITION = "a_readback_release_control"


def produce_a_report(path: Path) -> None:
    report = new_runtime_report(condition=CONDITION, attempt_id=CONDITION, mode="R0", features=[])
    increment_counter(report, "readback")
    report["public_readback_calls"] = 1
    report["references_released"] = True
    report["weak_reference_alive_after_release_count"] = 0
    complete_operation(report)
    write_operation_report(path, report)


def validate(root: Path, *, resource_pass=True, cleanup_pass=True) -> dict:
    return validate_operation_files(
        root / "post_readback_isolation.json",
        root / "resource_markers.jsonl",
        expected_condition=CONDITION,
        expected_attempt_id=CONDITION,
        resource_pass=resource_pass,
        cleanup_pass=cleanup_pass,
    )


def mutate_file(path: Path, mutation) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    mutation(report)
    write_operation_report(path, report)


def main() -> int:
    results = []

    def record(name: str, outcome: dict, expected: bool, required_reason: str | None = None) -> None:
        reason_ok = required_reason is None or required_reason in outcome["reasons"]
        results.append({
            "name": name, "expected": expected, "actual": outcome["pass"],
            "required_reason": required_reason,
            "reasons": outcome["reasons"],
            "pass": outcome["pass"] is expected and reason_ok,
        })

    with tempfile.TemporaryDirectory(prefix="phase6hd-e2e-") as temporary:
        root = Path(temporary)
        report_path = root / "post_readback_isolation.json"
        marker_path = root / "resource_markers.jsonl"
        marker_path.write_text("", encoding="utf-8")

        factory_defaults = new_counter_values()
        record("canonical_factory_has_all_explicit_int_zeros", {
            "pass": tuple(factory_defaults) == COUNTER_KEYS
                    and all(type(value) is int and value == 0 for value in factory_defaults.values()),
            "reasons": [],
        }, True)

        produce_a_report(report_path)
        produced = json.loads(report_path.read_text(encoding="utf-8"))
        counters = produced["calls"]
        record("producer_has_exact_counter_set", {
            "pass": tuple(counters.keys()) == tuple(sorted(COUNTER_KEYS)), "reasons": []
        }, True)
        record("producer_preserves_explicit_zero_for_uninvoked_counters", {
            "pass": all(type(value) is int and value == (1 if key == "readback" else 0)
                        for key, value in counters.items()), "reasons": []
        }, True)
        record("actual_producer_to_consumer_a_pass", validate(root), True)

        for key in COUNTER_KEYS:
            produce_a_report(report_path)
            mutate_file(report_path, lambda row, key=key: row["calls"].pop(key))
            record(f"missing_{key}", validate(root), False, f"forbidden_call_missing:{key}")

        for key in COUNTER_KEYS:
            if key == "readback":
                continue
            produce_a_report(report_path)
            mutate_file(report_path, lambda row, key=key: row["calls"].__setitem__(key, 1))
            record(f"nonzero_{key}", validate(root), False, f"forbidden_call_nonzero:{key}")

        type_key = COUNTER_KEYS[-3]
        for label, invalid in (("bool", False), ("null", None), ("string", "0"), ("float", 0.0)):
            produce_a_report(report_path)
            mutate_file(report_path, lambda row, value=invalid: row["calls"].__setitem__(type_key, value))
            record(f"invalid_type_{label}", validate(root), False, f"call_count_type_invalid:{type_key}")

        mutations = (
            ("schema_mismatch", lambda row: row.update(schema="legacy.schema"), "canonical_schema_mismatch"),
            ("condition_mismatch", lambda row: row.update(condition="b_bounded_array_metadata"), "canonical_condition_mismatch"),
            ("attempt_mismatch", lambda row: row["attempt_identity"].update(attempt_id="wrong"), "attempt_identity_mismatch"),
            ("operation_complete_missing", lambda row: row.update(operation_complete=False), "canonical_operation_incomplete"),
            ("references_incomplete", lambda row: row.update(references_released=False), "references_not_released"),
            ("weak_residual", lambda row: row.update(weak_reference_alive_after_release_count=1), "weak_reference_residual_nonzero"),
            ("unknown_key", lambda row: row["calls"].update(unknown_counter=0), "call_count_unknown:unknown_counter"),
        )
        for name, mutation, reason in mutations:
            produce_a_report(report_path)
            mutate_file(report_path, mutation)
            record(name, validate(root), False, reason)

        produce_a_report(report_path)
        record("resource_failure", validate(root, resource_pass=False), False, "resource_gate_failed")
        produce_a_report(report_path)
        record("cleanup_failure", validate(root, cleanup_pass=False), False, "cleanup_gate_failed")

        report_path.unlink()
        marker_path.write_text(json.dumps({"marker": COMPLETE_MARKER}) + "\n", encoding="utf-8")
        record("resource_only_not_substitute", validate(root), False, "canonical_report_missing")

        produce_a_report(report_path)
        marker_path.write_text(json.dumps({"marker": FAILURE_MARKER}) + "\n", encoding="utf-8")
        record("canonical_resource_conflict", validate(root), False, "canonical_resource_operation_conflict")

        # Removing a validator-required key from actual producer output must break the E2E path.
        marker_path.write_text("", encoding="utf-8")
        produce_a_report(report_path)
        first_key = COUNTER_KEYS[0]
        mutate_file(report_path, lambda row: row["calls"].pop(first_key))
        record("producer_required_key_deletion_breaks_e2e", validate(root), False,
               f"forbidden_call_missing:{first_key}")

    script_dir = Path(__file__).resolve().parent
    probe_source = (script_dir / "probe_phase6hd_candidate_lifecycle.py").read_text(encoding="utf-8")
    validator_source = (script_dir / "phase6hd_operation_schema.py").read_text(encoding="utf-8")
    results.extend([
        {"name": "probe_uses_shared_report_factory", "expected": True,
         "actual": "new_runtime_report(" in probe_source,
         "required_reason": None, "reasons": [], "pass": "new_runtime_report(" in probe_source},
        {"name": "probe_has_no_independent_counter_tuple", "expected": True,
         "actual": "COUNTER_KEYS =" not in probe_source,
         "required_reason": None, "reasons": [], "pass": "COUNTER_KEYS =" not in probe_source},
        {"name": "validator_uses_same_counter_tuple", "expected": True,
         "actual": validator_source.count("COUNTER_KEYS =") == 1,
         "required_reason": None, "reasons": [], "pass": validator_source.count("COUNTER_KEYS =") == 1},
    ])
    contract = json.loads((script_dir / "phase6hd_candidate_lifecycle_contract.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="phase6hd-command-") as temporary:
        command = " ".join(build_command(CONDITION, "R0", Path(temporary), contract))
        for name, token in (
            ("command_uses_phase6hd_probe", "probe_phase6hd_candidate_lifecycle.py"),
            ("command_uses_phase6hd_report_phase", "-ReportPhase phase6hd"),
        ):
            results.append({"name": name, "expected": True, "actual": token in command,
                            "required_reason": None, "reasons": [], "pass": token in command})

    summary = {
        "schema": "campfire.phase6hd.producer-consumer-fixture.v1",
        "pass": all(row["pass"] for row in results),
        "count": len(results), "counter_schema": list(COUNTER_KEYS), "results": results,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
