"""Flow-independent, mass-conserving wood thermal model for Phase 3.

The coefficients below are explicit SI-unit hypotheses for the MVP.  They are
not calibrated material data.  Keeping them in one immutable parameter object
makes later comparison against measured wood straightforward.
"""

import json
import math
from dataclasses import asdict, dataclass

from pxr import Sdf, Usd


MODEL_VERSION = 1
STATE_ATTRIBUTE = "campfire:combustionStateJson"
MODEL_VERSION_ATTRIBUTE = "campfire:combustionModelVersion"

WET_WOOD = "WET_WOOD"
DRY_WOOD = "DRY_WOOD"
PYROLYZING = "PYROLYZING"
CHAR = "CHAR"
ASH = "ASH"
DEPLETED = "DEPLETED"


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
    ambient_temperature_k: float = 293.15
    evaporation_start_temperature_k: float = 353.15
    water_latent_heat_j_kg: float = 2_256_000.0
    evaporation_max_fraction_s: float = 0.08
    pyrolysis_start_temperature_k: float = 573.15
    pyrolysis_full_temperature_k: float = 773.15
    pyrolysis_max_fraction_s: float = 0.025
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


@dataclass(frozen=True)
class FlowSourceState:
    fuel: float
    temperature: float
    smoke: float
    pyrolysis_gas_rate_kg_s: float


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
        self.initial_mass_kg = (
            float(initial_mass_kg)
            if initial_mass_kg is not None
            else sum(cell.current_mass_kg for cell in cells)
        )
        self._conduction_pairs = self._build_conduction_pairs()

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

    def _heat_capacity_j_k(self, cell: WoodCellState) -> float:
        p = self.parameters
        return max(
            cell.dry_wood_mass_kg * p.wood_specific_heat_j_kg_k
            + cell.moisture_mass_kg * p.water_specific_heat_j_kg_k
            + cell.char_mass_kg * p.char_specific_heat_j_kg_k
            + cell.ash_mass_kg * p.ash_specific_heat_j_kg_k,
            1.0e-9,
        )

    def _update_phase(self, cell: WoodCellState) -> None:
        mass_epsilon = max(self.initial_mass_kg * 1.0e-10, 1.0e-12)
        if cell.current_mass_kg <= mass_epsilon:
            cell.phase = DEPLETED
        elif cell.char_mass_kg > cell.dry_wood_mass_kg and cell.char_mass_kg > cell.ash_mass_kg:
            cell.phase = CHAR
        elif cell.ash_mass_kg > cell.dry_wood_mass_kg + cell.char_mass_kg:
            cell.phase = ASH
        elif (
            cell.temperature_k >= self.parameters.pyrolysis_start_temperature_k
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
    ) -> CombustionStepResult:
        """Advance one explicit SI-unit thermal/reaction step.

        A scalar applies a uniform surface flux.  A cell-sized sequence allows
        later phases to represent a local flame without changing the
        authoritative cell state or reaction accounting.
        """

        if not math.isfinite(dt_seconds) or dt_seconds <= 0.0:
            raise ValueError("dt_seconds must be finite and positive")
        if isinstance(external_heat_flux_w_m2, (int, float)):
            heat_fluxes = [float(external_heat_flux_w_m2)] * len(self.cells)
        else:
            heat_fluxes = [float(value) for value in external_heat_flux_w_m2]
            if len(heat_fluxes) != len(self.cells):
                raise ValueError("Cell heat-flux sequence must match the cell count")
        if any(not math.isfinite(value) or value < 0.0 for value in heat_fluxes):
            raise ValueError("External heat flux must be finite and non-negative")

        p = self.parameters
        ambient = p.ambient_temperature_k if ambient_temperature_k is None else ambient_temperature_k
        if not math.isfinite(ambient) or ambient <= 0.0:
            raise ValueError("ambient_temperature_k must be finite and positive")

        conduction_energy_j = [0.0] * len(self.cells)
        for first, second, conductance_w_k in self._conduction_pairs:
            energy_j = (
                conductance_w_k
                * (self.cells[second].temperature_k - self.cells[first].temperature_k)
                * dt_seconds
            )
            conduction_energy_j[first] += energy_j
            conduction_energy_j[second] -= energy_j

        evaporated_total = 0.0
        pyrolysis_gas_total = 0.0
        char_gas_total = 0.0
        external_heat_total = 0.0
        sigma = 5.670374419e-8

        for index, cell in enumerate(self.cells):
            heat_capacity = self._heat_capacity_j_k(cell)
            area = cell.external_area_m2 * cell.surface_exposure
            external_heat_w = heat_fluxes[index] * area
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

            if (
                cell.dry_wood_mass_kg > 0.0
                and cell.temperature_k > p.pyrolysis_start_temperature_k
            ):
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
                moisture_ratio = cell.moisture_mass_kg / max(
                    cell.dry_wood_mass_kg, 1.0e-12
                )
                dryness_factor = min(1.0, max(0.0, 1.0 - moisture_ratio / 0.10))
                rate_limited_kg = (
                    cell.dry_wood_mass_kg
                    * p.pyrolysis_max_fraction_s
                    * temperature_ramp
                    * dryness_factor
                    * dt_seconds
                )
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
                char_created_kg = reacted_wood_kg * p.pyrolysis_char_yield
                gas_created_kg = reacted_wood_kg - char_created_kg
                cell.dry_wood_mass_kg -= reacted_wood_kg
                cell.char_mass_kg += char_created_kg
                cell.volatile_potential_kg = max(
                    0.0, cell.volatile_potential_kg - gas_created_kg
                )
                cell.temperature_k -= (
                    reacted_wood_kg * p.pyrolysis_heat_j_kg / heat_capacity
                )
                pyrolysis_gas_total += gas_created_kg

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

            cell.temperature_k = min(
                p.max_temperature_k, max(ambient, cell.temperature_k)
            )
            cell.moisture_mass_kg = max(0.0, cell.moisture_mass_kg)
            cell.dry_wood_mass_kg = max(0.0, cell.dry_wood_mass_kg)
            cell.char_mass_kg = max(0.0, cell.char_mass_kg)
            cell.ash_mass_kg = max(0.0, cell.ash_mass_kg)
            self._update_phase(cell)

        self.elapsed_seconds += dt_seconds
        self.emitted_water_kg += evaporated_total
        self.emitted_pyrolysis_gas_kg += pyrolysis_gas_total
        self.emitted_char_gas_kg += char_gas_total
        return CombustionStepResult(
            elapsed_seconds=self.elapsed_seconds,
            evaporated_water_kg=evaporated_total,
            pyrolysis_gas_kg=pyrolysis_gas_total,
            char_oxidation_gas_kg=char_gas_total,
            evaporated_water_rate_kg_s=evaporated_total / dt_seconds,
            pyrolysis_gas_rate_kg_s=pyrolysis_gas_total / dt_seconds,
            char_oxidation_gas_rate_kg_s=char_gas_total / dt_seconds,
            external_heat_j=external_heat_total,
        )

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

    def metrics(self) -> dict:
        total_mass = self.current_mass_kg
        surface_cells = [cell for cell in self.cells if cell.surface_exposure > 0.0]
        weighted_temperature = sum(
            cell.temperature_k * cell.current_mass_kg for cell in self.cells
        ) / max(total_mass, 1.0e-12)
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "cell_count": len(self.cells),
            "mean_temperature_k": weighted_temperature,
            "max_temperature_k": max(cell.temperature_k for cell in self.cells),
            "surface_mean_temperature_k": sum(
                cell.temperature_k for cell in surface_cells
            )
            / len(surface_cells),
            "moisture_mass_kg": sum(cell.moisture_mass_kg for cell in self.cells),
            "dry_wood_mass_kg": sum(cell.dry_wood_mass_kg for cell in self.cells),
            "char_mass_kg": sum(cell.char_mass_kg for cell in self.cells),
            "ash_mass_kg": sum(cell.ash_mass_kg for cell in self.cells),
            "emitted_water_kg": self.emitted_water_kg,
            "emitted_pyrolysis_gas_kg": self.emitted_pyrolysis_gas_kg,
            "emitted_char_gas_kg": self.emitted_char_gas_kg,
            "initial_mass_kg": self.initial_mass_kg,
            "accounted_mass_kg": self.accounted_mass_kg,
            "mass_balance_error_kg": self.mass_balance_error_kg,
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
                            dry_mass_kg * (1.0 - p.pyrolysis_char_yield)
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


def flow_source_from_model(
    model: WoodThermalModel,
    step_result: CombustionStepResult,
    reference_fuel_rate_kg_s: float = 0.02,
) -> FlowSourceState:
    """Map authoritative mass release to dimensionless Flow display inputs."""

    if reference_fuel_rate_kg_s <= 0.0:
        raise ValueError("reference_fuel_rate_kg_s must be positive")
    surface_temperature = model.metrics()["surface_mean_temperature_k"]
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
