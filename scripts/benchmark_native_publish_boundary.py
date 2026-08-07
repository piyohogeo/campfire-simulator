"""Measure the Phase 6AY resident native app-output publication boundary."""

from __future__ import annotations

import argparse
import ctypes
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
ARRHENIUS_BENCHMARK = ROOT / "scripts" / "benchmark_native_arrhenius_complete_step.py"
OUTPUT_FIELDS = (
    "surface_mean_temperature_k",
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "char_mass_kg",
    "ash_mass_kg",
    "remaining_mass_ratio",
    "weakest_support_ratio",
    "flow_fuel",
    "flow_temperature",
    "flow_smoke",
    "pyrolysis_gas_rate_kg_s",
)
GUARD_FIELDS = (
    "temperature_k",
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "volatile_potential_kg",
    "char_mass_kg",
    "ash_mass_kg",
    "oxygen_factor",
    "surface_exposure",
    "phase",
    "volume_m3",
    "external_area_m2",
    "dry_wood_specific_heat_j_kg_k",
    "dry_wood_specific_heat_model",
)
REFERENCE_FUEL_RATE_KG_S = 0.02
CHAR_STRENGTH_FACTOR = 0.12
WOOD_BUDGET_MS = 4.0
EQUIVALENCE_TOLERANCE = 1.0e-12


def _load_arrhenius_benchmark():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6ax_publish_base", ARRHENIUS_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AX benchmark: {ARRHENIUS_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


arrhenius = _load_arrhenius_benchmark()
piecewise = arrhenius.piecewise
base = arrhenius.base
np = arrhenius.np


def _configure_publish_kernel(library) -> None:
    double_pointer = ctypes.POINTER(ctypes.c_double)
    library.campfire_native_publish_outputs.argtypes = (
        [ctypes.c_size_t]
        + [double_pointer] * 6
        + [ctypes.c_size_t] * 3
        + [double_pointer] * 4
        + [ctypes.c_double] * 4
    )
    library.campfire_native_publish_outputs.restype = ctypes.c_int32


def _call_native(
    library,
    arrays,
    log_count: int,
    cells_per_log: int,
    cells_per_section: int,
    initial_mass,
    initial_section_mass,
    step_output,
    published_output,
    ambient_temperature_k: float,
) -> None:
    pointer = ctypes.POINTER(ctypes.c_double)
    result = library.campfire_native_publish_outputs(
        arrays["temperature_k"].size,
        arrays["temperature_k"].ctypes.data_as(pointer),
        arrays["moisture_mass_kg"].ctypes.data_as(pointer),
        arrays["dry_wood_mass_kg"].ctypes.data_as(pointer),
        arrays["char_mass_kg"].ctypes.data_as(pointer),
        arrays["ash_mass_kg"].ctypes.data_as(pointer),
        arrays["surface_exposure"].ctypes.data_as(pointer),
        log_count,
        cells_per_log,
        cells_per_section,
        initial_mass.ctypes.data_as(pointer),
        initial_section_mass.ctypes.data_as(pointer),
        step_output.ctypes.data_as(pointer),
        published_output.ctypes.data_as(pointer),
        base.DT_SECONDS,
        ambient_temperature_k,
        REFERENCE_FUEL_RATE_KG_S,
        CHAR_STRENGTH_FACTOR,
    )
    if result != 0:
        raise RuntimeError(f"Native publish kernel failed with code {result}")


def _weakest_support_ratio(model) -> float:
    spec = model.spec
    cells_per_section = spec.circumferential_cells * spec.radial_cells
    initial_section_mass = (
        math.pi
        * spec.radius_m**2
        * (spec.length_m / spec.axial_cells)
        * model.parameters.dry_wood_density_kg_m3
    )
    ratios = []
    for axial_index in range(spec.axial_cells):
        start = axial_index * cells_per_section
        section = model.cells[start : start + cells_per_section]
        dry_mass = sum(cell.dry_wood_mass_kg for cell in section)
        char_mass = sum(cell.char_mass_kg for cell in section)
        ratios.append(
            min(
                1.0,
                max(
                    0.0,
                    (dry_mass + CHAR_STRENGTH_FACTOR * char_mass)
                    / max(initial_section_mass, 1.0e-12),
                ),
            )
        )
    interior = ratios[1:-1] if len(ratios) > 2 else ratios
    return min(interior)


