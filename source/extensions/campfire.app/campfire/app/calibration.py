"""Phase 6 reproducible calibration against a fixed NIST cone data subset."""

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

from .combustion import (
    CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
    USDA_FPL_DRY_WOOD_CP_MAX_TEMPERATURE_K,
    USDA_FPL_DRY_WOOD_CP_MIN_TEMPERATURE_K,
    USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL,
    WoodModelParameters,
    WoodThermalModel,
    create_cylindrical_wood_model,
    temperature_adjusted_dry_wood_specific_heat_j_kg_k,
)
from .panel import LayeredPanelThermalModel, create_layered_panel_model


REFERENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "nistir_7094_plywood_cone.json"
)
CALIBRATION_DT_SECONDS = 0.10
CALIBRATION_DURATION_SECONDS = 600.0
IGNITION_GAS_RATE_KG_S = 1.0e-6


@dataclass(frozen=True)
class CouponResult:
    incident_heat_flux_kw_m2: float
    ignition_seconds: float | None
    average_mass_loss_rate_g_s_m2: float
    initial_mass_kg: float
    remaining_mass_kg: float
    mass_balance_error_kg: float
    all_values_finite: bool
    model_kind: str
    specimen_thickness_m: float
    layer_count: int
    effective_dry_density_kg_m3: float
    final_layer_temperatures_k: tuple[float, ...]
    primary_product_mass_kg: dict[str, float]
    primary_product_yield_fraction: dict[str, float]
    post_secondary_product_mass_kg: dict[str, float]
    post_secondary_product_yield_fraction: dict[str, float]
    material_kind: str
    through_thickness_conductivity_w_m_k: float
    dry_wood_specific_heat_j_kg_k: float
    dry_wood_specific_heat_model: str
    dry_wood_specific_heat_valid_range_k: tuple[float, ...]
    final_layer_dry_wood_specific_heats_j_kg_k: tuple[float, ...]
    adhesive_interface_count: int
    adhesive_geometry_explicit: bool


