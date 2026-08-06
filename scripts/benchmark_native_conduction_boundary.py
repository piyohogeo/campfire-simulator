"""Measure the Phase 6AV resident native conduction-topology boundary."""

from __future__ import annotations

import argparse
import copy
import ctypes
import gc
import hashlib
import importlib.util
import json
import platform
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_BENCHMARK = ROOT / "scripts" / "benchmark_native_wood_boundary.py"


def _load_base():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6au_benchmark_base", BASE_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AU benchmark: {BASE_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


base = _load_base()
np = base.np


def _configure_conduction_kernel(library):
    double_pointer = ctypes.POINTER(ctypes.c_double)
    uint_pointer = ctypes.POINTER(ctypes.c_uint32)
    int_pointer = ctypes.POINTER(ctypes.c_int32)
    library.campfire_native_conduction_step.argtypes = (
        [ctypes.c_size_t]
        + [double_pointer] * 8
        + [int_pointer, ctypes.c_size_t]
        + [uint_pointer] * 2
        + [double_pointer] * 2
        + [ctypes.c_double] * 13
    )
    library.campfire_native_conduction_step.restype = ctypes.c_int32


def _topology_arrays(local_pairs, log_count: int, cells_per_log: int):
    combined = []
    for log_index in range(log_count):
        offset = log_index * cells_per_log
        combined.extend(
            (first + offset, second + offset, conductance)
            for first, second, conductance in local_pairs
        )
    return {
        "first_cell": np.fromiter(
            (pair[0] for pair in combined), dtype=np.uint32, count=len(combined)
        ),
        "second_cell": np.fromiter(
            (pair[1] for pair in combined), dtype=np.uint32, count=len(combined)
        ),
        "conductance_w_k": np.fromiter(
            (pair[2] for pair in combined), dtype=np.float64, count=len(combined)
        ),
        "python_pairs": combined,
    }


def _python_step(cells, pairs, p, mass_epsilon_kg: float):
    temperatures = [cell.temperature_k for cell in cells]
    conduction_energy = [0.0] * len(cells)
    for first, second, conductance_w_k in pairs:
        energy_j = (
            conductance_w_k
            * (temperatures[second] - temperatures[first])
            * base.DT_SECONDS
        )
        conduction_energy[first] += energy_j
        conduction_energy[second] -= energy_j

    ambient_squared = p.ambient_temperature_k * p.ambient_temperature_k
    ambient_fourth = ambient_squared * ambient_squared
    for index, cell in enumerate(cells):
        moisture = max(0.0, cell.moisture_mass_kg)
        dry_wood = max(0.0, cell.dry_wood_mass_kg)
        char = max(0.0, cell.char_mass_kg)
        ash = max(0.0, cell.ash_mass_kg)
        dry_specific_heat = (
            cell.dry_wood_specific_heat_j_kg_k
            if cell.dry_wood_specific_heat_j_kg_k is not None
            else p.wood_specific_heat_j_kg_k
        )
        heat_capacity = max(
            dry_wood * dry_specific_heat
            + moisture * p.water_specific_heat_j_kg_k
            + char * p.char_specific_heat_j_kg_k
            + ash * p.ash_specific_heat_j_kg_k,
            1.0e-9,
        )
        area = cell.external_area_m2 * cell.surface_exposure
        temperature_squared = cell.temperature_k * cell.temperature_k
        external_heat_w = base.HEAT_FLUX_W_M2 * p.radiant_absorptivity * area
        convective_loss_w = p.convection_w_m2_k * area * (
            cell.temperature_k - p.ambient_temperature_k
        )
        radiation_loss_w = p.emissivity * base.SIGMA_W_M2_K4 * area * (
            temperature_squared * temperature_squared - ambient_fourth
        )
        net_energy_j = conduction_energy[index] + (
            external_heat_w - convective_loss_w - radiation_loss_w
        ) * base.DT_SECONDS
        cell.temperature_k += net_energy_j / heat_capacity
        cell.temperature_k = min(
            p.max_temperature_k, max(p.ambient_temperature_k, cell.temperature_k)
        )
        cell.moisture_mass_kg = moisture
        cell.dry_wood_mass_kg = dry_wood
        cell.char_mass_kg = char
        cell.ash_mass_kg = ash
        cell.phase = base._phase_for_values(
            cell.temperature_k, moisture, dry_wood, char, ash, p, mass_epsilon_kg
        )
    return conduction_energy


