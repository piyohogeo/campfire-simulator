"""Aggregate Phase 6FE lag-aware one-readback/fuel-alias qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .analyze_phase6fd_fuel_alias_lifetime import _case as phase6fd_case
    from .analyze_phase6ew_r0_lifecycle import _json
    from .phase6fe_lagged_memory_response import evaluate
except ImportError:
    from analyze_phase6fd_fuel_alias_lifetime import _case as phase6fd_case
    from analyze_phase6ew_r0_lifecycle import _json
    from phase6fe_lagged_memory_response import evaluate


ORDERED_C1_MARKERS = [
    "startup_liveness_confirmed", "readback_call_before", "readback_call_after",
    "fuel_handle_selected", "fuel_conversion_before", "fuel_conversion_after",
    "original_tuple_and_all_handle_aliases_released", "converted_buffer_only_held",
    "converted_buffer_released", "python_references_released", "next_frame_started",
    "stability_observation_ended", "timeline_stop_request_before",
    "stage_close_request_before", "stage_close_request_after",
]


def _legacy_adapter(contract: dict) -> dict:
    adapted = dict(contract)
    adapted["dynamic_stationarity_thresholds"] = contract["global_boundedness_thresholds"]
    adapted["ordered_c1_markers"] = ORDERED_C1_MARKERS
    adapted["phase6ey_history"] = {
        "reference_only_immediate_acquire_delta_bytes": 144936960,
    }
    adapted["required_probe_markers"] = [
        "startup_liveness_confirmed", "stability_observation_started", "final_sample_complete",
        "stability_observation_ended", "measurement_complete", "timeline_stop_request_before",
        "timeline_stop_request_after", "timeline_stop_confirmed", "renderer_drain_started",
        "renderer_drain_complete", "flow_references_release_started", "flow_references_release_complete",
        "provider_readback_references_release_started", "provider_readback_references_release_complete",
        "stage_close_request_before", "stage_close_request_after", "usd_context_disconnected",
        "app_close_requested", "shutdown_complete",
    ]
    adapted["required_extension_markers"] = [
        "extension_on_startup", "extension_on_shutdown_begin", "extension_on_shutdown_end",
    ]
    adapted["required_runner_markers"] = ["os_process_exit_observed"]
    return adapted


def _case(run_root: Path, label: str, contract: dict) -> dict:
    case = phase6fd_case(run_root, label, _legacy_adapter(contract))
    legacy_failures = set(case.get("condition_gate_failures") or [])
    legacy_failures.discard("dynamic_stationarity")
    lagged = evaluate(case["aligned_time_series"], contract)
    failures = list(legacy_failures)
    if not lagged["gate_pass"]:
        failures.append("lagged_memory_response")
    if label == "C1_fuel_alias":
        boundary = case.get("boundary") or {}
        observable = boundary.get("observable_copy_contract") or {}
        delta = case["memory_deltas_bytes"].get("fuel_conversion_immediate")
        limit = int(contract["cross_run_reproducibility"]["maximum_absolute_c1_asarray_delta_bytes"])
        if observable.get("allocation_classification") != "same_object_zero_copy_alias":
            failures.append("not_same_object_zero_copy_alias")
        if delta is None or abs(int(delta)) > limit:
            failures.append("asarray_adjacent_delta")
    case["phase6fd_same_sample_history"] = case.pop("dynamic_stationarity")
    case["phase6fd_same_sample_history_pass"] = case.pop("dynamic_stationarity_pass")
    case["lagged_memory_response"] = lagged
    case["condition_gate_failures"] = sorted(set(failures))
    case["condition_gate_pass"] = not case["condition_gate_failures"]
    return case


def _ratio(values: list[float]) -> float | None:
    return None if not values or min(values) <= 0 else max(values) / min(values)


def _pair(c0: dict | None, c1: dict | None, contract: dict) -> dict:
    if not c0 or not c1:
        return {"complete": False, "gate_pass": False, "failures": ["pair_incomplete"]}
    maximum_ratio = float(contract["cross_run_reproducibility"]["maximum_active_mean_ratio"])
    a0 = c0["lagged_memory_response"]["global_boundedness"]["metrics"]["active_blocks"]["mean"]
    a1 = c1["lagged_memory_response"]["global_boundedness"]["metrics"]["active_blocks"]["mean"]
    ratio = max(a0, a1) / min(a0, a1)
    failures = []
    if not c0["condition_gate_pass"] or not c1["condition_gate_pass"]:
        failures.append("condition_gate")
    if ratio > maximum_ratio:
        failures.append("active_scale_ratio")
    if c0["startup"]["normalized_stage_sha256"] != c1["startup"]["normalized_stage_sha256"]:
        failures.append("stage_sha256")
    if c0["startup"]["payload_sha256"] != c1["startup"]["payload_sha256"]:
        failures.append("payload_sha256")
    return {
        "complete": True,
        "gate_pass": not failures,
        "failures": failures,
        "active_mean_c0": a0,
        "active_mean_c1": a1,
        "active_mean_max_min_ratio": ratio,
        "c1_asarray_immediate_delta_bytes": c1["memory_deltas_bytes"].get("fuel_conversion_immediate"),
        "c1_readback_immediate_delta_bytes": c1["memory_deltas_bytes"].get("readback_immediate"),
        "c1_observation_end_residual_bytes": c1["memory_deltas_bytes"].get("observation_end_residual"),
    }


def _cross_run(cases: dict, contract: dict) -> dict:
    if len(cases) != 6:
        return {"complete": False, "gate_pass": False, "failures": ["population_incomplete"]}
    limits = contract["cross_run_reproducibility"]
    c0 = [cases[f"run{index:02d}_C0_acquire_discard"] for index in range(1, 4)]
    c1 = [cases[f"run{index:02d}_C1_fuel_alias"] for index in range(1, 4)]
    all_cases = c0 + c1
    active_ratio = _ratio([
        case["lagged_memory_response"]["global_boundedness"]["metrics"]["active_blocks"]["mean"]
        for case in all_cases
    ])
    peak_ratio = _ratio([float(case["kit_peak_private_bytes"]) for case in all_cases])
    terminal_ratio = _ratio([float(case["terminal_kit_private_bytes"]) for case in all_cases])
    c0_deltas = [int(case["memory_deltas_bytes"]["readback_immediate"]) for case in c0]
    stage_close = [float(case["stage_close_seconds"]) for case in all_cases]
    failures = []
    if any(not case["condition_gate_pass"] for case in all_cases):
        failures.append("condition_gate")
    if active_ratio is None or active_ratio > float(limits["maximum_active_mean_ratio"]):
        failures.append("active_mean_ratio")
    if peak_ratio is None or peak_ratio > float(limits["maximum_kit_peak_ratio"]):
        failures.append("kit_peak_ratio")
    if terminal_ratio is None or terminal_ratio > float(limits["maximum_terminal_private_ratio"]):
        failures.append("terminal_private_ratio")
    if max(c0_deltas) - min(c0_deltas) > int(limits["maximum_c0_immediate_acquire_delta_spread_bytes"]):
        failures.append("c0_acquire_delta_spread")
    if max(stage_close) > float(limits["maximum_stage_close_seconds"]):
        failures.append("stage_close")
    return {
        "complete": True,
        "gate_pass": not failures,
        "failures": failures,
        "active_mean_max_min_ratio": active_ratio,
        "kit_peak_max_min_ratio": peak_ratio,
        "terminal_private_max_min_ratio": terminal_ratio,
        "c0_acquire_delta_spread_bytes": max(c0_deltas) - min(c0_deltas),
        "stage_close_seconds": stage_close,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    pairs = {}
    for run_index in range(1, 4):
        run_root = args.root / f"run{run_index:02d}"
        for label in ("C0_acquire_discard", "C1_fuel_alias"):
            if (run_root / label).exists():
                cases[f"run{run_index:02d}_{label}"] = _case(run_root, label, contract)
        pairs[f"run{run_index:02d}"] = _pair(
            cases.get(f"run{run_index:02d}_C0_acquire_discard"),
            cases.get(f"run{run_index:02d}_C1_fuel_alias"),
            contract,
        )
    cross_run = _cross_run(cases, contract)
    report = {
        "schema": "campfire.phase6fe.lagged-memory-response-qualification-report.v1",
        "phase": "phase6fe",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "phase6fd_safe_stop_frozen": True,
        "cases": cases,
        "pairs": pairs,
        "cross_run_reproducibility": cross_run,
        "completed_conditions": len(cases),
        "qualified": bool(
            len(cases) == 6
            and all(case["condition_gate_pass"] for case in cases.values())
            and all(pair["gate_pass"] for pair in pairs.values())
            and cross_run["gate_pass"]
        ),
        "qualification_scope": "three independent C0/C1 pairs; one public readback and at most one fuel same-object alias per process",
        "repeated_readback_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
