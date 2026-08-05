"""Planar layered panel adapter for cone-calorimeter specimens."""

from dataclasses import dataclass

from .combustion import (
    CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
    DRY_WOOD,
    WET_WOOD,
    WoodCellState,
    WoodModelParameters,
    WoodThermalModel,
    initial_volatile_potential_fraction,
)


@dataclass(frozen=True)
class LayeredPanelSpec:
    """Explicit SI geometry for a one-dimensional through-thickness panel."""

    log_id: str
    width_m: float
    depth_m: float
    thickness_m: float
    layer_count: int
    layer_orientations_deg: tuple[float, ...]
    effective_dry_density_kg_m3: float
    material_kind: str
    through_thickness_conductivity_w_m_k: float
    dry_wood_specific_heat_j_kg_k: float
    dry_wood_specific_heat_model: str
    adhesive_interface_count: int
    adhesive_geometry_explicit: bool
    material_property_source: str

    @property
    def cell_count(self) -> int:
        return self.layer_count

    # WoodThermalModel's stable indexing contract is retained while the
    # conduction graph is replaced with a planar through-thickness graph.
    @property
    def axial_cells(self) -> int:
        return self.layer_count

    @property
    def circumferential_cells(self) -> int:
        return 1

    @property
    def radial_cells(self) -> int:
        return 1


@dataclass(frozen=True)
class PanelCharGeometryDiagnostic:
    """Fixed-grid reaction progress kept separate from physical shrinkage."""

    layer_pyrolysis_conversion_fractions: tuple[float, ...]
    layer_char_mass_fractions_initial_dry: tuple[float, ...]
    equivalent_unshrunk_pyrolysis_depth_m: float
    physical_char_layer_thickness_m: float | None
    shrinkage_factor: float | None
    ready_for_darcy_layer_thickness: bool


class LayeredPanelThermalModel(WoodThermalModel):
    """Wood reaction state on explicit planar layers, exposed from one face."""

    spec: LayeredPanelSpec

    def _build_conduction_pairs(self) -> list[tuple[int, int, float]]:
        layer_thickness_m = self.spec.thickness_m / self.spec.layer_count
        exposed_area_m2 = self.spec.width_m * self.spec.depth_m
        conductance_w_k = (
            self.spec.through_thickness_conductivity_w_m_k
            * exposed_area_m2
            / layer_thickness_m
        )
        return [
            (layer, layer + 1, conductance_w_k)
            for layer in range(self.spec.layer_count - 1)
        ]

    def char_geometry_diagnostic(self) -> PanelCharGeometryDiagnostic:
        """Summarize reacted depth on the fixed grid without claiming shrinkage."""

        layer_thickness_m = self.spec.thickness_m / self.spec.layer_count
        conversion_fractions = []
        char_mass_fractions = []
        for cell in self.cells:
            initial_dry_mass_kg = (
                self.spec.effective_dry_density_kg_m3 * cell.volume_m3
            )
            if initial_dry_mass_kg <= 0.0:
                raise ValueError("Panel layer initial dry mass must be positive")
            conversion_fractions.append(
                min(
                    1.0,
                    max(0.0, 1.0 - cell.dry_wood_mass_kg / initial_dry_mass_kg),
                )
            )
            char_mass_fractions.append(
                min(1.0, max(0.0, cell.char_mass_kg / initial_dry_mass_kg))
            )
        equivalent_depth_m = layer_thickness_m * sum(conversion_fractions)
        return PanelCharGeometryDiagnostic(
            layer_pyrolysis_conversion_fractions=tuple(conversion_fractions),
            layer_char_mass_fractions_initial_dry=tuple(char_mass_fractions),
            equivalent_unshrunk_pyrolysis_depth_m=equivalent_depth_m,
            physical_char_layer_thickness_m=None,
            shrinkage_factor=None,
            ready_for_darcy_layer_thickness=False,
        )


