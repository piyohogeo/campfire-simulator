"""Benchmark the Phase 6AU native contiguous wood-state boundary.

The isolated kernel mirrors the Phase 6U sensible-heat and final-state segment.
It is a feasibility probe only: conduction and reactions remain outside scope.
"""

from __future__ import annotations

import argparse
import copy
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
COMBUSTION_MODULE = (
    ROOT / "source" / "extensions" / "campfire.app" / "campfire" / "app" / "combustion.py"
)
PIP_ROOT = (
    ROOT
    / "_build"
    / "windows-x86_64"
    / "release"
    / "extscache"
    / "omni.kit.pip_archive-0.0.0+698af100.wx64.cp312"
    / "pip_prebundle"
)
sys.path.insert(0, str(PIP_ROOT))
import numpy as np  # noqa: E402


DT_SECONDS = 0.2
HEAT_FLUX_W_M2 = 150_000.0
SIGMA_W_M2_K4 = 5.670374419e-8
TEMPERATURE_TOLERANCE_K = 1.0e-9
MASS_TOLERANCE_KG = 1.0e-12
PHASE_TO_CODE = {
    "WET_WOOD": 0,
    "DRY_WOOD": 1,
    "PYROLYZING": 2,
    "CHAR": 3,
    "ASH": 4,
    "DEPLETED": 5,
}
CODE_TO_PHASE = {value: key for key, value in PHASE_TO_CODE.items()}
DOUBLE_FIELDS = (
    "temperature_k",
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "char_mass_kg",
    "ash_mass_kg",
    "external_area_m2",
    "surface_exposure",
    "dry_specific_heat_j_kg_k",
)


