"""Measure bounded whole-log approximate sleep against exact references.

This is an isolated Phase 6AT rejection/adoption trial.  It does not alter the
authoritative production model.  Accuracy histories compare two logs in
lockstep; performance histories run the twenty-log app contract over twelve
fixed frame slots with a moving five-log heat input.
"""

from __future__ import annotations

import argparse
import gc
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import json

import benchmark_app_scheduler_contract as app_contract
import benchmark_distributed_wood_updates as distributed
import benchmark_wood_scaling as scaling


@dataclass(frozen=True)
class ApproximateSleepCandidate:
    name: str
    maximum_ambient_deviation_k: float
    maximum_temperature_span_k: float
    maximum_consecutive_sleep_ticks: int


CANDIDATES = (
    ApproximateSleepCandidate("strict", 0.25, 0.10, 5),
    ApproximateSleepCandidate("balanced", 1.00, 0.50, 10),
    ApproximateSleepCandidate("aggressive", 5.00, 2.00, 25),
)
REACTION_MARGIN_K = 10.0
ACCURACY_SCENARIOS = {
    "gentle_pulse": 180,
    "flame_pulse": 180,
    "continuous_ignition": 360,
}
ERROR_BUDGETS = {
    "maximum_cell_temperature_error_k": 1.0,
    "maximum_surface_temperature_error_k": 0.25,
    "maximum_total_mass_error_kg": 1.0e-6,
    "maximum_flow_component_error": 0.002,
    "maximum_support_ratio_error": 1.0e-4,
    "maximum_ignition_time_error_s": scaling.DT_SECONDS,
    "maximum_mass_balance_error_kg": 1.0e-9,
    "maximum_frame_p95_ms": 4.0,
}


def _candidate_dict(candidate: ApproximateSleepCandidate) -> dict:
    return asdict(candidate)


def _accuracy_heat_flux(scenario: str, tick: int) -> float:
    if scenario == "gentle_pulse":
        return 2_000.0 if tick % 4 == 0 else 0.0
    if scenario == "flame_pulse":
        return 150_000.0 if tick % 4 == 0 else 0.0
    if scenario == "continuous_ignition":
        return 150_000.0
    raise ValueError(f"Unknown accuracy scenario: {scenario}")


