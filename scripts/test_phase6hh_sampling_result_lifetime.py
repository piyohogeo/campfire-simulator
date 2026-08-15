"""No-Kit producer/consumer and one-variable fixtures for Phase 6HH."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import phase6hf_operation_schema as hf
import phase6hh_retention_contract as contract
import run_phase6hh_sampling_result_lifetime as runner

ROOT = Path(__file__).resolve().parents[1]


def result(name: str, passed: bool, detail=None) -> dict:
    return {"name": name, "pass": bool(passed), "detail": detail}


def populate(report: dict, condition: str) -> None:
    report["calls"].update(contract.expected_counts(condition))
    row = contract.ROW_BY_NAME[condition]
    report["executed_roi_names"] = [] if row["roi_count"] == 0 else ["scene"]
    report["references_released"] = True
    report["weak_reference_alive_after_release_count"] = 0
    if row["roi_count"]:
        report["sampling_result_evidence"] = {
            "python_type": "builtins.dict",
            "container_structure": "mapping_with_scalar_leaves",
            "keys": ["available", "maximum", "mean", "nonzero_voxel_count", "p95", "sum", "voxel_count"],
            "value_types": {},
            "contains_numpy": False,
            "contains_native_wrapper": False,
            "weakref_supported": False,
            "sample_result_identity": 123,
        }
        report["sampling_bounded_metadata"] = {
            "available": True, "voxel_count": 3, "nonzero_voxel_count": 2,
            "mean": 1.0, "sum": 3.0, "p95": 2.0, "maximum": 2.0,
        }
        report["sampling_local_result_clear_completed"] = True
        report["sampling_result_retained_count"] = 1 if row["retention"] == "retain" else 0
        report["sampling_result_retained_to_operation_report"] = row["retention"] == "retain"
    contract.complete_operation(report)


def validate(report: dict, condition: str, root: Path) -> dict:
    report_path = root / f"{condition}.json"
    resource_path = root / f"{condition}.jsonl"
    contract.write_operation_report(report_path, report)
    resource_path.write_text("", encoding="utf-8")
    return contract.validate_operation_files(
        report_path, resource_path,
        expected_condition=condition, expected_attempt_id=condition,
        resource_pass=True, cleanup_pass=True,
    )


def main() -> int:
    rows: list[dict] = []
    audit = contract.build_read_only_audit(ROOT)
    rows.append(result("read_only_audit_pass", audit["status"] == "pass"))
    rows.append(result("audit_confirms_dict_scalar_result", audit["sample_result"]["python_type"] == "builtins.dict" and not audit["sample_result"]["contains_numpy"] and not audit["sample_result"]["contains_native_wrapper"]))
    rows.append(result("audit_confirms_phase6hf_lifecycle_only_failure", audit["phase6hf_r1_axes"]["sampling_complete"] and audit["phase6hf_r1_axes"]["shutdown_complete"] and not audit["phase6hf_r1_axes"]["natural_os_exit"]))
    rows.append(result("fixed_ladder_order", [row["mode"] for row in contract.CONDITIONS] == ["L0", "L1", "L2"]))
    rows.append(result("single_variable_retention", contract.CONDITIONS[1]["roi_count"] == contract.CONDITIONS[2]["roi_count"] == 1 and contract.CONDITIONS[1]["retention"] != contract.CONDITIONS[2]["retention"]))

    with tempfile.TemporaryDirectory(prefix="phase6hh-fixture-") as temp:
        root = Path(temp)
        for condition in contract.ROW_BY_NAME:
            report = contract.new_runtime_report(condition=condition, attempt_id=condition)
            populate(report, condition)
            verdict = validate(report, condition, root)
            rows.append(result(f"producer_to_consumer_{condition}", verdict["pass"], verdict["reasons"]))

        for key in hf.COUNTER_KEYS:
            report = contract.new_runtime_report(condition="l1_scene_immediate_clear", attempt_id="l1_scene_immediate_clear")
            populate(report, "l1_scene_immediate_clear")
            del report["calls"][key]
            verdict = validate(report, "l1_scene_immediate_clear", root)
            rows.append(result(f"missing_{key}", f"forbidden_call_missing:{key}" in verdict["reasons"], verdict["reasons"]))

        mutations = {
            "wrong_retention": ("retention_mode", "retain", "retention_mode_mismatch"),
            "missing_result_evidence": ("sampling_result_evidence", None, "sampling_result_evidence_missing"),
            "numpy_owner": ("sampling_result_evidence.contains_numpy", True, "sampling_result_contains_forbidden_owner"),
            "local_not_cleared": ("sampling_local_result_clear_completed", False, "sampling_local_result_not_cleared"),
            "wrong_retained_count": ("sampling_result_retained_count", 1, "sampling_retained_count_mismatch"),
            "wrong_report_retention": ("sampling_result_retained_to_operation_report", True, "sampling_report_retention_mismatch"),
        }
        for name, (path, value, reason) in mutations.items():
            report = contract.new_runtime_report(condition="l1_scene_immediate_clear", attempt_id="l1_scene_immediate_clear")
            populate(report, "l1_scene_immediate_clear")
            if path == "sampling_result_evidence.contains_numpy":
                report["sampling_result_evidence"]["contains_numpy"] = value
            else:
                report[path] = value
            verdict = validate(report, "l1_scene_immediate_clear", root)
            rows.append(result(name, reason in verdict["reasons"], verdict["reasons"]))

    shared = (ROOT / "scripts/probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
    probe = (ROOT / "scripts/probe_phase6hh_sampling_result_lifetime.py").read_text(encoding="utf-8")
    run_source = (ROOT / "scripts/run_phase6hh_sampling_result_lifetime.py").read_text(encoding="utf-8")
    rows.extend([
        result("helper_default_retention_remains_legacy", 'if diagnostic_roi_result_retention is None:\n            result["rois"][name] = sample_result' in shared),
        result("helper_has_immediate_clear", 'diagnostic_roi_result_retention == "retain"' in shared and "sample_result = None" in shared),
        result("probe_uses_same_sample_helper", "hb.shared._save_and_sample(" in probe),
        result("probe_uses_same_scene_roi_source", "hb.shared._p3_world_rois()" in probe),
        result("probe_has_no_forced_gc", "gc.collect" not in probe and "gc.collect" not in shared),
        result("probe_forbids_temperature_collector_profile", '"temperature_conversion"' in probe and "spatial_collector=None" in probe and '"velocity_profile"' in probe),
        result("l1_l2_same_bounded_report_shape", 'hb.report["sampling_bounded_metadata"]' in probe and 'report_copy = {' in probe),
        result("runner_stops_first_non_normal", 'if summary["classification"] != "normal_exit":\n                break' in run_source),
        result("runner_has_no_retry_replacement", '"retries": 0' in run_source and '"replacements": 0' in run_source),
    ])
    contract_json = json.loads((ROOT / "scripts/phase6hh_sampling_result_lifetime_contract.json").read_text(encoding="utf-8"))
    rows.append(result("contract_matches_runtime_ladder", contract_json["ladder"] == [dict(row) for row in contract.CONDITIONS]))
    command = runner.build_command("l1_scene_immediate_clear", "L1", Path(tempfile.gettempdir()) / "phase6hh-command", contract_json)
    rows.append(result("command_uses_phase6hh_probe", any(str(value).endswith("probe_phase6hh_sampling_result_lifetime.py") for value in command)))
    rows.append(result("command_uses_phase6hh_report_phase", "phase6hh" in command))

    output = {
        "schema": "campfire.phase6hh.producer-consumer-fixture.v1",
        "pass": all(row["pass"] for row in rows),
        "count": len(rows),
        "results": rows,
        "audit": audit,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
