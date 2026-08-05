"""Compare CPU and GPU execution shapes for two isolated wood-step hot segments.

Run this with the Kit Python executable.  The benchmark deliberately excludes
conduction, evaporation, and reactions: it only compares the cell-local
sensible-heat update plus state clamp/phase classification identified by Phase
6T.  Results therefore decide a data-layout prototype, not production physics.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
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
BUILD_ROOT = REPOSITORY_ROOT / "_build" / "windows-x86_64" / "release"
WARP_ROOT = BUILD_ROOT / "extscache" / "omni.warp.core-1.14.0+wx64"
PIP_ROOT = (
    BUILD_ROOT
    / "extscache"
    / "omni.kit.pip_archive-0.0.0+698af100.wx64.cp312"
    / "pip_prebundle"
)
WARP_CACHE = REPOSITORY_ROOT / "artifacts" / "performance" / "warp_cache"

sys.path[:0] = [str(PIP_ROOT), str(WARP_ROOT)]
import numpy as np  # noqa: E402
import warp as wp  # noqa: E402


PHASE_TO_CODE = {
    "WET_WOOD": 0,
    "DRY_WOOD": 1,
    "PYROLYZING": 2,
    "CHAR": 3,
    "ASH": 4,
    "DEPLETED": 5,
}
CODE_TO_PHASE = {value: key for key, value in PHASE_TO_CODE.items()}


@wp.kernel
def sensible_finalize_kernel(
    temperature_k: wp.array(dtype=wp.float64),
    moisture_mass_kg: wp.array(dtype=wp.float64),
    dry_wood_mass_kg: wp.array(dtype=wp.float64),
    char_mass_kg: wp.array(dtype=wp.float64),
    ash_mass_kg: wp.array(dtype=wp.float64),
    external_area_m2: wp.array(dtype=wp.float64),
    surface_exposure: wp.array(dtype=wp.float64),
    dry_specific_heat_j_kg_k: wp.array(dtype=wp.float64),
    phase_code: wp.array(dtype=wp.int32),
    dt_seconds: wp.float64,
    heat_flux_w_m2: wp.float64,
    absorptivity: wp.float64,
    convection_w_m2_k: wp.float64,
    emissivity: wp.float64,
    sigma: wp.float64,
    ambient_temperature_k: wp.float64,
    water_specific_heat_j_kg_k: wp.float64,
    char_specific_heat_j_kg_k: wp.float64,
    ash_specific_heat_j_kg_k: wp.float64,
    max_temperature_k: wp.float64,
    pyrolysis_start_temperature_k: wp.float64,
    mass_epsilon_kg: wp.float64,
):
    index = wp.tid()
    temperature = temperature_k[index]
    moisture = wp.max(moisture_mass_kg[index], wp.float64(0.0))
    dry_wood = wp.max(dry_wood_mass_kg[index], wp.float64(0.0))
    char = wp.max(char_mass_kg[index], wp.float64(0.0))
    ash = wp.max(ash_mass_kg[index], wp.float64(0.0))
    area = external_area_m2[index] * surface_exposure[index]
    heat_capacity = wp.max(
        dry_wood * dry_specific_heat_j_kg_k[index]
        + moisture * water_specific_heat_j_kg_k
        + char * char_specific_heat_j_kg_k
        + ash * ash_specific_heat_j_kg_k,
        wp.float64(1.0e-9),
    )
    temperature_squared = temperature * temperature
    ambient_squared = ambient_temperature_k * ambient_temperature_k
    external_heat_w = heat_flux_w_m2 * absorptivity * area
    convective_loss_w = convection_w_m2_k * area * (
        temperature - ambient_temperature_k
    )
    radiation_loss_w = emissivity * sigma * area * (
        temperature_squared * temperature_squared - ambient_squared * ambient_squared
    )
    temperature = temperature + (
        external_heat_w - convective_loss_w - radiation_loss_w
    ) * dt_seconds / heat_capacity
    temperature = wp.min(
        max_temperature_k, wp.max(ambient_temperature_k, temperature)
    )

    phase = wp.int32(1)
    if moisture > dry_wood * wp.float64(0.01):
        phase = wp.int32(0)
    if temperature >= pyrolysis_start_temperature_k and dry_wood > mass_epsilon_kg:
        phase = wp.int32(2)
    if ash > dry_wood + char:
        phase = wp.int32(4)
    if char > dry_wood and char > ash:
        phase = wp.int32(3)
    if moisture + dry_wood + char + ash <= mass_epsilon_kg:
        phase = wp.int32(5)

    temperature_k[index] = temperature
    moisture_mass_kg[index] = moisture
    dry_wood_mass_kg[index] = dry_wood
    char_mass_kg[index] = char
    ash_mass_kg[index] = ash
    phase_code[index] = phase


def _load_combustion_module():
    specification = importlib.util.spec_from_file_location(
        "campfire_combustion_array_benchmark", COMBUSTION_MODULE
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load wood model: {COMBUSTION_MODULE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _create_cells_and_parameters():
    combustion = _load_combustion_module()
    dry = combustion.create_cylindrical_wood_model(
        "benchmark_dry", 0.16, 1.80, moisture_ratio_dry_basis=0.12
    )
    wet = combustion.create_cylindrical_wood_model(
        "benchmark_wet", 0.16, 1.80, moisture_ratio_dry_basis=0.60
    )
    return dry.cells + wet.cells, dry.parameters, dry._mass_epsilon_kg


def _phase_for_values(
    temperature_k: float,
    moisture_mass_kg: float,
    dry_wood_mass_kg: float,
    char_mass_kg: float,
    ash_mass_kg: float,
    pyrolysis_start_temperature_k: float,
    mass_epsilon_kg: float,
) -> str:
    if (
        moisture_mass_kg + dry_wood_mass_kg + char_mass_kg + ash_mass_kg
        <= mass_epsilon_kg
    ):
        return "DEPLETED"
    if char_mass_kg > dry_wood_mass_kg and char_mass_kg > ash_mass_kg:
        return "CHAR"
    if ash_mass_kg > dry_wood_mass_kg + char_mass_kg:
        return "ASH"
    if (
        temperature_k >= pyrolysis_start_temperature_k
        and dry_wood_mass_kg > mass_epsilon_kg
    ):
        return "PYROLYZING"
    if moisture_mass_kg > dry_wood_mass_kg * 0.01:
        return "WET_WOOD"
    return "DRY_WOOD"


def _python_step(cells, p, mass_epsilon_kg: float) -> None:
    sigma = 5.670374419e-8
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
        external_heat_w = 150_000.0 * p.radiant_absorptivity * area
        convective_loss_w = p.convection_w_m2_k * area * (
            cell.temperature_k - p.ambient_temperature_k
        )
        radiation_loss_w = p.emissivity * sigma * area * (
            temperature_squared * temperature_squared - ambient_fourth
        )
        cell.temperature_k += (
            external_heat_w - convective_loss_w - radiation_loss_w
        ) * 0.2 / heat_capacity
        cell.temperature_k = min(
            p.max_temperature_k, max(p.ambient_temperature_k, cell.temperature_k)
        )
        cell.moisture_mass_kg = moisture
        cell.dry_wood_mass_kg = dry_wood
        cell.char_mass_kg = char
        cell.ash_mass_kg = ash
        cell.phase = _phase_for_values(
            cell.temperature_k,
            moisture,
            dry_wood,
            char,
            ash,
            p.pyrolysis_start_temperature_k,
            mass_epsilon_kg,
        )


def _extract_numpy(cells) -> dict[str, np.ndarray]:
    return {
        "temperature_k": np.fromiter(
            (cell.temperature_k for cell in cells), dtype=np.float64
        ),
        "moisture_mass_kg": np.fromiter(
            (cell.moisture_mass_kg for cell in cells), dtype=np.float64
        ),
        "dry_wood_mass_kg": np.fromiter(
            (cell.dry_wood_mass_kg for cell in cells), dtype=np.float64
        ),
        "char_mass_kg": np.fromiter(
            (cell.char_mass_kg for cell in cells), dtype=np.float64
        ),
        "ash_mass_kg": np.fromiter(
            (cell.ash_mass_kg for cell in cells), dtype=np.float64
        ),
        "external_area_m2": np.fromiter(
            (cell.external_area_m2 for cell in cells), dtype=np.float64
        ),
        "surface_exposure": np.fromiter(
            (cell.surface_exposure for cell in cells), dtype=np.float64
        ),
        "dry_specific_heat_j_kg_k": np.fromiter(
            (
                cell.dry_wood_specific_heat_j_kg_k
                if cell.dry_wood_specific_heat_j_kg_k is not None
                else 1700.0
                for cell in cells
            ),
            dtype=np.float64,
        ),
        "phase_code": np.fromiter(
            (PHASE_TO_CODE[cell.phase] for cell in cells), dtype=np.int32
        ),
    }


def _write_numpy_to_cells(arrays: dict[str, np.ndarray], cells) -> None:
    for index, cell in enumerate(cells):
        cell.temperature_k = float(arrays["temperature_k"][index])
        cell.moisture_mass_kg = float(arrays["moisture_mass_kg"][index])
        cell.dry_wood_mass_kg = float(arrays["dry_wood_mass_kg"][index])
        cell.char_mass_kg = float(arrays["char_mass_kg"][index])
        cell.ash_mass_kg = float(arrays["ash_mass_kg"][index])
        cell.phase = CODE_TO_PHASE[int(arrays["phase_code"][index])]


def _numpy_step(arrays: dict[str, np.ndarray], p, mass_epsilon_kg: float) -> None:
    temperature = arrays["temperature_k"]
    moisture = arrays["moisture_mass_kg"]
    dry_wood = arrays["dry_wood_mass_kg"]
    char = arrays["char_mass_kg"]
    ash = arrays["ash_mass_kg"]
    np.maximum(moisture, 0.0, out=moisture)
    np.maximum(dry_wood, 0.0, out=dry_wood)
    np.maximum(char, 0.0, out=char)
    np.maximum(ash, 0.0, out=ash)
    area = arrays["external_area_m2"] * arrays["surface_exposure"]
    heat_capacity = (
        dry_wood * arrays["dry_specific_heat_j_kg_k"]
        + moisture * p.water_specific_heat_j_kg_k
        + char * p.char_specific_heat_j_kg_k
        + ash * p.ash_specific_heat_j_kg_k
    )
    np.maximum(heat_capacity, 1.0e-9, out=heat_capacity)
    temperature_squared = temperature * temperature
    ambient_squared = p.ambient_temperature_k * p.ambient_temperature_k
    external_heat_w = 150_000.0 * p.radiant_absorptivity * area
    convective_loss_w = (
        p.convection_w_m2_k * area * (temperature - p.ambient_temperature_k)
    )
    radiation_loss_w = (
        p.emissivity
        * 5.670374419e-8
        * area
        * (
            temperature_squared * temperature_squared
            - ambient_squared * ambient_squared
        )
    )
    temperature += (
        external_heat_w - convective_loss_w - radiation_loss_w
    ) * 0.2 / heat_capacity
    np.clip(temperature, p.ambient_temperature_k, p.max_temperature_k, out=temperature)

    phase = arrays["phase_code"]
    phase.fill(PHASE_TO_CODE["DRY_WOOD"])
    phase[moisture > dry_wood * 0.01] = PHASE_TO_CODE["WET_WOOD"]
    phase[
        (temperature >= p.pyrolysis_start_temperature_k)
        & (dry_wood > mass_epsilon_kg)
    ] = PHASE_TO_CODE["PYROLYZING"]
    phase[ash > dry_wood + char] = PHASE_TO_CODE["ASH"]
    phase[(char > dry_wood) & (char > ash)] = PHASE_TO_CODE["CHAR"]
    phase[moisture + dry_wood + char + ash <= mass_epsilon_kg] = PHASE_TO_CODE[
        "DEPLETED"
    ]


def _warp_arrays(arrays: dict[str, np.ndarray], device: str) -> dict:
    return {
        name: wp.array(
            value,
            dtype=wp.int32 if name == "phase_code" else wp.float64,
            device=device,
        )
        for name, value in arrays.items()
    }


def _launch_warp(arrays: dict, p, mass_epsilon_kg: float, device: str) -> None:
    wp.launch(
        sensible_finalize_kernel,
        dim=arrays["temperature_k"].size,
        inputs=[
            arrays["temperature_k"],
            arrays["moisture_mass_kg"],
            arrays["dry_wood_mass_kg"],
            arrays["char_mass_kg"],
            arrays["ash_mass_kg"],
            arrays["external_area_m2"],
            arrays["surface_exposure"],
            arrays["dry_specific_heat_j_kg_k"],
            arrays["phase_code"],
            0.2,
            150_000.0,
            p.radiant_absorptivity,
            p.convection_w_m2_k,
            p.emissivity,
            5.670374419e-8,
            p.ambient_temperature_k,
            p.water_specific_heat_j_kg_k,
            p.char_specific_heat_j_kg_k,
            p.ash_specific_heat_j_kg_k,
            p.max_temperature_k,
            p.pyrolysis_start_temperature_k,
            mass_epsilon_kg,
        ],
        device=device,
    )


def _warp_to_numpy(arrays: dict) -> dict[str, np.ndarray]:
    return {name: value.numpy() for name, value in arrays.items()}


def _state_digest(cells) -> str:
    encoded = json.dumps(
        [
            [
                cell.temperature_k,
                cell.moisture_mass_kg,
                cell.dry_wood_mass_kg,
                cell.char_mass_kg,
                cell.ash_mass_kg,
                cell.phase,
            ]
            for cell in cells
        ],
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compare_cells(reference, candidate) -> dict:
    max_temperature_error_k = max(
        abs(left.temperature_k - right.temperature_k)
        for left, right in zip(reference, candidate)
    )
    max_mass_error_kg = max(
        abs(left_value - right_value)
        for left, right in zip(reference, candidate)
        for left_value, right_value in (
            (left.moisture_mass_kg, right.moisture_mass_kg),
            (left.dry_wood_mass_kg, right.dry_wood_mass_kg),
            (left.char_mass_kg, right.char_mass_kg),
            (left.ash_mass_kg, right.ash_mass_kg),
        )
    )
    phase_mismatch_count = sum(
        left.phase != right.phase for left, right in zip(reference, candidate)
    )
    return {
        "max_temperature_error_k": max_temperature_error_k,
        "max_mass_error_kg": max_mass_error_kg,
        "phase_mismatch_count": phase_mismatch_count,
        "exact_state_sha256_match": _state_digest(reference) == _state_digest(candidate),
        "within_candidate_tolerance": (
            max_temperature_error_k <= 1.0e-9
            and max_mass_error_kg <= 1.0e-12
            and phase_mismatch_count == 0
        ),
    }


def _time_python(base_cells, p, mass_epsilon_kg: float, steps: int):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    for _ in range(steps):
        _python_step(cells, p, mass_epsilon_kg)
    return (time.perf_counter() - started) * 1000.0, cells


def _time_numpy_roundtrip(base_cells, p, mass_epsilon_kg: float, steps: int):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    for _ in range(steps):
        arrays = _extract_numpy(cells)
        _numpy_step(arrays, p, mass_epsilon_kg)
        _write_numpy_to_cells(arrays, cells)
    return (time.perf_counter() - started) * 1000.0, cells


def _time_numpy_resident(base_cells, p, mass_epsilon_kg: float, steps: int):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    arrays = _extract_numpy(cells)
    for _ in range(steps):
        _numpy_step(arrays, p, mass_epsilon_kg)
    _write_numpy_to_cells(arrays, cells)
    return (time.perf_counter() - started) * 1000.0, cells


def _time_warp_roundtrip(
    base_cells, p, mass_epsilon_kg: float, steps: int, device: str
):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    for _ in range(steps):
        host_arrays = _extract_numpy(cells)
        device_arrays = _warp_arrays(host_arrays, device)
        _launch_warp(device_arrays, p, mass_epsilon_kg, device)
        wp.synchronize_device(device)
        _write_numpy_to_cells(_warp_to_numpy(device_arrays), cells)
    return (time.perf_counter() - started) * 1000.0, cells


def _time_warp_resident(
    base_cells,
    p,
    mass_epsilon_kg: float,
    steps: int,
    device: str,
    sync_interval: int,
):
    cells = copy.deepcopy(base_cells)
    started = time.perf_counter()
    device_arrays = _warp_arrays(_extract_numpy(cells), device)
    for step_index in range(steps):
        _launch_warp(device_arrays, p, mass_epsilon_kg, device)
        if (step_index + 1) % sync_interval == 0:
            wp.synchronize_device(device)
    wp.synchronize_device(device)
    _write_numpy_to_cells(_warp_to_numpy(device_arrays), cells)
    return (time.perf_counter() - started) * 1000.0, cells


def _summary(values: list[float], steps: int) -> dict:
    return {
        "run_count": len(values),
        "total_ms_min": min(values),
        "total_ms_median": statistics.median(values),
        "total_ms_max": max(values),
        "per_step_ms_median": statistics.median(values) / steps,
    }


def run_benchmark(steps: int, runs: int, device: str) -> dict:
    base_cells, parameters, mass_epsilon_kg = _create_cells_and_parameters()
    WARP_CACHE.mkdir(parents=True, exist_ok=True)
    wp.config.kernel_cache_dir = str(WARP_CACHE)
    wp.init()
    if device not in {str(value) for value in wp.get_devices()}:
        raise RuntimeError(f"Warp device is unavailable: {device}")

    warmup_arrays = _warp_arrays(_extract_numpy(base_cells), device)
    _launch_warp(warmup_arrays, parameters, mass_epsilon_kg, device)
    wp.synchronize_device(device)

    timings: dict[str, list[float]] = {
        "python_aos": [],
        "numpy_aos_roundtrip": [],
        "numpy_resident": [],
        "warp_aos_roundtrip": [],
        "warp_resident_sync_each_step": [],
        "warp_resident_sync_every_5_steps": [],
        "warp_resident_final_sync": [],
    }
    comparisons = {}
    reference_cells = None
    for _ in range(runs):
        elapsed, candidate = _time_python(
            base_cells, parameters, mass_epsilon_kg, steps
        )
        timings["python_aos"].append(elapsed)
        reference_cells = candidate
        for name, timer in (
            ("numpy_aos_roundtrip", _time_numpy_roundtrip),
            ("numpy_resident", _time_numpy_resident),
        ):
            elapsed, candidate = timer(
                base_cells, parameters, mass_epsilon_kg, steps
            )
            timings[name].append(elapsed)
            comparisons[name] = _compare_cells(reference_cells, candidate)

        elapsed, candidate = _time_warp_roundtrip(
            base_cells, parameters, mass_epsilon_kg, steps, device
        )
        timings["warp_aos_roundtrip"].append(elapsed)
        comparisons["warp_aos_roundtrip"] = _compare_cells(
            reference_cells, candidate
        )
        for name, sync_interval in (
            ("warp_resident_sync_each_step", 1),
            ("warp_resident_sync_every_5_steps", 5),
            ("warp_resident_final_sync", steps),
        ):
            elapsed, candidate = _time_warp_resident(
                base_cells,
                parameters,
                mass_epsilon_kg,
                steps,
                device,
                sync_interval,
            )
            timings[name].append(elapsed)
            comparisons[name] = _compare_cells(reference_cells, candidate)

    if reference_cells is None:
        raise RuntimeError("Benchmark produced no reference state")
    if not all(result["within_candidate_tolerance"] for result in comparisons.values()):
        raise RuntimeError("One or more array candidates changed the isolated result")
    measurements = {name: _summary(values, steps) for name, values in timings.items()}
    python_median = measurements["python_aos"]["total_ms_median"]
    for measurement in measurements.values():
        measurement["relative_to_python"] = (
            measurement["total_ms_median"] / python_median
        )
    return {
        "schema_version": 1,
        "benchmark": "isolated_sensible_heat_and_state_finalize",
        "cell_count": len(base_cells),
        "steps": steps,
        "runs": runs,
        "dt_seconds": 0.2,
        "external_heat_flux_w_m2": 150_000.0,
        "numpy_version": np.__version__,
        "warp_version": wp.__version__,
        "warp_device": device,
        "warp_device_name": wp.get_device(device).name,
        "measurements": measurements,
        "candidate_comparisons": comparisons,
        "reference_state_sha256": _state_digest(reference_cells),
        "boundary": {
            "included_segments": ["sensible_heat", "state_finalize"],
            "excluded_segments": [
                "conduction",
                "evaporation",
                "pyrolysis",
                "char_oxidation",
                "metrics",
                "Flow/USD adapters",
            ],
            "warp_compilation_excluded": True,
            "roundtrip_includes_aos_conversion_and_device_transfer": True,
            "resident_includes_initial_upload_and_final_download": True,
            "production_model_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.steps <= 0 or arguments.runs <= 0:
        parser.error("--steps and --runs must be positive")

    result = run_benchmark(arguments.steps, arguments.runs, arguments.device)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