def load_nist_plywood_reference(path: Path | None = None) -> dict:
    reference_path = path or REFERENCE_PATH
    data = json.loads(reference_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported calibration reference schema")
    if data.get("reference_id") != "NISTIR_7094_TABLE_2_PLYWOOD":
        raise ValueError("Unexpected calibration reference")
    if len(data.get("targets", [])) != 2:
        raise ValueError("Calibration reference must contain two flux targets")
    panel_model = data.get("panel_model", {})
    if not math.isclose(float(panel_model.get("nominal_thickness_m", 0.0)), 0.0127):
        raise ValueError("Panel model must record the nominal 12.7 mm source thickness")
    if panel_model.get("plywood_layer_count") != 5:
        raise ValueError("Plywood panel model must contain five plies")
    if panel_model.get("adhesive_layers_explicit") is not False:
        raise ValueError("Unreported adhesive layers must not be treated as explicit geometry")
    material_profiles = data.get("material_property_profiles", {})
    for material_kind in ("plywood", "osb"):
        profile = material_profiles.get(material_kind, {})
        if (
            float(profile.get("thermal_conductivity_w_m_k", 0.0)) <= 0.0
            or float(profile.get("specific_heat_j_kg_k", 0.0)) <= 0.0
        ):
            raise ValueError(f"{material_kind} thermal property profile is incomplete")
        if profile.get("adhesive_geometry_explicit") is not False:
            raise ValueError("Unreported adhesive geometry must remain non-explicit")
    heat_capacity_model = data.get("temperature_dependent_heat_capacity", {})
    if heat_capacity_model.get("model") != USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL:
        raise ValueError("Unexpected dry-wood specific-heat model")
    if heat_capacity_model.get("source_valid_temperature_range_k") != [
        USDA_FPL_DRY_WOOD_CP_MIN_TEMPERATURE_K,
        USDA_FPL_DRY_WOOD_CP_MAX_TEMPERATURE_K,
    ]:
        raise ValueError("Dry-wood specific-heat source range changed")
    if not math.isclose(
        float(heat_capacity_model.get("reference_temperature_k", 0.0)), 293.15
    ):
        raise ValueError("Dry-wood specific-heat reference temperature changed")
    kinetics = data.get("arrhenius_model", {})
    if kinetics.get("reaction_order") != 1.0:
        raise ValueError("Phase 6 Arrhenius calibration requires first-order kinetics")
    pathways = kinetics.get("source_pathways", [])
    if len(pathways) != 3 or any(
        float(pathway.get("preexponential_s", 0.0)) <= 0.0
        or float(pathway.get("activation_energy_j_mol", 0.0)) <= 0.0
        for pathway in pathways
    ):
        raise ValueError("Phase 6 Arrhenius source pathways are incomplete")
    if {pathway.get("product") for pathway in pathways} != {"gas", "tar", "char"}:
        raise ValueError("Phase 6 Arrhenius pathways must identify gas, tar, and char")
    secondary_tar = data.get("secondary_tar_cracking", {})
    secondary_range = secondary_tar.get("application_temperature_range_k", [])
    if (
        float(secondary_tar.get("preexponential_s", 0.0)) <= 0.0
        or float(secondary_tar.get("activation_energy_j_mol", 0.0)) <= 0.0
        or float(secondary_tar.get("residence_time_s", 0.0)) <= 0.0
        or len(secondary_range) != 2
        or float(secondary_range[1]) < float(secondary_range[0])
    ):
        raise ValueError("Secondary-tar diagnostic definition is incomplete")
    sensitivity = secondary_tar.get("residence_time_sensitivity", {})
    scenarios = sensitivity.get("scenarios_s", [])
    experiment_temperature_range = sensitivity.get(
        "experiment_temperature_range_k", []
    )
    experiment_residence_range = sensitivity.get(
        "experiment_residence_time_range_s", []
    )
    experiment_conversion_range = sensitivity.get(
        "experiment_tar_conversion_range_fraction", []
    )
    if (
        scenarios != [0.9, 1.0, 2.2]
        or sensitivity.get("used_for_parameter_selection") is not False
        or experiment_temperature_range != [773.0, 1073.0]
        or experiment_residence_range != [0.9, 2.2]
        or experiment_conversion_range != [0.05, 0.88]
    ):
        raise ValueError("Secondary-tar residence sensitivity definition changed")
    transport = data.get("gas_transport_diagnostic", {})
    transport_context = transport.get("source_context", {})
    missing_transport_inputs = transport.get("missing_current_panel_inputs", [])
    required_missing_transport_inputs = {
        "char_layer_thickness_m",
        "through_thickness_porosity_fraction",
        "through_thickness_permeability_m2",
        "gas_dynamic_viscosity_pa_s",
        "char_layer_pressure_drop_pa",
    }
    if (
        transport.get("model") != "steady_one_dimensional_darcy"
        or transport.get("ready_for_secondary_tar_coupling") is not False
        or transport.get("used_for_parameter_selection") is not False
        or set(missing_transport_inputs) != required_missing_transport_inputs
        or float(transport_context.get("wood_porosity_fraction", 0.0)) <= 0.0
        or float(transport_context.get("char_porosity_fraction", 0.0)) <= 0.0
        or float(transport_context.get("wood_permeability_m2", 0.0)) <= 0.0
        or float(transport_context.get("char_permeability_m2", 0.0)) <= 0.0
        or float(transport_context.get("reported_reference_pressure_drop_pa", 0.0))
        <= 0.0
        or transport.get("current_panel_known_inputs", {}).get(
            "overall_specimen_thickness_m"
        )
        != panel_model.get("nominal_thickness_m")
    ):
        raise ValueError("Gas-transport diagnostic definition is incomplete")
    common_scales = kinetics.get("parallel_common_scales", [])
    if not common_scales or any(float(scale) <= 0.0 for scale in common_scales):
        raise ValueError("Parallel Arrhenius common scales must be positive")
    replicate_groups = data.get("plywood_replicates", [])
    if len(replicate_groups) != 2 or any(
        len(group.get("samples", [])) != 3 for group in replicate_groups
    ):
        raise ValueError("Calibration reference must contain three plywood replicates per flux")
    split = data.get("replicate_split", {})
    selection_ids = set(split.get("selection_sample_ids", []))
    validation_ids = set(split.get("validation_sample_ids", []))
    if not selection_ids or not validation_ids or selection_ids & validation_ids:
        raise ValueError("Replicate selection and validation IDs must be non-empty and disjoint")
    for group in replicate_groups:
        available_ids = {sample["sample_id"] for sample in group["samples"]}
        if selection_ids | validation_ids != available_ids:
            raise ValueError("Replicate split must account for every sample in each flux group")
    holdout = data.get("holdout", {})
    if holdout.get("used_for_parameter_selection") is not False:
        raise ValueError("Holdout must be excluded from parameter selection")
    if len(holdout.get("targets", [])) != 2:
        raise ValueError("Calibration reference must contain two holdout targets")
    return data


def build_replicate_split_targets(reference: dict) -> tuple[list[dict], list[dict]]:
    """Build fixed selection and same-material validation targets from raw replicates."""

    split = reference["replicate_split"]
    numeric_keys = (
        "time_to_sustained_ignition_s",
        "average_mass_loss_rate_g_s_m2",
        "initial_specimen_mass_g",
        "final_specimen_mass_g",
    )

    def aggregate(sample_ids: list[str]) -> list[dict]:
        targets = []
        for group in reference["plywood_replicates"]:
            selected = [
                sample
                for sample in group["samples"]
                if sample["sample_id"] in sample_ids
            ]
            if len(selected) != len(sample_ids):
                raise ValueError("Replicate split references a missing sample")
            target = {
                "incident_heat_flux_kw_m2": group["incident_heat_flux_kw_m2"],
                "sample_ids": list(sample_ids),
            }
            target.update(
                {
                    key: sum(float(sample[key]) for sample in selected) / len(selected)
                    for key in numeric_keys
                }
            )
            targets.append(target)
        return targets

    return (
        aggregate(split["selection_sample_ids"]),
        aggregate(split["validation_sample_ids"]),
    )


def create_equivalent_coupon(
    target: dict,
    reference: dict,
    parameters: WoodModelParameters,
) -> WoodThermalModel:
    """Map the one-sided square specimen to the existing cylindrical grid."""

    area_m2 = float(reference["method"]["exposed_area_m2"])
    moisture_ratio = float(
        reference["adapter_assumptions"]["moisture_ratio_dry_basis"]
    )
    initial_wet_mass_kg = float(target["initial_specimen_mass_g"]) / 1000.0
    dry_mass_kg = initial_wet_mass_kg / (1.0 + moisture_ratio)
    radius_m = math.sqrt(area_m2 / math.pi)
    thickness_m = dry_mass_kg / (
        parameters.dry_wood_density_kg_m3 * area_m2
    )
    model = create_cylindrical_wood_model(
        f"NistCoupon_{int(target['incident_heat_flux_kw_m2'])}",
        radius_m,
        thickness_m,
        moisture_ratio,
        axial_cells=2,
        circumferential_cells=4,
        radial_cells=1,
        parameters=parameters,
    )

    cells_per_section = model.spec.circumferential_cells
    for index, cell in enumerate(model.cells):
        exposed_face = index // cells_per_section == 0
        cell.external_area_m2 = area_m2 / cells_per_section if exposed_face else 0.0
        cell.surface_exposure = 1.0 if exposed_face else 0.0
        cell.oxygen_factor = cell.surface_exposure
    return model


def create_layered_coupon(
    target: dict,
    reference: dict,
    parameters: WoodModelParameters,
    *,
    material_kind: str = "plywood",
) -> LayeredPanelThermalModel:
    """Create a mass-preserving planar panel with explicit nominal thickness."""

    if material_kind not in {"plywood", "osb"}:
        raise ValueError("material_kind must be 'plywood' or 'osb'")
    panel = reference["panel_model"]
    material_profile = reference["material_property_profiles"][material_kind]
    heat_capacity_model = reference["temperature_dependent_heat_capacity"]
    layer_count = (
        panel["plywood_layer_count"]
        if material_kind == "plywood"
        else panel["osb_layer_count"]
    )
    orientations = (
        tuple(panel["plywood_grain_orientation_assumption_deg"])
        if material_kind == "plywood"
        else (0.0,)
    )
    return create_layered_panel_model(
        f"Nist_{material_kind}_{int(target['incident_heat_flux_kw_m2'])}",
        width_m=float(reference["method"]["sample_width_m"]),
        depth_m=float(reference["method"]["sample_depth_m"]),
        thickness_m=float(panel["nominal_thickness_m"]),
        layer_count=int(layer_count),
        initial_wet_mass_kg=float(target["initial_specimen_mass_g"]) / 1000.0,
        moisture_ratio_dry_basis=float(
            reference["adapter_assumptions"]["moisture_ratio_dry_basis"]
        ),
        layer_orientations_deg=orientations,
        parameters=parameters,
        material_kind=material_kind,
        through_thickness_conductivity_w_m_k=float(
            material_profile["thermal_conductivity_w_m_k"]
        ),
        dry_wood_specific_heat_j_kg_k=float(
            material_profile["specific_heat_j_kg_k"]
        ),
        dry_wood_specific_heat_model=str(heat_capacity_model["model"]),
        adhesive_interface_count=int(
            material_profile["adhesive_interface_count"]
        ),
        adhesive_geometry_explicit=bool(
            material_profile["adhesive_geometry_explicit"]
        ),
        material_property_source=str(
            reference["material_property_profiles"]["source"]
        ),
    )


def simulate_equivalent_coupon(
    target: dict,
    reference: dict,
    parameters: WoodModelParameters,
    dt_seconds: float = CALIBRATION_DT_SECONDS,
    duration_seconds: float = CALIBRATION_DURATION_SECONDS,
) -> CouponResult:
    """Run the retained Phase 6A cylindrical adapter for comparison."""

    if parameters.radiant_absorptivity <= 0.0 or parameters.radiant_absorptivity > 1.0:
        raise ValueError("radiant_absorptivity must be within (0, 1]")
    model = create_equivalent_coupon(target, reference, parameters)
    return _simulate_coupon_model(
        model,
        target,
        reference,
        dt_seconds,
        duration_seconds,
        model_kind="equivalent_cylinder_legacy",
        layer_count=0,
        effective_dry_density_kg_m3=parameters.dry_wood_density_kg_m3,
    )


def simulate_layered_coupon(
    target: dict,
    reference: dict,
    parameters: WoodModelParameters,
    dt_seconds: float = CALIBRATION_DT_SECONDS,
    duration_seconds: float = CALIBRATION_DURATION_SECONDS,
    *,
    material_kind: str = "plywood",
) -> CouponResult:
    """Run an explicit planar plywood or OSB through-thickness model."""

    if parameters.radiant_absorptivity <= 0.0 or parameters.radiant_absorptivity > 1.0:
        raise ValueError("radiant_absorptivity must be within (0, 1]")
    model = create_layered_coupon(
        target, reference, parameters, material_kind=material_kind
    )
    return _simulate_coupon_model(
        model,
        target,
        reference,
        dt_seconds,
        duration_seconds,
        model_kind=f"layered_{material_kind}",
        layer_count=model.spec.layer_count,
        effective_dry_density_kg_m3=model.spec.effective_dry_density_kg_m3,
    )


def _simulate_coupon_model(
    model: WoodThermalModel,
    target: dict,
    reference: dict,
    dt_seconds: float,
    duration_seconds: float,
    *,
    model_kind: str,
    layer_count: int,
    effective_dry_density_kg_m3: float,
) -> CouponResult:
    heat_flux_w_m2 = float(target["incident_heat_flux_kw_m2"]) * 1000.0
    ignition_seconds = None
    burning_mass_loss_rates = []
    steps = int(round(duration_seconds / dt_seconds))
    for _ in range(steps):
        result = model.step(dt_seconds, heat_flux_w_m2)
        released_rate_kg_s = (
            result.evaporated_water_rate_kg_s
            + result.pyrolysis_gas_rate_kg_s
            + result.char_oxidation_gas_rate_kg_s
        )
        if (
            ignition_seconds is None
            and result.pyrolysis_gas_rate_kg_s >= IGNITION_GAS_RATE_KG_S
        ):
            ignition_seconds = result.elapsed_seconds
        if ignition_seconds is not None and released_rate_kg_s >= IGNITION_GAS_RATE_KG_S:
            burning_mass_loss_rates.append(released_rate_kg_s)

    area_m2 = float(reference["method"]["exposed_area_m2"])
    mean_rate_kg_s = (
        sum(burning_mass_loss_rates) / len(burning_mass_loss_rates)
        if burning_mass_loss_rates
        else 0.0
    )
    metrics = model.metrics()
    return CouponResult(
        incident_heat_flux_kw_m2=heat_flux_w_m2 / 1000.0,
        ignition_seconds=ignition_seconds,
        average_mass_loss_rate_g_s_m2=mean_rate_kg_s * 1000.0 / area_m2,
        initial_mass_kg=model.initial_mass_kg,
        remaining_mass_kg=model.current_mass_kg,
        mass_balance_error_kg=model.mass_balance_error_kg,
        all_values_finite=all(
            math.isfinite(cell.temperature_k)
            and math.isfinite(cell.current_mass_kg)
            for cell in model.cells
        ),
        model_kind=model_kind,
        specimen_thickness_m=float(
            reference["panel_model"]["nominal_thickness_m"]
            if layer_count
            else model.spec.length_m
        ),
        layer_count=layer_count,
        effective_dry_density_kg_m3=effective_dry_density_kg_m3,
        final_layer_temperatures_k=tuple(cell.temperature_k for cell in model.cells),
        primary_product_mass_kg={
            "gas": metrics["emitted_primary_gas_kg"],
            "tar": metrics["emitted_tar_kg"],
            "char": metrics["produced_primary_char_kg"],
        },
        primary_product_yield_fraction=metrics[
            "primary_product_yield_fraction"
        ],
        post_secondary_product_mass_kg={
            "gas": metrics["emitted_primary_gas_kg"]
            + metrics["converted_secondary_tar_kg"],
            "tar": metrics["emitted_uncracked_tar_kg"],
            "char": metrics["produced_primary_char_kg"],
        },
        post_secondary_product_yield_fraction=metrics[
            "post_secondary_product_yield_fraction"
        ],
        material_kind=getattr(model.spec, "material_kind", "generic_wood"),
        through_thickness_conductivity_w_m_k=float(
            getattr(
                model.spec,
                "through_thickness_conductivity_w_m_k",
                model.parameters.conductivity_radial_w_m_k,
            )
        ),
        dry_wood_specific_heat_j_kg_k=float(
            getattr(
                model.spec,
                "dry_wood_specific_heat_j_kg_k",
                model.parameters.wood_specific_heat_j_kg_k,
            )
        ),
        dry_wood_specific_heat_model=str(
            getattr(
                model.spec,
                "dry_wood_specific_heat_model",
                CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
            )
        ),
        dry_wood_specific_heat_valid_range_k=(
            tuple(
                float(value)
                for value in reference["temperature_dependent_heat_capacity"][
                    "source_valid_temperature_range_k"
                ]
            )
            if getattr(
                model.spec,
                "dry_wood_specific_heat_model",
                CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
            )
            == USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL
            else ()
        ),
        final_layer_dry_wood_specific_heats_j_kg_k=tuple(
            temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                (
                    cell.dry_wood_specific_heat_j_kg_k
                    if cell.dry_wood_specific_heat_j_kg_k is not None
                    else model.parameters.wood_specific_heat_j_kg_k
                ),
                cell.temperature_k,
                cell.dry_wood_specific_heat_model,
            )
            for cell in model.cells
        ),
        adhesive_interface_count=int(
            getattr(model.spec, "adhesive_interface_count", 0)
        ),
        adhesive_geometry_explicit=bool(
            getattr(model.spec, "adhesive_geometry_explicit", False)
        ),
    )


