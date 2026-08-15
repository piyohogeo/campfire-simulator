"""No-Kit producer/consumer and exact ROI-prefix fixture for Phase 6HF."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6hf_operation_schema import (
    CONDITIONS,
    COUNTER_KEYS,
    ROI_ORDER,
    complete_operation,
    expected_counts,
    increment_counter,
    new_counter_values,
    new_runtime_report,
    validate_operation_files,
    write_operation_report,
)
from run_phase6hf_velocity_roi_lifecycle import build_command


def produce_report(root: Path, condition: str) -> Path:
    report = new_runtime_report(condition=condition, attempt_id=condition)
    for key, value in expected_counts(condition).items():
        if value:
            increment_counter(report, key, value)
    report["executed_roi_names"] = list(next(row["roi_names"] for row in CONDITIONS if row["name"] == condition))
    report["references_released"] = True
    report["weak_reference_alive_after_release_count"] = 0
    complete_operation(report)
    path = root / "post_readback_isolation.json"
    write_operation_report(path, report)
    return path


def rewrite(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    results = []

    def check(name: str, passed: bool, detail=None) -> None:
        results.append({"name": name, "pass": bool(passed), "detail": detail})

    defaults = new_counter_values()
    check("factory_uses_phase6he_25_key_schema", len(defaults) == 25 and tuple(defaults) == COUNTER_KEYS)
    check("factory_all_explicit_integer_zero", all(type(value) is int and value == 0 for value in defaults.values()))
    check("fixed_roi_order", ROI_ORDER == ("scene", "inter_log_gap", "flame_rise", "opposite_above", "side_control"))
    check("six_cumulative_conditions", [row["roi_count"] for row in CONDITIONS] == list(range(6)))
    check("each_condition_adds_one_roi", all(row["roi_names"] == list(ROI_ORDER[:row["roi_count"]]) for row in CONDITIONS))

    with tempfile.TemporaryDirectory(prefix="phase6hf-e2e-") as temporary:
        root = Path(temporary)
        resource = root / "resource_markers.jsonl"
        resource.write_text("", encoding="utf-8")
        for row in CONDITIONS:
            report_path = produce_report(root, row["name"])
            verdict = validate_operation_files(
                report_path,
                resource,
                expected_condition=row["name"],
                expected_attempt_id=row["name"],
                resource_pass=True,
                cleanup_pass=True,
            )
            check(f"producer_to_consumer_{row['mode']}", verdict["pass"], verdict["reasons"])

        baseline = CONDITIONS[0]["name"]
        for key in COUNTER_KEYS:
            report_path = produce_report(root, baseline)
            rewrite(report_path, lambda value, key=key: value["calls"].pop(key))
            verdict = validate_operation_files(
                report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
                resource_pass=True, cleanup_pass=True,
            )
            check(f"missing_{key}", f"forbidden_call_missing:{key}" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value["calls"].__setitem__("velocity_roi_sampling", 1))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("r0_rejects_sampling", "forbidden_call_nonzero:velocity_roi_sampling" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, CONDITIONS[-1]["name"])
        rewrite(report_path, lambda value: value.__setitem__("executed_roi_names", list(reversed(ROI_ORDER))))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=CONDITIONS[-1]["name"], expected_attempt_id=CONDITIONS[-1]["name"],
            resource_pass=True, cleanup_pass=True,
        )
        check("rejects_roi_order_mismatch", "executed_roi_order_mismatch" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value["calls"].__setitem__("velocity_profile", 1))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("profile_forbidden", "forbidden_call_nonzero:velocity_profile" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value["calls"].__setitem__("temperature_conversion", 1))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("temperature_forbidden", "forbidden_call_nonzero:temperature_conversion" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value.__setitem__("references_released", False))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("release_required", "references_not_released" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=False, cleanup_pass=True,
        )
        check("resource_fail_closed", "resource_gate_failed" in verdict["reasons"], verdict["reasons"])
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=False,
        )
        check("cleanup_fail_closed", "cleanup_gate_failed" in verdict["reasons"], verdict["reasons"])

    helper = (SCRIPT_DIR / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
    probe = (SCRIPT_DIR / "probe_phase6hf_velocity_roi_lifecycle.py").read_text(encoding="utf-8")
    runner = (SCRIPT_DIR / "run_phase6hf_velocity_roi_lifecycle.py").read_text(encoding="utf-8")
    check("helper_roi_limit_default_none", "diagnostic_roi_limit: int | None = None" in helper)
    check("helper_limits_existing_order", "roi_items = roi_items[:diagnostic_roi_limit]" in helper)
    check("helper_retains_result_dictionary", 'result["rois"][name] = sample_result' in helper)
    check("helper_emits_bounded_sampling_metadata", 'nonzero_voxel_count=int(sample_result.get("nonzero_voxel_count", 0))' in helper)
    check("probe_uses_actual_save_and_sample", "hb.shared._save_and_sample(" in probe)
    check("probe_uses_existing_world_rois", "hb.shared._p3_world_rois()" in probe)
    check("probe_preserves_result_until_release", probe.index('hb.report["velocity_result"] = velocity_result') < probe.index("velocity_result = None"))
    check("probe_uses_cumulative_limit", "diagnostic_roi_limit=None if roi_count == 0 else roi_count" in probe)
    check("probe_has_no_collector", "spatial_collector=None" in probe and '"velocity_collector"' in probe)
    check("probe_forbids_profile", '"velocity_profile"' in probe and 'diagnostic_stop_after="basic_metadata" if roi_count == 0 else "roi_sampling"' in probe)
    check("probe_has_no_temperature_conversion", "buffer_to_volume(temperature" not in probe)
    check("runner_stops_first_non_normal", 'if summary["classification"] != "normal_exit":\n                break' in runner)
    check("runner_has_no_retry_or_replacement", '"retries": 0' in runner and '"replacements": 0' in runner)

    contract = json.loads((SCRIPT_DIR / "phase6hf_velocity_roi_lifecycle_contract.json").read_text(encoding="utf-8"))
    canonical = [
        {key: row[key] for key in ("name", "mode", "roi_count", "roi_names", "adds")}
        for row in CONDITIONS
    ]
    check("contract_ladder_matches_runtime", contract["ladder"] == canonical)
    check("contract_freezes_phase6he", contract["history"]["phase6he_frozen"] and not contract["history"]["phase6he_artifacts_reused"])
    check("r5_matches_phase6he_v6_roi_order", CONDITIONS[-1]["roi_names"] == list(ROI_ORDER))

    with tempfile.TemporaryDirectory(prefix="phase6hf-command-") as temporary:
        command = build_command(CONDITIONS[0]["name"], "R0", Path(temporary), contract)
        check("command_uses_phase6hf_probe", any(value.endswith("probe_phase6hf_velocity_roi_lifecycle.py") for value in command), command)
        check("command_uses_phase6hf_report_phase", "phase6hf" in command)
        check("command_uses_frozen_r2_prefix", "R2" in command)

    report = {
        "schema": "campfire.phase6hf.producer-consumer-fixture.v1",
        "pass": all(row["pass"] for row in results),
        "count": len(results),
        "counter_schema": list(COUNTER_KEYS),
        "roi_order": list(ROI_ORDER),
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
