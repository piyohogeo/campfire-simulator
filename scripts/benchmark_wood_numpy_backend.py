"""Benchmark the complete production wood step with Python and NumPy segments."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
import time
from dataclasses import asdict
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
PIP_ROOT = (
    REPOSITORY_ROOT
    / "_build"
    / "windows-x86_64"
    / "release"
    / "extscache"
    / "omni.kit.pip_archive-0.0.0+698af100.wx64.cp312"
    / "pip_prebundle"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "performance"
    / "wood_numpy_backend_benchmark.json"
)


def _load_combustion_module():
    sys.path.insert(0, str(PIP_ROOT))
    specification = importlib.util.spec_from_file_location(
        "campfire_combustion_numpy_benchmark", COMBUSTION_MODULE
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load wood model: {COMBUSTION_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _base_model_payloads(combustion) -> list[dict]:
    return [
        combustion.create_cylindrical_wood_model(
            "benchmark_dry",
            radius_m=0.16,
            length_m=1.80,
            moisture_ratio_dry_basis=0.12,
        ).to_dict(),
        combustion.create_cylindrical_wood_model(
            "benchmark_wet",
            radius_m=0.16,
            length_m=1.80,
            moisture_ratio_dry_basis=0.60,
        ).to_dict(),
    ]


def _run_backend(combustion, payloads: list[dict], backend: str, steps: int) -> dict:
    models = [combustion.WoodThermalModel.from_dict(payload) for payload in payloads]
    history_hash = hashlib.sha256()
    started = time.perf_counter()
    for _ in range(steps):
        for model in models:
            result = model.step(0.2, 150_000.0, array_backend=backend)
            history_hash.update(
                json.dumps(
                    asdict(result),
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    state_payload = [model.to_dict() for model in models]
    state_json = json.dumps(
        state_payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "elapsed_ms": elapsed_ms,
        "per_pair_step_ms": elapsed_ms / steps,
        "per_model_step_ms": elapsed_ms / (steps * len(models)),
        "history_sha256": history_hash.hexdigest(),
        "state_sha256": hashlib.sha256(state_json).hexdigest(),
        "state": state_payload,
        "metrics": [model.metrics() for model in models],
    }


def _summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "minimum_ms": ordered[0],
        "maximum_ms": ordered[-1],
    }


def run_benchmark(steps: int, runs: int, warmup_steps: int) -> dict:
    if steps <= 0 or runs <= 0 or warmup_steps < 0:
        raise ValueError("steps and runs must be positive; warmup must be non-negative")
    combustion = _load_combustion_module()
    payloads = _base_model_payloads(combustion)

    for backend in (
        combustion.PYTHON_ARRAY_BACKEND,
        combustion.NUMPY_ARRAY_BACKEND,
    ):
        _run_backend(combustion, payloads, backend, warmup_steps)

    samples = {
        combustion.PYTHON_ARRAY_BACKEND: [],
        combustion.NUMPY_ARRAY_BACKEND: [],
    }
    reference = None
    candidate = None
    orders = [
        (combustion.PYTHON_ARRAY_BACKEND, combustion.NUMPY_ARRAY_BACKEND),
        (combustion.NUMPY_ARRAY_BACKEND, combustion.PYTHON_ARRAY_BACKEND),
    ]
    for run_index in range(runs):
        for backend in orders[run_index % len(orders)]:
            result = _run_backend(combustion, payloads, backend, steps)
            samples[backend].append(result["per_model_step_ms"])
            if backend == combustion.PYTHON_ARRAY_BACKEND:
                reference = result
            else:
                candidate = result

    if reference is None or candidate is None:
        raise RuntimeError("Both benchmark backends must run")
    exact_state_match = reference["state_sha256"] == candidate["state_sha256"]
    exact_history_match = (
        reference["history_sha256"] == candidate["history_sha256"]
    )
    exact_metrics_match = reference["metrics"] == candidate["metrics"]
    python_summary = _summarize(samples[combustion.PYTHON_ARRAY_BACKEND])
    numpy_summary = _summarize(samples[combustion.NUMPY_ARRAY_BACKEND])
    improvement_fraction = (
        python_summary["median_ms"] - numpy_summary["median_ms"]
    ) / python_summary["median_ms"]
    eligible = (
        exact_state_match
        and exact_history_match
        and exact_metrics_match
        and improvement_fraction > 0.0
    )
    import numpy

    return {
        "benchmark": "complete_wood_step_numpy_boundary",
        "steps": steps,
        "runs": runs,
        "warmup_steps": warmup_steps,
        "model_count": len(payloads),
        "cells_per_model": len(reference["state"][0]["cells"]),
        "total_cells": sum(len(model["cells"]) for model in reference["state"]),
        "dt_seconds": 0.2,
        "heat_flux_w_m2": 150_000.0,
        "measurements": {
            combustion.PYTHON_ARRAY_BACKEND: python_summary,
            combustion.NUMPY_ARRAY_BACKEND: numpy_summary,
        },
        "equivalence": {
            "exact_state_sha256_match": exact_state_match,
            "exact_step_history_sha256_match": exact_history_match,
            "exact_metrics_match": exact_metrics_match,
            "python_state_sha256": reference["state_sha256"],
            "numpy_state_sha256": candidate["state_sha256"],
            "python_history_sha256": reference["history_sha256"],
            "numpy_history_sha256": candidate["history_sha256"],
        },
        "decision": {
            "numpy_improvement_fraction": improvement_fraction,
            "eligible_for_phase3_trial": eligible,
            "default_backend": combustion.PYTHON_ARRAY_BACKEND,
            "scope": ["sensible_heat", "state_finalize"],
        },
        "numpy_version": numpy.__version__,
        "python_version": sys.version,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup-steps", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    report = run_benchmark(arguments.steps, arguments.runs, arguments.warmup_steps)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
