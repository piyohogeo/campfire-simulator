"""Compare the Phase 6AW resident native piecewise-linear complete wood step."""

from __future__ import annotations

import argparse
import copy
import ctypes
import dataclasses
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
CONDUCTION_BENCHMARK = ROOT / "scripts" / "benchmark_native_conduction_boundary.py"
IGNITION_RATE_KG_S = 1.0e-6
STEP_OUTPUT_COUNT = 9
CUMULATIVE_OUTPUT_COUNT = 7
TEMPERATURE_TOLERANCE_K = 1.0e-8
MASS_TOLERANCE_KG = 1.0e-12
STEP_OUTPUT_TOLERANCE = 1.0e-8
IGNITION_TOLERANCE_S = 0.2


def _load_conduction_base():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6av_benchmark_base", CONDUCTION_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AV benchmark: {CONDUCTION_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


conduction = _load_conduction_base()
base = conduction.base
np = base.np
STEP_ARGUMENTS = {
    "python_surface_boundary_fast_path": True,
    "python_state_clamp_fast_path": True,
    "update_cell_phases": True,
    "python_constant_heat_capacity_fast_path": True,
    "python_homogeneous_heat_capacity_fast_path": True,
    "python_inline_homogeneous_sensible_heat_capacity_fast_path": True,
}
CUMULATIVE_FIELDS = (
    "emitted_water_kg",
    "emitted_pyrolysis_gas_kg",
    "emitted_char_gas_kg",
    "emitted_primary_gas_kg",
    "emitted_tar_kg",
    "produced_primary_char_kg",
    "converted_secondary_tar_kg",
)


def _configure_complete_kernel(library):
    double_pointer = ctypes.POINTER(ctypes.c_double)
    uint_pointer = ctypes.POINTER(ctypes.c_uint32)
    int_pointer = ctypes.POINTER(ctypes.c_int32)
    library.campfire_native_piecewise_complete_step.argtypes = (
        [ctypes.c_size_t]
        + [double_pointer] * 10
        + [int_pointer, ctypes.c_size_t]
        + [uint_pointer] * 2
        + [double_pointer] * 3
        + [ctypes.c_size_t] * 2
        + [double_pointer] * 3
        + [ctypes.c_double] * 24
    )
    library.campfire_native_piecewise_complete_step.restype = ctypes.c_int32


def _precondition_template(combustion, name: str, moisture: float, steps: int):
    model = combustion.create_cylindrical_wood_model(
        name, 0.16, 1.80, moisture_ratio_dry_basis=moisture
    )
    model.use_slotted_cell_storage()
    for _ in range(steps):
        model.step(base.DT_SECONDS, base.HEAT_FLUX_W_M2, **STEP_ARGUMENTS)
    if model.parameters.pyrolysis_rate_model != "piecewise_linear":
        raise RuntimeError("Phase 6AW only accepts the piecewise-linear model")
    if model.parameters.secondary_tar_cracking_enabled:
        raise RuntimeError("Phase 6AW does not yet accept secondary tar cracking")
    return model.to_dict()


def _clone_models(combustion, templates: dict[str, dict], log_count: int):
    models = []
    for index in range(log_count):
        kind = "dry" if index % 2 == 0 else "wet"
        model = combustion.WoodThermalModel.from_dict(templates[kind])
        model.use_slotted_cell_storage()
        models.append(model)
    return models


def _combined_cells(models):
    return [cell for model in models for cell in model.cells]


def _extract_complete_arrays(cells, default_dry_specific_heat: float):
    arrays = base._extract_arrays(cells, default_dry_specific_heat)
    arrays["volatile_potential_kg"] = np.fromiter(
        (cell.volatile_potential_kg for cell in cells),
        dtype=np.float64,
        count=len(cells),
    )
    arrays["oxygen_factor"] = np.fromiter(
        (cell.oxygen_factor for cell in cells), dtype=np.float64, count=len(cells)
    )
    return arrays