def _oxygen_factor(tick: int, log_index: int) -> float:
    return 0.45 + 0.10 * (((tick // 30) + log_index) % 4)


def _can_sleep_approximately(
    model,
    external_heat_flux_w_m2: float,
    candidate: ApproximateSleepCandidate,
    consecutive_sleep_ticks: int,
) -> bool:
    if external_heat_flux_w_m2 != 0.0:
        return False
    if consecutive_sleep_ticks >= candidate.maximum_consecutive_sleep_ticks:
        return False
    parameters = model.parameters
    if parameters.pyrolysis_rate_model != "piecewise_linear":
        return False
    ambient = parameters.ambient_temperature_k
    reaction_limit = min(
        parameters.evaporation_start_temperature_k,
        parameters.pyrolysis_start_temperature_k,
        parameters.char_oxidation_start_temperature_k,
    ) - REACTION_MARGIN_K
    minimum_temperature = math.inf
    maximum_temperature = -math.inf
    maximum_ambient_deviation = 0.0
    for cell in model.cells:
        temperature = cell.temperature_k
        if not math.isfinite(temperature):
            return False
        minimum_temperature = min(minimum_temperature, temperature)
        maximum_temperature = max(maximum_temperature, temperature)
        maximum_ambient_deviation = max(
            maximum_ambient_deviation, abs(temperature - ambient)
        )
    return (
        maximum_temperature < reaction_limit
        and maximum_ambient_deviation
        <= candidate.maximum_ambient_deviation_k
        and maximum_temperature - minimum_temperature
        <= candidate.maximum_temperature_span_k
    )


def _advance_candidate(
    model,
    external_heat_flux_w_m2: float,
    candidate: ApproximateSleepCandidate,
    consecutive_sleep_ticks: int,
):
    if distributed.can_skip_exact_equilibrium(model, external_heat_flux_w_m2):
        model.elapsed_seconds += scaling.DT_SECONDS
        return None, "exact_sleep", 0
    if _can_sleep_approximately(
        model, external_heat_flux_w_m2, candidate, consecutive_sleep_ticks
    ):
        model.elapsed_seconds += scaling.DT_SECONDS
        return None, "approximate_sleep", consecutive_sleep_ticks + 1
    result = model.step(
        scaling.DT_SECONDS,
        external_heat_flux_w_m2,
        **scaling.STEP_ARGUMENTS,
    )
    return result, "full_step", 0


def _flow_tuple(combustion, model, result, surface_temperature_k: float):
    if result is None:
        return None
    source = combustion.flow_source_from_model(
        model, result, surface_temperature_k=surface_temperature_k
    )
    return (source.fuel, source.temperature, source.smoke)


def _current_mass_kg(metrics: dict) -> float:
    return sum(
        metrics[key]
        for key in (
            "moisture_mass_kg",
            "dry_wood_mass_kg",
            "char_mass_kg",
            "ash_mass_kg",
        )
    )


def _accuracy_trial(combustion, candidate: ApproximateSleepCandidate) -> dict:
    templates = app_contract._templates(combustion)
    maximum_cell_temperature_error_k = 0.0
    maximum_surface_temperature_error_k = 0.0
    maximum_total_mass_error_kg = 0.0
    maximum_flow_component_error = 0.0
    maximum_support_ratio_error = 0.0
    maximum_mass_balance_error_kg = 0.0
    ignition_errors_s = []
    scenario_rows = []

    for scenario, cycles in ACCURACY_SCENARIOS.items():
        reference_models, kinds = app_contract._clone_models(
            combustion, templates
        )
        candidate_models, _ = app_contract._clone_models(combustion, templates)
        reference_models = reference_models[:2]
        candidate_models = candidate_models[:2]
        kinds = kinds[:2]
        reference_topologies = [
            model.capture_runtime_topology() for model in reference_models
        ]
        candidate_topologies = [
            model.capture_runtime_topology() for model in candidate_models
        ]
        sleep_streaks = [0, 0]
        applied_oxygen = [None, None]
        last_candidate_flow = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
        reference_ignition = {kind: None for kind in kinds}
        candidate_ignition = {kind: None for kind in kinds}
        mode_counts = {"exact_sleep": 0, "approximate_sleep": 0, "full_step": 0}
        scenario_temperature_error_k = 0.0
        scenario_surface_error_k = 0.0

        for tick in range(cycles):
            heat_flux = _accuracy_heat_flux(scenario, tick)
            for log_index, kind in enumerate(kinds):
                oxygen = _oxygen_factor(tick, log_index)
                if applied_oxygen[log_index] != oxygen:
                    app_contract._apply_oxygen(reference_models[log_index], oxygen)
                    app_contract._apply_oxygen(candidate_models[log_index], oxygen)
                    applied_oxygen[log_index] = oxygen
                reference_result = reference_models[log_index].step(
                    scaling.DT_SECONDS,
                    heat_flux,
                    **scaling.STEP_ARGUMENTS,
                )
                candidate_result, mode, sleep_streaks[log_index] = (
                    _advance_candidate(
                        candidate_models[log_index],
                        heat_flux,
                        candidate,
                        sleep_streaks[log_index],
                    )
                )
                mode_counts[mode] += 1

                reference_metrics = reference_models[log_index].runtime_metrics(
                    reference_topologies[log_index]
                )
                candidate_metrics = candidate_models[log_index].runtime_metrics(
                    candidate_topologies[log_index]
                )
                reference_flow = _flow_tuple(
                    combustion,
                    reference_models[log_index],
                    reference_result,
                    reference_metrics["surface_mean_temperature_k"],
                )
                candidate_flow = _flow_tuple(
                    combustion,
                    candidate_models[log_index],
                    candidate_result,
                    candidate_metrics["surface_mean_temperature_k"],
                )
                if candidate_flow is None:
                    candidate_flow = last_candidate_flow[log_index]
                else:
                    last_candidate_flow[log_index] = candidate_flow

                cell_error = max(
                    abs(reference_cell.temperature_k - candidate_cell.temperature_k)
                    for reference_cell, candidate_cell in zip(
                        reference_models[log_index].cells,
                        candidate_models[log_index].cells,
                    )
                )
                surface_error = abs(
                    reference_metrics["surface_mean_temperature_k"]
                    - candidate_metrics["surface_mean_temperature_k"]
                )
                mass_error = abs(
                    _current_mass_kg(reference_metrics)
                    - _current_mass_kg(candidate_metrics)
                )
                flow_error = max(
                    abs(reference_value - candidate_value)
                    for reference_value, candidate_value in zip(
                        reference_flow, candidate_flow
                    )
                )
                support_error = abs(
                    app_contract._weakest_support_ratio(reference_models[log_index])
                    - app_contract._weakest_support_ratio(candidate_models[log_index])
                )
                scenario_temperature_error_k = max(
                    scenario_temperature_error_k, cell_error
                )
                scenario_surface_error_k = max(
                    scenario_surface_error_k, surface_error
                )
                maximum_cell_temperature_error_k = max(
                    maximum_cell_temperature_error_k, cell_error
                )
                maximum_surface_temperature_error_k = max(
                    maximum_surface_temperature_error_k, surface_error
                )
                maximum_total_mass_error_kg = max(
                    maximum_total_mass_error_kg, mass_error
                )
                maximum_flow_component_error = max(
                    maximum_flow_component_error, flow_error
                )
                maximum_support_ratio_error = max(
                    maximum_support_ratio_error, support_error
                )
                for model in (
                    reference_models[log_index],
                    candidate_models[log_index],
                ):
                    maximum_mass_balance_error_kg = max(
                        maximum_mass_balance_error_kg,
                        abs(float(model.metrics()["mass_balance_error_kg"])),
                    )

                if (
                    reference_ignition[kind] is None
                    and reference_result.pyrolysis_gas_rate_kg_s
                    > scaling.IGNITION_RATE_KG_S
                ):
                    reference_ignition[kind] = reference_result.elapsed_seconds
                if (
                    candidate_ignition[kind] is None
                    and candidate_result is not None
                    and candidate_result.pyrolysis_gas_rate_kg_s
                    > scaling.IGNITION_RATE_KG_S
                ):
                    candidate_ignition[kind] = candidate_result.elapsed_seconds

        for kind in kinds:
            reference_time = reference_ignition[kind]
            candidate_time = candidate_ignition[kind]
            if reference_time is None and candidate_time is None:
                continue
            if reference_time is None or candidate_time is None:
                ignition_errors_s.append(math.inf)
            else:
                ignition_errors_s.append(abs(reference_time - candidate_time))
        scenario_rows.append(
            {
                "scenario": scenario,
                "cycles": cycles,
                "model_seconds": cycles * scaling.DT_SECONDS,
                "maximum_cell_temperature_error_k": scenario_temperature_error_k,
                "maximum_surface_temperature_error_k": scenario_surface_error_k,
                "mode_counts": mode_counts,
                "reference_ignition_seconds": reference_ignition,
                "candidate_ignition_seconds": candidate_ignition,
            }
        )

    maximum_ignition_time_error_s = max(ignition_errors_s, default=0.0)
    errors = {
        "maximum_cell_temperature_error_k": maximum_cell_temperature_error_k,
        "maximum_surface_temperature_error_k": maximum_surface_temperature_error_k,
        "maximum_total_mass_error_kg": maximum_total_mass_error_kg,
        "maximum_flow_component_error": maximum_flow_component_error,
        "maximum_support_ratio_error": maximum_support_ratio_error,
        "maximum_ignition_time_error_s": maximum_ignition_time_error_s,
        "maximum_mass_balance_error_kg": maximum_mass_balance_error_kg,
    }
    gates = {
        key: errors[key] <= ERROR_BUDGETS[key]
        for key in errors
    }
    return {
        "candidate": candidate.name,
        "candidate_parameters": _candidate_dict(candidate),
        "errors": errors,
        "error_gates": gates,
        "all_accuracy_budgets_passed": all(gates.values()),
        "scenarios": scenario_rows,
    }


def _performance_trial(
    combustion,
    candidate: ApproximateSleepCandidate,
    cycles: int,
    warmup_cycles: int,
) -> dict:
    templates = app_contract._templates(combustion)
    models, _ = app_contract._clone_models(combustion, templates)
    topologies = [model.capture_runtime_topology() for model in models]
    outputs = [
        app_contract._initial_output(model, topology, index)
        for index, (model, topology) in enumerate(zip(models, topologies))
    ]
    slot_members = [
        [index for index in range(app_contract.TOTAL_LOGS) if index % app_contract.FRAME_SLOTS == slot]
        for slot in range(app_contract.FRAME_SLOTS)
    ]
    applied_oxygen = [None] * app_contract.TOTAL_LOGS
    sleep_streaks = [0] * app_contract.TOTAL_LOGS
    frame_times_ms = []
    mode_counts_by_cycle = []
    consumer_checksum = 0.0

    gc.collect()
    for tick in range(cycles):
        first_frame_started = time.perf_counter()
        snapshots = app_contract._snapshot_inputs("rotating5", tick)
        cycle_modes = {"exact_sleep": 0, "approximate_sleep": 0, "full_step": 0}
        for slot, members in enumerate(slot_members):
            frame_started = first_frame_started if slot == 0 else time.perf_counter()
            published_frame = tick * app_contract.FRAME_SLOTS + slot
            for log_index in members:
                snapshot = snapshots[log_index]
                if applied_oxygen[log_index] != snapshot.oxygen_factor:
                    app_contract._apply_oxygen(models[log_index], snapshot.oxygen_factor)
                    applied_oxygen[log_index] = snapshot.oxygen_factor
                result, mode, sleep_streaks[log_index] = _advance_candidate(
                    models[log_index],
                    snapshot.heat_flux_w_m2,
                    candidate,
                    sleep_streaks[log_index],
                )
                cycle_modes[mode] += 1
                outputs[log_index] = app_contract._publish_output(
                    combustion,
                    models[log_index],
                    topologies[log_index],
                    outputs[log_index],
                    snapshot,
                    published_frame,
                    result,
                )
            _, checksum = app_contract._consume_outputs(outputs, tick)
            consumer_checksum += checksum
            frame_times_ms.append((time.perf_counter() - frame_started) * 1000.0)
        mode_counts_by_cycle.append(cycle_modes)

    measured_frames = frame_times_ms[warmup_cycles * app_contract.FRAME_SLOTS :]
    measured_modes = mode_counts_by_cycle[warmup_cycles:]
    aggregate_modes = {
        mode: sum(row[mode] for row in measured_modes)
        for mode in ("exact_sleep", "approximate_sleep", "full_step")
    }
    total_scheduled = sum(aggregate_modes.values())
    maximum_mass_balance_error_kg = 0.0
    for model in models:
        model.refresh_cell_phases()
        maximum_mass_balance_error_kg = max(
            maximum_mass_balance_error_kg,
            abs(float(model.metrics()["mass_balance_error_kg"])),
        )
    return {
        "candidate": candidate.name,
        "sample_count_frames": len(measured_frames),
        "warmup_frames_excluded": warmup_cycles * app_contract.FRAME_SLOTS,
        "frame_mean_ms": statistics.fmean(measured_frames),
        "frame_p95_ms": scaling._percentile_95(measured_frames),
        "frame_max_ms": max(measured_frames),
        "frames_over_4ms_fraction": sum(value > 4.0 for value in measured_frames)
        / len(measured_frames),
        "measured_mode_counts": aggregate_modes,
        "approximate_sleep_fraction": aggregate_modes["approximate_sleep"]
        / total_scheduled,
        "full_step_fraction": aggregate_modes["full_step"] / total_scheduled,
        "median_full_steps_per_tick": statistics.median(
            row["full_step"] for row in measured_modes
        ),
        "final_full_steps_per_tick": measured_modes[-1]["full_step"],
        "maximum_mass_balance_error_kg": maximum_mass_balance_error_kg,
        "consumer_checksum": consumer_checksum,
    }


def run_benchmark(runs: int, cycles: int, warmup_cycles: int) -> dict:
    combustion = scaling._load_combustion_module()
    accuracy = [_accuracy_trial(combustion, candidate) for candidate in CANDIDATES]
    performance = []
    candidates = list(CANDIDATES)
    for run_index in range(runs):
        if run_index % 3 == 0:
            order = candidates
            order_label = "forward"
        elif run_index % 3 == 1:
            order = list(reversed(candidates))
            order_label = "reverse"
        else:
            order = candidates[1:] + candidates[:1]
            order_label = "rotated"
        for candidate in order:
            result = _performance_trial(
                combustion, candidate, cycles, warmup_cycles
            )
            result["run"] = run_index + 1
            result["order"] = order_label
            performance.append(result)
    return {
        "schema_version": 1,
        "benchmark": "approximate_whole_log_sleep",
        "status": "ok",
        "measurement_boundary": {
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in scaling.sys.executable.replace("\\", "/"),
            "isolated_trial_not_production": True,
            "authoritative_reference_uses_every_step": True,
            "whole_log_only": True,
            "cell_sleep_rejected_for_conduction": True,
            "app_contract_output_cost_included": True,
            "usd_flow_render_physx_excluded": True,
        },
        "scenario": {
            "total_logs_performance": app_contract.TOTAL_LOGS,
            "frame_slots": app_contract.FRAME_SLOTS,
            "render_fps_assumption": app_contract.RENDER_FPS,
            "wood_update_hz": 1.0 / scaling.DT_SECONDS,
            "performance_pattern": "rotating5",
            "performance_cycles": cycles,
            "warmup_cycles_excluded": warmup_cycles,
            "accuracy_scenarios": ACCURACY_SCENARIOS,
            "reaction_margin_k": REACTION_MARGIN_K,
        },
        "error_budgets": ERROR_BUDGETS,
        "candidates": [_candidate_dict(candidate) for candidate in CANDIDATES],
        "accuracy": accuracy,
        "performance_runs": performance,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cycles", type=int, default=180)
    parser.add_argument("--warmup-cycles", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.runs < 3:
        parser.error("--runs must be at least 3")
    if not 0 <= arguments.warmup_cycles < arguments.cycles:
        parser.error("--warmup-cycles must be in [0, cycles)")
    report = run_benchmark(
        arguments.runs, arguments.cycles, arguments.warmup_cycles
    )
    destination = arguments.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