def _relative_error(predicted: float | None, observed: float) -> float:
    if predicted is None or not math.isfinite(predicted):
        return 4.0
    return abs(predicted - observed) / observed


def evaluate_parameters(
    reference: dict,
    parameters: WoodModelParameters,
    targets: list[dict] | None = None,
    *,
    model_kind: str = "layered_plywood",
) -> dict:
    cases = []
    squared_errors = []
    for target in targets or reference["targets"]:
        if model_kind == "equivalent_cylinder_legacy":
            result = simulate_equivalent_coupon(target, reference, parameters)
        elif model_kind in {"layered_plywood", "layered_osb"}:
            result = simulate_layered_coupon(
                target,
                reference,
                parameters,
                material_kind=model_kind.removeprefix("layered_"),
            )
        else:
            raise ValueError(f"Unsupported coupon model: {model_kind}")
        ignition_error = _relative_error(
            result.ignition_seconds,
            float(target["time_to_sustained_ignition_s"]),
        )
        mass_loss_error = _relative_error(
            result.average_mass_loss_rate_g_s_m2,
            float(target["average_mass_loss_rate_g_s_m2"]),
        )
        squared_errors.extend((ignition_error**2, mass_loss_error**2))
        cases.append(
            {
                "incident_heat_flux_kw_m2": result.incident_heat_flux_kw_m2,
                "observed_ignition_seconds": target["time_to_sustained_ignition_s"],
                "predicted_ignition_seconds": result.ignition_seconds,
                "ignition_relative_error": ignition_error,
                "observed_mass_loss_rate_g_s_m2": target[
                    "average_mass_loss_rate_g_s_m2"
                ],
                "predicted_mass_loss_rate_g_s_m2": (
                    result.average_mass_loss_rate_g_s_m2
                ),
                "mass_loss_relative_error": mass_loss_error,
                "mass_balance_error_kg": result.mass_balance_error_kg,
                "all_values_finite": result.all_values_finite,
                "model_kind": result.model_kind,
                "specimen_thickness_m": result.specimen_thickness_m,
                "layer_count": result.layer_count,
                "effective_dry_density_kg_m3": result.effective_dry_density_kg_m3,
                "final_layer_temperatures_k": list(
                    result.final_layer_temperatures_k
                ),
                "primary_product_mass_kg": result.primary_product_mass_kg,
                "primary_product_yield_fraction": (
                    result.primary_product_yield_fraction
                ),
                "post_secondary_product_mass_kg": (
                    result.post_secondary_product_mass_kg
                ),
                "post_secondary_product_yield_fraction": (
                    result.post_secondary_product_yield_fraction
                ),
                "material_kind": result.material_kind,
                "through_thickness_conductivity_w_m_k": (
                    result.through_thickness_conductivity_w_m_k
                ),
                "dry_wood_specific_heat_j_kg_k": (
                    result.dry_wood_specific_heat_j_kg_k
                ),
                "dry_wood_specific_heat_model": result.dry_wood_specific_heat_model,
                "dry_wood_specific_heat_valid_range_k": list(
                    result.dry_wood_specific_heat_valid_range_k
                ),
                "final_layer_dry_wood_specific_heats_j_kg_k": list(
                    result.final_layer_dry_wood_specific_heats_j_kg_k
                ),
                "adhesive_interface_count": result.adhesive_interface_count,
                "adhesive_geometry_explicit": result.adhesive_geometry_explicit,
            }
        )
    return {
        "score_rmse_relative": math.sqrt(sum(squared_errors) / len(squared_errors)),
        "parameters": _parameter_summary(parameters),
        "cases": cases,
    }


