"""Measure adopted authoritative wood updates from 2 through 20 logs.

Run with the Kit Python executable.  Flow, USD, rendering, runtime metrics,
and opt-in internal timers are deliberately outside this measurement boundary.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMBUSTION_MODULE = (
    ROOT
    / "source"
    / "extensions"
    / "campfire.app"
    / "campfire"
    / "app"
    / "combustion.py"
)
DT_SECONDS = 0.2
HEAT_FLUX_W_M2 = 150_000.0
IGNITION_RATE_KG_S = 1.0e-6
STEP_ARGUMENTS = {
    "python_surface_boundary_fast_path": True,
    "python_state_clamp_fast_path": True,
    "update_cell_phases": False,
    "python_constant_heat_capacity_fast_path": True,
    "python_homogeneous_heat_capacity_fast_path": True,
    "python_inline_homogeneous_sensible_heat_capacity_fast_path": True,
}


def _load_combustion_module():
    specification = importlib.util.spec_from_file_location(
        "campfire_combustion_scaling_benchmark", COMBUSTION_MODULE
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load wood model: {COMBUSTION_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _state_sha256(model) -> str:
    encoded = json.dumps(
        model.to_dict(), allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def _precondition_template(combustion, name: str, moisture: float, steps: int):
    model = combustion.create_cylindrical_wood_model(
        name,
        radius_m=0.16,
        length_m=1.80,
        moisture_ratio_dry_basis=moisture,
    )
    model.use_slotted_cell_storage()
    ignition_seconds = None
    for _ in range(steps):
        result = model.step(DT_SECONDS, HEAT_FLUX_W_M2, **STEP_ARGUMENTS)
        if (
            ignition_seconds is None
            and result.pyrolysis_gas_rate_kg_s > IGNITION_RATE_KG_S
        ):
            ignition_seconds = result.elapsed_seconds
    model.refresh_cell_phases()
    if ignition_seconds is None:
        raise RuntimeError(f"{name} did not ignite during preconditioning")
    return model.to_dict(), ignition_seconds


def _clone_models(combustion, templates: dict[str, dict], log_count: int):
    models = []
    kinds = []
    for index in range(log_count):
        kind = "dry" if index % 2 == 0 else "wet"
        model = combustion.WoodThermalModel.from_dict(templates[kind])
        model.use_slotted_cell_storage()
        models.append(model)
        kinds.append(kind)
    return models, kinds


def run_benchmark(
    counts: list[int],
    runs: int,
    steps: int,
    warmup_steps: int,
    precondition_steps: int,
) -> dict:
    combustion = _load_combustion_module()
    dry_template, dry_ignition = _precondition_template(
        combustion, "scaling_dry", 0.12, precondition_steps
    )
    wet_template, wet_ignition = _precondition_template(
        combustion, "scaling_wet", 0.60, precondition_steps
    )
    templates = {"dry": dry_template, "wet": wet_template}
    cell_count_per_log = len(dry_template["cells"])
    if len(wet_template["cells"]) != cell_count_per_log:
        raise RuntimeError("Dry and wet templates use different cell counts")

    results = []
    observed_hashes = {"dry": set(), "wet": set()}
    maximum_mass_balance_error_kg = 0.0
    all_cells_slotted = True
    for run_index in range(runs):
        order = counts if run_index % 2 == 0 else list(reversed(counts))
        for log_count in order:
            models, kinds = _clone_models(combustion, templates, log_count)
            all_cells_slotted = all_cells_slotted and all(
                not hasattr(cell, "__dict__")
                for model in models
                for cell in model.cells
            )
            gc.collect()
            step_times_ms = []
            started = time.perf_counter()
            for _ in range(steps):
                step_started = time.perf_counter()
                for model in models:
                    model.step(DT_SECONDS, HEAT_FLUX_W_M2, **STEP_ARGUMENTS)
                step_times_ms.append((time.perf_counter() - step_started) * 1000.0)
            wall_seconds = time.perf_counter() - started
            for model in models:
                model.refresh_cell_phases()

            hashes_by_kind = {"dry": set(), "wet": set()}
            for model, kind in zip(models, kinds):
                metrics = model.metrics()
                for cell in model.cells:
                    state_values = (
                        cell.temperature_k,
                        cell.moisture_mass_kg,
                        cell.dry_wood_mass_kg,
                        cell.volatile_potential_kg,
                        cell.char_mass_kg,
                        cell.ash_mass_kg,
                    )
                    if not all(math.isfinite(value) for value in state_values):
                        raise RuntimeError(f"{kind} model produced non-finite values")
                    if any(value < 0.0 for value in state_values[1:]):
                        raise RuntimeError(f"{kind} model produced negative mass")
                error = abs(float(metrics["mass_balance_error_kg"]))
                maximum_mass_balance_error_kg = max(
                    maximum_mass_balance_error_kg, error
                )
                if error > 1.0e-9:
                    raise RuntimeError(f"{kind} model violated mass conservation")
                digest = _state_sha256(model)
                hashes_by_kind[kind].add(digest)
                observed_hashes[kind].add(digest)
            for kind, hashes in hashes_by_kind.items():
                if hashes and len(hashes) != 1:
                    raise RuntimeError(f"Replicated {kind} logs diverged")

            measured = step_times_ms[warmup_steps:]
            mean_ms = statistics.fmean(measured)
            results.append(
                {
                    "run": run_index + 1,
                    "order": "ascending" if run_index % 2 == 0 else "descending",
                    "log_count": log_count,
                    "dry_log_count": kinds.count("dry"),
                    "wet_log_count": kinds.count("wet"),
                    "combined_cell_count": log_count * cell_count_per_log,
                    "sample_count": len(measured),
                    "warmup_samples_excluded": warmup_steps,
                    "aggregate_step_mean_ms": mean_ms,
                    "aggregate_step_p95_ms": _percentile_95(measured),
                    "aggregate_step_max_ms": max(measured),
                    "mean_ms_per_log": mean_ms / log_count,
                    "mean_ms_per_1000_cells": mean_ms
                    / (log_count * cell_count_per_log)
                    * 1000.0,
                    "wall_seconds": wall_seconds,
                    "final_state_sha256": {
                        kind: next(iter(hashes)) if hashes else None
                        for kind, hashes in hashes_by_kind.items()
                    },
                }
            )

    if not all_cells_slotted:
        raise RuntimeError("Benchmark did not retain slotted cell storage")
    if any(len(hashes) != 1 for hashes in observed_hashes.values()):
        raise RuntimeError("Final per-log state changed with scale or run order")
    return {
        "schema_version": 1,
        "benchmark": "adopted_python_wood_scaling",
        "status": "ok",
        "runtime": {
            "python": platform.python_version(),
            "executable": sys.executable,
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in sys.executable.replace("\\", "/"),
            "garbage_collection_enabled": gc.isenabled(),
        },
        "measurement_boundary": {
            "authoritative_cpu_wood_step_only": True,
            "flow_excluded": True,
            "usd_excluded": True,
            "rendering_excluded": True,
            "runtime_metrics_excluded": True,
            "internal_timing_disabled": True,
            "models_updated_sequentially": True,
        },
        "adopted_settings": {
            "backend": "python",
            "slotted_cell_storage": True,
            "surface_boundary_fast_path": True,
            "conditional_state_clamp": True,
            "deferred_phase_updates": True,
            "constant_heat_capacity_fast_path": True,
            "homogeneous_heat_capacity_fast_path": True,
            "inline_homogeneous_sensible_heat_capacity_fast_path": True,
        },
        "scenario": {
            "counts": counts,
            "runs_per_count": runs,
            "steps_per_run": steps,
            "warmup_steps_excluded": warmup_steps,
            "measured_model_seconds": steps * DT_SECONDS,
            "precondition_steps": precondition_steps,
            "precondition_model_seconds": precondition_steps * DT_SECONDS,
            "dt_seconds": DT_SECONDS,
            "external_heat_flux_w_m2": HEAT_FLUX_W_M2,
            "cell_count_per_log": cell_count_per_log,
            "moisture_pattern": "alternating dry 0.12 / wet 0.60 dry-basis",
            "precondition_ignition_seconds": {
                "dry": dry_ignition,
                "wet": wet_ignition,
            },
        },
        "equivalence": {
            "exact_per_log_state_across_scales_and_runs": True,
            "all_cells_slotted": all_cells_slotted,
            "maximum_mass_balance_error_kg": maximum_mass_balance_error_kg,
            "final_state_sha256": {
                kind: next(iter(hashes)) for kind, hashes in observed_hashes.items()
            },
        },
        "runs": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--counts", type=int, nargs="+", default=[2, 5, 10, 20])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--warmup-steps", type=int, default=20)
    parser.add_argument("--precondition-steps", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    counts = sorted(set(arguments.counts))
    if not counts or counts[0] < 2:
        parser.error("--counts must contain values of at least 2")
    if arguments.runs < 3:
        parser.error("--runs must be at least 3")
    if not 0 <= arguments.warmup_steps < arguments.steps:
        parser.error("--warmup-steps must be in [0, steps)")
    if arguments.precondition_steps <= 0:
        parser.error("--precondition-steps must be positive")

    report = run_benchmark(
        counts,
        arguments.runs,
        arguments.steps,
        arguments.warmup_steps,
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
