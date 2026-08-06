"""Flow-independent, mass-conserving wood thermal model for Phase 3.

The coefficients below are explicit SI-unit hypotheses for the MVP.  They are
not calibrated material data.  Keeping them in one immutable parameter object
makes later comparison against measured wood straightforward.
"""

from __future__ import annotations

import json
import math
import time
from typing import TYPE_CHECKING
from dataclasses import asdict, dataclass

if TYPE_CHECKING:
    from pxr import Usd


MODEL_VERSION = 1
STATE_ATTRIBUTE = "campfire:combustionStateJson"
MODEL_VERSION_ATTRIBUTE = "campfire:combustionModelVersion"
UNIVERSAL_GAS_CONSTANT_J_MOL_K = 8.31446261815324
CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL = "constant"
USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL = (
    "usda_fpl_normalized_linear_280_420_k"
)
USDA_FPL_DRY_WOOD_CP_INTERCEPT_J_KG_K = 103.1
USDA_FPL_DRY_WOOD_CP_SLOPE_J_KG_K2 = 3.867
USDA_FPL_DRY_WOOD_CP_MIN_TEMPERATURE_K = 280.0
USDA_FPL_DRY_WOOD_CP_MAX_TEMPERATURE_K = 420.0
USDA_FPL_DRY_WOOD_CP_REFERENCE_TEMPERATURE_K = 293.15

WET_WOOD = "WET_WOOD"
DRY_WOOD = "DRY_WOOD"
PYROLYZING = "PYROLYZING"
CHAR = "CHAR"
ASH = "ASH"
DEPLETED = "DEPLETED"
_PHASE_NAMES = (WET_WOOD, DRY_WOOD, PYROLYZING, CHAR, ASH, DEPLETED)
_PHASE_INDEX = {name: index for index, name in enumerate(_PHASE_NAMES)}
PYTHON_ARRAY_BACKEND = "python"
NUMPY_ARRAY_BACKEND = "numpy"
_NUMPY = None


def _require_numpy():
    global _NUMPY
    if _NUMPY is None:
        try:
            import numpy
        except ImportError as exc:
            raise RuntimeError(
                "The NumPy wood-step backend requires the numpy package"
            ) from exc
        _NUMPY = numpy
    return _NUMPY


@dataclass(frozen=True)
class WoodModelParameters:
    """Uncalibrated Phase 3 coefficients, all in SI units."""

    dry_wood_density_kg_m3: float = 520.0
    wood_specific_heat_j_kg_k: float = 1700.0
    water_specific_heat_j_kg_k: float = 4180.0
    char_specific_heat_j_kg_k: float = 1000.0
    ash_specific_heat_j_kg_k: float = 800.0
    conductivity_axial_w_m_k: float = 0.25
    conductivity_radial_w_m_k: float = 0.12
    convection_w_m2_k: float = 12.0
    emissivity: float = 0.82
    radiant_absorptivity: float = 1.0
    ambient_temperature_k: float = 293.15
    evaporation_start_temperature_k: float = 353.15
    water_latent_heat_j_kg: float = 2_256_000.0
    evaporation_max_fraction_s: float = 0.08
    pyrolysis_start_temperature_k: float = 573.15
    pyrolysis_full_temperature_k: float = 773.15
    pyrolysis_max_fraction_s: float = 0.025
    pyrolysis_rate_model: str = "piecewise_linear"
    pyrolysis_arrhenius_preexponential_s: float = 738_333.3333333334
    pyrolysis_arrhenius_activation_energy_j_mol: float = 106_500.0
    pyrolysis_arrhenius_reaction_order: float = 1.0
    pyrolysis_arrhenius_source_label: str = "Thurner-Mann char branch"
    pyrolysis_parallel_common_scale: float = 1.0
    pyrolysis_parallel_gas_preexponential_s: float = 14_350.0
    pyrolysis_parallel_gas_activation_energy_j_mol: float = 88_600.0
    pyrolysis_parallel_tar_preexponential_s: float = 4_116_666.6666666665
    pyrolysis_parallel_tar_activation_energy_j_mol: float = 112_700.0
    pyrolysis_parallel_char_preexponential_s: float = 738_333.3333333334
    pyrolysis_parallel_char_activation_energy_j_mol: float = 106_500.0
    pyrolysis_parallel_source_label: str = "Thurner-Mann three parallel branches"
    secondary_tar_cracking_enabled: bool = False
    secondary_tar_cracking_residence_time_s: float = 1.0
    secondary_tar_cracking_preexponential_s: float = 4_280_000.0
    secondary_tar_cracking_activation_energy_j_mol: float = 108_000.0
    secondary_tar_cracking_min_temperature_k: float = 773.0
    secondary_tar_cracking_max_temperature_k: float = 1073.0
    secondary_tar_cracking_source_label: str = "Di Blasi Model III tar-to-gas branch"
    pyrolysis_heat_j_kg: float = 300_000.0
    pyrolysis_char_yield: float = 0.22
    char_oxidation_start_temperature_k: float = 673.15
    char_oxidation_max_fraction_s: float = 0.0005
    char_ash_yield: float = 0.08
    char_oxidation_heat_j_kg: float = 15_000_000.0
    max_temperature_k: float = 1600.0


@dataclass
class WoodCellState:
    temperature_k: float
    moisture_mass_kg: float
    dry_wood_mass_kg: float
    volatile_potential_kg: float
    char_mass_kg: float
    ash_mass_kg: float
    oxygen_factor: float
    surface_exposure: float
    phase: str
    volume_m3: float
    external_area_m2: float
    dry_wood_specific_heat_j_kg_k: float | None = None
    dry_wood_specific_heat_model: str = CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL

    @property
    def current_mass_kg(self) -> float:
        return (
            self.moisture_mass_kg
            + self.dry_wood_mass_kg
            + self.char_mass_kg
            + self.ash_mass_kg
        )


@dataclass(frozen=True)
class WoodGridSpec:
    log_id: str
    radius_m: float
    length_m: float
    axial_cells: int = 24
    circumferential_cells: int = 12
    radial_cells: int = 4

    @property
    def cell_count(self) -> int:
        return self.axial_cells * self.circumferential_cells * self.radial_cells


@dataclass(frozen=True)
class CombustionStepResult:
    elapsed_seconds: float
    evaporated_water_kg: float
    pyrolysis_gas_kg: float
    char_oxidation_gas_kg: float
    evaporated_water_rate_kg_s: float
    pyrolysis_gas_rate_kg_s: float
    char_oxidation_gas_rate_kg_s: float
    external_heat_j: float
    primary_gas_kg: float
    primary_tar_kg: float
    primary_char_kg: float
    primary_gas_rate_kg_s: float
    primary_tar_rate_kg_s: float
    primary_char_rate_kg_s: float
    secondary_tar_cracked_kg: float
    secondary_gas_rate_kg_s: float
    uncracked_tar_kg: float
    uncracked_tar_rate_kg_s: float


@dataclass(frozen=True)
class FlowSourceState:
    fuel: float
    temperature: float
    smoke: float
    pyrolysis_gas_rate_kg_s: float


@dataclass(frozen=True)
class WoodRuntimeTopology:
    """Explicit snapshot of immutable cell relationships for hot-loop reads."""

    cells: tuple[WoodCellState, ...]
    surface_cells: tuple[WoodCellState, ...]
    initial_dry_mass_kg: float