def _python_publish(combustion, models, topologies, step_results):
    rows = []
    for model, topology, result in zip(models, topologies, step_results):
        metrics = model.runtime_metrics(topology)
        remaining_mass = sum(
            metrics[field]
            for field in (
                "moisture_mass_kg",
                "dry_wood_mass_kg",
                "char_mass_kg",
                "ash_mass_kg",
            )
        )
        flow = combustion.flow_source_from_model(
            model,
            result,
            reference_fuel_rate_kg_s=REFERENCE_FUEL_RATE_KG_S,
            surface_temperature_k=metrics["surface_mean_temperature_k"],
        )
        rows.append(
            [
                metrics["surface_mean_temperature_k"],
                metrics["moisture_mass_kg"],
                metrics["dry_wood_mass_kg"],
                metrics["char_mass_kg"],
                metrics["ash_mass_kg"],
                remaining_mass / model.initial_mass_kg,
                _weakest_support_ratio(model),
                flow.fuel,
                flow.temperature,
                flow.smoke,
                flow.pyrolysis_gas_rate_kg_s,
            ]
        )
    return rows


def _guard_shadow(cells):
    return tuple(tuple(getattr(cell, field) for field in GUARD_FIELDS) for cell in cells)


def _scan_public_mutation(cells, shadow):
    for cell_index, (cell, expected) in enumerate(zip(cells, shadow)):
        for field_index, field in enumerate(GUARD_FIELDS):
            actual = getattr(cell, field)
            if actual != expected[field_index]:
                return {
                    "cell_index": cell_index,
                    "field": field,
                    "expected": expected[field_index],
                    "actual": actual,
                }
    return None


def _timing_summary(samples):
    ordered = sorted(samples)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "sample_count": len(samples),
        "mean_ms": statistics.fmean(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[p95_index],
        "maximum_ms": ordered[-1],
    }


def _measure(operation, iterations: int):
    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000.0)
    return _timing_summary(samples)


def _step_output_array(results):
    return np.asarray(
        [
            [
                result.evaporated_water_kg,
                result.pyrolysis_gas_kg,
                result.char_oxidation_gas_kg,
                result.external_heat_j,
                result.primary_gas_kg,
                result.primary_tar_kg,
                result.primary_char_kg,
                result.secondary_tar_cracked_kg,
                result.uncracked_tar_kg,
            ]
            for result in results
        ],
        dtype=np.float64,
    ).reshape(-1)