def create_layered_panel_model(
    panel_id: str,
    *,
    width_m: float,
    depth_m: float,
    thickness_m: float,
    layer_count: int,
    initial_wet_mass_kg: float,
    moisture_ratio_dry_basis: float,
    layer_orientations_deg: tuple[float, ...] | None = None,
    initial_temperature_k: float = 293.15,
    parameters: WoodModelParameters | None = None,
    material_kind: str = "generic_wood_panel",
    through_thickness_conductivity_w_m_k: float | None = None,
    dry_wood_specific_heat_j_kg_k: float | None = None,
    dry_wood_specific_heat_model: str = CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
    adhesive_interface_count: int = 0,
    adhesive_geometry_explicit: bool = False,
    material_property_source: str = "WoodModelParameters generic wood hypothesis",
) -> LayeredPanelThermalModel:
    """Create equal-thickness layers while preserving measured wet mass."""

    if min(width_m, depth_m, thickness_m, initial_wet_mass_kg) <= 0.0:
        raise ValueError("Panel dimensions and mass must be positive")
    if layer_count <= 0:
        raise ValueError("layer_count must be positive")
    if moisture_ratio_dry_basis < 0.0:
        raise ValueError("Dry-basis moisture ratio must be non-negative")
    if adhesive_interface_count < 0 or adhesive_interface_count > layer_count - 1:
        raise ValueError("Adhesive interface count must fit between panel layers")
    orientations = layer_orientations_deg or tuple(
        0.0 if index % 2 == 0 else 90.0 for index in range(layer_count)
    )
    if len(orientations) != layer_count:
        raise ValueError("One grain orientation is required per panel layer")

    p = parameters or WoodModelParameters()
    panel_conductivity_w_m_k = (
        float(through_thickness_conductivity_w_m_k)
        if through_thickness_conductivity_w_m_k is not None
        else p.conductivity_radial_w_m_k
    )
    panel_specific_heat_j_kg_k = (
        float(dry_wood_specific_heat_j_kg_k)
        if dry_wood_specific_heat_j_kg_k is not None
        else p.wood_specific_heat_j_kg_k
    )
    if panel_conductivity_w_m_k <= 0.0 or panel_specific_heat_j_kg_k <= 0.0:
        raise ValueError("Panel conductivity and specific heat must be positive")
    if not dry_wood_specific_heat_model:
        raise ValueError("Panel specific-heat model must be named")
    exposed_area_m2 = width_m * depth_m
    total_volume_m3 = exposed_area_m2 * thickness_m
    dry_mass_kg = initial_wet_mass_kg / (1.0 + moisture_ratio_dry_basis)
    moisture_mass_kg = initial_wet_mass_kg - dry_mass_kg
    spec = LayeredPanelSpec(
        log_id=panel_id,
        width_m=width_m,
        depth_m=depth_m,
        thickness_m=thickness_m,
        layer_count=layer_count,
        layer_orientations_deg=tuple(float(value) for value in orientations),
        effective_dry_density_kg_m3=dry_mass_kg / total_volume_m3,
        material_kind=material_kind,
        through_thickness_conductivity_w_m_k=panel_conductivity_w_m_k,
        dry_wood_specific_heat_j_kg_k=panel_specific_heat_j_kg_k,
        dry_wood_specific_heat_model=dry_wood_specific_heat_model,
        adhesive_interface_count=adhesive_interface_count,
        adhesive_geometry_explicit=adhesive_geometry_explicit,
        material_property_source=material_property_source,
    )
    layer_volume_m3 = total_volume_m3 / layer_count
    cells = []
    for layer in range(layer_count):
        layer_dry_mass_kg = dry_mass_kg / layer_count
        layer_moisture_mass_kg = moisture_mass_kg / layer_count
        exposed = 1.0 if layer == 0 else 0.0
        cells.append(
            WoodCellState(
                temperature_k=initial_temperature_k,
                moisture_mass_kg=layer_moisture_mass_kg,
                dry_wood_mass_kg=layer_dry_mass_kg,
                volatile_potential_kg=(
                    layer_dry_mass_kg * initial_volatile_potential_fraction(p)
                ),
                char_mass_kg=0.0,
                ash_mass_kg=0.0,
                oxygen_factor=exposed,
                surface_exposure=exposed,
                phase=WET_WOOD if layer_moisture_mass_kg > 0.0 else DRY_WOOD,
                volume_m3=layer_volume_m3,
                external_area_m2=exposed_area_m2 if exposed else 0.0,
                dry_wood_specific_heat_j_kg_k=panel_specific_heat_j_kg_k,
                dry_wood_specific_heat_model=dry_wood_specific_heat_model,
            )
        )
    return LayeredPanelThermalModel(spec, cells, p)
