"""Aggregate Phase 6FF control/C0/C1 memory boundedness qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .analyze_phase6ey_dynamic_stationarity import _case as phase6ey_case
    from .analyze_phase6fd_fuel_alias_lifetime import _case as phase6fd_case
    from .analyze_phase6fd_fuel_alias_lifetime import _runner_safety, _startup
    from .analyze_phase6ew_r0_lifecycle import _json
    from .phase6ff_memory_boundedness import evaluate
except ImportError:
    from analyze_phase6ey_dynamic_stationarity import _case as phase6ey_case
    from analyze_phase6fd_fuel_alias_lifetime import _case as phase6fd_case
    from analyze_phase6fd_fuel_alias_lifetime import _runner_safety, _startup
    from analyze_phase6ew_r0_lifecycle import _json
    from phase6ff_memory_boundedness import evaluate


ORDERED_C1 = [
    "startup_liveness_confirmed", "readback_call_before", "readback_call_after",
    "fuel_handle_selected", "fuel_conversion_before", "fuel_conversion_after",
    "original_tuple_and_all_handle_aliases_released", "converted_buffer_only_held",
    "converted_buffer_released", "python_references_released", "next_frame_started",
    "stability_observation_ended", "timeline_stop_request_before", "stage_close_request_before",
    "stage_close_request_after",
]


def compatibility(contract: dict) -> dict:
    # Compatibility fields are parser-only. Phase 6FF qualification exclusively
    # uses the new boundedness evaluator below.
    old = json.loads((Path(__file__).with_name("phase6fe_lagged_memory_response_contract.json")).read_text(encoding="utf-8"))
    result = dict(contract)
    result["dynamic_stationarity_thresholds"] = old["global_boundedness_thresholds"]
    result["plateau_contract"] = {
        "stability_frames": [240, 280, 320],
        "maximum_active_block_range_fraction": 1.0e9,
        "minimum_resource_samples_in_stability_interval": 0,
        "maximum_private_growth_bytes_per_second": 1.0e30,
    }
    result["ordered_c1_markers"] = ORDERED_C1
    result["phase6ey_history"] = {"reference_only_immediate_acquire_delta_bytes": 144936960}
    result["required_probe_markers"] = [
        "startup_liveness_confirmed", "stability_observation_started", "final_sample_complete",
        "stability_observation_ended", "measurement_complete", "timeline_stop_request_before",
        "timeline_stop_request_after", "timeline_stop_confirmed", "renderer_drain_started",
        "renderer_drain_complete", "flow_references_release_started", "flow_references_release_complete",
        "provider_readback_references_release_started", "provider_readback_references_release_complete",
        "stage_close_request_before", "stage_close_request_after", "usd_context_disconnected",
        "app_close_requested", "shutdown_complete",
    ]
    result["required_extension_markers"] = [
        "extension_on_startup", "extension_on_shutdown_begin", "extension_on_shutdown_end",
    ]
    result["required_runner_markers"] = ["os_process_exit_observed"]
    gates = dict(contract["gates"])
    gates.update({
        "required_public_readback_calls_per_condition": 1,
        "required_c1_numpy_asarray_calls": contract["gates"]["required_c1_numpy_asarray_calls"],
        "required_field_persistence_calls": 0,
        "c0_minimum_immediate_acquire_delta_bytes": 0,
        "c0_phase6ey_reference_maximum_absolute_delta_difference_bytes": 268435456,
    })
    result["gates"] = gates
    return result


def _common_gate(case: dict, contract: dict, startup: dict, safety: dict) -> list[str]:
    failures = []
    if startup.get("classification") != "representative_ingestion":
        failures.append("startup_not_representative")
    if not startup.get("identity_and_exact_source_pass") or not startup.get("exact_source_sums"):
        failures.append("startup_contract")
    if startup.get("payload_sha256") != contract["expected_stage"]["payload_sha256"]:
        failures.append("payload_sha256")
    if startup.get("normalized_stage_sha256") != contract["expected_stage"]["normalized_stage_sha256"]:
        failures.append("stage_sha256")
    if not case.get("normal_exit") or not case.get("probe_markers_complete") or not case.get("extension_markers_complete") or not case.get("runner_markers_complete"):
        failures.append("lifecycle")
    if not case.get("synchronous_memory_valid"):
        failures.append("memory_markers")
    if any(int(safety.get(key, -1)) != 0 for key in ("fatal_count", "dump_count", "upload_attempt_count")):
        failures.append("fatal_dump_or_upload")
    if safety.get("production_changed") is not False:
        failures.append("production_hash")
    if safety.get("functional_status") != "pass" or safety.get("lifecycle_status") != "normal_exit":
        failures.append("shutdown_classification")
    return failures


def case_for(group_root: Path, label: str, prefix: str, mode: str, contract: dict) -> dict:
    adapted = compatibility(contract)
    case_dir = group_root / label
    raw = _json(case_dir / "raw.json") or {}
    if mode == "control":
        case = phase6ey_case(group_root, label, prefix, adapted)
        startup = _startup(case_dir, raw, adapted)
        safety = _runner_safety(case_dir)
        counts = {}
        for sample in raw.get("samples", []):
            boundary = sample.get("readback_boundary") or {}
            if boundary:
                counts = boundary.get("operation_counts") or {}
                break
        failures = _common_gate(case, contract, startup, safety)
        if int(counts.get("public_readback_calls", 0)) != 0:
            failures.append("unexpected_readback")
    else:
        case = phase6fd_case(group_root, label, adapted)
        startup = case["startup"]
        safety = case["runner_safety"]
        failures = _common_gate(case, contract, startup, safety)
        boundary = case.get("boundary") or {}
        counts = boundary.get("operation_counts") or {}
        if counts.get("public_readback_calls") != 1:
            failures.append("public_readback_count")
        if counts.get("field_persistence_calls") != 0:
            failures.append("field_persistence")
        if mode == "c1":
            if counts.get("numpy_asarray_calls") != 1:
                failures.append("numpy_asarray_count")
            observable = boundary.get("observable_copy_contract") or {}
            if observable.get("allocation_classification") != "same_object_zero_copy_alias":
                failures.append("not_same_object_zero_copy_alias")
            delta = case["memory_deltas_bytes"].get("fuel_conversion_immediate")
            if delta is None or abs(int(delta)) > int(contract["control_comparison"]["maximum_absolute_c1_asarray_delta_bytes"]):
                failures.append("asarray_adjacent_delta")
    bounded = evaluate(case.get("aligned_time_series") or [], contract)
    if not bounded["gate_pass"]:
        failures.append("memory_boundedness")
    case.update({
        "startup": startup,
        "runner_safety": safety,
        "memory_boundedness": bounded,
        "condition_gate_failures": sorted(set(failures)),
        "condition_gate_pass": not failures,
    })
    return case


def _range_fraction(values: list[float]) -> float | None:
    return None if not values else (max(values) - min(values)) / max(1.0, sum(values) / len(values))


def group_gate(cases: list[dict], contract: dict, mode: str, controls: list[dict] | None = None) -> dict:
    if len(cases) != 3:
        return {"complete": False, "gate_pass": False, "failures": ["population_incomplete"]}
    limits = contract["control_comparison"]
    peaks = [float(case["kit_peak_private_bytes"]) for case in cases]
    terminals = [float(case["memory_boundedness"]["metrics"]["terminal_private_bytes"]) for case in cases]
    closes = [float(case["stage_close_seconds"]) for case in cases]
    active = [float(case["memory_boundedness"]["metrics"]["active_blocks"]["mean"]) for case in cases]
    failures = []
    if any(not case["condition_gate_pass"] for case in cases):
        failures.append("condition_gate")
    if _range_fraction(peaks) > float(limits["maximum_control_peak_range_fraction"]):
        failures.append("peak_reproducibility")
    if _range_fraction(terminals) > float(limits["maximum_control_terminal_range_fraction"]):
        failures.append("terminal_reproducibility")
    if max(closes) > float(limits["maximum_stage_close_seconds"]):
        failures.append("stage_close")
    comparison = None
    if controls:
        control_peak = statistics_median([float(case["kit_peak_private_bytes"]) for case in controls])
        control_terminal = statistics_median([float(case["memory_boundedness"]["metrics"]["terminal_private_bytes"]) for case in controls])
        control_active = statistics_median([float(case["memory_boundedness"]["metrics"]["active_blocks"]["mean"]) for case in controls])
        active_ratio = max(statistics_median(active), control_active) / min(statistics_median(active), control_active)
        comparison = {
            "median_peak_added_bytes": statistics_median(peaks) - control_peak,
            "median_terminal_added_bytes": statistics_median(terminals) - control_terminal,
            "active_mean_ratio": active_ratio,
        }
        if active_ratio > float(limits["maximum_active_mean_ratio"]):
            failures.append("active_scale")
        if comparison["median_peak_added_bytes"] > int(limits["maximum_readback_added_peak_bytes"]):
            failures.append("readback_added_peak")
        if comparison["median_terminal_added_bytes"] > int(limits["maximum_readback_added_terminal_bytes"]):
            failures.append("readback_added_terminal")
    return {
        "complete": True,
        "gate_pass": not failures,
        "failures": failures,
        "peak_range_fraction": _range_fraction(peaks),
        "terminal_range_fraction": _range_fraction(terminals),
        "stage_close_seconds": closes,
        "comparison_to_control": comparison,
    }


def statistics_median(values: list[float]) -> float:
    return sorted(values)[len(values) // 2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    cases = {}
    specifications = (
        ("control", "R0_none", "control"),
        ("c0", "C0_acquire_discard", "c0"),
        ("c1", "C1_fuel_alias", "c1"),
    )
    for group, label, mode in specifications:
        for run in range(1, 4):
            group_root = args.root / group / f"run{run:02d}"
            if (group_root / label).exists():
                key = f"{group}_run{run:02d}"
                cases[key] = case_for(group_root, label, label, mode, contract)
    controls = [cases[key] for key in sorted(cases) if key.startswith("control_")]
    c0s = [cases[key] for key in sorted(cases) if key.startswith("c0_")]
    c1s = [cases[key] for key in sorted(cases) if key.startswith("c1_")]
    groups = {
        "control": group_gate(controls, contract, "control"),
        "c0": group_gate(c0s, contract, "c0", controls if len(controls) == 3 else None),
        "c1": group_gate(c1s, contract, "c1", controls if len(controls) == 3 else None),
    }
    qualified = all(groups[name]["gate_pass"] for name in ("control", "c0", "c1"))
    report = {
        "schema": "campfire.phase6ff.memory-boundedness-qualification-report.v1",
        "phase": "phase6ff",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "phase6fd_phase6fe_history_frozen": True,
        "cases": cases,
        "groups": groups,
        "completed_conditions": len(cases),
        "qualified": qualified,
        "one_fuel_alias_lifetime_qualified": qualified,
        "repeated_readback_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