def run_benchmark(dll_path: Path, log_count: int, iterations: int, runs: int):
    combustion = base._load_combustion_module()
    templates = {
        "dry": arrhenius._precondition_template(combustion, "publish_dry", 0.12, 300),
        "wet": arrhenius._precondition_template(combustion, "publish_wet", 0.60, 800),
    }
    models = piecewise._clone_models(combustion, templates, log_count)
    step_results = [
        model.step(base.DT_SECONDS, base.HEAT_FLUX_W_M2, **piecewise.STEP_ARGUMENTS)
        for model in models
    ]
    topologies = [model.capture_runtime_topology() for model in models]
    cells = piecewise._combined_cells(models)
    arrays = piecewise._extract_complete_arrays(
        cells, models[0].parameters.wood_specific_heat_j_kg_k
    )
    cells_per_log = len(models[0].cells)
    cells_per_section = (
        models[0].spec.circumferential_cells * models[0].spec.radial_cells
    )
    initial_mass = np.asarray([model.initial_mass_kg for model in models], dtype=np.float64)
    initial_section_mass = np.asarray(
        [
            math.pi
            * model.spec.radius_m**2
            * (model.spec.length_m / model.spec.axial_cells)
            * model.parameters.dry_wood_density_kg_m3
            for model in models
        ],
        dtype=np.float64,
    )
    step_output = _step_output_array(step_results)
    published_output = np.zeros(log_count * len(OUTPUT_FIELDS), dtype=np.float64)
    library = base._load_native_kernel(dll_path)
    _configure_publish_kernel(library)
    native_operation = lambda: _call_native(
        library,
        arrays,
        log_count,
        cells_per_log,
        cells_per_section,
        initial_mass,
        initial_section_mass,
        step_output,
        published_output,
        models[0].parameters.ambient_temperature_k,
    )
    python_operation = lambda: _python_publish(
        combustion, models, topologies, step_results
    )
    native_operation()
    python_rows = python_operation()
    native_rows = published_output.reshape((log_count, len(OUTPUT_FIELDS))).tolist()
    maximum_error = max(
        abs(reference - candidate)
        for reference_row, candidate_row in zip(python_rows, native_rows)
        for reference, candidate in zip(reference_row, candidate_row)
    )
    field_errors = {
        field: max(
            abs(python_rows[row][column] - native_rows[row][column])
            for row in range(log_count)
        )
        for column, field in enumerate(OUTPUT_FIELDS)
    }
    if maximum_error > EQUIVALENCE_TOLERANCE:
        raise RuntimeError(f"Native publication exceeded tolerance: {field_errors}")

    shadow = _guard_shadow(cells)
    if _scan_public_mutation(cells, shadow) is not None:
        raise RuntimeError("Fresh public-state shadow unexpectedly differs")
    cells[0].temperature_k += 1.0
    mutation = _scan_public_mutation(cells, shadow)
    cells[0].temperature_k -= 1.0
    if mutation is None or mutation["field"] != "temperature_k":
        raise RuntimeError("Public mutation probe was not detected")

    methods = {
        "python_object_publish": python_operation,
        "native_resident_publish": native_operation,
        "public_mutable_guard_scan": lambda: _scan_public_mutation(cells, shadow),
    }
    orders = [
        list(methods),
        ["native_resident_publish", "public_mutable_guard_scan", "python_object_publish"],
        ["public_mutable_guard_scan", "python_object_publish", "native_resident_publish"],
    ]
    raw_runs = []
    for run_index in range(runs):
        gc.collect()
        timings = {}
        order = orders[run_index % len(orders)]
        for name in order:
            timings[name] = _measure(methods[name], iterations)
        raw_runs.append({"run": run_index + 1, "order": order, "methods": timings})

    digest = hashlib.sha256()
    for source in (
        ROOT / "native" / "phase6au" / "wood_cell_kernel.cpp",
        ROOT / "native" / "phase6au" / "native_publish_outputs.inl",
    ):
        digest.update(source.name.encode("utf-8"))
        digest.update(source.read_bytes())
    return {
        "schema_version": 1,
        "phase": "phase6ay",
        "status": "ok",
        "runtime": {
            "python": platform.python_version(),
            "executable": sys.executable,
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in sys.executable.replace("\\", "/"),
            "numpy": np.__version__,
        },
        "native_toolchain": {
            "abi_version": library.campfire_native_abi_version(),
            "msvc_version": library.campfire_native_msvc_version(),
            "msvc_full_version": library.campfire_native_msvc_full_version(),
            "floating_point": "/fp:strict",
            "dll_sha256": hashlib.sha256(dll_path.read_bytes()).hexdigest(),
            "source_sha256": digest.hexdigest(),
        },
        "measurement": {
            "log_count": log_count,
            "cell_count_per_log": cells_per_log,
            "combined_cell_count": len(cells),
            "iterations_per_method": iterations,
            "runs": runs,
            "balanced_method_order": True,
            "dt_seconds": base.DT_SECONDS,
            "heat_flux_w_m2": base.HEAT_FLUX_W_M2,
            "output_field_count_per_log": len(OUTPUT_FIELDS),
        },
        "contract": {
            "output_fields": list(OUTPUT_FIELDS),
            "guard_fields": list(GUARD_FIELDS),
            "reference_fuel_rate_kg_s": REFERENCE_FUEL_RATE_KG_S,
            "char_strength_factor": CHAR_STRENGTH_FACTOR,
            "immutable_copy_required_before_app_consumption": True,
        },
        "equivalence": {
            "tolerance": EQUIVALENCE_TOLERANCE,
            "maximum_absolute_error": maximum_error,
            "field_maximum_absolute_errors": field_errors,
            "passed": maximum_error <= EQUIVALENCE_TOLERANCE,
        },
        "mutation_probe": {
            "injected_delta_k": 1.0,
            "detected": mutation is not None,
            "detection": mutation,
            "restored_after_probe": True,
        },
        "boundary": {
            "included": [
                "runtime_metrics",
                "remaining_mass_ratio",
                "weakest_support_ratio",
                "flow_source_mapping",
                "pyrolysis_gas_rate",
                "public_mutable_state_guard_cost",
            ],
            "excluded": [
                "automatic_guard_fallback",
                "revision_or_dirty_api",
                "5_hz_scheduler_integration",
                "Flow/USD/rendering/PhysX",
            ],
            "production_model_changed": False,
            "python_json_schema_changed": False,
        },
        "budget_ms": WOOD_BUDGET_MS,
        "runs": raw_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--logs", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if not arguments.dll.is_file():
        parser.error(f"Native DLL does not exist: {arguments.dll}")
    if arguments.logs <= 0 or arguments.iterations < 40 or arguments.runs < 3:
        parser.error("Require positive logs, at least 40 iterations, and three runs")
    report = run_benchmark(
        arguments.dll, arguments.logs, arguments.iterations, arguments.runs
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