def _parameter_summary(parameters: WoodModelParameters) -> dict:
    return {
        "radiant_absorptivity": parameters.radiant_absorptivity,
        "pyrolysis_rate_model": parameters.pyrolysis_rate_model,
        "pyrolysis_start_temperature_k": parameters.pyrolysis_start_temperature_k,
        "pyrolysis_full_temperature_k": parameters.pyrolysis_full_temperature_k,
        "pyrolysis_max_fraction_s": parameters.pyrolysis_max_fraction_s,
        "pyrolysis_arrhenius_preexponential_s": (
            parameters.pyrolysis_arrhenius_preexponential_s
        ),
        "pyrolysis_arrhenius_activation_energy_j_mol": (
            parameters.pyrolysis_arrhenius_activation_energy_j_mol
        ),
        "pyrolysis_arrhenius_reaction_order": (
            parameters.pyrolysis_arrhenius_reaction_order
        ),
        "pyrolysis_arrhenius_source_label": (
            parameters.pyrolysis_arrhenius_source_label
        ),
        "pyrolysis_parallel_common_scale": parameters.pyrolysis_parallel_common_scale,
        "pyrolysis_parallel_gas_preexponential_s": (
            parameters.pyrolysis_parallel_gas_preexponential_s
        ),
        "pyrolysis_parallel_gas_activation_energy_j_mol": (
            parameters.pyrolysis_parallel_gas_activation_energy_j_mol
        ),
        "pyrolysis_parallel_tar_preexponential_s": (
            parameters.pyrolysis_parallel_tar_preexponential_s
        ),
        "pyrolysis_parallel_tar_activation_energy_j_mol": (
            parameters.pyrolysis_parallel_tar_activation_energy_j_mol
        ),
        "pyrolysis_parallel_char_preexponential_s": (
            parameters.pyrolysis_parallel_char_preexponential_s
        ),
        "pyrolysis_parallel_char_activation_energy_j_mol": (
            parameters.pyrolysis_parallel_char_activation_energy_j_mol
        ),
        "pyrolysis_parallel_source_label": parameters.pyrolysis_parallel_source_label,
        "secondary_tar_cracking_enabled": parameters.secondary_tar_cracking_enabled,
        "secondary_tar_cracking_residence_time_s": (
            parameters.secondary_tar_cracking_residence_time_s
        ),
        "secondary_tar_cracking_preexponential_s": (
            parameters.secondary_tar_cracking_preexponential_s
        ),
        "secondary_tar_cracking_activation_energy_j_mol": (
            parameters.secondary_tar_cracking_activation_energy_j_mol
        ),
        "secondary_tar_cracking_min_temperature_k": (
            parameters.secondary_tar_cracking_min_temperature_k
        ),
        "secondary_tar_cracking_max_temperature_k": (
            parameters.secondary_tar_cracking_max_temperature_k
        ),
        "secondary_tar_cracking_source_label": (
            parameters.secondary_tar_cracking_source_label
        ),
    }


def arrhenius_baseline_parameters(reference: dict | None = None) -> WoodModelParameters:
    """Use the published char-pathway pair as the unscaled Arrhenius baseline."""

    data = reference or load_nist_plywood_reference()
    pathway = data["arrhenius_model"]["source_pathways"][2]
    return replace(
        WoodModelParameters(),
        pyrolysis_rate_model="arrhenius_first_order",
        pyrolysis_arrhenius_preexponential_s=float(pathway["preexponential_s"]),
        pyrolysis_arrhenius_activation_energy_j_mol=float(
            pathway["activation_energy_j_mol"]
        ),
        pyrolysis_arrhenius_reaction_order=float(
            data["arrhenius_model"]["reaction_order"]
        ),
        pyrolysis_arrhenius_source_label=str(pathway["label"]),
    )


def parallel_arrhenius_baseline_parameters(
    reference: dict | None = None,
) -> WoodModelParameters:
    """Use all three published mass-basis pathways without relative refitting."""

    data = reference or load_nist_plywood_reference()
    pathways = {
        pathway["product"]: pathway
        for pathway in data["arrhenius_model"]["source_pathways"]
    }
    secondary_tar = data["secondary_tar_cracking"]
    secondary_temperature_range = secondary_tar["application_temperature_range_k"]
    return replace(
        WoodModelParameters(),
        pyrolysis_rate_model="arrhenius_parallel_first_order",
        pyrolysis_arrhenius_reaction_order=float(
            data["arrhenius_model"]["reaction_order"]
        ),
        pyrolysis_parallel_common_scale=1.0,
        pyrolysis_parallel_gas_preexponential_s=float(
            pathways["gas"]["preexponential_s"]
        ),
        pyrolysis_parallel_gas_activation_energy_j_mol=float(
            pathways["gas"]["activation_energy_j_mol"]
        ),
        pyrolysis_parallel_tar_preexponential_s=float(
            pathways["tar"]["preexponential_s"]
        ),
        pyrolysis_parallel_tar_activation_energy_j_mol=float(
            pathways["tar"]["activation_energy_j_mol"]
        ),
        pyrolysis_parallel_char_preexponential_s=float(
            pathways["char"]["preexponential_s"]
        ),
        pyrolysis_parallel_char_activation_energy_j_mol=float(
            pathways["char"]["activation_energy_j_mol"]
        ),
        pyrolysis_parallel_source_label=(
            "Thurner-Mann gas + tar + char competing branches"
        ),
        secondary_tar_cracking_enabled=True,
        secondary_tar_cracking_residence_time_s=float(
            secondary_tar["residence_time_s"]
        ),
        secondary_tar_cracking_preexponential_s=float(
            secondary_tar["preexponential_s"]
        ),
        secondary_tar_cracking_activation_energy_j_mol=float(
            secondary_tar["activation_energy_j_mol"]
        ),
        secondary_tar_cracking_min_temperature_k=float(
            secondary_temperature_range[0]
        ),
        secondary_tar_cracking_max_temperature_k=float(
            secondary_temperature_range[1]
        ),
        secondary_tar_cracking_source_label="Di Blasi Model III tar-to-gas branch",
    )


def calibration_candidates(reference: dict | None = None) -> list[WoodModelParameters]:
    data = reference or load_nist_plywood_reference()
    baseline = parallel_arrhenius_baseline_parameters(data)
    candidates = []
    for absorptivity in (0.55, 0.70, 0.85, 1.0):
        for scale in data["arrhenius_model"]["parallel_common_scales"]:
            candidates.append(
                replace(
                    baseline,
                    radiant_absorptivity=absorptivity,
                    pyrolysis_parallel_common_scale=float(scale),
                )
            )
    unique = {}
    for candidate in candidates:
        key = (
            candidate.radiant_absorptivity,
            candidate.pyrolysis_start_temperature_k,
            candidate.pyrolysis_full_temperature_k,
            candidate.pyrolysis_max_fraction_s,
            candidate.pyrolysis_rate_model,
            candidate.pyrolysis_arrhenius_preexponential_s,
            candidate.pyrolysis_arrhenius_activation_energy_j_mol,
            candidate.pyrolysis_parallel_common_scale,
        )
        unique[key] = candidate
    return list(unique.values())


def evaluate_secondary_tar_residence_sensitivity(
    reference: dict,
    parameters: WoodModelParameters,
    one_second_evaluation: dict,
) -> dict:
    """Apply source-bounded residence scenarios without selecting or refitting them."""

    definition = reference["secondary_tar_cracking"]["residence_time_sensitivity"]
    scenarios = []
    for residence_time_s in definition["scenarios_s"]:
        if math.isclose(
            float(residence_time_s),
            parameters.secondary_tar_cracking_residence_time_s,
        ):
            evaluation = one_second_evaluation
        else:
            evaluation = evaluate_parameters(
                reference,
                replace(
                    parameters,
                    secondary_tar_cracking_residence_time_s=float(
                        residence_time_s
                    ),
                ),
            )
        scenarios.append(
            {
                "residence_time_s": float(residence_time_s),
                "used_for_parameter_selection": False,
                "score_rmse_relative": evaluation["score_rmse_relative"],
                "cases": evaluation["cases"],
            }
        )
    return {
        "source": definition["source"],
        "source_doi": definition["source_doi"],
        "experiment_temperature_range_k": definition[
            "experiment_temperature_range_k"
        ],
        "experiment_residence_time_range_s": definition[
            "experiment_residence_time_range_s"
        ],
        "experiment_tar_conversion_range_fraction": definition[
            "experiment_tar_conversion_range_fraction"
        ],
        "used_for_parameter_selection": False,
        "scenarios": scenarios,
    }