def _call_native(library, arrays, topology, scratch, p, mass_epsilon_kg: float):
    double_pointer = ctypes.POINTER(ctypes.c_double)
    uint_pointer = ctypes.POINTER(ctypes.c_uint32)
    result = library.campfire_native_conduction_step(
        arrays["temperature_k"].size,
        *(arrays[name].ctypes.data_as(double_pointer) for name in base.DOUBLE_FIELDS),
        arrays["phase_code"].ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        topology["first_cell"].size,
        topology["first_cell"].ctypes.data_as(uint_pointer),
        topology["second_cell"].ctypes.data_as(uint_pointer),
        topology["conductance_w_k"].ctypes.data_as(double_pointer),
        scratch.ctypes.data_as(double_pointer),
        base.DT_SECONDS,
        base.HEAT_FLUX_W_M2,
        p.radiant_absorptivity,
        p.convection_w_m2_k,
        p.emissivity,
        base.SIGMA_W_M2_K4,
        p.ambient_temperature_k,
        p.water_specific_heat_j_kg_k,
        p.char_specific_heat_j_kg_k,
        p.ash_specific_heat_j_kg_k,
        p.max_temperature_k,
        p.pyrolysis_start_temperature_k,
        mass_epsilon_kg,
    )
    if result != 0:
        raise RuntimeError(f"Native conduction kernel failed with code {result}")


def _time_python(base_cells, topology, p, epsilon, steps, warmup):
    cells = copy.deepcopy(base_cells)
    samples = []
    final_energy = None
    for _ in range(steps):
        started = time.perf_counter()
        final_energy = _python_step(cells, topology["python_pairs"], p, epsilon)
        samples.append((time.perf_counter() - started) * 1000.0)
    invariant = abs(sum(final_energy)) if final_energy is not None else None
    return base._timing_summary(samples, warmup), cells, None, invariant


def _time_roundtrip(base_cells, topology, p, epsilon, library, steps, warmup):
    cells = copy.deepcopy(base_cells)
    scratch = np.zeros(len(cells), dtype=np.float64)
    samples = []
    for _ in range(steps):
        started = time.perf_counter()
        arrays = base._extract_arrays(cells, p.wood_specific_heat_j_kg_k)
        _call_native(library, arrays, topology, scratch, p, epsilon)
        base._write_arrays(arrays, cells)
        samples.append((time.perf_counter() - started) * 1000.0)
    return (
        base._timing_summary(samples, warmup),
        cells,
        None,
        abs(float(np.sum(scratch))),
    )


def _time_resident(base_cells, topology, p, epsilon, library, steps, warmup):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    arrays = base._extract_arrays(cells, p.wood_specific_heat_j_kg_k)
    scratch = np.zeros(len(cells), dtype=np.float64)
    import_ms = (time.perf_counter() - started) * 1000.0
    samples = []
    for _ in range(steps):
        started = time.perf_counter()
        _call_native(library, arrays, topology, scratch, p, epsilon)
        samples.append((time.perf_counter() - started) * 1000.0)
    started = time.perf_counter()
    base._write_arrays(arrays, cells)
    export_ms = (time.perf_counter() - started) * 1000.0
    return (
        base._timing_summary(samples, warmup),
        cells,
        {"one_time_import_ms": import_ms, "one_time_export_ms": export_ms},
        abs(float(np.sum(scratch))),
    )


