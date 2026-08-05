"""Run the wood model without Kit, Flow, USD, or rendering.

This benchmark isolates the authoritative CPU thermal/reaction step from the
much larger end-to-end Phase 3 capture cost. It intentionally loads the pure
model module by file path so importing the Omniverse extension package is not
required.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import statistics
import sys
import time
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMBUSTION_MODULE = (
    REPOSITORY_ROOT
    / "source"
    / "extensions"
    / "campfire.app"
    / "campfire"
    / "app"
    / "combustion.py"
)


def _load_combustion_module():
    specification = importlib.util.spec_from_file_location(
        "campfire_combustion_benchmark", COMBUSTION_MODULE
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load wood model: {COMBUSTION_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def run_benchmark(steps: int, warmup_steps: int) -> dict:
    combustion = _load_combustion_module()
    dry = combustion.create_cylindrical_wood_model(
        "benchmark_dry",
        radius_m=0.16,
        length_m=1.80,
        moisture_ratio_dry_basis=0.12,
    )
    wet = combustion.create_cylindrical_wood_model(
        "benchmark_wet",
        radius_m=0.16,
        length_m=1.80,
        moisture_ratio_dry_basis=0.60,
    )
    dt_seconds = 0.2
    heat_flux_w_m2 = 150_000.0
    ignition_rate_kg_s = 1.0e-6
    ignition_seconds = {"dry": None, "wet": None}
    step_times_ms = []
    metrics_times_ms = []

    started = time.perf_counter()
    for step_index in range(steps):
        step_started = time.perf_counter()
        dry_result = dry.step(dt_seconds, heat_flux_w_m2)
        wet_result = wet.step(dt_seconds, heat_flux_w_m2)
        step_times_ms.append((time.perf_counter() - step_started) * 1000.0)

        metrics_started = time.perf_counter()
        dry_metrics = dry.metrics()
        wet_metrics = wet.metrics()
        metrics_times_ms.append((time.perf_counter() - metrics_started) * 1000.0)
        for name, result in (("dry", dry_result), ("wet", wet_result)):
            if (
                ignition_seconds[name] is None
                and result.pyrolysis_gas_rate_kg_s > ignition_rate_kg_s
            ):
                ignition_seconds[name] = result.elapsed_seconds
    wall_seconds = time.perf_counter() - started

    measured_steps = step_times_ms[warmup_steps:]
    measured_metrics = metrics_times_ms[warmup_steps:]
    return {
        "schema_version": 1,
        "benchmark": "two_log_cpu_wood_model",
        "python": platform.python_version(),
        "steps": steps,
        "warmup_steps_excluded": warmup_steps,
        "model_duration_seconds": steps * dt_seconds,
        "cell_count_per_log": len(dry.cells),
        "combined_cell_count": len(dry.cells) + len(wet.cells),
        "dt_seconds": dt_seconds,
        "external_heat_flux_w_m2": heat_flux_w_m2,
        "two_log_step_mean_ms": statistics.fmean(measured_steps),
        "two_log_step_p95_ms": _percentile_95(measured_steps),
        "two_log_metrics_mean_ms": statistics.fmean(measured_metrics),
        "two_log_metrics_p95_ms": _percentile_95(measured_metrics),
        "wall_seconds": wall_seconds,
        "ignition_seconds": ignition_seconds,
        "dry_mass_balance_error_kg": dry_metrics["mass_balance_error_kg"],
        "wet_mass_balance_error_kg": wet_metrics["mass_balance_error_kg"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--warmup-steps", type=int, default=20)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.steps <= 0:
        parser.error("--steps must be positive")
    if not 0 <= arguments.warmup_steps < arguments.steps:
        parser.error("--warmup-steps must be in [0, steps)")

    result = run_benchmark(arguments.steps, arguments.warmup_steps)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output:
        destination = arguments.output.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