def evaluate_gas_transport_readiness(reference: dict) -> dict:
    """Report the independent Darcy input contract without inventing missing state."""

    definition = reference["gas_transport_diagnostic"]
    missing_inputs = list(definition["missing_current_panel_inputs"])
    return {
        "model": definition["model"],
        "equations": definition["equations"],
        "source": definition["source"],
        "source_doi": definition["source_doi"],
        "source_context": definition["source_context"],
        "current_panel_known_inputs": definition["current_panel_known_inputs"],
        "missing_current_panel_inputs": missing_inputs,
        "ready_for_secondary_tar_coupling": not missing_inputs,
        "used_for_parameter_selection": False,
        "predicted_residence_time_s": None,
        "policy": definition["policy"],
    }


def run_nist_plywood_calibration() -> dict:
    reference = load_nist_plywood_reference()
    baseline_parameters = parallel_arrhenius_baseline_parameters(reference)
    selection_targets, validation_targets = build_replicate_split_targets(reference)
    selection_baseline = evaluate_parameters(
        reference, baseline_parameters, selection_targets
    )
    evaluated = [
        (
            candidate,
            evaluate_parameters(reference, candidate, selection_targets),
        )
        for candidate in calibration_candidates(reference)
    ]
    evaluated.sort(key=lambda item: item[1]["score_rmse_relative"])
    best_parameters, selection_best = evaluated[0]
    ranked = [result for _, result in evaluated]
    baseline = evaluate_parameters(reference, baseline_parameters)
    best = evaluate_parameters(reference, best_parameters)
    secondary_tar_residence_sensitivity = (
        evaluate_secondary_tar_residence_sensitivity(
            reference, best_parameters, best
        )
    )
    gas_transport_readiness = evaluate_gas_transport_readiness(reference)
    validation_baseline = evaluate_parameters(
        reference, baseline_parameters, validation_targets
    )
    validation_calibrated = evaluate_parameters(
        reference, best_parameters, validation_targets
    )
    validation_score_change_fraction = 1.0 - (
        validation_calibrated["score_rmse_relative"]
        / validation_baseline["score_rmse_relative"]
    )
    holdout = reference["holdout"]
    holdout_baseline = evaluate_parameters(
        reference,
        baseline_parameters,
        holdout["targets"],
        model_kind="layered_osb",
    )
    holdout_calibrated = evaluate_parameters(
        reference,
        best_parameters,
        holdout["targets"],
        model_kind="layered_osb",
    )
    holdout_score_change_fraction = 1.0 - (
        holdout_calibrated["score_rmse_relative"]
        / holdout_baseline["score_rmse_relative"]
    )
    return {
        "reference": {
            key: reference[key]
            for key in ("reference_id", "title", "report", "published", "url", "location")
        },
        "calibration_material": reference["material"],
        "adapter_assumptions": reference["adapter_assumptions"],
        "panel_model": reference["panel_model"],
        "material_property_profiles": reference["material_property_profiles"],
        "temperature_dependent_heat_capacity": reference[
            "temperature_dependent_heat_capacity"
        ],
        "secondary_tar_cracking": reference["secondary_tar_cracking"],
        "secondary_tar_residence_sensitivity": (
            secondary_tar_residence_sensitivity
        ),
        "gas_transport_readiness": gas_transport_readiness,
        "arrhenius_model": reference["arrhenius_model"],
        "candidate_count": len(ranked),
        "selection": {
            "strategy": reference["replicate_split"]["strategy"],
            "sample_ids": reference["replicate_split"]["selection_sample_ids"],
            "targets": selection_targets,
            "baseline": selection_baseline,
            "best": selection_best,
            "improvement_fraction": 1.0
            - selection_best["score_rmse_relative"]
            / selection_baseline["score_rmse_relative"],
            "improved": (
                selection_best["score_rmse_relative"]
                < selection_baseline["score_rmse_relative"]
            ),
        },
        "baseline": baseline,
        "best": best,
        "improvement_fraction": 1.0
        - best["score_rmse_relative"] / baseline["score_rmse_relative"],
        "improved": best["score_rmse_relative"] < baseline["score_rmse_relative"],
        "top_candidates": ranked[:5],
        "replicate_holdout": {
            "material": reference["material"],
            "sample_ids": reference["replicate_split"]["validation_sample_ids"],
            "used_for_parameter_selection": False,
            "targets": validation_targets,
            "baseline": validation_baseline,
            "calibrated": validation_calibrated,
            "score_change_fraction": validation_score_change_fraction,
            "improved": (
                validation_calibrated["score_rmse_relative"]
                < validation_baseline["score_rmse_relative"]
            ),
        },
        "holdout": {
            "material": holdout["material"],
            "relationship": holdout["relationship"],
            "used_for_parameter_selection": holdout[
                "used_for_parameter_selection"
            ],
            "baseline": holdout_baseline,
            "calibrated": holdout_calibrated,
            "score_change_fraction": holdout_score_change_fraction,
            "improved": (
                holdout_calibrated["score_rmse_relative"]
                < holdout_baseline["score_rmse_relative"]
            ),
        },
        "model_scope": (
            "Nominal 12.7 mm planar panel with five equal plywood plies; cone-specimen "
            "thickness is inferred from the source roof panel; aggregate NIST roof-sheathing "
            "conductivity and heat capacity distinguish plywood from OSB while measured cone "
            "mass still determines density; the USDA dry-wood cp(T) shape is normalized to "
            "each panel value, clamped to its 280-420 K source range, and not extrapolated "
            "through pyrolysis; four plywood adhesive interfaces are recorded "
            "without invented geometry or extra resistance; "
            "with competing first-order gas, tar, and char pathways using published "
            "mass-basis kinetics and one common calibration scale; a bounded, fixed-one-second "
            "tar-to-gas diagnostic reclassifies product mass without changing the solid heat "
            "balance or total volatile release."
        ),
    }


def write_calibration_svg(calibration: dict, destination: Path) -> Path:
    """Write a dependency-free, browser-readable calibration comparison."""

    improvement = calibration["improvement_fraction"] * 100.0
    return _write_comparison_svg(
        calibration["baseline"],
        calibration["best"],
        destination,
        title="Phase 6H — Bounded cp(T) plywood calibration",
        subtitle="Exterior-plywood k · USDA-normalized cp(T) · competing gas / tar / char rates",
        summary=(
            "Relative RMSE: baseline "
            f"{calibration['baseline']['score_rmse_relative']:.3f} → calibrated "
            f"{calibration['best']['score_rmse_relative']:.3f} "
            f"({improvement:.1f}% improvement)"
        ),
        scope=(
            "Scope: one common A scale and absorptivity selected on SAMP.1/2; relative "
            "gas/tar/char rates stay fixed to the published mass-basis kinetics."
        ),
    )


def write_holdout_svg(calibration: dict, destination: Path) -> Path:
    """Write the no-refit OSB external-material holdout comparison."""

    holdout = calibration["holdout"]
    score_change = holdout["score_change_fraction"] * 100.0
    return _write_comparison_svg(
        holdout["baseline"],
        holdout["calibrated"],
        destination,
        title="Phase 6H — Bounded cp(T) OSB holdout",
        subtitle="OSB-specific k · USDA-normalized cp(T) · plywood-fit reaction parameters",
        summary=(
            "Relative RMSE (no refit): baseline "
            f"{holdout['baseline']['score_rmse_relative']:.3f} → plywood-fit "
            f"{holdout['calibrated']['score_rmse_relative']:.3f} "
            f"({score_change:+.1f}% score change)"
        ),
        scope=(
            "Scope: OSB is a different wood product. This is an external-material "
            "stress test, not in-plywood validation."
        ),
        calibrated_label="Plywood-fit",
        ignition_maximum=170.0,
        mass_loss_maximum=22.0,
    )


