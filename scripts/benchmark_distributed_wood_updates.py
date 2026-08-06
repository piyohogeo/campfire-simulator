"""Measure a deterministic 5 Hz wood scheduler and exact dormant-log gate.

Twenty independent authoritative wood models are assigned to twelve fixed
render-frame slots.  Inputs are snapshotted per logical 0.2 s tick before the
timed frame work.  This is an isolated architecture trial, not an app default.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import statistics
import time
from dataclasses import replace
from pathlib import Path

import benchmark_wood_scaling as scaling


TOTAL_LOGS = 20
FRAME_SLOTS = 12
WOOD_BUDGET_MS = 4.0


def _precondition(combustion, name: str, moisture: float, steps: int, flux: float):
    model = combustion.create_cylindrical_wood_model(
        name,
        radius_m=0.16,
        length_m=1.80,
        moisture_ratio_dry_basis=moisture,
    )
    model.use_slotted_cell_storage()
    for _ in range(steps):
        model.step(scaling.DT_SECONDS, flux, **scaling.STEP_ARGUMENTS)
    model.refresh_cell_phases()
    return model.to_dict()


def can_skip_exact_equilibrium(model, external_heat_flux_w_m2: float) -> bool:
    """Return true only when a deferred-phase step changes elapsed time alone."""

    if external_heat_flux_w_m2 != 0.0:
        return False
    parameters = model.parameters
    ambient = parameters.ambient_temperature_k
    if (
        parameters.pyrolysis_rate_model != "piecewise_linear"
        or not math.isfinite(ambient)
        or ambient <= 0.0
        or ambient >= parameters.evaporation_start_temperature_k
        or ambient >= parameters.pyrolysis_start_temperature_k
        or ambient >= parameters.char_oxidation_start_temperature_k
    ):
        return False
    return all(cell.temperature_k == ambient for cell in model.cells)


def _advance_or_sleep(model, external_heat_flux_w_m2: float) -> bool:
    if can_skip_exact_equilibrium(model, external_heat_flux_w_m2):
        model.elapsed_seconds += scaling.DT_SECONDS
        return True
    model.step(
        scaling.DT_SECONDS,
        external_heat_flux_w_m2,
        **scaling.STEP_ARGUMENTS,
    )
    return False


def _flux_history(cycles: int) -> list[list[float]]:
    return [
        [
            120_000.0 + 7_500.0 * ((cycle_index + log_index) % 5)
            for log_index in range(TOTAL_LOGS)
        ]
        for cycle_index in range(cycles)
    ]


def _clone(combustion, payload: dict):
    model = combustion.WoodThermalModel.from_dict(payload)
    model.use_slotted_cell_storage()
    return model


def _audit_gate(combustion, sleeping_payload: dict, active_payload: dict) -> dict:
    sleeping = _clone(combustion, sleeping_payload)
    active = _clone(combustion, active_payload)
    if not can_skip_exact_equilibrium(sleeping, 0.0):
        raise RuntimeError("Ambient zero-flux model was not recognized as dormant")
    if can_skip_exact_equilibrium(sleeping, 1.0):
        raise RuntimeError("Positive heat flux did not wake a dormant model")
    sleeping.cells[0].temperature_k += 1.0e-9
    if can_skip_exact_equilibrium(sleeping, 0.0):
        raise RuntimeError("A temperature edit did not wake a dormant model")
    sleeping.cells[0].temperature_k -= 1.0e-9
    original_parameters = sleeping.parameters
    sleeping.parameters = replace(
        original_parameters, pyrolysis_rate_model="arrhenius_first_order"
    )
    if can_skip_exact_equilibrium(sleeping, 0.0):
        raise RuntimeError("An Arrhenius model was incorrectly allowed to sleep")
    sleeping.parameters = original_parameters
    if can_skip_exact_equilibrium(active, 0.0):
        raise RuntimeError("A thermally active model was incorrectly allowed to sleep")
    return {
        "zero_flux_ambient_allowed": True,
        "positive_flux_wakes": True,
        "public_temperature_edit_wakes": True,
        "arrhenius_model_wakes": True,
        "nonuniform_active_state_wakes": True,
        "predicate_rescans_public_temperature_each_scheduled_tick": True,
    }


def _build_references(
    combustion,
    active_templates: dict[str, dict],
    sleeping_templates: dict[str, dict],
    histories: list[list[float]],
) -> tuple[list[str], dict[str, str]]:
    active_hashes = []
    for log_index in range(TOTAL_LOGS):
        kind = "dry" if log_index % 2 == 0 else "wet"
        model = _clone(combustion, active_templates[kind])
        for cycle_index in range(len(histories)):
            model.step(
                scaling.DT_SECONDS,
                histories[cycle_index][log_index],
                **scaling.STEP_ARGUMENTS,
            )
        model.refresh_cell_phases()
        active_hashes.append(scaling._state_sha256(model))

    sleeping_hashes = {}
    for kind, payload in sleeping_templates.items():
        model = _clone(combustion, payload)
        for _ in histories:
            model.step(scaling.DT_SECONDS, 0.0, **scaling.STEP_ARGUMENTS)
        model.refresh_cell_phases()
        sleeping_hashes[kind] = scaling._state_sha256(model)
    return active_hashes, sleeping_hashes


def run_benchmark(
    active_counts: list[int],
    runs: int,
    cycles: int,
    warmup_cycles: int,
    precondition_steps: int,
) -> dict:
    combustion = scaling._load_combustion_module()
    active_templates = {
        "dry": _precondition(
            combustion, "distributed_dry", 0.12, precondition_steps, 150_000.0
        ),
        "wet": _precondition(
            combustion, "distributed_wet", 0.60, precondition_steps, 150_000.0
        ),
    }
    sleeping_templates = {
        "dry": _precondition(
            combustion, "distributed_dry", 0.12, precondition_steps, 0.0
        ),
        "wet": _precondition(
            combustion, "distributed_wet", 0.60, precondition_steps, 0.0
        ),
    }
    gate_audit = _audit_gate(
        combustion, sleeping_templates["dry"], active_templates["dry"]
    )
    histories = _flux_history(cycles)
    active_hashes, sleeping_hashes = _build_references(
        combustion, active_templates, sleeping_templates, histories
    )
    slot_members = [
        [index for index in range(TOTAL_LOGS) if index % FRAME_SLOTS == slot]
        for slot in range(FRAME_SLOTS)
    ]
    results = []
    maximum_mass_balance_error_kg = 0.0
    all_states_exact = True

    for run_index in range(runs):
        order = active_counts if run_index % 2 == 0 else list(reversed(active_counts))
        for active_count in order:
            models = []
            kinds = []
            for log_index in range(TOTAL_LOGS):
                kind = "dry" if log_index % 2 == 0 else "wet"
                payload = (
                    active_templates[kind]
                    if log_index < active_count
                    else sleeping_templates[kind]
                )
                models.append(_clone(combustion, payload))
                kinds.append(kind)

            gc.collect()
            frame_times_ms = []
            cycle_times_ms = []
            sleeping_gate_hits = 0
            active_steps = 0
            for cycle_index in range(cycles):
                cycle_total_ms = 0.0
                snapshotted_fluxes = histories[cycle_index]
                for members in slot_members:
                    frame_started = time.perf_counter()
                    for log_index in members:
                        flux = (
                            snapshotted_fluxes[log_index]
                            if log_index < active_count
                            else 0.0
                        )
                        if _advance_or_sleep(models[log_index], flux):
                            sleeping_gate_hits += 1
                        else:
                            active_steps += 1
                    elapsed_ms = (time.perf_counter() - frame_started) * 1000.0
                    frame_times_ms.append(elapsed_ms)
                    cycle_total_ms += elapsed_ms
                cycle_times_ms.append(cycle_total_ms)

            final_hashes = []
            for log_index, (model, kind) in enumerate(zip(models, kinds)):
                model.refresh_cell_phases()
                digest = scaling._state_sha256(model)
                expected = (
                    active_hashes[log_index]
                    if log_index < active_count
                    else sleeping_hashes[kind]
                )
                exact = digest == expected
                all_states_exact = all_states_exact and exact
                if not exact:
                    raise RuntimeError(
                        f"Distributed state diverged for log {log_index} at "
                        f"active_count={active_count}"
                    )
                error = abs(float(model.metrics()["mass_balance_error_kg"]))
                maximum_mass_balance_error_kg = max(
                    maximum_mass_balance_error_kg, error
                )
                if error > 1.0e-9:
                    raise RuntimeError("Distributed model violated mass conservation")
                final_hashes.append(digest)

            warmup_frames = warmup_cycles * FRAME_SLOTS
            measured_frames = frame_times_ms[warmup_frames:]
            measured_cycles = cycle_times_ms[warmup_cycles:]
            results.append(
                {
                    "run": run_index + 1,
                    "order": "ascending" if run_index % 2 == 0 else "descending",
                    "active_log_count": active_count,
                    "sleeping_log_count": TOTAL_LOGS - active_count,
                    "frame_slot_count": FRAME_SLOTS,
                    "slot_sizes": [len(members) for members in slot_members],
                    "sample_count_frames": len(measured_frames),
                    "warmup_frames_excluded": warmup_frames,
                    "frame_mean_ms": statistics.fmean(measured_frames),
                    "frame_p95_ms": scaling._percentile_95(measured_frames),
                    "frame_max_ms": max(measured_frames),
                    "frames_over_4ms_fraction": sum(
                        value > WOOD_BUDGET_MS for value in measured_frames
                    )
                    / len(measured_frames),
                    "cycle_mean_ms": statistics.fmean(measured_cycles),
                    "sleeping_gate_hits": sleeping_gate_hits,
                    "active_model_steps": active_steps,
                    "exact_reference_states": True,
                    "final_state_sha256": final_hashes,
                }
            )

    if not all_states_exact:
        raise RuntimeError("Distributed scheduler violated exact reference states")
    return {
        "schema_version": 1,
        "benchmark": "distributed_5hz_wood_updates",
        "status": "ok",
        "measurement_boundary": {
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in scaling.sys.executable.replace("\\", "/"),
            "authoritative_cpu_wood_step_only": True,
            "flow_usd_render_metrics_excluded": True,
            "input_snapshot_outside_timed_frames": True,
            "fixed_deterministic_slot_assignment": True,
            "trial_not_production_default": True,
        },
        "scenario": {
            "total_logs": TOTAL_LOGS,
            "active_counts": active_counts,
            "frame_slots_per_logical_tick": FRAME_SLOTS,
            "render_fps_assumption": 60,
            "wood_update_hz": 5,
            "cycles_per_run": cycles,
            "warmup_cycles_excluded": warmup_cycles,
            "precondition_model_seconds": precondition_steps * scaling.DT_SECONDS,
            "measured_model_seconds": cycles * scaling.DT_SECONDS,
            "dt_seconds": scaling.DT_SECONDS,
            "cell_count_per_log": len(active_templates["dry"]["cells"]),
            "slot_members": slot_members,
        },
        "gate_contract": gate_audit,
        "equivalence": {
            "exact_reference_states_all_runs": all_states_exact,
            "maximum_mass_balance_error_kg": maximum_mass_balance_error_kg,
            "same_logical_dt_and_step_count": True,
            "snapshotted_inputs_preserve_discrete_solver_order": True,
        },
        "runs": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--active-counts", type=int, nargs="+", default=[2, 5, 10, 12, 20]
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cycles", type=int, default=200)
    parser.add_argument("--warmup-cycles", type=int, default=20)
    parser.add_argument("--precondition-steps", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    active_counts = sorted(set(arguments.active_counts))
    if not active_counts or active_counts[0] < 1 or active_counts[-1] > TOTAL_LOGS:
        parser.error("--active-counts must be within 1..20")
    if arguments.runs < 3:
        parser.error("--runs must be at least 3")
    if not 0 <= arguments.warmup_cycles < arguments.cycles:
        parser.error("--warmup-cycles must be in [0, cycles)")

    report = run_benchmark(
        active_counts,
        arguments.runs,
        arguments.cycles,
        arguments.warmup_cycles,
        arguments.precondition_steps,
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
