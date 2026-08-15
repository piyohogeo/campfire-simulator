"""No-Kit contract and static fixtures for Phase 6HB."""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

from phase6hb_candidate_lifecycle_contract import LADDER, classify_axes, validate_ladder
from run_phase6hb_candidate_lifecycle import build_command

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent


def evidence(**updates) -> dict:
    base = {
        "markers": [
            "phase6hb_readback_after", "phase6hb_release_after", "phase6hb_operation_complete",
            "stage_close_complete", "shutdown_complete",
        ],
        "operation_result": "pass", "references_released": True,
        "temperature_volume_calls": 0, "temperature_metadata_calls": 0,
        "temperature_save_calls": 0, "temperature_sampling_calls": 0,
        "temperature_typed_read_calls": 0, "temperature_collector_calls": 0,
        "raw_classification": "normal_exit", "process_exit_code": 0,
        "resource_pass": True, "cleanup_pass": True, "residual_process_count": 0,
    }
    base.update(updates)
    return base


def main() -> int:
    results = []

    def check(name: str, condition: bool) -> None:
        results.append({"name": name, "pass": bool(condition)})

    rows = [{"name": row["name"], "features": row["features"]} for row in LADDER]
    check("ladder_positive", validate_ladder(rows)["pass"])
    malformed = [dict(row) for row in rows]
    malformed[2]["features"] = tuple(LADDER[0]["features"])
    check("ladder_rejects_non_increment", not validate_ladder(malformed)["pass"])
    check("normal_exit", classify_axes(evidence())["classification"] == "normal_exit")
    check("operation_failure", classify_axes(evidence(operation_result="failure"))["classification"] == "operation_failure")
    check("missing_stage_close", classify_axes(evidence(markers=[
        "phase6hb_readback_after", "phase6hb_release_after", "phase6hb_operation_complete", "shutdown_complete"
    ]))["classification"] == "stage_close_failure")
    check("missing_shutdown", classify_axes(evidence(markers=[
        "phase6hb_readback_after", "phase6hb_release_after", "phase6hb_operation_complete", "stage_close_complete"
    ]))["classification"] == "shutdown_marker_failure")
    check("post_shutdown_exit_failure", classify_axes(evidence(
        raw_classification="os_exit_timeout", process_exit_code=None
    ))["classification"] == "post_shutdown_os_exit_failure")
    check("resource_failure", classify_axes(evidence(resource_pass=False))["classification"] == "safety_failure")
    check("cleanup_failure", classify_axes(evidence(cleanup_pass=False))["classification"] == "safety_failure")
    check("residual_failure", classify_axes(evidence(residual_process_count=1))["classification"] == "safety_failure")
    check("temperature_call_rejected", classify_axes(evidence(temperature_volume_calls=1))["classification"] == "operation_failure")

    probe_path = SCRIPT_DIR / "probe_phase6hb_candidate_lifecycle.py"
    runner_path = SCRIPT_DIR / "run_phase6hb_candidate_lifecycle.py"
    contract_path = SCRIPT_DIR / "phase6hb_candidate_lifecycle_contract.json"
    probe = probe_path.read_text(encoding="utf-8")
    runner = runner_path.read_text(encoding="utf-8")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ast.parse(probe)
    ast.parse(runner)
    check("temperature_index_excluded_from_schema_prefix", "for index in range(1, 6):" in probe)
    check("single_velocity_pipeline_callsite", probe.count("shared._save_and_sample(") == 1)
    check("no_numpy_asarray", "np.asarray" not in probe and "numpy.asarray" not in probe)
    check("no_temperature_native_callsite", "buffer_to_volume(temperature_alias" not in probe)
    check("no_temperature_save_callsite", "save_volume(temperature" not in probe)
    check("temperature_prohibitions_zero", all(value == 0 for value in contract["temperature_prohibitions"].values()))
    check("six_one_shot_conditions", contract["execution"]["maximum_launches"] == 6 and
          contract["execution"]["retries"] == 0 and contract["execution"]["replacements"] == 0)
    check("runner_stops_first_non_normal", "if summary[\"classification\"] != \"normal_exit\":" in runner)
    check("runner_refuses_root_reuse", "refuses artifact root reuse" in runner)
    check("history_frozen", contract["history"] == {
        "phase6gz_frozen": True, "phase6ha_frozen": True,
        "reclassified": False, "runtime_samples_reused": False,
    })
    check("identical_conditions_omitted", set(contract["audit"]["identical_conditions_omitted"]) == {
        "candidate_stage_payload_only", "collector_generation_only", "ownership_release_order_only",
    })

    with tempfile.TemporaryDirectory(prefix="phase6hb-command-") as temporary:
        command = build_command("a_readback_release_control", "R0", Path(temporary), contract)
        joined = " ".join(str(value) for value in command)
        check("actual_command_uses_phase6hb_probe", "probe_phase6hb_candidate_lifecycle.py" in joined)
        check("actual_command_uses_phase6hb_report_phase", "-ReportPhase phase6hb" in joined)
        check("actual_command_fixes_common_stage_arguments", all(token in joined for token in (
            "production_four", "phase6er_corrected", "allow_self_center", "60,120,180,240",
            "-SpatialColliderIndices 0,1,2,3", "-RendererDrainUpdates 8", "after_stage_close",
        )))
        check("actual_command_has_no_retry_or_replacement", "retry" not in joined.lower() and "replacement" not in joined.lower())

    gs = (SCRIPT_DIR / "probe_phase6gs_volume_metadata.py").read_text(encoding="utf-8")
    gz = (SCRIPT_DIR / "probe_phase6gz_candidate_boundary.py").read_text(encoding="utf-8")
    shared = (SCRIPT_DIR / "probe_phase6fo_supply_comparison.py").read_text(encoding="utf-8")
    check("same_phase6gn_base", "probe_phase6gn_supply_comparison.py" in gs and "probe_phase6gn_supply_comparison.py" in gz)
    check("shared_release_after_close_path_present", "after_stage_close" in shared and "post_close_renderer_update" in shared)

    report = {
        "schema": "campfire.phase6hb.no-kit-fixture.v1",
        "pass": all(row["pass"] for row in results),
        "count": len(results), "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