def write_replicate_holdout_svg(calibration: dict, destination: Path) -> Path:
    """Write the no-refit SAMP.3 same-material validation comparison."""

    holdout = calibration["replicate_holdout"]
    score_change = holdout["score_change_fraction"] * 100.0
    return _write_comparison_svg(
        holdout["baseline"],
        holdout["calibrated"],
        destination,
        title="Phase 6H — Bounded cp(T) plywood replicate holdout",
        subtitle="USDA-normalized cp(T) · SAMP.1/2 fit applied to reserved SAMP.3",
        summary=(
            "Relative RMSE (no refit): baseline "
            f"{holdout['baseline']['score_rmse_relative']:.3f} → SAMP.1/2-fit "
            f"{holdout['calibrated']['score_rmse_relative']:.3f} "
            f"({score_change:+.1f}% score change)"
        ),
        scope=(
            "Scope: same material and heat flux, held-out replicate. This tests "
            "repeatability, not a new exposure condition."
        ),
        calibrated_label="SAMP.1/2-fit",
        ignition_maximum=100.0,
    )


def write_layer_profile_svg(calibration: dict, destination: Path) -> Path:
    """Write the explicit five-ply geometry and final temperature profiles."""

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    panel = calibration["panel_model"]
    cases = calibration["best"]["cases"]
    orientations = panel["plywood_grain_orientation_assumption_deg"]

    def temperature_color(temperature_k: float) -> str:
        fraction = min(1.0, max(0.0, (temperature_k - 293.15) / 900.0))
        red = round(55 + 200 * fraction)
        green = round(117 - 67 * fraction)
        blue = round(112 - 82 * fraction)
        return f"#{red:02x}{green:02x}{blue:02x}"

    panels = []
    for case_index, case in enumerate(cases):
        x = 80 + case_index * 570
        panels.append(
            f'<text x="{x}" y="135" class="panel-title">'
            f'{case["incident_heat_flux_kw_m2"]:.0f} kW/m²</text>'
        )
        panels.append(
            f'<text x="{x}" y="164" class="muted">final state at 600 s</text>'
        )
        temperatures = case["final_layer_temperatures_k"]
        for layer, temperature_k in enumerate(temperatures):
            y = 198 + layer * 66
            panels.extend(
                (
                    f'<rect x="{x}" y="{y}" width="390" height="56" rx="5" '
                    f'fill="{temperature_color(temperature_k)}"/>',
                    f'<text x="{x + 18}" y="{y + 35}" class="layer">'
                    f'Ply {layer + 1} · {orientations[layer]:.0f}°</text>',
                    f'<text x="{x + 365}" y="{y + 35}" class="temperature" '
                    f'text-anchor="end">{temperature_k:.1f} K</text>',
                )
            )
        panels.append(
            f'<text x="{x + 415}" y="232" class="heat">← incident heat</text>'
        )
        panels.append(
            f'<text x="{x}" y="548" class="muted">effective dry density '
            f'{case["effective_dry_density_kg_m3"]:.1f} kg/m³</text>'
        )
        panels.append(
            f'<text x="{x}" y="570" class="muted">k '
            f'{case["through_thickness_conductivity_w_m_k"]:.3f} W/(m·K) · cp(T) '
            f'{case["dry_wood_specific_heat_j_kg_k"]:.0f} @293 K → '
            f'{max(case["final_layer_dry_wood_specific_heats_j_kg_k"]):.0f} J/(kg·K) · '
            f'{case["adhesive_interface_count"]} unresolved glue interfaces</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 15px; fill: #d7b982; }}
    .panel-title {{ font-size: 22px; font-weight: 700; }}
    .layer {{ font-size: 15px; font-weight: 650; }}
    .temperature {{ font-size: 15px; font-weight: 700; }}
    .muted {{ font-size: 13px; fill: #c9bda9; }}
    .heat {{ font-size: 13px; fill: #f09a61; }}
    .note {{ font-size: 14px; fill: #f0d8ad; }}
  </style>
  <text x="60" y="52" class="title">Phase 6H — Bounded temperature-dependent cp</text>
  <text x="60" y="82" class="subtitle">0.1 m × 0.1 m × 12.7 mm nominal · five equal 2.54 mm plies · exposed from ply 1</text>
  {''.join(panels)}
  <line x1="60" y1="585" x2="1140" y2="585" stroke="#53483d"/>
  <text x="60" y="620" class="note">Sides and rear are foil-wrapped. The 12.7 mm cone-specimen thickness is inferred from the reported source roof panel.</text>
  <text x="60" y="648" class="muted">USDA dry-wood cp(T) is normalized at 293 K and clamped to 280–420 K; constant k and unresolved glue geometry remain explicit limits.</text>
</svg>'''
    destination.write_text(svg, encoding="utf-8")
    return destination


def write_kinetics_svg(calibration: dict, destination: Path) -> Path:
    """Plot the three competing pathways, total rate, and predicted yields."""

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    baseline = calibration["baseline"]["parameters"]
    selected = calibration["best"]["parameters"]
    gas_constant = float(calibration["arrhenius_model"]["gas_constant_j_mol_k"])
    temperatures = tuple(range(400, 801, 25))

    def pathway_rate(parameters: dict, product: str, temperature_k: float) -> float:
        prefix = f"pyrolysis_parallel_{product}"
        return (
            float(parameters["pyrolysis_parallel_common_scale"])
            * float(parameters[f"{prefix}_preexponential_s"])
            * math.exp(
                -float(parameters[f"{prefix}_activation_energy_j_mol"])
                / (gas_constant * temperature_k)
            )
        )

    def total_rate(parameters: dict, temperature_k: float) -> float:
        return sum(
            pathway_rate(parameters, product, temperature_k)
            for product in ("gas", "tar", "char")
        )

    secondary_tar = calibration["secondary_tar_cracking"]

    def secondary_tar_rate(temperature_k: float) -> float:
        minimum_k, maximum_k = secondary_tar["application_temperature_range_k"]
        if temperature_k < float(minimum_k):
            return 0.0
        bounded_temperature_k = min(temperature_k, float(maximum_k))
        return float(secondary_tar["preexponential_s"]) * math.exp(
            -float(secondary_tar["activation_energy_j_mol"])
            / (gas_constant * bounded_temperature_k)
        )

    left, top, width, height = 100.0, 150.0, 720.0, 390.0
    minimum_log, maximum_log = -9.0, 2.0

    def point(temperature_k: float, value: float) -> tuple[float, float]:
        x = left + (temperature_k - 400.0) / 400.0 * width
        log_value = min(maximum_log, max(minimum_log, math.log10(max(value, 1e-12))))
        y = top + (maximum_log - log_value) / (maximum_log - minimum_log) * height
        return x, y

    def polyline(rate_function) -> str:
        return " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (point(t, rate_function(t)) for t in temperatures)
        )

    grid = []
    for exponent in range(-8, 3, 2):
        y = point(400.0, 10.0**exponent)[1]
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" class="grid"/>'
            f'<text x="{left - 16}" y="{y + 5:.1f}" class="axis" text-anchor="end">10^{exponent}</text>'
        )
    for temperature in range(400, 801, 100):
        x = point(float(temperature), 1.0)[0]
        grid.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + height}" class="grid"/>'
            f'<text x="{x:.1f}" y="{top + height + 28}" class="axis" text-anchor="middle">{temperature}</text>'
        )

    pathway_lines = []
    colors = {"gas": "#f0a45d", "tar": "#66a8d8", "char": "#c98b72"}
    for product in ("gas", "tar", "char"):
        pathway_lines.append(
            f'<polyline points="{polyline(lambda t, p=product: pathway_rate(baseline, p, t))}" '
            f'fill="none" stroke="{colors[product]}" stroke-width="2.5"/>'
        )

    yield_rows = []
    for index, case in enumerate(calibration["best"]["cases"]):
        primary_yields = case["primary_product_yield_fraction"]
        final_yields = case["post_secondary_product_yield_fraction"]
        yield_rows.append(
            f'<text x="870" y="{402 + index * 52}" class="value">'
            f'{case["incident_heat_flux_kw_m2"]:.0f} kW/m² · '
            f'primary gas/tar {100.0 * primary_yields["gas"]:.1f}/{100.0 * primary_yields["tar"]:.1f}%</text>'
            f'<text x="890" y="{423 + index * 52}" class="value">'
            f'after 1 s gas/tar {100.0 * final_yields["gas"]:.1f}/{100.0 * final_yields["tar"]:.1f}% · '
            f'char {100.0 * final_yields["char"]:.1f}%</text>'
        )

    selected_scale = float(selected["pyrolysis_parallel_common_scale"])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 15px; fill: #d7b982; }}
    .axis {{ font-size: 13px; fill: #c9bda9; }}
    .grid {{ stroke: #493f36; stroke-width: 1; }}
    .legend {{ font-size: 14px; font-weight: 650; }}
    .value {{ font-size: 13px; fill: #eadbc4; }}
    .note {{ font-size: 13px; fill: #c9bda9; }}
  </style>
  <text x="60" y="52" class="title">Phase 6I — Secondary tar diagnostic</text>
  <text x="60" y="82" class="subtitle">Primary gas / tar / char plus bounded tar → gas conversion · logarithmic axis</text>
  {''.join(grid)}
  {''.join(pathway_lines)}
  <polyline points="{polyline(lambda t: total_rate(baseline, t))}" fill="none" stroke="#df654e" stroke-width="4" stroke-dasharray="10 7"/>
  <polyline points="{polyline(lambda t: total_rate(selected, t))}" fill="none" stroke="#58b889" stroke-width="4"/>
  <polyline points="{polyline(secondary_tar_rate)}" fill="none" stroke="#b987d9" stroke-width="3" stroke-dasharray="5 5"/>
  <text x="{left + width / 2}" y="595" class="axis" text-anchor="middle">Temperature (K)</text>
  <text x="30" y="{top + height / 2}" class="axis" text-anchor="middle" transform="rotate(-90 30 {top + height / 2})">Rate constant k (s⁻¹)</text>
  <text x="870" y="158" class="legend">Published branches</text>
  <rect x="870" y="178" width="18" height="5" fill="#f0a45d"/><text x="900" y="185" class="value">gas · A 1.435e4 · E 88.6 kJ/mol</text>
  <rect x="870" y="208" width="18" height="5" fill="#66a8d8"/><text x="900" y="215" class="value">tar · A 4.117e6 · E 112.7 kJ/mol</text>
  <rect x="870" y="238" width="18" height="5" fill="#c98b72"/><text x="900" y="245" class="value">char · A 7.383e5 · E 106.5 kJ/mol</text>
  <line x1="870" y1="278" x2="888" y2="278" stroke="#df654e" stroke-width="4" stroke-dasharray="7 5"/>
  <text x="900" y="283" class="value">published total · common scale 1</text>
  <line x1="870" y1="310" x2="888" y2="310" stroke="#58b889" stroke-width="4"/>
  <text x="900" y="315" class="value">selected total · common scale {selected_scale:g}</text>
  <line x1="870" y1="340" x2="888" y2="340" stroke="#b987d9" stroke-width="3" stroke-dasharray="5 5"/>
  <text x="900" y="345" class="value">secondary tar → gas · A 4.28e6 · E 108 kJ/mol</text>
  <text x="870" y="378" class="legend">Predicted product yields</text>
  {''.join(yield_rows)}
  <line x1="60" y1="620" x2="1140" y2="620" stroke="#53483d"/>
  <text x="60" y="650" class="note">Secondary scenario: τ = 1 s; zero below {float(secondary_tar["application_temperature_range_k"][0]):g} K, clamp above {float(secondary_tar["application_temperature_range_k"][1]):g} K. Diagnostic only; calibration and total volatile mass are unchanged.</text>
</svg>'''
    destination.write_text(svg, encoding="utf-8")
    return destination


def write_tar_residence_sensitivity_svg(
    calibration: dict,
    destination: Path,
) -> Path:
    """Plot post-secondary gas/tar yields across source-bounded residence times."""

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    sensitivity = calibration["secondary_tar_residence_sensitivity"]
    scenarios = sensitivity["scenarios"]
    left, top, width, height = 110.0, 145.0, 690.0, 390.0
    minimum_residence_s, maximum_residence_s = map(
        float, sensitivity["experiment_residence_time_range_s"]
    )
    maximum_yield_percent = 60.0

    def point(residence_time_s: float, yield_fraction: float) -> tuple[float, float]:
        x = left + (
            (residence_time_s - minimum_residence_s)
            / (maximum_residence_s - minimum_residence_s)
            * width
        )
        y = top + height * (1.0 - 100.0 * yield_fraction / maximum_yield_percent)
        return x, y

    series = (
        ("35 kW/m² gas", 0, "gas", "#f0a45d"),
        ("35 kW/m² tar", 0, "tar", "#66a8d8"),
        ("70 kW/m² gas", 1, "gas", "#58b889"),
        ("70 kW/m² tar", 1, "tar", "#b987d9"),
    )
    grid = []
    for yield_percent in range(0, 61, 10):
        y = top + height * (1.0 - yield_percent / maximum_yield_percent)
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" class="grid"/>'
            f'<text x="{left - 18}" y="{y + 5:.1f}" class="axis" text-anchor="end">{yield_percent}%</text>'
        )
    lines = []
    legend = []
    for series_index, (label, case_index, product, color) in enumerate(series):
        points = []
        markers = []
        for scenario_index, scenario in enumerate(scenarios):
            value = scenario["cases"][case_index][
                "post_secondary_product_yield_fraction"
            ][product]
            x, y = point(scenario["residence_time_s"], value)
            if scenario_index == 0:
                label_x, label_anchor = x - 7.0, "end"
            elif scenario_index == 1:
                label_x, label_anchor = x + 7.0, "start"
            else:
                label_x, label_anchor = x, "middle"
            label_y = y - 11.0 if case_index == 0 else y + 20.0
            points.append(f"{x:.1f},{y:.1f}")
            markers.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>'
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="value" text-anchor="{label_anchor}">{100.0 * value:.2f}</text>'
            )
        lines.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>'
            + "".join(markers)
        )
        legend_y = 180 + series_index * 34
        legend.append(
            f'<line x1="855" y1="{legend_y}" x2="880" y2="{legend_y}" stroke="{color}" stroke-width="4"/>'
            f'<text x="895" y="{legend_y + 5}" class="value">{label}</text>'
        )
    x_labels = []
    for scenario in scenarios:
        x, _ = point(scenario["residence_time_s"], 0.0)
        x_labels.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + height}" class="grid"/>'
            f'<text x="{x:.1f}" y="{top + height + 30}" class="axis" text-anchor="middle">{scenario["residence_time_s"]:g}</text>'
        )
    conversion_range = sensitivity["experiment_tar_conversion_range_fraction"]
    temperature_range = sensitivity["experiment_temperature_range_k"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 15px; fill: #d7b982; }}
    .axis {{ font-size: 13px; fill: #c9bda9; }}
    .grid {{ stroke: #493f36; stroke-width: 1; }}
    .legend {{ font-size: 15px; font-weight: 650; }}
    .value {{ font-size: 13px; fill: #eadbc4; }}
    .note {{ font-size: 13px; fill: #c9bda9; }}
  </style>
  <text x="60" y="52" class="title">Phase 6J — Tar residence-time sensitivity</text>
  <text x="60" y="82" class="subtitle">Same selected solid model · no refitting · post-secondary product split only</text>
  {''.join(grid)}
  {''.join(x_labels)}
  {''.join(lines)}
  <text x="{left + width / 2}" y="600" class="axis" text-anchor="middle">Fixed vapor residence scenario τ (s)</text>
  <text x="30" y="{top + height / 2}" class="axis" text-anchor="middle" transform="rotate(-90 30 {top + height / 2})">Cumulative product yield</text>
  <text x="855" y="145" class="legend">Modeled yield sensitivity</text>
  {''.join(legend)}
  <text x="855" y="340" class="legend">Primary experiment envelope</text>
  <text x="855" y="372" class="value">Temperature · {float(temperature_range[0]):g}–{float(temperature_range[1]):g} K</text>
  <text x="855" y="400" class="value">Residence · {minimum_residence_s:g}–{maximum_residence_s:g} s</text>
  <text x="855" y="428" class="value">Observed tar conversion · {100 * conversion_range[0]:.0f}–{100 * conversion_range[1]:.0f}%</text>
  <text x="855" y="468" class="note">Boroson et al. · sweet gum hardwood</text>
  <text x="855" y="491" class="note">Distributed kinetics fit better than one reaction.</text>
  <line x1="60" y1="620" x2="1140" y2="620" stroke="#53483d"/>
  <text x="60" y="650" class="note">The experiment envelope is context, not a fit target. Di Blasi Model III kinetics remain separate; ignition, MLR, heat, and total volatile mass are unchanged.</text>
</svg>'''
    destination.write_text(svg, encoding="utf-8")
    return destination


def write_gas_transport_readiness_svg(
    calibration: dict,
    destination: Path,
) -> Path:
    """Render the Darcy input contract and the current no-coupling gate."""

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    transport = calibration["gas_transport_readiness"]
    context = transport["source_context"]
    known = transport["current_panel_known_inputs"]
    missing_labels = {
        "char_layer_thickness_m": "char-layer thickness L",
        "through_thickness_porosity_fraction": "plywood char porosity ε",
        "through_thickness_permeability_m2": "through-thickness permeability K",
        "gas_dynamic_viscosity_pa_s": "hot mixed-gas viscosity μ(T, composition)",
        "char_layer_pressure_drop_pa": "char-layer pressure drop ΔP",
    }
    missing_values = [
        missing_labels[name] for name in transport["missing_current_panel_inputs"]
    ]
    missing_text_line_1 = " · ".join(missing_values[:3])
    missing_text_line_2 = " · ".join(missing_values[3:])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 15px; fill: #d7b982; }}
    .label {{ font-size: 13px; font-weight: 700; letter-spacing: 1px; }}
    .heading {{ font-size: 19px; font-weight: 700; }}
    .body {{ font-size: 14px; fill: #ded2c0; }}
    .small {{ font-size: 12px; fill: #bcae9a; }}
    .formula {{ font-size: 18px; font-weight: 650; fill: #f4c36d; }}
  </style>
  <text x="60" y="52" class="title">Phase 6K — Independent gas-transport readiness</text>
  <text x="60" y="82" class="subtitle">Complete Darcy input contract · no invented plywood transport properties · no secondary-reaction coupling</text>

  <rect x="60" y="120" width="1080" height="80" rx="10" fill="#1c2820" stroke="#4f966b"/>
  <text x="82" y="148" class="label" fill="#73d79a">KNOWN GEOMETRY</text>
  <text x="82" y="177" class="heading">Overall coupon thickness · {1000.0 * float(known["overall_specimen_thickness_m"]):.1f} mm</text>
  <text x="650" y="169" class="formula">τ = ε μ L² / (K ΔP)</text>

  <rect x="60" y="220" width="1080" height="112" rx="10" fill="#282218" stroke="#a77a38"/>
  <text x="82" y="248" class="label" fill="#e7ad59">SOURCE CONTEXT — NOT PLYWOOD INPUT</text>
  <text x="82" y="278" class="heading">Beech sphere model</text>
  <text x="82" y="306" class="body">wood ε {float(context["wood_porosity_fraction"]):.2f} · char ε {float(context["char_porosity_fraction"]):.2f} · wood K {float(context["wood_permeability_m2"]):.2e} m² · char K {float(context["char_permeability_m2"]):.1e} m² · reference ΔP {float(context["reported_reference_pressure_drop_pa"])/1000.0:.0f} kPa</text>

  <rect x="60" y="352" width="1080" height="126" rx="10" fill="#2a1918" stroke="#ad5149"/>
  <text x="82" y="380" class="label" fill="#ef7f72">MISSING CURRENT-PANEL STATE · 5 INPUTS</text>
  <text x="82" y="410" class="body">{missing_text_line_1}</text>
  <text x="82" y="437" class="body">{missing_text_line_2}</text>
  <text x="82" y="462" class="small">The five-ply thermal cells do not yet resolve shrinkage, open pore volume, pressure, or gas composition.</text>

  <rect x="60" y="498" width="1080" height="92" rx="10" fill="#211817" stroke="#e06555" stroke-width="2"/>
  <text x="82" y="530" class="label" fill="#ff8f7e">COUPLING GATE</text>
  <text x="82" y="563" class="heading">Residence time withheld · secondary tar remains a non-coupled sensitivity diagnostic</text>

  <line x1="60" y1="620" x2="1140" y2="620" stroke="#53483d"/>
  <text x="60" y="650" class="small">Pozzobon et al. (2014), Fuel Processing Technology 128, 319–330 · Darcy flow validated for their beech-sphere model; values are contextual here.</text>
</svg>'''
    destination.write_text(svg, encoding="utf-8")
    return destination


def _write_comparison_svg(
    baseline: dict,
    best: dict,
    destination: Path,
    *,
    title: str,
    subtitle: str,
    summary: str,
    scope: str,
    calibrated_label: str = "Calibrated",
    ignition_maximum: float = 80.0,
    mass_loss_maximum: float = 18.0,
) -> Path:

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    colors = {"observed": "#f3d7a1", "baseline": "#df654e", "calibrated": "#58b889"}
    labels = {
        "observed": "Observed",
        "baseline": "Baseline",
        "calibrated": calibrated_label,
    }
    panels = (
        (
            "Time to ignition (s)",
            "observed_ignition_seconds",
            "predicted_ignition_seconds",
            ignition_maximum,
        ),
        (
            "Average mass-loss rate (g/s/m²)",
            "observed_mass_loss_rate_g_s_m2",
            "predicted_mass_loss_rate_g_s_m2",
            mass_loss_maximum,
        ),
    )
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">',
        '<rect width="1200" height="680" fill="#17130f"/>',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#f4eadb}.muted{fill:#b9aa98}.grid{stroke:#51483e;stroke-width:1}</style>',
        f'<text x="60" y="58" font-size="30" font-weight="700">{title}</text>',
        f'<text x="60" y="88" class="muted" font-size="16">{subtitle}</text>',
    ]
    for label, color in colors.items():
        x = 710 + list(colors).index(label) * 150
        lines.extend(
            (
                f'<rect x="{x}" y="62" width="18" height="18" rx="3" fill="{color}"/>',
                f'<text x="{x + 27}" y="77" font-size="14">{labels[label]}</text>',
            )
        )
    for panel_index, (title, observed_key, predicted_key, maximum) in enumerate(panels):
        panel_x = 60 + panel_index * 570
        panel_y = 135
        chart_height = 390
        chart_width = 500
        lines.append(f'<text x="{panel_x}" y="{panel_y}" font-size="20" font-weight="600">{title}</text>')
        for tick in range(5):
            value = maximum * tick / 4
            y = panel_y + 420 - chart_height * tick / 4
            lines.extend(
                (
                    f'<line class="grid" x1="{panel_x + 42}" y1="{y:.1f}" x2="{panel_x + chart_width}" y2="{y:.1f}"/>',
                    f'<text x="{panel_x + 34}" y="{y + 5:.1f}" text-anchor="end" class="muted" font-size="13">{value:g}</text>',
                )
            )
        for case_index, flux in enumerate((35, 70)):
            base_case = baseline["cases"][case_index]
            best_case = best["cases"][case_index]
            values = (
                ("observed", float(base_case[observed_key])),
                ("baseline", float(base_case[predicted_key] or 0.0)),
                ("calibrated", float(best_case[predicted_key] or 0.0)),
            )
            group_x = panel_x + 85 + case_index * 225
            for series_index, (series, value) in enumerate(values):
                height = min(value / maximum, 1.0) * chart_height
                x = group_x + series_index * 48
                y = panel_y + 420 - height
                lines.extend(
                    (
                        f'<rect x="{x}" y="{y:.1f}" width="38" height="{height:.1f}" rx="3" fill="{colors[series]}"/>',
                        f'<text x="{x + 19}" y="{max(y - 8, panel_y + 28):.1f}" text-anchor="middle" font-size="12">{value:.2f}</text>',
                    )
                )
            lines.append(f'<text x="{group_x + 67}" y="{panel_y + 448}" text-anchor="middle" font-size="15">{flux} kW/m²</text>')
    lines.extend(
        (
            f'<text x="60" y="625" font-size="17">{summary}</text>',
            f'<text x="60" y="652" class="muted" font-size="14">{scope}</text>',
            '</svg>',
        )
    )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
