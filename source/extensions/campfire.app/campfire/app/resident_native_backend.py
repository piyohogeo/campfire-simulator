"""Opt-in resident native wood backend using the audited Phase 6AU C ABI."""

from __future__ import annotations

import ctypes
import math
import time
from dataclasses import dataclass
from pathlib import Path

from .combustion import CombustionStepResult
from .resident_snapshot import (
    RESIDENT_PUBLISHED_FIELD_NAMES,
    ResidentNativeSnapshotProducer,
    ResidentPublishedSnapshot,
)


NATIVE_ABI_VERSION = 1
SIGMA_W_M2_K4 = 5.670374419e-8
REFERENCE_FUEL_RATE_KG_S = 0.02
CHAR_STRENGTH_FACTOR = 0.12
STEP_OUTPUT_COUNT = 9
CUMULATIVE_FIELDS = (
    "emitted_water_kg",
    "emitted_pyrolysis_gas_kg",
    "emitted_char_gas_kg",
    "emitted_primary_gas_kg",
    "emitted_tar_kg",
    "produced_primary_char_kg",
    "converted_secondary_tar_kg",
)
PHASE_TO_CODE = {
    "WET_WOOD": 0,
    "DRY_WOOD": 1,
    "PYROLYZING": 2,
    "CHAR": 3,
    "ASH": 4,
    "DEPLETED": 5,
}
CODE_TO_PHASE = {value: key for key, value in PHASE_TO_CODE.items()}


def _require_numpy():
    try:
        import numpy
    except ImportError as error:
        raise RuntimeError("Resident native backend requires NumPy") from error
    return numpy


@dataclass(frozen=True)
class ResidentNativeStep:
    results: tuple[CombustionStepResult, ...]
    snapshot: ResidentPublishedSnapshot