def _load_combustion_module():
    specification = importlib.util.spec_from_file_location(
        "campfire_combustion_native_boundary", COMBUSTION_MODULE
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load wood model: {COMBUSTION_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _load_native_kernel(path: Path):
    library = ctypes.CDLL(str(path.resolve()))
    double_pointer = ctypes.POINTER(ctypes.c_double)
    int_pointer = ctypes.POINTER(ctypes.c_int32)
    library.campfire_native_step.argtypes = (
        [ctypes.c_size_t]
        + [double_pointer] * 8
        + [int_pointer]
        + [ctypes.c_double] * 13
    )
    library.campfire_native_step.restype = ctypes.c_int32
    library.campfire_native_abi_version.argtypes = []
    library.campfire_native_abi_version.restype = ctypes.c_int32
    library.campfire_native_msvc_version.argtypes = []
    library.campfire_native_msvc_version.restype = ctypes.c_int32
    library.campfire_native_msvc_full_version.argtypes = []
    library.campfire_native_msvc_full_version.restype = ctypes.c_int64
    if library.campfire_native_abi_version() != 1:
        raise RuntimeError("Unsupported native wood ABI")
    return library


def _phase_for_values(temperature, moisture, dry_wood, char, ash, p, epsilon):
    if moisture + dry_wood + char + ash <= epsilon:
        return "DEPLETED"
    if char > dry_wood and char > ash:
        return "CHAR"
    if ash > dry_wood + char:
        return "ASH"
    if temperature >= p.pyrolysis_start_temperature_k and dry_wood > epsilon:
        return "PYROLYZING"
    if moisture > dry_wood * 0.01:
        return "WET_WOOD"
    return "DRY_WOOD"


def _python_step(cells, p, mass_epsilon_kg: float) -> None:
    ambient_squared = p.ambient_temperature_k * p.ambient_temperature_k
    ambient_fourth = ambient_squared * ambient_squared
    for cell in cells:
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
        external_heat_w = HEAT_FLUX_W_M2 * p.radiant_absorptivity * area
        convective_loss_w = p.convection_w_m2_k * area * (
            cell.temperature_k - p.ambient_temperature_k
        )
        radiation_loss_w = p.emissivity * SIGMA_W_M2_K4 * area * (
            temperature_squared * temperature_squared - ambient_fourth
        )
        cell.temperature_k += (
            external_heat_w - convective_loss_w - radiation_loss_w
        ) * DT_SECONDS / heat_capacity
        cell.temperature_k = min(
            p.max_temperature_k, max(p.ambient_temperature_k, cell.temperature_k)
        )
        cell.moisture_mass_kg = moisture
        cell.dry_wood_mass_kg = dry_wood
        cell.char_mass_kg = char
        cell.ash_mass_kg = ash
        cell.phase = _phase_for_values(
            cell.temperature_k, moisture, dry_wood, char, ash, p, mass_epsilon_kg
        )


def _extract_arrays(cells, default_dry_specific_heat: float):
    values = {
        "temperature_k": (cell.temperature_k for cell in cells),
        "moisture_mass_kg": (cell.moisture_mass_kg for cell in cells),
        "dry_wood_mass_kg": (cell.dry_wood_mass_kg for cell in cells),
        "char_mass_kg": (cell.char_mass_kg for cell in cells),
        "ash_mass_kg": (cell.ash_mass_kg for cell in cells),
        "external_area_m2": (cell.external_area_m2 for cell in cells),
        "surface_exposure": (cell.surface_exposure for cell in cells),
        "dry_specific_heat_j_kg_k": (
            cell.dry_wood_specific_heat_j_kg_k
            if cell.dry_wood_specific_heat_j_kg_k is not None
            else default_dry_specific_heat
            for cell in cells
        ),
    }
    arrays = {
        name: np.fromiter(iterator, dtype=np.float64, count=len(cells))
        for name, iterator in values.items()
    }
    arrays["phase_code"] = np.fromiter(
        (PHASE_TO_CODE[cell.phase] for cell in cells), dtype=np.int32, count=len(cells)
    )
    return arrays


def _write_arrays(arrays, cells) -> None:
    for index, cell in enumerate(cells):
        cell.temperature_k = float(arrays["temperature_k"][index])
        cell.moisture_mass_kg = float(arrays["moisture_mass_kg"][index])
        cell.dry_wood_mass_kg = float(arrays["dry_wood_mass_kg"][index])
        cell.char_mass_kg = float(arrays["char_mass_kg"][index])
        cell.ash_mass_kg = float(arrays["ash_mass_kg"][index])
        cell.phase = CODE_TO_PHASE[int(arrays["phase_code"][index])]


def _call_native(library, arrays, p, mass_epsilon_kg: float) -> None:
    double_pointer = ctypes.POINTER(ctypes.c_double)
    result = library.campfire_native_step(
        arrays["temperature_k"].size,
        *(arrays[name].ctypes.data_as(double_pointer) for name in DOUBLE_FIELDS),
        arrays["phase_code"].ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        DT_SECONDS,
        HEAT_FLUX_W_M2,
        p.radiant_absorptivity,
        p.convection_w_m2_k,
        p.emissivity,
        SIGMA_W_M2_K4,
        p.ambient_temperature_k,
        p.water_specific_heat_j_kg_k,
        p.char_specific_heat_j_kg_k,
        p.ash_specific_heat_j_kg_k,
        p.max_temperature_k,
        p.pyrolysis_start_temperature_k,
        mass_epsilon_kg,
    )
    if result != 0:
        raise RuntimeError(f"Native kernel rejected the state with code {result}")


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def _timing_summary(samples: list[float], warmup_steps: int) -> dict:
    measured = samples[warmup_steps:]
    return {
        "sample_count": len(measured),
        "warmup_samples_excluded": warmup_steps,
        "mean_ms": statistics.fmean(measured),
        "p95_ms": _percentile_95(measured),
        "max_ms": max(measured),
    }


def _state_digest(cells) -> str:
    payload = [
        [
            cell.temperature_k,
            cell.moisture_mass_kg,
            cell.dry_wood_mass_kg,
            cell.char_mass_kg,
            cell.ash_mass_kg,
            cell.phase,
        ]
        for cell in cells
    ]
    return hashlib.sha256(
        json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _compare(reference, candidate) -> dict:
    max_temperature_error = max(
        abs(left.temperature_k - right.temperature_k)
        for left, right in zip(reference, candidate)
    )
    max_mass_error = max(
        abs(left_value - right_value)
        for left, right in zip(reference, candidate)
        for left_value, right_value in (
            (left.moisture_mass_kg, right.moisture_mass_kg),
            (left.dry_wood_mass_kg, right.dry_wood_mass_kg),
            (left.char_mass_kg, right.char_mass_kg),
            (left.ash_mass_kg, right.ash_mass_kg),
        )
    )
    phase_mismatches = sum(
        left.phase != right.phase for left, right in zip(reference, candidate)
    )
    return {
        "maximum_temperature_error_k": max_temperature_error,
        "maximum_mass_error_kg": max_mass_error,
        "phase_mismatch_count": phase_mismatches,
        "exact_state_sha256_match": _state_digest(reference) == _state_digest(candidate),
        "within_tolerance": (
            max_temperature_error <= TEMPERATURE_TOLERANCE_K
            and max_mass_error <= MASS_TOLERANCE_KG
            and phase_mismatches == 0
        ),
    }


def _time_python(base_cells, p, epsilon, steps, warmup):
    cells = copy.deepcopy(base_cells)
    samples = []
    for _ in range(steps):
        started = time.perf_counter()
        _python_step(cells, p, epsilon)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _timing_summary(samples, warmup), cells, None


def _time_native_roundtrip(base_cells, p, epsilon, library, steps, warmup):
    cells = copy.deepcopy(base_cells)
    samples = []
    for _ in range(steps):
        started = time.perf_counter()
        arrays = _extract_arrays(cells, p.wood_specific_heat_j_kg_k)
        _call_native(library, arrays, p, epsilon)
        _write_arrays(arrays, cells)
        samples.append((time.perf_counter() - started) * 1000.0)
    return _timing_summary(samples, warmup), cells, None


def _time_native_resident(base_cells, p, epsilon, library, steps, warmup):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    arrays = _extract_arrays(cells, p.wood_specific_heat_j_kg_k)
    import_ms = (time.perf_counter() - started) * 1000.0
    samples = []
    for _ in range(steps):
        started = time.perf_counter()
        _call_native(library, arrays, p, epsilon)
        samples.append((time.perf_counter() - started) * 1000.0)
    started = time.perf_counter()
    _write_arrays(arrays, cells)
    export_ms = (time.perf_counter() - started) * 1000.0
    boundary = {"one_time_import_ms": import_ms, "one_time_export_ms": export_ms}
    return _timing_summary(samples, warmup), cells, boundary


def run_benchmark(dll_path: Path, log_count: int, steps: int, warmup: int, runs: int):
    combustion = _load_combustion_module()
    dry = combustion.create_cylindrical_wood_model(
        "native_boundary_dry", 0.16, 1.80, moisture_ratio_dry_basis=0.12
    )
    wet = combustion.create_cylindrical_wood_model(
        "native_boundary_wet", 0.16, 1.80, moisture_ratio_dry_basis=0.60
    )
    if len(dry.cells) != len(wet.cells):
        raise RuntimeError("Dry and wet templates have different cell counts")
    base_cells = []
    for index in range(log_count):
        base_cells.extend(copy.deepcopy(dry.cells if index % 2 == 0 else wet.cells))
    library = _load_native_kernel(dll_path)
    methods = {
        "python_aos": lambda: _time_python(
            base_cells, dry.parameters, dry._mass_epsilon_kg, steps, warmup
        ),
        "native_aos_roundtrip": lambda: _time_native_roundtrip(
            base_cells,
            dry.parameters,
            dry._mass_epsilon_kg,
            library,
            steps,
            warmup,
        ),
        "native_resident_soa": lambda: _time_native_resident(
            base_cells,
            dry.parameters,
            dry._mass_epsilon_kg,
            library,
            steps,
            warmup,
        ),
    }
    orders = [
        list(methods),
        ["native_aos_roundtrip", "native_resident_soa", "python_aos"],
        ["native_resident_soa", "python_aos", "native_aos_roundtrip"],
    ]
    raw_runs = []
    comparisons = []
    for run_index in range(runs):
        gc.collect()
        outcomes = {}
        for name in orders[run_index % len(orders)]:
            timing, cells, boundary = methods[name]()
            outcomes[name] = {"timing": timing, "cells": cells, "boundary": boundary}
        reference = outcomes["python_aos"]["cells"]
        run_comparisons = {
            name: _compare(reference, outcomes[name]["cells"])
            for name in ("native_aos_roundtrip", "native_resident_soa")
        }
        if not all(item["within_tolerance"] for item in run_comparisons.values()):
            raise RuntimeError("Native result exceeded the declared equivalence budget")
        comparisons.append(run_comparisons)
        raw_runs.append(
            {
                "run": run_index + 1,
                "order": orders[run_index % len(orders)],
                "methods": {
                    name: {
                        "timing": outcomes[name]["timing"],
                        "boundary": outcomes[name]["boundary"],
                        "final_state_sha256": _state_digest(outcomes[name]["cells"]),
                    }
                    for name in methods
                },
                "comparisons": run_comparisons,
            }
        )
    return {
        "schema_version": 1,
        "phase": "phase6au",
        "status": "ok",
        "runtime": {
            "python": platform.python_version(),
            "executable": sys.executable,
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in sys.executable.replace("\\", "/"),
            "numpy": np.__version__,
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "native_toolchain": {
            "abi_version": library.campfire_native_abi_version(),
            "msvc_version": library.campfire_native_msvc_version(),
            "msvc_full_version": library.campfire_native_msvc_full_version(),
            "dll_sha256": hashlib.sha256(dll_path.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(
                (ROOT / "native" / "phase6au" / "wood_cell_kernel.cpp").read_bytes()
            ).hexdigest(),
            "floating_point": "/fp:strict",
        },
        "measurement": {
            "log_count": log_count,
            "cell_count_per_log": len(dry.cells),
            "combined_cell_count": len(base_cells),
            "steps_per_run": steps,
            "warmup_steps_excluded": warmup,
            "runs": runs,
            "dt_seconds": DT_SECONDS,
            "heat_flux_w_m2": HEAT_FLUX_W_M2,
            "balanced_method_order": True,
        },
        "boundary": {
            "included": ["sensible_heat", "state_clamp", "phase_classification"],
            "excluded": [
                "conduction",
                "evaporation",
                "pyrolysis",
                "char_oxidation",
                "runtime_metrics",
                "Flow/USD/rendering/PhysX",
            ],
            "state_layout": "structure_of_arrays_float64_plus_int32_phase",
            "python_json_schema_changed": False,
            "production_model_changed": False,
        },
        "tolerances": {
            "maximum_temperature_error_k": TEMPERATURE_TOLERANCE_K,
            "maximum_mass_error_kg": MASS_TOLERANCE_KG,
            "maximum_phase_mismatch_count": 0,
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