def run_benchmark(dll_path: Path, log_count: int, steps: int, warmup: int, runs: int):
    combustion = base._load_combustion_module()
    dry = combustion.create_cylindrical_wood_model(
        "native_conduction_dry", 0.16, 1.80, moisture_ratio_dry_basis=0.12
    )
    wet = combustion.create_cylindrical_wood_model(
        "native_conduction_wet", 0.16, 1.80, moisture_ratio_dry_basis=0.60
    )
    base_cells = []
    for index in range(log_count):
        base_cells.extend(copy.deepcopy(dry.cells if index % 2 == 0 else wet.cells))
    topology = _topology_arrays(dry._conduction_pairs, log_count, len(dry.cells))
    library = base._load_native_kernel(dll_path)
    _configure_conduction_kernel(library)
    methods = {
        "python_aos_conduction": lambda: _time_python(
            base_cells, topology, dry.parameters, dry._mass_epsilon_kg, steps, warmup
        ),
        "native_aos_roundtrip_conduction": lambda: _time_roundtrip(
            base_cells,
            topology,
            dry.parameters,
            dry._mass_epsilon_kg,
            library,
            steps,
            warmup,
        ),
        "native_resident_soa_conduction": lambda: _time_resident(
            base_cells,
            topology,
            dry.parameters,
            dry._mass_epsilon_kg,
            library,
            steps,
            warmup,
        ),
    }
    orders = [
        list(methods),
        ["native_aos_roundtrip_conduction", "native_resident_soa_conduction", "python_aos_conduction"],
        ["native_resident_soa_conduction", "python_aos_conduction", "native_aos_roundtrip_conduction"],
    ]
    raw_runs = []
    for run_index in range(runs):
        gc.collect()
        outcomes = {}
        for name in orders[run_index % len(orders)]:
            timing, cells, boundary, balance = methods[name]()
            outcomes[name] = {
                "timing": timing,
                "cells": cells,
                "boundary": boundary,
                "conduction_balance_error_j": balance,
            }
        reference = outcomes["python_aos_conduction"]["cells"]
        comparisons = {
            name: base._compare(reference, outcomes[name]["cells"])
            for name in (
                "native_aos_roundtrip_conduction",
                "native_resident_soa_conduction",
            )
        }
        if not all(item["within_tolerance"] for item in comparisons.values()):
            raise RuntimeError("Native conduction result exceeded the tolerance")
        raw_runs.append(
            {
                "run": run_index + 1,
                "order": orders[run_index % len(orders)],
                "methods": {
                    name: {
                        "timing": value["timing"],
                        "boundary": value["boundary"],
                        "conduction_balance_error_j": value["conduction_balance_error_j"],
                        "final_state_sha256": base._state_digest(value["cells"]),
                    }
                    for name, value in outcomes.items()
                },
                "comparisons": comparisons,
            }
        )
    return {
        "schema_version": 1,
        "phase": "phase6av",
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
            "source_sha256": hashlib.sha256(
                (ROOT / "native" / "phase6au" / "wood_cell_kernel.cpp").read_bytes()
            ).hexdigest(),
        },
        "measurement": {
            "log_count": log_count,
            "cell_count_per_log": len(dry.cells),
            "combined_cell_count": len(base_cells),
            "conduction_pairs_per_log": len(dry._conduction_pairs),
            "combined_conduction_pair_count": topology["first_cell"].size,
            "steps_per_run": steps,
            "warmup_steps_excluded": warmup,
            "runs": runs,
            "dt_seconds": base.DT_SECONDS,
            "heat_flux_w_m2": base.HEAT_FLUX_W_M2,
            "balanced_method_order": True,
        },
        "boundary": {
            "included": [
                "immutable_conduction_topology",
                "pairwise_conduction",
                "sensible_heat",
                "state_clamp",
                "phase_classification",
            ],
            "excluded": [
                "evaporation",
                "pyrolysis",
                "char_oxidation",
                "runtime_metrics",
                "Flow/USD/rendering/PhysX",
            ],
            "production_model_changed": False,
            "python_json_schema_changed": False,
        },
        "tolerances": {
            "maximum_temperature_error_k": base.TEMPERATURE_TOLERANCE_K,
            "maximum_mass_error_kg": base.MASS_TOLERANCE_KG,
            "maximum_phase_mismatch_count": 0,
            "maximum_conduction_balance_error_j": 1.0e-9,
        },
        "runs": raw_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--logs", type=int, default=20)
    parser.add_argument("--steps", type=int, default=180)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if not arguments.dll.is_file():
        parser.error(f"Native DLL does not exist: {arguments.dll}")
    if arguments.logs <= 0 or arguments.steps <= arguments.warmup or arguments.runs < 3:
        parser.error("Require positive logs, steps > warmup, and at least three runs")
    result = run_benchmark(
        arguments.dll, arguments.logs, arguments.steps, arguments.warmup, arguments.runs
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