def _write_complete_arrays(arrays, cells) -> None:
    base._write_arrays(arrays, cells)
    for index, cell in enumerate(cells):
        cell.volatile_potential_kg = float(arrays["volatile_potential_kg"][index])


def _model_boundary_arrays(models):
    elapsed = np.fromiter(
        (model.elapsed_seconds for model in models),
        dtype=np.float64,
        count=len(models),
    )
    cumulative = np.asarray(
        [[getattr(model, field) for field in CUMULATIVE_FIELDS] for model in models],
        dtype=np.float64,
    ).reshape(-1)
    return elapsed, cumulative


def _write_model_boundary(elapsed, cumulative, models) -> None:
    matrix = cumulative.reshape((len(models), CUMULATIVE_OUTPUT_COUNT))
    for index, model in enumerate(models):
        model.elapsed_seconds = float(elapsed[index])
        for field_index, field in enumerate(CUMULATIVE_FIELDS):
            setattr(model, field, float(matrix[index, field_index]))


def _call_native(
    library,
    arrays,
    topology,
    conduction_scratch,
    heat_capacity_scratch,
    elapsed,
    cumulative,
    step_output,
    log_count: int,
    cells_per_log: int,
    p,
    mass_epsilon_kg: float,
):
    dp = ctypes.POINTER(ctypes.c_double)
    up = ctypes.POINTER(ctypes.c_uint32)
    result = library.campfire_native_piecewise_complete_step(
        arrays["temperature_k"].size,
        arrays["temperature_k"].ctypes.data_as(dp),
        arrays["moisture_mass_kg"].ctypes.data_as(dp),
        arrays["dry_wood_mass_kg"].ctypes.data_as(dp),
        arrays["volatile_potential_kg"].ctypes.data_as(dp),
        arrays["char_mass_kg"].ctypes.data_as(dp),
        arrays["ash_mass_kg"].ctypes.data_as(dp),
        arrays["oxygen_factor"].ctypes.data_as(dp),
        arrays["external_area_m2"].ctypes.data_as(dp),
        arrays["surface_exposure"].ctypes.data_as(dp),
        arrays["dry_specific_heat_j_kg_k"].ctypes.data_as(dp),
        arrays["phase_code"].ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        topology["first_cell"].size,
        topology["first_cell"].ctypes.data_as(up),
        topology["second_cell"].ctypes.data_as(up),
        topology["conductance_w_k"].ctypes.data_as(dp),
        conduction_scratch.ctypes.data_as(dp),
        heat_capacity_scratch.ctypes.data_as(dp),
        log_count,
        cells_per_log,
        elapsed.ctypes.data_as(dp),
        cumulative.ctypes.data_as(dp),
        step_output.ctypes.data_as(dp),
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
        p.evaporation_start_temperature_k,
        p.water_latent_heat_j_kg,
        p.evaporation_max_fraction_s,
        p.pyrolysis_start_temperature_k,
        p.pyrolysis_full_temperature_k,
        p.pyrolysis_max_fraction_s,
        p.pyrolysis_heat_j_kg,
        p.pyrolysis_char_yield,
        p.char_oxidation_start_temperature_k,
        p.char_oxidation_max_fraction_s,
        p.char_ash_yield,
        p.char_oxidation_heat_j_kg,
        mass_epsilon_kg,
    )
    if result != 0:
        raise RuntimeError(f"Native complete-step kernel failed with code {result}")


def _result_row(result) -> list[float]:
    return [float(value) for value in dataclasses.astuple(result)]