class ResidentNativeBackend:
    """Own resident SoA state until an explicit export or shutdown."""

    def __init__(
        self,
        models,
        library_path,
        *,
        dt_seconds: float,
        heat_flux_w_m2: float,
    ):
        self._np = _require_numpy()
        self._models = tuple(models)
        if not self._models:
            raise ValueError("Resident native backend requires at least one model")
        if not math.isfinite(dt_seconds) or dt_seconds <= 0.0:
            raise ValueError("Resident native dt must be positive and finite")
        if not math.isfinite(heat_flux_w_m2) or heat_flux_w_m2 < 0.0:
            raise ValueError("Resident native heat flux must be finite and non-negative")
        self._dt_seconds = float(dt_seconds)
        self._heat_flux_w_m2 = float(heat_flux_w_m2)
        self._validate_models()
        self._library_path = Path(library_path).resolve()
        if not self._library_path.is_file():
            raise ValueError(f"Resident native library does not exist: {self._library_path}")
        self._library = ctypes.CDLL(str(self._library_path))
        self._configure_library()
        self._cells_per_log = len(self._models[0].cells)
        self._cells = tuple(cell for model in self._models for cell in model.cells)
        self._arrays = self._extract_arrays()
        self._topology = self._build_topology()
        self._elapsed = self._np.fromiter(
            (model.elapsed_seconds for model in self._models),
            dtype=self._np.float64,
            count=len(self._models),
        )
        self._cumulative = self._np.asarray(
            [
                [getattr(model, field) for field in CUMULATIVE_FIELDS]
                for model in self._models
            ],
            dtype=self._np.float64,
        ).reshape(-1)
        self._conduction_scratch = self._np.zeros(len(self._cells), dtype=self._np.float64)
        self._heat_capacity_scratch = self._np.zeros(len(self._cells), dtype=self._np.float64)
        self._step_output = self._np.zeros(
            len(self._models) * STEP_OUTPUT_COUNT, dtype=self._np.float64
        )
        self._published_output = self._np.zeros(
            len(self._models) * len(RESIDENT_PUBLISHED_FIELD_NAMES),
            dtype=self._np.float64,
        )
        self._initial_mass = self._np.asarray(
            [model.initial_mass_kg for model in self._models], dtype=self._np.float64
        )
        self._initial_section_mass = self._np.asarray(
            [
                math.pi
                * model.spec.radius_m**2
                * (model.spec.length_m / model.spec.axial_cells)
                * model.parameters.dry_wood_density_kg_m3
                for model in self._models
            ],
            dtype=self._np.float64,
        )
        self._snapshot_producer = ResidentNativeSnapshotProducer(
            tuple(model.spec.log_id for model in self._models)
        )
        self._revision = 0
        self._tick = -1
        self._step_count = 0
        self._export_count = 0
        self._closed = False

    @property
    def models(self):
        return self._models

    @property
    def revision(self):
        return self._revision

    @property
    def published_output(self):
        view = memoryview(self._published_output)
        return view.toreadonly()

    def _validate_models(self):
        reference = self._models[0]
        reference_shape = (
            reference.spec.radius_m,
            reference.spec.length_m,
            reference.spec.axial_cells,
            reference.spec.circumferential_cells,
            reference.spec.radial_cells,
        )
        reference_pairs = reference._conduction_pairs
        for model in self._models:
            shape = (
                model.spec.radius_m,
                model.spec.length_m,
                model.spec.axial_cells,
                model.spec.circumferential_cells,
                model.spec.radial_cells,
            )
            if shape != reference_shape or len(model.cells) != len(reference.cells):
                raise ValueError("Resident native backend requires homogeneous log grids")
            if model.parameters != reference.parameters:
                raise ValueError("Resident native backend requires common model parameters")
            if model._conduction_pairs != reference_pairs:
                raise ValueError("Resident native backend requires common conduction topology")
            if model.parameters.pyrolysis_rate_model != "piecewise_linear":
                raise ValueError("Resident native backend currently requires piecewise pyrolysis")
            if model.parameters.secondary_tar_cracking_enabled:
                raise ValueError("Piecewise resident backend does not support secondary tar cracking")

    def _configure_library(self):
        double_pointer = ctypes.POINTER(ctypes.c_double)
        uint_pointer = ctypes.POINTER(ctypes.c_uint32)
        int_pointer = ctypes.POINTER(ctypes.c_int32)
        self._library.campfire_native_abi_version.argtypes = []
        self._library.campfire_native_abi_version.restype = ctypes.c_int32
        self._library.campfire_native_msvc_version.argtypes = []
        self._library.campfire_native_msvc_version.restype = ctypes.c_int32
        self._library.campfire_native_msvc_full_version.argtypes = []
        self._library.campfire_native_msvc_full_version.restype = ctypes.c_int64
        if self._library.campfire_native_abi_version() != NATIVE_ABI_VERSION:
            raise RuntimeError("Unsupported resident native ABI")
        self._library.campfire_native_piecewise_complete_step.argtypes = (
            [ctypes.c_size_t]
            + [double_pointer] * 10
            + [int_pointer, ctypes.c_size_t]
            + [uint_pointer] * 2
            + [double_pointer] * 3
            + [ctypes.c_size_t] * 2
            + [double_pointer] * 3
            + [ctypes.c_double] * 24
        )
        self._library.campfire_native_piecewise_complete_step.restype = ctypes.c_int32
        self._library.campfire_native_publish_outputs.argtypes = (
            [ctypes.c_size_t]
            + [double_pointer] * 6
            + [ctypes.c_size_t] * 3
            + [double_pointer] * 4
            + [ctypes.c_double] * 4
        )
        self._library.campfire_native_publish_outputs.restype = ctypes.c_int32

    def _extract_arrays(self):
        np = self._np
        default_heat = self._models[0].parameters.wood_specific_heat_j_kg_k
        fields = {
            "temperature_k": (cell.temperature_k for cell in self._cells),
            "moisture_mass_kg": (cell.moisture_mass_kg for cell in self._cells),
            "dry_wood_mass_kg": (cell.dry_wood_mass_kg for cell in self._cells),
            "volatile_potential_kg": (
                cell.volatile_potential_kg for cell in self._cells
            ),
            "char_mass_kg": (cell.char_mass_kg for cell in self._cells),
            "ash_mass_kg": (cell.ash_mass_kg for cell in self._cells),
            "oxygen_factor": (cell.oxygen_factor for cell in self._cells),
            "external_area_m2": (cell.external_area_m2 for cell in self._cells),
            "surface_exposure": (cell.surface_exposure for cell in self._cells),
            "dry_specific_heat_j_kg_k": (
                cell.dry_wood_specific_heat_j_kg_k
                if cell.dry_wood_specific_heat_j_kg_k is not None
                else default_heat
                for cell in self._cells
            ),
        }
        arrays = {
            name: np.fromiter(values, dtype=np.float64, count=len(self._cells))
            for name, values in fields.items()
        }
        arrays["phase_code"] = np.fromiter(
            (PHASE_TO_CODE[cell.phase] for cell in self._cells),
            dtype=np.int32,
            count=len(self._cells),
        )
        return arrays

    def _build_topology(self):
        np = self._np
        pairs = self._models[0]._conduction_pairs
        pair_count = len(pairs) * len(self._models)
        first = np.empty(pair_count, dtype=np.uint32)
        second = np.empty(pair_count, dtype=np.uint32)
        conductance = np.empty(pair_count, dtype=np.float64)
        target = 0
        for log_index in range(len(self._models)):
            offset = log_index * len(self._models[0].cells)
            for local_first, local_second, value in pairs:
                first[target] = local_first + offset
                second[target] = local_second + offset
                conductance[target] = value
                target += 1
        return {
            "first_cell": first,
            "second_cell": second,
            "conductance_w_k": conductance,
        }

    def _checkpoint(self):
        return {
            "arrays": {name: values.copy() for name, values in self._arrays.items()},
            "elapsed": self._elapsed.copy(),
            "cumulative": self._cumulative.copy(),
            "step_output": self._step_output.copy(),
            "published_output": self._published_output.copy(),
            "revision": self._revision,
            "tick": self._tick,
            "step_count": self._step_count,
        }

    def _restore(self, checkpoint):
        for name, values in checkpoint["arrays"].items():
            self._arrays[name][:] = values
        self._elapsed[:] = checkpoint["elapsed"]
        self._cumulative[:] = checkpoint["cumulative"]
        self._step_output[:] = checkpoint["step_output"]
        self._published_output[:] = checkpoint["published_output"]
        self._revision = checkpoint["revision"]
        self._tick = checkpoint["tick"]
        self._step_count = checkpoint["step_count"]

    def _require_open(self):
        if self._closed:
            raise RuntimeError("Resident native backend is closed")

    def _call_step(self):
        p = self._models[0].parameters
        dp = ctypes.POINTER(ctypes.c_double)
        up = ctypes.POINTER(ctypes.c_uint32)
        result = self._library.campfire_native_piecewise_complete_step(
            self._arrays["temperature_k"].size,
            self._arrays["temperature_k"].ctypes.data_as(dp),
            self._arrays["moisture_mass_kg"].ctypes.data_as(dp),
            self._arrays["dry_wood_mass_kg"].ctypes.data_as(dp),
            self._arrays["volatile_potential_kg"].ctypes.data_as(dp),
            self._arrays["char_mass_kg"].ctypes.data_as(dp),
            self._arrays["ash_mass_kg"].ctypes.data_as(dp),
            self._arrays["oxygen_factor"].ctypes.data_as(dp),
            self._arrays["external_area_m2"].ctypes.data_as(dp),
            self._arrays["surface_exposure"].ctypes.data_as(dp),
            self._arrays["dry_specific_heat_j_kg_k"].ctypes.data_as(dp),
            self._arrays["phase_code"].ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            self._topology["first_cell"].size,
            self._topology["first_cell"].ctypes.data_as(up),
            self._topology["second_cell"].ctypes.data_as(up),
            self._topology["conductance_w_k"].ctypes.data_as(dp),
            self._conduction_scratch.ctypes.data_as(dp),
            self._heat_capacity_scratch.ctypes.data_as(dp),
            len(self._models),
            self._cells_per_log,
            self._elapsed.ctypes.data_as(dp),
            self._cumulative.ctypes.data_as(dp),
            self._step_output.ctypes.data_as(dp),
            self._dt_seconds,
            self._heat_flux_w_m2,
            p.radiant_absorptivity,
            p.convection_w_m2_k,
            p.emissivity,
            SIGMA_W_M2_K4,
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
            self._models[0]._mass_epsilon_kg,
        )
        if result != 0:
            raise RuntimeError(f"Native complete-step kernel failed with code {result}")

    def _call_publish(self):
        dp = ctypes.POINTER(ctypes.c_double)
        spec = self._models[0].spec
        result = self._library.campfire_native_publish_outputs(
            self._arrays["temperature_k"].size,
            self._arrays["temperature_k"].ctypes.data_as(dp),
            self._arrays["moisture_mass_kg"].ctypes.data_as(dp),
            self._arrays["dry_wood_mass_kg"].ctypes.data_as(dp),
            self._arrays["char_mass_kg"].ctypes.data_as(dp),
            self._arrays["ash_mass_kg"].ctypes.data_as(dp),
            self._arrays["surface_exposure"].ctypes.data_as(dp),
            len(self._models),
            self._cells_per_log,
            spec.circumferential_cells * spec.radial_cells,
            self._initial_mass.ctypes.data_as(dp),
            self._initial_section_mass.ctypes.data_as(dp),
            self._step_output.ctypes.data_as(dp),
            self._published_output.ctypes.data_as(dp),
            self._dt_seconds,
            self._models[0].parameters.ambient_temperature_k,
            REFERENCE_FUEL_RATE_KG_S,
            CHAR_STRENGTH_FACTOR,
        )
        if result != 0:
            raise RuntimeError(f"Native publish kernel failed with code {result}")

    def _step_results(self):
        matrix = self._step_output.reshape((len(self._models), STEP_OUTPUT_COUNT))
        results = []
        for index, values in enumerate(matrix):
            evaporated = float(values[0])
            pyrolysis = float(values[1])
            char_gas = float(values[2])
            primary_gas = float(values[4])
            primary_tar = float(values[5])
            primary_char = float(values[6])
            secondary = float(values[7])
            uncracked = float(values[8])
            results.append(
                CombustionStepResult(
                    elapsed_seconds=float(self._elapsed[index]),
                    evaporated_water_kg=evaporated,
                    pyrolysis_gas_kg=pyrolysis,
                    char_oxidation_gas_kg=char_gas,
                    evaporated_water_rate_kg_s=evaporated / self._dt_seconds,
                    pyrolysis_gas_rate_kg_s=pyrolysis / self._dt_seconds,
                    char_oxidation_gas_rate_kg_s=char_gas / self._dt_seconds,
                    external_heat_j=float(values[3]),
                    primary_gas_kg=primary_gas,
                    primary_tar_kg=primary_tar,
                    primary_char_kg=primary_char,
                    primary_gas_rate_kg_s=primary_gas / self._dt_seconds,
                    primary_tar_rate_kg_s=primary_tar / self._dt_seconds,
                    primary_char_rate_kg_s=primary_char / self._dt_seconds,
                    secondary_tar_cracked_kg=secondary,
                    secondary_gas_rate_kg_s=secondary / self._dt_seconds,
                    uncracked_tar_kg=uncracked,
                    uncracked_tar_rate_kg_s=uncracked / self._dt_seconds,
                )
            )
        return tuple(results)

    def step(self, *, tick: int, inject_failure_after_native: bool = False):
        self._require_open()
        if tick < 0 or tick <= self._tick:
            raise ValueError("Resident native tick must increase monotonically")
        checkpoint = self._checkpoint()
        try:
            self._call_step()
            if inject_failure_after_native:
                raise RuntimeError("Injected resident post-native failure")
            self._call_publish()
            revision = self._revision + 1
            snapshot = self._snapshot_producer.build(
                revision=revision,
                tick=tick,
                values=self._published_output,
            )
            results = self._step_results()
            self._revision = revision
            self._tick = tick
            self._step_count += 1
            return ResidentNativeStep(results=results, snapshot=snapshot)
        except Exception:
            self._restore(checkpoint)
            raise

    def export_all(self):
        self._require_open()
        started = time.perf_counter()
        for index, cell in enumerate(self._cells):
            cell.temperature_k = float(self._arrays["temperature_k"][index])
            cell.moisture_mass_kg = float(self._arrays["moisture_mass_kg"][index])
            cell.dry_wood_mass_kg = float(self._arrays["dry_wood_mass_kg"][index])
            cell.volatile_potential_kg = float(
                self._arrays["volatile_potential_kg"][index]
            )
            cell.char_mass_kg = float(self._arrays["char_mass_kg"][index])
            cell.ash_mass_kg = float(self._arrays["ash_mass_kg"][index])
            cell.phase = CODE_TO_PHASE[int(self._arrays["phase_code"][index])]
        cumulative = self._cumulative.reshape((len(self._models), len(CUMULATIVE_FIELDS)))
        for model_index, model in enumerate(self._models):
            model.elapsed_seconds = float(self._elapsed[model_index])
            for field_index, field in enumerate(CUMULATIVE_FIELDS):
                setattr(model, field, float(cumulative[model_index, field_index]))
        self._export_count += 1
        return (time.perf_counter() - started) * 1000.0

    def status(self):
        return {
            "active": not self._closed,
            "revision": self._revision,
            "tick": self._tick,
            "step_count": self._step_count,
            "export_count": self._export_count,
            "log_count": len(self._models),
            "cells_per_log": self._cells_per_log,
            "library_path": str(self._library_path),
            "abi_version": self._library.campfire_native_abi_version(),
            "msvc_version": self._library.campfire_native_msvc_version(),
            "msvc_full_version": self._library.campfire_native_msvc_full_version(),
        }

    def close(self):
        if self._closed:
            return {**self.status(), "already_closed": True, "export_ms": 0.0}
        export_ms = self.export_all()
        self._closed = True
        return {**self.status(), "already_closed": False, "export_ms": export_ms}