class WoodThermalModel:
    """Structured cylindrical cells fixed in a rigid log's local frame."""

    def __init__(
        self,
        spec: WoodGridSpec,
        cells: list[WoodCellState],
        parameters: WoodModelParameters | None = None,
        elapsed_seconds: float = 0.0,
        emitted_water_kg: float = 0.0,
        emitted_pyrolysis_gas_kg: float = 0.0,
        emitted_char_gas_kg: float = 0.0,
        emitted_primary_gas_kg: float = 0.0,
        emitted_tar_kg: float = 0.0,
        produced_primary_char_kg: float = 0.0,
        converted_secondary_tar_kg: float = 0.0,
        initial_mass_kg: float | None = None,
    ):
        if len(cells) != spec.cell_count:
            raise ValueError(
                f"Cell count {len(cells)} does not match grid {spec.cell_count}"
            )
        self.spec = spec
        self.cells = cells
        self.parameters = parameters or WoodModelParameters()
        self.elapsed_seconds = float(elapsed_seconds)
        self.emitted_water_kg = float(emitted_water_kg)
        self.emitted_pyrolysis_gas_kg = float(emitted_pyrolysis_gas_kg)
        self.emitted_char_gas_kg = float(emitted_char_gas_kg)
        self.emitted_primary_gas_kg = float(emitted_primary_gas_kg)
        self.emitted_tar_kg = float(emitted_tar_kg)
        self.produced_primary_char_kg = float(produced_primary_char_kg)
        self.converted_secondary_tar_kg = float(converted_secondary_tar_kg)
        self.initial_mass_kg = (
            float(initial_mass_kg)
            if initial_mass_kg is not None
            else sum(cell.current_mass_kg for cell in cells)
        )
        self._conduction_pairs = self._build_conduction_pairs()
        self._mass_epsilon_kg = max(self.initial_mass_kg * 1.0e-10, 1.0e-12)

    def _index(self, axial: int, circumferential: int, radial: int) -> int:
        return (
            (axial * self.spec.circumferential_cells + circumferential)
            * self.spec.radial_cells
            + radial
        )

    def _build_conduction_pairs(self) -> list[tuple[int, int, float]]:
        """Return unique cell pairs with thermal conductance in W/K."""

        p = self.parameters
        s = self.spec
        dz = s.length_m / s.axial_cells
        dr = s.radius_m / s.radial_cells
        dtheta = 2.0 * math.pi / s.circumferential_cells
        pairs = []

        for z in range(s.axial_cells):
            for theta in range(s.circumferential_cells):
                for radial in range(s.radial_cells):
                    index = self._index(z, theta, radial)
                    r_inner = radial * dr
                    r_outer = (radial + 1) * dr
                    annular_sector_area = (
                        0.5 * (r_outer**2 - r_inner**2) * dtheta
                    )

                    if z + 1 < s.axial_cells:
                        neighbor = self._index(z + 1, theta, radial)
                        conductance = (
                            p.conductivity_axial_w_m_k
                            * annular_sector_area
                            / dz
                        )
                        pairs.append((index, neighbor, conductance))

                    # Add each periodic circumferential pair once.
                    next_theta = (theta + 1) % s.circumferential_cells
                    neighbor = self._index(z, next_theta, radial)
                    r_mid = max((r_inner + r_outer) * 0.5, dr * 0.5)
                    distance = r_mid * dtheta
                    interface_area = dr * dz
                    conductance = (
                        p.conductivity_radial_w_m_k * interface_area / distance
                    )
                    pairs.append((index, neighbor, conductance))

                    if radial + 1 < s.radial_cells:
                        neighbor = self._index(z, theta, radial + 1)
                        boundary_radius = r_outer
                        interface_area = boundary_radius * dtheta * dz
                        conductance = (
                            p.conductivity_radial_w_m_k * interface_area / dr
                        )
                        pairs.append((index, neighbor, conductance))
        return pairs

    def _dry_wood_specific_heat_j_kg_k(self, cell: WoodCellState) -> float:
        p = self.parameters
        reference_specific_heat_j_kg_k = (
            cell.dry_wood_specific_heat_j_kg_k
            if cell.dry_wood_specific_heat_j_kg_k is not None
            else p.wood_specific_heat_j_kg_k
        )
        if cell.dry_wood_specific_heat_model == CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL:
            if (
                not math.isfinite(reference_specific_heat_j_kg_k)
                or reference_specific_heat_j_kg_k <= 0.0
            ):
                raise ValueError(
                    "reference_specific_heat_j_kg_k must be finite and positive"
                )
            if not math.isfinite(cell.temperature_k) or cell.temperature_k <= 0.0:
                raise ValueError("temperature_k must be finite and positive")
            dry_wood_specific_heat_j_kg_k = reference_specific_heat_j_kg_k
        else:
            dry_wood_specific_heat_j_kg_k = (
                temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                    reference_specific_heat_j_kg_k,
                    cell.temperature_k,
                    cell.dry_wood_specific_heat_model,
                )
            )
        return dry_wood_specific_heat_j_kg_k

    def _heat_capacity_j_k(self, cell: WoodCellState) -> float:
        p = self.parameters
        dry_wood_specific_heat_j_kg_k = self._dry_wood_specific_heat_j_kg_k(cell)
        return max(
            cell.dry_wood_mass_kg * dry_wood_specific_heat_j_kg_k
            + cell.moisture_mass_kg * p.water_specific_heat_j_kg_k
            + cell.char_mass_kg * p.char_specific_heat_j_kg_k
            + cell.ash_mass_kg * p.ash_specific_heat_j_kg_k,
            1.0e-9,
        )

    def _numpy_sensible_heat(
        self,
        dt_seconds: float,
        scalar_heat_flux_w_m2: float | None,
        heat_fluxes: list[float] | None,
        ambient: float,
        conduction_energy_j: list[float],
    ) -> tuple[list[float], float]:
        np = _require_numpy()
        cells = self.cells
        p = self.parameters
        cell_count = len(cells)
        temperature_k = np.fromiter(
            (cell.temperature_k for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        moisture_mass_kg = np.fromiter(
            (cell.moisture_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        dry_wood_mass_kg = np.fromiter(
            (cell.dry_wood_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        char_mass_kg = np.fromiter(
            (cell.char_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        ash_mass_kg = np.fromiter(
            (cell.ash_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        dry_specific_heat_j_kg_k = np.fromiter(
            (self._dry_wood_specific_heat_j_kg_k(cell) for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        heat_capacities_j_k = (
            dry_wood_mass_kg * dry_specific_heat_j_kg_k
            + moisture_mass_kg * p.water_specific_heat_j_kg_k
            + char_mass_kg * p.char_specific_heat_j_kg_k
            + ash_mass_kg * p.ash_specific_heat_j_kg_k
        )
        np.maximum(heat_capacities_j_k, 1.0e-9, out=heat_capacities_j_k)
        area_m2 = np.fromiter(
            (cell.external_area_m2 * cell.surface_exposure for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        if scalar_heat_flux_w_m2 is None:
            heat_flux_w_m2 = np.asarray(heat_fluxes, dtype=np.float64)
        else:
            heat_flux_w_m2 = scalar_heat_flux_w_m2
        external_heat_w = heat_flux_w_m2 * p.radiant_absorptivity * area_m2
        convective_loss_w = (
            p.convection_w_m2_k * area_m2 * (temperature_k - ambient)
        )
        radiation_loss_w = (
            p.emissivity
            * 5.670374419e-8
            * area_m2
            * (np.power(temperature_k, 4) - ambient**4)
        )
        temperature_k += (
            np.asarray(conduction_energy_j, dtype=np.float64)
            + (external_heat_w - convective_loss_w - radiation_loss_w)
            * dt_seconds
        ) / heat_capacities_j_k
        for index, cell in enumerate(cells):
            cell.temperature_k = float(temperature_k[index])

        external_heat_total = 0.0
        for index, cell in enumerate(cells):
            cell_heat_flux_w_m2 = (
                scalar_heat_flux_w_m2
                if scalar_heat_flux_w_m2 is not None
                else heat_fluxes[index]
            )
            external_heat_total += (
                cell_heat_flux_w_m2
                * p.radiant_absorptivity
                * cell.external_area_m2
                * cell.surface_exposure
                * dt_seconds
            )
        return heat_capacities_j_k.tolist(), external_heat_total

    def _numpy_finalize_state(
        self, ambient: float, update_cell_phases: bool
    ) -> None:
        np = _require_numpy()
        cells = self.cells
        cell_count = len(cells)
        temperature_k = np.fromiter(
            (cell.temperature_k for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        moisture_mass_kg = np.fromiter(
            (cell.moisture_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        dry_wood_mass_kg = np.fromiter(
            (cell.dry_wood_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        char_mass_kg = np.fromiter(
            (cell.char_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        ash_mass_kg = np.fromiter(
            (cell.ash_mass_kg for cell in cells),
            dtype=np.float64,
            count=cell_count,
        )
        np.clip(temperature_k, ambient, self.parameters.max_temperature_k, out=temperature_k)
        np.maximum(moisture_mass_kg, 0.0, out=moisture_mass_kg)
        np.maximum(dry_wood_mass_kg, 0.0, out=dry_wood_mass_kg)
        np.maximum(char_mass_kg, 0.0, out=char_mass_kg)
        np.maximum(ash_mass_kg, 0.0, out=ash_mass_kg)

        if update_cell_phases:
            phase_code = np.full(cell_count, 1, dtype=np.int8)
            phase_code[moisture_mass_kg > dry_wood_mass_kg * 0.01] = 0
            phase_code[
                (temperature_k >= self.parameters.pyrolysis_start_temperature_k)
                & (dry_wood_mass_kg > self._mass_epsilon_kg)
            ] = 2
            phase_code[ash_mass_kg > dry_wood_mass_kg + char_mass_kg] = 4
            phase_code[
                (char_mass_kg > dry_wood_mass_kg) & (char_mass_kg > ash_mass_kg)
            ] = 3
            phase_code[
                moisture_mass_kg + dry_wood_mass_kg + char_mass_kg + ash_mass_kg
                <= self._mass_epsilon_kg
            ] = 5
        for index, cell in enumerate(cells):
            cell.temperature_k = float(temperature_k[index])
            cell.moisture_mass_kg = float(moisture_mass_kg[index])
            cell.dry_wood_mass_kg = float(dry_wood_mass_kg[index])
            cell.char_mass_kg = float(char_mass_kg[index])
            cell.ash_mass_kg = float(ash_mass_kg[index])
            if update_cell_phases:
                cell.phase = _PHASE_NAMES[int(phase_code[index])]

    def refresh_cell_phases(self) -> None:
        """Classify every cell from its current authoritative numerical state."""

        mass_epsilon = self._mass_epsilon_kg
        pyrolysis_start_temperature_k = (
            self.parameters.pyrolysis_start_temperature_k
        )
        for cell in self.cells:
            if (
                cell.moisture_mass_kg
                + cell.dry_wood_mass_kg
                + cell.char_mass_kg
                + cell.ash_mass_kg
                <= mass_epsilon
            ):
                cell.phase = DEPLETED
            elif (
                cell.char_mass_kg > cell.dry_wood_mass_kg
                and cell.char_mass_kg > cell.ash_mass_kg
            ):
                cell.phase = CHAR
            elif cell.ash_mass_kg > cell.dry_wood_mass_kg + cell.char_mass_kg:
                cell.phase = ASH
            elif (
                cell.temperature_k >= pyrolysis_start_temperature_k
                and cell.dry_wood_mass_kg > mass_epsilon
            ):
                cell.phase = PYROLYZING
            elif cell.moisture_mass_kg > cell.dry_wood_mass_kg * 0.01:
                cell.phase = WET_WOOD
            else:
                cell.phase = DRY_WOOD

    def step(
        self,
        dt_seconds: float,
        external_heat_flux_w_m2: float | list[float] | tuple[float, ...],
        ambient_temperature_k: float | None = None,
        timing_ms: dict[str, float] | None = None,
        array_backend: str = PYTHON_ARRAY_BACKEND,
        python_surface_boundary_fast_path: bool = True,
        state_diagnostics: dict[str, int] | None = None,
        python_state_clamp_fast_path: bool = True,
        update_cell_phases: bool = True,
    ) -> CombustionStepResult:
        """Advance one explicit SI-unit thermal/reaction step.

        A scalar applies a uniform surface flux.  A cell-sized sequence allows
        later phases to represent a local flame without changing the
        authoritative cell state or reaction accounting.
        """

        timing_enabled = timing_ms is not None
        segment_started = time.perf_counter() if timing_enabled else 0.0
        if array_backend not in (PYTHON_ARRAY_BACKEND, NUMPY_ARRAY_BACKEND):
            raise ValueError(f"Unsupported wood-step array backend: {array_backend}")
        if state_diagnostics is not None and array_backend != PYTHON_ARRAY_BACKEND:
            raise ValueError("Wood state diagnostics require the Python backend")
        if state_diagnostics is not None and not update_cell_phases:
            raise ValueError("Wood state diagnostics require cell phase updates")
        if not math.isfinite(dt_seconds) or dt_seconds <= 0.0:
            raise ValueError("dt_seconds must be finite and positive")
        scalar_heat_flux_w_m2 = None
        if isinstance(external_heat_flux_w_m2, (int, float)):
            scalar_heat_flux_w_m2 = float(external_heat_flux_w_m2)
            if (
                not math.isfinite(scalar_heat_flux_w_m2)
                or scalar_heat_flux_w_m2 < 0.0
            ):
                raise ValueError("External heat flux must be finite and non-negative")
            heat_fluxes = None
        else:
            heat_fluxes = [float(value) for value in external_heat_flux_w_m2]
            if len(heat_fluxes) != len(self.cells):
                raise ValueError("Cell heat-flux sequence must match the cell count")
        if heat_fluxes is not None and any(
            not math.isfinite(value) or value < 0.0 for value in heat_fluxes
        ):
            raise ValueError("External heat flux must be finite and non-negative")

        p = self.parameters
        ambient = p.ambient_temperature_k if ambient_temperature_k is None else ambient_temperature_k
        if not math.isfinite(ambient) or ambient <= 0.0:
            raise ValueError("ambient_temperature_k must be finite and positive")
        if timing_enabled:
            timing_ms["input_validation"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        cells = self.cells
        temperatures_k = [cell.temperature_k for cell in cells]
        conduction_energy_j = [0.0] * len(cells)
        for first, second, conductance_w_k in self._conduction_pairs:
            energy_j = (
                conductance_w_k
                * (temperatures_k[second] - temperatures_k[first])
                * dt_seconds
            )
            conduction_energy_j[first] += energy_j
            conduction_energy_j[second] -= energy_j
        if timing_enabled:
            timing_ms["conduction"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        evaporated_total = 0.0
        pyrolysis_gas_total = 0.0
        char_gas_total = 0.0
        primary_gas_total = 0.0
        primary_tar_total = 0.0
        primary_char_total = 0.0
        secondary_tar_cracked_total = 0.0
        uncracked_tar_total = 0.0
        external_heat_total = 0.0
        sigma = 5.670374419e-8

        if array_backend == NUMPY_ARRAY_BACKEND:
            heat_capacities_j_k, external_heat_total = self._numpy_sensible_heat(
                dt_seconds,
                scalar_heat_flux_w_m2,
                heat_fluxes,
                ambient,
                conduction_energy_j,
            )
        else:
            heat_capacities_j_k = [0.0] * len(cells)
            for index, cell in enumerate(cells):
                heat_capacity = self._heat_capacity_j_k(cell)
                heat_capacities_j_k[index] = heat_capacity
                area = cell.external_area_m2 * cell.surface_exposure
                if python_surface_boundary_fast_path and area == 0.0:
                    cell.temperature_k += conduction_energy_j[index] / heat_capacity
                    continue
                heat_flux_w_m2 = (
                    scalar_heat_flux_w_m2
                    if scalar_heat_flux_w_m2 is not None
                    else heat_fluxes[index]
                )
                external_heat_w = heat_flux_w_m2 * p.radiant_absorptivity * area
                convective_loss_w = p.convection_w_m2_k * area * (
                    cell.temperature_k - ambient
                )
                radiation_loss_w = (
                    p.emissivity
                    * sigma
                    * area
                    * (cell.temperature_k**4 - ambient**4)
                )
                external_heat_total += external_heat_w * dt_seconds
                net_energy_j = conduction_energy_j[index] + (
                    external_heat_w - convective_loss_w - radiation_loss_w
                ) * dt_seconds
                cell.temperature_k += net_energy_j / heat_capacity
        if timing_enabled:
            timing_ms["sensible_heat"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        for index, cell in enumerate(cells):
            heat_capacity = heat_capacities_j_k[index]
            if (
                cell.moisture_mass_kg > 0.0
                and cell.temperature_k > p.evaporation_start_temperature_k
            ):
                sensible_excess_j = (
                    cell.temperature_k - p.evaporation_start_temperature_k
                ) * heat_capacity
                energy_limited_kg = sensible_excess_j / p.water_latent_heat_j_kg
                rate_limited_kg = (
                    cell.moisture_mass_kg
                    * p.evaporation_max_fraction_s
                    * dt_seconds
                )
                evaporated_kg = min(
                    cell.moisture_mass_kg, energy_limited_kg, rate_limited_kg
                )
                cell.moisture_mass_kg -= evaporated_kg
                cell.temperature_k -= (
                    evaporated_kg * p.water_latent_heat_j_kg / heat_capacity
                )
                evaporated_total += evaporated_kg
        if timing_enabled:
            timing_ms["evaporation"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        for cell in cells:
            if (
                cell.dry_wood_mass_kg > 0.0
                and (
                    p.pyrolysis_rate_model == "arrhenius_first_order"
                    or p.pyrolysis_rate_model == "arrhenius_parallel_first_order"
                    or cell.temperature_k > p.pyrolysis_start_temperature_k
                )
            ):
                moisture_ratio = cell.moisture_mass_kg / max(
                    cell.dry_wood_mass_kg, 1.0e-12
                )
                dryness_factor = min(1.0, max(0.0, 1.0 - moisture_ratio / 0.10))
                if p.pyrolysis_rate_model == "arrhenius_first_order":
                    rate_constant_s = arrhenius_pyrolysis_rate_constant_s(
                        p, cell.temperature_k
                    )
                    reacted_fraction = 1.0 - math.exp(
                        -rate_constant_s * dryness_factor * dt_seconds
                    )
                    rate_limited_kg = cell.dry_wood_mass_kg * reacted_fraction
                    pathway_fractions = {
                        "gas": 1.0 - p.pyrolysis_char_yield,
                        "tar": 0.0,
                        "char": p.pyrolysis_char_yield,
                    }
                elif p.pyrolysis_rate_model == "arrhenius_parallel_first_order":
                    pathway_rates_s = parallel_arrhenius_rate_constants_s(
                        p, cell.temperature_k
                    )
                    total_rate_s = sum(pathway_rates_s.values())
                    reacted_fraction = 1.0 - math.exp(
                        -total_rate_s * dryness_factor * dt_seconds
                    )
                    rate_limited_kg = cell.dry_wood_mass_kg * reacted_fraction
                    pathway_fractions = {
                        product: rate_s / total_rate_s
                        for product, rate_s in pathway_rates_s.items()
                    }
                elif p.pyrolysis_rate_model == "piecewise_linear":
                    temperature_ramp = min(
                        1.0,
                        max(
                            0.0,
                            (cell.temperature_k - p.pyrolysis_start_temperature_k)
                            / (
                                p.pyrolysis_full_temperature_k
                                - p.pyrolysis_start_temperature_k
                            ),
                        ),
                    )
                    rate_limited_kg = (
                        cell.dry_wood_mass_kg
                        * p.pyrolysis_max_fraction_s
                        * temperature_ramp
                        * dryness_factor
                        * dt_seconds
                    )
                    pathway_fractions = {
                        "gas": 1.0 - p.pyrolysis_char_yield,
                        "tar": 0.0,
                        "char": p.pyrolysis_char_yield,
                    }
                else:
                    raise ValueError(
                        f"Unsupported pyrolysis rate model: {p.pyrolysis_rate_model}"
                    )
                pyrolysis_temperature_k = cell.temperature_k
                heat_capacity = self._heat_capacity_j_k(cell)
                energy_limited_kg = max(
                    0.0,
                    (cell.temperature_k - p.pyrolysis_start_temperature_k)
                    * heat_capacity
                    / p.pyrolysis_heat_j_kg,
                )
                reacted_wood_kg = min(
                    cell.dry_wood_mass_kg, rate_limited_kg, energy_limited_kg
                )
                gas_created_kg = reacted_wood_kg * pathway_fractions["gas"]
                tar_created_kg = reacted_wood_kg * pathway_fractions["tar"]
                char_created_kg = reacted_wood_kg * pathway_fractions["char"]
                volatile_created_kg = gas_created_kg + tar_created_kg
                cell.dry_wood_mass_kg -= reacted_wood_kg
                cell.char_mass_kg += char_created_kg
                cell.volatile_potential_kg = max(
                    0.0, cell.volatile_potential_kg - volatile_created_kg
                )
                cell.temperature_k -= (
                    reacted_wood_kg * p.pyrolysis_heat_j_kg / heat_capacity
                )
                pyrolysis_gas_total += volatile_created_kg
                primary_gas_total += gas_created_kg
                primary_tar_total += tar_created_kg
                primary_char_total += char_created_kg
                secondary_fraction = secondary_tar_conversion_fraction(
                    p, pyrolysis_temperature_k
                )
                secondary_tar_cracked_kg = tar_created_kg * secondary_fraction
                secondary_tar_cracked_total += secondary_tar_cracked_kg
                uncracked_tar_total += tar_created_kg - secondary_tar_cracked_kg
        if timing_enabled:
            timing_ms["pyrolysis"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        for cell in cells:
            if (
                cell.char_mass_kg > 0.0
                and cell.temperature_k > p.char_oxidation_start_temperature_k
                and cell.oxygen_factor > 0.0
                and cell.surface_exposure > 0.0
            ):
                temperature_ramp = min(
                    1.0,
                    max(
                        0.0,
                        (cell.temperature_k - p.char_oxidation_start_temperature_k)
                        / 300.0,
                    ),
                )
                oxidized_char_kg = min(
                    cell.char_mass_kg,
                    cell.char_mass_kg
                    * p.char_oxidation_max_fraction_s
                    * temperature_ramp
                    * cell.oxygen_factor
                    * cell.surface_exposure
                    * dt_seconds,
                )
                ash_created_kg = oxidized_char_kg * p.char_ash_yield
                char_gas_kg = oxidized_char_kg - ash_created_kg
                cell.char_mass_kg -= oxidized_char_kg
                cell.ash_mass_kg += ash_created_kg
                heat_capacity = self._heat_capacity_j_k(cell)
                cell.temperature_k += (
                    oxidized_char_kg * p.char_oxidation_heat_j_kg / heat_capacity
                )
                char_gas_total += char_gas_kg
        if timing_enabled:
            timing_ms["char_oxidation"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        if array_backend == NUMPY_ARRAY_BACKEND:
            self._numpy_finalize_state(ambient, update_cell_phases)
        else:
            mass_epsilon = self._mass_epsilon_kg
            pyrolysis_start_temperature_k = p.pyrolysis_start_temperature_k
            diagnostics_enabled = state_diagnostics is not None
            if diagnostics_enabled:
                cells_evaluated = 0
                temperature_clamped_low = 0
                temperature_clamped_high = 0
                moisture_mass_clamped = 0
                dry_wood_mass_clamped = 0
                char_mass_clamped = 0
                ash_mass_clamped = 0
                phase_changes = 0
                phase_assignments = [0] * len(_PHASE_NAMES)
                phase_transitions = [0] * (len(_PHASE_NAMES) ** 2)
            for cell in cells:
                if diagnostics_enabled:
                    cells_evaluated += 1
                    previous_phase_index = _PHASE_INDEX[cell.phase]
                    if cell.temperature_k < ambient:
                        temperature_clamped_low += 1
                    elif cell.temperature_k > p.max_temperature_k:
                        temperature_clamped_high += 1
                    moisture_mass_clamped += cell.moisture_mass_kg < 0.0
                    dry_wood_mass_clamped += cell.dry_wood_mass_kg < 0.0
                    char_mass_clamped += cell.char_mass_kg < 0.0
                    ash_mass_clamped += cell.ash_mass_kg < 0.0
                if python_state_clamp_fast_path:
                    temperature_k = cell.temperature_k
                    if not temperature_k > ambient:
                        cell.temperature_k = ambient
                    elif temperature_k > p.max_temperature_k:
                        cell.temperature_k = p.max_temperature_k
                    if not cell.moisture_mass_kg > 0.0:
                        cell.moisture_mass_kg = 0.0
                    if not cell.dry_wood_mass_kg > 0.0:
                        cell.dry_wood_mass_kg = 0.0
                    if not cell.char_mass_kg > 0.0:
                        cell.char_mass_kg = 0.0
                    if not cell.ash_mass_kg > 0.0:
                        cell.ash_mass_kg = 0.0
                else:
                    cell.temperature_k = min(
                        p.max_temperature_k, max(ambient, cell.temperature_k)
                    )
                    cell.moisture_mass_kg = max(0.0, cell.moisture_mass_kg)
                    cell.dry_wood_mass_kg = max(0.0, cell.dry_wood_mass_kg)
                    cell.char_mass_kg = max(0.0, cell.char_mass_kg)
                    cell.ash_mass_kg = max(0.0, cell.ash_mass_kg)
                if update_cell_phases:
                    if (
                        cell.moisture_mass_kg
                        + cell.dry_wood_mass_kg
                        + cell.char_mass_kg
                        + cell.ash_mass_kg
                        <= mass_epsilon
                    ):
                        cell.phase = DEPLETED
                    elif (
                        cell.char_mass_kg > cell.dry_wood_mass_kg
                        and cell.char_mass_kg > cell.ash_mass_kg
                    ):
                        cell.phase = CHAR
                    elif (
                        cell.ash_mass_kg
                        > cell.dry_wood_mass_kg + cell.char_mass_kg
                    ):
                        cell.phase = ASH
                    elif (
                        cell.temperature_k >= pyrolysis_start_temperature_k
                        and cell.dry_wood_mass_kg > mass_epsilon
                    ):
                        cell.phase = PYROLYZING
                    elif cell.moisture_mass_kg > cell.dry_wood_mass_kg * 0.01:
                        cell.phase = WET_WOOD
                    else:
                        cell.phase = DRY_WOOD
                if diagnostics_enabled:
                    phase_index = _PHASE_INDEX[cell.phase]
                    phase_assignments[phase_index] += 1
                    if phase_index != previous_phase_index:
                        phase_changes += 1
                        phase_transitions[
                            previous_phase_index * len(_PHASE_NAMES) + phase_index
                        ] += 1
            if diagnostics_enabled:
                diagnostic_values = {
                    "cells_evaluated": cells_evaluated,
                    "temperature_clamped_low": temperature_clamped_low,
                    "temperature_clamped_high": temperature_clamped_high,
                    "moisture_mass_clamped": moisture_mass_clamped,
                    "dry_wood_mass_clamped": dry_wood_mass_clamped,
                    "char_mass_clamped": char_mass_clamped,
                    "ash_mass_clamped": ash_mass_clamped,
                    "phase_changes": phase_changes,
                }
                diagnostic_values.update(
                    {
                        f"phase_{phase.lower()}": phase_assignments[index]
                        for index, phase in enumerate(_PHASE_NAMES)
                    }
                )
                diagnostic_values.update(
                    {
                        f"transition_{source.lower()}_to_{target.lower()}": (
                            phase_transitions[
                                source_index * len(_PHASE_NAMES) + target_index
                            ]
                        )
                        for source_index, source in enumerate(_PHASE_NAMES)
                        for target_index, target in enumerate(_PHASE_NAMES)
                        if phase_transitions[
                            source_index * len(_PHASE_NAMES) + target_index
                        ]
                    }
                )
                for name, value in diagnostic_values.items():
                    state_diagnostics[name] = state_diagnostics.get(name, 0) + value
        if timing_enabled:
            timing_ms["state_finalize"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
            segment_started = time.perf_counter()

        self.elapsed_seconds += dt_seconds
        self.emitted_water_kg += evaporated_total
        self.emitted_pyrolysis_gas_kg += pyrolysis_gas_total
        self.emitted_char_gas_kg += char_gas_total
        self.emitted_primary_gas_kg += primary_gas_total
        self.emitted_tar_kg += primary_tar_total
        self.produced_primary_char_kg += primary_char_total
        self.converted_secondary_tar_kg += secondary_tar_cracked_total
        result = CombustionStepResult(
            elapsed_seconds=self.elapsed_seconds,
            evaporated_water_kg=evaporated_total,
            pyrolysis_gas_kg=pyrolysis_gas_total,
            char_oxidation_gas_kg=char_gas_total,
            evaporated_water_rate_kg_s=evaporated_total / dt_seconds,
            pyrolysis_gas_rate_kg_s=pyrolysis_gas_total / dt_seconds,
            char_oxidation_gas_rate_kg_s=char_gas_total / dt_seconds,
            external_heat_j=external_heat_total,
            primary_gas_kg=primary_gas_total,
            primary_tar_kg=primary_tar_total,
            primary_char_kg=primary_char_total,
            primary_gas_rate_kg_s=primary_gas_total / dt_seconds,
            primary_tar_rate_kg_s=primary_tar_total / dt_seconds,
            primary_char_rate_kg_s=primary_char_total / dt_seconds,
            secondary_tar_cracked_kg=secondary_tar_cracked_total,
            secondary_gas_rate_kg_s=secondary_tar_cracked_total / dt_seconds,
            uncracked_tar_kg=uncracked_tar_total,
            uncracked_tar_rate_kg_s=uncracked_tar_total / dt_seconds,
        )
        if timing_enabled:
            timing_ms["result_aggregation"] = (
                time.perf_counter() - segment_started
            ) * 1000.0
        return result

    @property
    def current_mass_kg(self) -> float:
        return sum(cell.current_mass_kg for cell in self.cells)

    @property
    def accounted_mass_kg(self) -> float:
        return (
            self.current_mass_kg
            + self.emitted_water_kg
            + self.emitted_pyrolysis_gas_kg
            + self.emitted_char_gas_kg
        )

    @property
    def mass_balance_error_kg(self) -> float:
        return self.accounted_mass_kg - self.initial_mass_kg

    def capture_runtime_topology(self) -> WoodRuntimeTopology:
        """Capture topology only after callers finish editing public cell metadata."""

        cells = tuple(self.cells)
        return WoodRuntimeTopology(
            cells=cells,
            surface_cells=tuple(
                cell for cell in cells if cell.surface_exposure > 0.0
            ),
            initial_dry_mass_kg=(
                sum(
                    cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
                    for cell in cells
                )
                + self.emitted_pyrolysis_gas_kg
                + self.emitted_char_gas_kg
            ),
        )

    def runtime_metrics(
        self, topology: WoodRuntimeTopology | None = None
    ) -> dict:
        """Return the aggregate fields consumed inside the Phase 3 step loop."""

        surface_temperature_sum = 0.0
        moisture_mass_kg = 0.0
        dry_wood_mass_kg = 0.0
        char_mass_kg = 0.0
        ash_mass_kg = 0.0
        cells = self.cells if topology is None else topology.cells
        if topology is None:
            surface_cell_count = 0
            for cell in cells:
                if cell.surface_exposure > 0.0:
                    surface_temperature_sum += cell.temperature_k
                    surface_cell_count += 1
                moisture_mass_kg += cell.moisture_mass_kg
                dry_wood_mass_kg += cell.dry_wood_mass_kg
                char_mass_kg += cell.char_mass_kg
                ash_mass_kg += cell.ash_mass_kg
        else:
            surface_cell_count = len(topology.surface_cells)
            for cell in topology.surface_cells:
                surface_temperature_sum += cell.temperature_k
            for cell in cells:
                moisture_mass_kg += cell.moisture_mass_kg
                dry_wood_mass_kg += cell.dry_wood_mass_kg
                char_mass_kg += cell.char_mass_kg
                ash_mass_kg += cell.ash_mass_kg
        return {
            "surface_mean_temperature_k": (
                surface_temperature_sum / surface_cell_count
            ),
            "moisture_mass_kg": moisture_mass_kg,
            "dry_wood_mass_kg": dry_wood_mass_kg,
            "char_mass_kg": char_mass_kg,
            "ash_mass_kg": ash_mass_kg,
        }

    def metrics(self) -> dict:
        total_mass = 0.0
        weighted_temperature_sum = 0.0
        max_temperature_k = -math.inf
        surface_temperature_sum = 0.0
        surface_cell_count = 0
        moisture_mass_kg = 0.0
        dry_wood_mass_kg = 0.0
        char_mass_kg = 0.0
        ash_mass_kg = 0.0
        for cell in self.cells:
            cell_mass_kg = (
                cell.moisture_mass_kg
                + cell.dry_wood_mass_kg
                + cell.char_mass_kg
                + cell.ash_mass_kg
            )
            total_mass += cell_mass_kg
            weighted_temperature_sum += cell.temperature_k * cell_mass_kg
            max_temperature_k = max(max_temperature_k, cell.temperature_k)
            if cell.surface_exposure > 0.0:
                surface_temperature_sum += cell.temperature_k
                surface_cell_count += 1
            moisture_mass_kg += cell.moisture_mass_kg
            dry_wood_mass_kg += cell.dry_wood_mass_kg
            char_mass_kg += cell.char_mass_kg
            ash_mass_kg += cell.ash_mass_kg
        weighted_temperature = weighted_temperature_sum / max(total_mass, 1.0e-12)
        accounted_mass_kg = (
            total_mass
            + self.emitted_water_kg
            + self.emitted_pyrolysis_gas_kg
            + self.emitted_char_gas_kg
        )
        primary_product_total_kg = (
            self.emitted_primary_gas_kg
            + self.emitted_tar_kg
            + self.produced_primary_char_kg
        )
        primary_product_yields = {
            "gas": self.emitted_primary_gas_kg / max(primary_product_total_kg, 1.0e-12),
            "tar": self.emitted_tar_kg / max(primary_product_total_kg, 1.0e-12),
            "char": self.produced_primary_char_kg
            / max(primary_product_total_kg, 1.0e-12),
        }
        post_secondary_product_yields = {
            "gas": (self.emitted_primary_gas_kg + self.converted_secondary_tar_kg)
            / max(primary_product_total_kg, 1.0e-12),
            "tar": (self.emitted_tar_kg - self.converted_secondary_tar_kg)
            / max(primary_product_total_kg, 1.0e-12),
            "char": self.produced_primary_char_kg
            / max(primary_product_total_kg, 1.0e-12),
        }
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "cell_count": len(self.cells),
            "mean_temperature_k": weighted_temperature,
            "max_temperature_k": max_temperature_k,
            "surface_mean_temperature_k": (
                surface_temperature_sum / surface_cell_count
            ),
            "moisture_mass_kg": moisture_mass_kg,
            "dry_wood_mass_kg": dry_wood_mass_kg,
            "char_mass_kg": char_mass_kg,
            "ash_mass_kg": ash_mass_kg,
            "emitted_water_kg": self.emitted_water_kg,
            "emitted_pyrolysis_gas_kg": self.emitted_pyrolysis_gas_kg,
            "emitted_char_gas_kg": self.emitted_char_gas_kg,
            "emitted_primary_gas_kg": self.emitted_primary_gas_kg,
            "emitted_tar_kg": self.emitted_tar_kg,
            "produced_primary_char_kg": self.produced_primary_char_kg,
            "converted_secondary_tar_kg": self.converted_secondary_tar_kg,
            "emitted_uncracked_tar_kg": (
                self.emitted_tar_kg - self.converted_secondary_tar_kg
            ),
            "primary_product_yield_fraction": primary_product_yields,
            "post_secondary_product_yield_fraction": post_secondary_product_yields,
            "initial_mass_kg": self.initial_mass_kg,
            "accounted_mass_kg": accounted_mass_kg,
            "mass_balance_error_kg": accounted_mass_kg - self.initial_mass_kg,
        }

    def to_dict(self) -> dict:
        return {
            "version": MODEL_VERSION,
            "spec": asdict(self.spec),
            "parameters": asdict(self.parameters),
            "elapsed_seconds": self.elapsed_seconds,
            "emitted_water_kg": self.emitted_water_kg,
            "emitted_pyrolysis_gas_kg": self.emitted_pyrolysis_gas_kg,
            "emitted_char_gas_kg": self.emitted_char_gas_kg,
            "emitted_primary_gas_kg": self.emitted_primary_gas_kg,
            "emitted_tar_kg": self.emitted_tar_kg,
            "produced_primary_char_kg": self.produced_primary_char_kg,
            "converted_secondary_tar_kg": self.converted_secondary_tar_kg,
            "initial_mass_kg": self.initial_mass_kg,
            "cells": [asdict(cell) for cell in self.cells],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WoodThermalModel":
        if data.get("version") != MODEL_VERSION:
            raise ValueError(f"Unsupported wood model version: {data.get('version')}")
        return cls(
            spec=WoodGridSpec(**data["spec"]),
            cells=[WoodCellState(**cell) for cell in data["cells"]],
            parameters=WoodModelParameters(**data["parameters"]),
            elapsed_seconds=data["elapsed_seconds"],
            emitted_water_kg=data["emitted_water_kg"],
            emitted_pyrolysis_gas_kg=data["emitted_pyrolysis_gas_kg"],
            emitted_char_gas_kg=data["emitted_char_gas_kg"],
            emitted_primary_gas_kg=data.get("emitted_primary_gas_kg", 0.0),
            emitted_tar_kg=data.get("emitted_tar_kg", 0.0),
            produced_primary_char_kg=data.get("produced_primary_char_kg", 0.0),
            converted_secondary_tar_kg=data.get("converted_secondary_tar_kg", 0.0),
            initial_mass_kg=data["initial_mass_kg"],
        )


def create_cylindrical_wood_model(
    log_id: str,
    radius_m: float,
    length_m: float,
    moisture_ratio_dry_basis: float,
    initial_temperature_k: float = 293.15,
    axial_cells: int = 24,
    circumferential_cells: int = 12,
    radial_cells: int = 4,
    parameters: WoodModelParameters | None = None,
) -> WoodThermalModel:
    """Create equal-angle cylindrical cells; moisture uses a dry-mass basis."""

    if radius_m <= 0.0 or length_m <= 0.0:
        raise ValueError("Log dimensions must be positive")
    if moisture_ratio_dry_basis < 0.0:
        raise ValueError("Dry-basis moisture ratio must be non-negative")
    if min(axial_cells, circumferential_cells, radial_cells) <= 0:
        raise ValueError("Grid dimensions must be positive")

    p = parameters or WoodModelParameters()
    spec = WoodGridSpec(
        log_id=log_id,
        radius_m=radius_m,
        length_m=length_m,
        axial_cells=axial_cells,
        circumferential_cells=circumferential_cells,
        radial_cells=radial_cells,
    )
    dz = length_m / axial_cells
    dr = radius_m / radial_cells
    dtheta = 2.0 * math.pi / circumferential_cells
    cells = []
    for z in range(axial_cells):
        for _theta in range(circumferential_cells):
            for radial in range(radial_cells):
                r_inner = radial * dr
                r_outer = (radial + 1) * dr
                volume_m3 = (
                    0.5 * (r_outer**2 - r_inner**2) * dtheta * dz
                )
                dry_mass_kg = volume_m3 * p.dry_wood_density_kg_m3
                moisture_mass_kg = dry_mass_kg * moisture_ratio_dry_basis
                outer_area_m2 = (
                    r_outer * dtheta * dz if radial == radial_cells - 1 else 0.0
                )
                end_area_m2 = (
                    0.5 * (r_outer**2 - r_inner**2) * dtheta
                    if z == 0 or z == axial_cells - 1
                    else 0.0
                )
                external_area_m2 = outer_area_m2 + end_area_m2
                exposed = 1.0 if external_area_m2 > 0.0 else 0.0
                cells.append(
                    WoodCellState(
                        temperature_k=initial_temperature_k,
                        moisture_mass_kg=moisture_mass_kg,
                        dry_wood_mass_kg=dry_mass_kg,
                        volatile_potential_kg=(
                            dry_mass_kg
                            * initial_volatile_potential_fraction(p)
                        ),
                        char_mass_kg=0.0,
                        ash_mass_kg=0.0,
                        oxygen_factor=exposed,
                        surface_exposure=exposed,
                        phase=WET_WOOD if moisture_mass_kg > 0.0 else DRY_WOOD,
                        volume_m3=volume_m3,
                        external_area_m2=external_area_m2,
                    )
                )
    return WoodThermalModel(spec, cells, p)


def temperature_adjusted_dry_wood_specific_heat_j_kg_k(
    reference_specific_heat_j_kg_k: float,
    temperature_k: float,
    model: str = CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
) -> float:
    """Return dry-wood cp while respecting the selected source range.

    The USDA Forest Products Laboratory relation is normalized at 293.15 K
    so a panel keeps its NISTIR 4916 material-specific reference value.  The
    equation is only published for 280--420 K; temperatures outside that
    interval use the nearest endpoint rather than an unsupported extrapolation.
    """

    if (
        not math.isfinite(reference_specific_heat_j_kg_k)
        or reference_specific_heat_j_kg_k <= 0.0
    ):
        raise ValueError("reference_specific_heat_j_kg_k must be finite and positive")
    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be finite and positive")
    if model == CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL:
        return reference_specific_heat_j_kg_k
    if model != USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL:
        raise ValueError(f"Unsupported dry-wood specific-heat model: {model}")

    bounded_temperature_k = min(
        USDA_FPL_DRY_WOOD_CP_MAX_TEMPERATURE_K,
        max(USDA_FPL_DRY_WOOD_CP_MIN_TEMPERATURE_K, temperature_k),
    )
    source_specific_heat_j_kg_k = (
        USDA_FPL_DRY_WOOD_CP_INTERCEPT_J_KG_K
        + USDA_FPL_DRY_WOOD_CP_SLOPE_J_KG_K2 * bounded_temperature_k
    )
    source_reference_specific_heat_j_kg_k = (
        USDA_FPL_DRY_WOOD_CP_INTERCEPT_J_KG_K
        + USDA_FPL_DRY_WOOD_CP_SLOPE_J_KG_K2
        * USDA_FPL_DRY_WOOD_CP_REFERENCE_TEMPERATURE_K
    )
    return (
        reference_specific_heat_j_kg_k
        * source_specific_heat_j_kg_k
        / source_reference_specific_heat_j_kg_k
    )


def arrhenius_pyrolysis_rate_constant_s(
    parameters: WoodModelParameters,
    temperature_k: float,
) -> float:
    """Return A exp(-E/RT) for the configured first-order solid reaction."""

    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be finite and positive")
    if parameters.pyrolysis_arrhenius_preexponential_s <= 0.0:
        raise ValueError("Arrhenius pre-exponential factor must be positive")
    if parameters.pyrolysis_arrhenius_activation_energy_j_mol <= 0.0:
        raise ValueError("Arrhenius activation energy must be positive")
    if not math.isclose(parameters.pyrolysis_arrhenius_reaction_order, 1.0):
        raise ValueError("Only first-order Arrhenius pyrolysis is implemented")
    return parameters.pyrolysis_arrhenius_preexponential_s * math.exp(
        -parameters.pyrolysis_arrhenius_activation_energy_j_mol
        / (UNIVERSAL_GAS_CONSTANT_J_MOL_K * temperature_k)
    )


def secondary_tar_conversion_fraction(
    parameters: WoodModelParameters,
    temperature_k: float,
) -> float:
    """Return bounded tar-to-gas conversion for the fixed residence scenario.

    This is a diagnostic product split.  It does not add a gas-phase control
    volume, alter the total volatile release, or feed heat back to the solid.
    Below the documented application range conversion is zero; above it the
    temperature is clamped rather than extrapolated.
    """

    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be finite and positive")
    if not parameters.secondary_tar_cracking_enabled:
        return 0.0
    residence_time_s = parameters.secondary_tar_cracking_residence_time_s
    preexponential_s = parameters.secondary_tar_cracking_preexponential_s
    activation_energy_j_mol = (
        parameters.secondary_tar_cracking_activation_energy_j_mol
    )
    minimum_temperature_k = parameters.secondary_tar_cracking_min_temperature_k
    maximum_temperature_k = parameters.secondary_tar_cracking_max_temperature_k
    if not math.isfinite(residence_time_s) or residence_time_s <= 0.0:
        raise ValueError("Secondary-tar residence time must be finite and positive")
    if not math.isfinite(preexponential_s) or preexponential_s <= 0.0:
        raise ValueError("Secondary-tar pre-exponential factor must be positive")
    if not math.isfinite(activation_energy_j_mol) or activation_energy_j_mol <= 0.0:
        raise ValueError("Secondary-tar activation energy must be positive")
    if (
        not math.isfinite(minimum_temperature_k)
        or not math.isfinite(maximum_temperature_k)
        or minimum_temperature_k <= 0.0
        or maximum_temperature_k < minimum_temperature_k
    ):
        raise ValueError("Secondary-tar temperature bounds are invalid")
    if temperature_k < minimum_temperature_k:
        return 0.0
    bounded_temperature_k = min(temperature_k, maximum_temperature_k)
    rate_constant_s = preexponential_s * math.exp(
        -activation_energy_j_mol
        / (UNIVERSAL_GAS_CONSTANT_J_MOL_K * bounded_temperature_k)
    )
    return 1.0 - math.exp(-rate_constant_s * residence_time_s)


def parallel_arrhenius_rate_constants_s(
    parameters: WoodModelParameters,
    temperature_k: float,
) -> dict[str, float]:
    """Return competing gas, tar, and char first-order rates in s^-1."""

    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be finite and positive")
    if not math.isclose(parameters.pyrolysis_arrhenius_reaction_order, 1.0):
        raise ValueError("Only first-order parallel Arrhenius pyrolysis is implemented")
    if (
        not math.isfinite(parameters.pyrolysis_parallel_common_scale)
        or parameters.pyrolysis_parallel_common_scale <= 0.0
    ):
        raise ValueError("Parallel Arrhenius common scale must be finite and positive")
    pathway_parameters = {
        "gas": (
            parameters.pyrolysis_parallel_gas_preexponential_s,
            parameters.pyrolysis_parallel_gas_activation_energy_j_mol,
        ),
        "tar": (
            parameters.pyrolysis_parallel_tar_preexponential_s,
            parameters.pyrolysis_parallel_tar_activation_energy_j_mol,
        ),
        "char": (
            parameters.pyrolysis_parallel_char_preexponential_s,
            parameters.pyrolysis_parallel_char_activation_energy_j_mol,
        ),
    }
    rates = {}
    for product, (preexponential_s, activation_energy_j_mol) in pathway_parameters.items():
        if preexponential_s <= 0.0 or activation_energy_j_mol <= 0.0:
            raise ValueError("Parallel Arrhenius A and E values must be positive")
        rates[product] = (
            parameters.pyrolysis_parallel_common_scale
            * preexponential_s
            * math.exp(
                -activation_energy_j_mol
                / (UNIVERSAL_GAS_CONSTANT_J_MOL_K * temperature_k)
            )
        )
    return rates


def initial_volatile_potential_fraction(parameters: WoodModelParameters) -> float:
    """Return a diagnostic upper bound for volatile product mass."""

    if parameters.pyrolysis_rate_model == "arrhenius_parallel_first_order":
        return 1.0
    return 1.0 - parameters.pyrolysis_char_yield


def flow_source_from_model(
    model: WoodThermalModel,
    step_result: CombustionStepResult,
    reference_fuel_rate_kg_s: float = 0.02,
    surface_temperature_k: float | None = None,
) -> FlowSourceState:
    """Map authoritative mass release to dimensionless Flow display inputs."""

    if reference_fuel_rate_kg_s <= 0.0:
        raise ValueError("reference_fuel_rate_kg_s must be positive")
    surface_temperature = (
        model.metrics()["surface_mean_temperature_k"]
        if surface_temperature_k is None
        else float(surface_temperature_k)
    )
    fuel = min(1.0, step_result.pyrolysis_gas_rate_kg_s / reference_fuel_rate_kg_s)
    normalized_temperature = min(
        2.0,
        max(
            0.0,
            (surface_temperature - model.parameters.ambient_temperature_k) / 500.0,
        ),
    )
    smoke = min(1.0, 0.25 * fuel + 5.0 * step_result.char_oxidation_gas_rate_kg_s)
    return FlowSourceState(
        fuel=fuel,
        temperature=normalized_temperature,
        smoke=smoke,
        pyrolysis_gas_rate_kg_s=step_result.pyrolysis_gas_rate_kg_s,
    )


def save_model_to_prim(model: WoodThermalModel, prim: Usd.Prim) -> None:
    """Persist the authoritative state as versioned JSON on its log prim."""

    from pxr import Sdf

    if not prim:
        raise ValueError("A valid log prim is required")
    prim.CreateAttribute(MODEL_VERSION_ATTRIBUTE, Sdf.ValueTypeNames.Int).Set(
        MODEL_VERSION
    )
    prim.CreateAttribute(STATE_ATTRIBUTE, Sdf.ValueTypeNames.String).Set(
        json.dumps(model.to_dict(), separators=(",", ":"), sort_keys=True)
    )


def load_model_from_prim(prim: Usd.Prim) -> WoodThermalModel:
    if not prim:
        raise ValueError("A valid log prim is required")
    state = prim.GetAttribute(STATE_ATTRIBUTE)
    if not state or not state.Get():
        raise ValueError(f"Log has no combustion state: {prim.GetPath()}")
    return WoodThermalModel.from_dict(json.loads(state.Get()))