def _native_result_rows(step_output, elapsed) -> list[list[float]]:
    rows = []
    matrix = step_output.reshape((len(elapsed), STEP_OUTPUT_COUNT))
    for index, values in enumerate(matrix):
        evaporated = float(values[0])
        pyrolysis = float(values[1])
        char_gas = float(values[2])
        external_heat = float(values[3])
        primary_gas = float(values[4])
        primary_tar = float(values[5])
        primary_char = float(values[6])
        secondary = float(values[7])
        uncracked = float(values[8])
        rows.append(
            [
                float(elapsed[index]),
                evaporated,
                pyrolysis,
                char_gas,
                evaporated / base.DT_SECONDS,
                pyrolysis / base.DT_SECONDS,
                char_gas / base.DT_SECONDS,
                external_heat,
                primary_gas,
                primary_tar,
                primary_char,
                primary_gas / base.DT_SECONDS,
                primary_tar / base.DT_SECONDS,
                primary_char / base.DT_SECONDS,
                secondary,
                secondary / base.DT_SECONDS,
                uncracked,
                uncracked / base.DT_SECONDS,
            ]
        )
    return rows


def _history_sha256(history) -> str:
    return hashlib.sha256(
        json.dumps(history, allow_nan=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _models_sha256(models) -> str:
    return hashlib.sha256(
        json.dumps(
            [model.to_dict() for model in models],
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _ignition_times(history, initial_elapsed):
    ignition = [None] * len(initial_elapsed)
    for step_rows in history:
        for index, row in enumerate(step_rows):
            if ignition[index] is None and row[5] > IGNITION_RATE_KG_S:
                ignition[index] = row[0]
    return ignition


def _time_python(combustion, templates, log_count, steps, warmup):
    models = _clone_models(combustion, templates, log_count)
    initial_elapsed = [model.elapsed_seconds for model in models]
    samples = []
    history = []
    for _ in range(steps):
        started = time.perf_counter()
        results = [
            model.step(base.DT_SECONDS, base.HEAT_FLUX_W_M2, **STEP_ARGUMENTS)
            for model in models
        ]
        samples.append((time.perf_counter() - started) * 1000.0)
        history.append([_result_row(result) for result in results])
    return {
        "timing": base._timing_summary(samples, warmup),
        "models": models,
        "history": history,
        "ignition_times_s": _ignition_times(history, initial_elapsed),
        "boundary": None,
        "conduction_balance_error_j": None,
    }


def _time_native(
    combustion,
    templates,
    topology,
    library,
    log_count,
    steps,
    warmup,
    resident: bool,
):
    models = _clone_models(combustion, templates, log_count)
    cells = _combined_cells(models)
    p = models[0].parameters
    cells_per_log = len(models[0].cells)
    elapsed, cumulative = _model_boundary_arrays(models)
    initial_elapsed = elapsed.tolist()
    conduction_scratch = np.zeros(len(cells), dtype=np.float64)
    heat_capacity_scratch = np.zeros(len(cells), dtype=np.float64)
    step_output = np.zeros(log_count * STEP_OUTPUT_COUNT, dtype=np.float64)
    arrays = None
    import_ms = None
    if resident:
        started = time.perf_counter()
        arrays = _extract_complete_arrays(cells, p.wood_specific_heat_j_kg_k)
        import_ms = (time.perf_counter() - started) * 1000.0
    samples = []
    history = []
    for _ in range(steps):
        started = time.perf_counter()
        if not resident:
            arrays = _extract_complete_arrays(cells, p.wood_specific_heat_j_kg_k)
        _call_native(
            library,
            arrays,
            topology,
            conduction_scratch,
            heat_capacity_scratch,
            elapsed,
            cumulative,
            step_output,
            log_count,
            cells_per_log,
            p,
            models[0]._mass_epsilon_kg,
        )
        if not resident:
            _write_complete_arrays(arrays, cells)
        samples.append((time.perf_counter() - started) * 1000.0)
        history.append(_native_result_rows(step_output, elapsed))
    started = time.perf_counter()
    if resident:
        _write_complete_arrays(arrays, cells)
    _write_model_boundary(elapsed, cumulative, models)
    export_ms = (time.perf_counter() - started) * 1000.0
    return {
        "timing": base._timing_summary(samples, warmup),
        "models": models,
        "history": history,
        "ignition_times_s": _ignition_times(history, initial_elapsed),
        "boundary": (
            {"one_time_import_ms": import_ms, "one_time_export_ms": export_ms}
            if resident
            else None
        ),
        "conduction_balance_error_j": abs(float(np.sum(conduction_scratch))),
    }


def _compare(reference, candidate) -> dict:
    reference_cells = _combined_cells(reference["models"])
    candidate_cells = _combined_cells(candidate["models"])
    max_temperature_error = max(
        abs(left.temperature_k - right.temperature_k)
        for left, right in zip(reference_cells, candidate_cells)
    )
    max_mass_error = max(
        abs(left_value - right_value)
        for left, right in zip(reference_cells, candidate_cells)
        for left_value, right_value in (
            (left.moisture_mass_kg, right.moisture_mass_kg),
            (left.dry_wood_mass_kg, right.dry_wood_mass_kg),
            (left.volatile_potential_kg, right.volatile_potential_kg),
            (left.char_mass_kg, right.char_mass_kg),
            (left.ash_mass_kg, right.ash_mass_kg),
        )
    )
    phase_mismatch = sum(
        left.phase != right.phase
        for left, right in zip(reference_cells, candidate_cells)
    )
    max_cumulative_error = max(
        abs(getattr(left, field) - getattr(right, field))
        for left, right in zip(reference["models"], candidate["models"])
        for field in ("elapsed_seconds", *CUMULATIVE_FIELDS)
    )
    max_step_output_error = max(
        abs(left_value - right_value)
        for left_step, right_step in zip(reference["history"], candidate["history"])
        for left_row, right_row in zip(left_step, right_step)
        for left_value, right_value in zip(left_row, right_row)
    )
    ignition_errors = [
        abs(left - right)
        for left, right in zip(
            reference["ignition_times_s"], candidate["ignition_times_s"]
        )
        if left is not None and right is not None
    ]
    all_ignited = all(
        value is not None
        for value in (
            *reference["ignition_times_s"],
            *candidate["ignition_times_s"],
        )
    )
    max_ignition_error = max(ignition_errors, default=math.inf)
    maximum_mass_balance_error = max(
        abs(model.metrics()["mass_balance_error_kg"])
        for model in candidate["models"]
    )
    within = (
        max_temperature_error <= TEMPERATURE_TOLERANCE_K
        and max_mass_error <= MASS_TOLERANCE_KG
        and phase_mismatch == 0
        and max_cumulative_error <= MASS_TOLERANCE_KG
        and max_step_output_error <= STEP_OUTPUT_TOLERANCE
        and all_ignited
        and max_ignition_error <= IGNITION_TOLERANCE_S
        and maximum_mass_balance_error <= 1.0e-9
    )
    return {
        "maximum_temperature_error_k": max_temperature_error,
        "maximum_cell_mass_error_kg": max_mass_error,
        "phase_mismatch_count": phase_mismatch,
        "maximum_cumulative_error": max_cumulative_error,
        "maximum_step_output_error": max_step_output_error,
        "all_logs_ignited": all_ignited,
        "maximum_ignition_time_error_s": max_ignition_error,
        "maximum_candidate_mass_balance_error_kg": maximum_mass_balance_error,
        "exact_state_sha256_match": _models_sha256(reference["models"])
        == _models_sha256(candidate["models"]),
        "exact_step_history_sha256_match": _history_sha256(reference["history"])
        == _history_sha256(candidate["history"]),
        "within_tolerance": within,
    }


def run_benchmark(dll_path: Path, log_count: int, steps: int, warmup: int, runs: int):
    combustion = base._load_combustion_module()
    templates = {
        "dry": _precondition_template(combustion, "native_complete_dry", 0.12, 300),
        "wet": _precondition_template(combustion, "native_complete_wet", 0.60, 800),
    }
    probe = _clone_models(combustion, templates, log_count)
    topology = conduction._topology_arrays(
        probe[0]._conduction_pairs, log_count, len(probe[0].cells)
    )
    library = base._load_native_kernel(dll_path)
    _configure_complete_kernel(library)
    methods = {
        "python_complete_step": lambda: _time_python(
            combustion, templates, log_count, steps, warmup
        ),
        "native_roundtrip_complete_step": lambda: _time_native(
            combustion,
            templates,
            topology,
            library,
            log_count,
            steps,
            warmup,
            False,
        ),
        "native_resident_complete_step": lambda: _time_native(
            combustion,
            templates,
            topology,
            library,
            log_count,
            steps,
            warmup,
            True,
        ),
    }
    orders = [
        list(methods),
        ["native_roundtrip_complete_step", "native_resident_complete_step", "python_complete_step"],
        ["native_resident_complete_step", "python_complete_step", "native_roundtrip_complete_step"],
    ]
    raw_runs = []
    for run_index in range(runs):
        gc.collect()
        outcomes = {}
        for name in orders[run_index % len(orders)]:
            outcomes[name] = methods[name]()
        reference = outcomes["python_complete_step"]
        comparisons = {
            name: _compare(reference, outcomes[name])
            for name in (
                "native_roundtrip_complete_step",
                "native_resident_complete_step",
            )
        }
        if not all(value["within_tolerance"] for value in comparisons.values()):
            output = {
                name: value for name, value in comparisons.items()
            }
            raise RuntimeError(f"Native complete step exceeded tolerance: {output}")
        raw_runs.append(
            {
                "run": run_index + 1,
                "order": orders[run_index % len(orders)],
                "methods": {
                    name: {
                        "timing": outcome["timing"],
                        "boundary": outcome["boundary"],
                        "conduction_balance_error_j": outcome[
                            "conduction_balance_error_j"
                        ],
                        "final_state_sha256": _models_sha256(outcome["models"]),
                        "step_history_sha256": _history_sha256(outcome["history"]),
                        "ignition_times_s": outcome["ignition_times_s"],
                    }
                    for name, outcome in outcomes.items()
                },
                "comparisons": comparisons,
            }
        )
    return {
        "schema_version": 1,
        "phase": "phase6aw",
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
            "cell_count_per_log": len(probe[0].cells),
            "combined_cell_count": sum(len(model.cells) for model in probe),
            "combined_conduction_pair_count": topology["first_cell"].size,
            "steps_per_run": steps,
            "warmup_steps_excluded": warmup,
            "runs": runs,
            "dt_seconds": base.DT_SECONDS,
            "heat_flux_w_m2": base.HEAT_FLUX_W_M2,
            "dry_initial_elapsed_seconds": templates["dry"]["elapsed_seconds"],
            "wet_initial_elapsed_seconds": templates["wet"]["elapsed_seconds"],
            "balanced_method_order": True,
        },
        "boundary": {
            "included": [
                "conduction",
                "sensible_heat",
                "evaporation",
                "piecewise_linear_pyrolysis",
                "char_oxidation",
                "state_finalize",
                "step_result",
                "cumulative_products",
            ],
            "excluded": [
                "arrhenius_pyrolysis",
                "secondary_tar_cracking",
                "runtime_metrics",
                "Flow/USD/rendering/PhysX",
            ],
            "production_model_changed": False,
            "python_json_schema_changed": False,
        },
        "tolerances": {
            "maximum_temperature_error_k": TEMPERATURE_TOLERANCE_K,
            "maximum_mass_error_kg": MASS_TOLERANCE_KG,
            "maximum_step_output_error": STEP_OUTPUT_TOLERANCE,
            "maximum_ignition_time_error_s": IGNITION_TOLERANCE_S,
            "maximum_mass_balance_error_kg": 1.0e-9,
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

