"""Compare the Phase 6AX resident native parallel-Arrhenius complete step."""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIECEWISE_BENCHMARK = ROOT / "scripts" / "benchmark_native_piecewise_complete_step.py"


def _load_piecewise_benchmark():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6aw_benchmark_base", PIECEWISE_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AW benchmark: {PIECEWISE_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


piecewise = _load_piecewise_benchmark()
base = piecewise.base
np = piecewise.np
GAS_CONSTANT_J_MOL_K = 8.31446261815324
SECONDARY_TAR_BRANCH_SEED_K = 800.0


def _arrhenius_parameters(combustion):
    return dataclasses.replace(
        combustion.WoodModelParameters(),
        pyrolysis_rate_model="arrhenius_parallel_first_order",
        pyrolysis_parallel_common_scale=1.0,
        secondary_tar_cracking_enabled=True,
    )


def _precondition_template(combustion, name: str, moisture: float, steps: int):
    model = combustion.create_cylindrical_wood_model(
        name,
        0.16,
        1.80,
        moisture_ratio_dry_basis=moisture,
        parameters=_arrhenius_parameters(combustion),
    )
    model.use_slotted_cell_storage()
    for _ in range(steps):
        model.step(base.DT_SECONDS, base.HEAT_FLUX_W_M2, **piecewise.STEP_ARGUMENTS)
    seeded_cell = next(
        cell
        for cell in model.cells
        if cell.external_area_m2 > 0.0 and cell.surface_exposure > 0.0
    )
    seeded_cell.temperature_k = max(
        seeded_cell.temperature_k, SECONDARY_TAR_BRANCH_SEED_K
    )
    if model.parameters.pyrolysis_rate_model != "arrhenius_parallel_first_order":
        raise RuntimeError("Phase 6AX requires parallel first-order Arrhenius pyrolysis")
    if not model.parameters.secondary_tar_cracking_enabled:
        raise RuntimeError("Phase 6AX requires the bounded secondary-tar split")
    return model.to_dict()


def _configure_arrhenius_kernel(library):
    double_pointer = ctypes.POINTER(ctypes.c_double)
    uint_pointer = ctypes.POINTER(ctypes.c_uint32)
    int_pointer = ctypes.POINTER(ctypes.c_int32)
    library.campfire_native_arrhenius_complete_step.argtypes = (
        [ctypes.c_size_t]
        + [double_pointer] * 10
        + [int_pointer, ctypes.c_size_t]
        + [uint_pointer] * 2
        + [double_pointer] * 3
        + [ctypes.c_size_t] * 2
        + [double_pointer] * 3
        + [ctypes.c_double] * 34
    )
    library.campfire_native_arrhenius_complete_step.restype = ctypes.c_int32


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
    result = library.campfire_native_arrhenius_complete_step(
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
        p.pyrolysis_heat_j_kg,
        GAS_CONSTANT_J_MOL_K,
        p.pyrolysis_parallel_common_scale,
        p.pyrolysis_parallel_gas_preexponential_s,
        p.pyrolysis_parallel_gas_activation_energy_j_mol,
        p.pyrolysis_parallel_tar_preexponential_s,
        p.pyrolysis_parallel_tar_activation_energy_j_mol,
        p.pyrolysis_parallel_char_preexponential_s,
        p.pyrolysis_parallel_char_activation_energy_j_mol,
        p.secondary_tar_cracking_residence_time_s,
        p.secondary_tar_cracking_preexponential_s,
        p.secondary_tar_cracking_activation_energy_j_mol,
        p.secondary_tar_cracking_min_temperature_k,
        p.secondary_tar_cracking_max_temperature_k,
        p.char_oxidation_start_temperature_k,
        p.char_oxidation_max_fraction_s,
        p.char_ash_yield,
        p.char_oxidation_heat_j_kg,
        mass_epsilon_kg,
    )
    if result != 0:
        raise RuntimeError(f"Native Arrhenius complete-step kernel failed with code {result}")


def _combined_source_sha256() -> str:
    digest = hashlib.sha256()
    for path in (
        ROOT / "native" / "phase6au" / "wood_cell_kernel.cpp",
        ROOT / "native" / "phase6au" / "arrhenius_complete_step.inl",
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_benchmark(dll_path: Path, log_count: int, steps: int, warmup: int, runs: int):
    original_configure = piecewise._configure_complete_kernel
    original_precondition = piecewise._precondition_template
    original_call = piecewise._call_native
    try:
        piecewise._configure_complete_kernel = _configure_arrhenius_kernel
        piecewise._precondition_template = _precondition_template
        piecewise._call_native = _call_native
        report = piecewise.run_benchmark(dll_path, log_count, steps, warmup, runs)
    finally:
        piecewise._configure_complete_kernel = original_configure
        piecewise._precondition_template = original_precondition
        piecewise._call_native = original_call

    report["phase"] = "phase6ax"
    report["native_toolchain"]["source_sha256"] = _combined_source_sha256()
    report["measurement"]["scope"] = (
        "parallel Arrhenius complete wood step + bounded secondary tar + outputs"
    )
    report["measurement"]["secondary_tar_branch_seed"] = {
        "temperature_k": SECONDARY_TAR_BRANCH_SEED_K,
        "seeded_surface_cells_per_log": 1,
        "purpose": "software branch coverage only; not a physical initial condition",
    }
    report["boundary"]["included"] = [
        "conduction",
        "sensible_heat",
        "evaporation",
        "parallel_arrhenius_pyrolysis",
        "bounded_secondary_tar_cracking",
        "char_oxidation",
        "state_finalize",
        "step_result",
        "cumulative_products",
    ]
    report["boundary"]["excluded"] = [
        "single_path_arrhenius_pyrolysis",
        "runtime_metrics",
        "public_mutable_state_fallback",
        "app_scheduler_contract",
        "Flow/USD/rendering/PhysX",
    ]
    parameters = _arrhenius_parameters(base._load_combustion_module())
    report["kinetics"] = {
        "gas_constant_j_mol_k": GAS_CONSTANT_J_MOL_K,
        "parallel_common_scale": parameters.pyrolysis_parallel_common_scale,
        "secondary_residence_time_s": parameters.secondary_tar_cracking_residence_time_s,
        "secondary_temperature_range_k": [
            parameters.secondary_tar_cracking_min_temperature_k,
            parameters.secondary_tar_cracking_max_temperature_k,
        ],
        "source_pathways": ["gas", "tar", "char"],
    }
    combustion = base._load_combustion_module()
    probe_template = _precondition_template(
        combustion, "native_arrhenius_product_probe", 0.12, 300
    )
    probe_model = combustion.WoodThermalModel.from_dict(probe_template)
    probe_model.use_slotted_cell_storage()
    product_totals = {
        "primary_gas_kg": 0.0,
        "primary_tar_kg": 0.0,
        "primary_char_kg": 0.0,
        "secondary_tar_cracked_kg": 0.0,
        "uncracked_tar_kg": 0.0,
    }
    for _ in range(steps):
        step_result = probe_model.step(
            base.DT_SECONDS, base.HEAT_FLUX_W_M2, **piecewise.STEP_ARGUMENTS
        )
        for field in product_totals:
            product_totals[field] += float(getattr(step_result, field))
    report["reaction_evidence"] = product_totals
    return report


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
        arguments.dll,
        arguments.logs,
        arguments.steps,
        arguments.warmup,
        arguments.runs,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
