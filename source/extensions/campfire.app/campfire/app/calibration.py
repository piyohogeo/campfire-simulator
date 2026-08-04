"""Phase 6 reproducible calibration against a fixed NIST cone data subset."""

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

from .combustion import (
    WoodModelParameters,
    WoodThermalModel,
    create_cylindrical_wood_model,
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
            }
        )
    return {
        "score_rmse_relative": math.sqrt(sum(squared_errors) / len(squared_errors)),
        "parameters": {
            "radiant_absorptivity": parameters.radiant_absorptivity,
            "pyrolysis_start_temperature_k": parameters.pyrolysis_start_temperature_k,
            "pyrolysis_full_temperature_k": parameters.pyrolysis_full_temperature_k,
            "pyrolysis_max_fraction_s": parameters.pyrolysis_max_fraction_s,
        },
        "cases": cases,
    }


def calibration_candidates() -> list[WoodModelParameters]:
    baseline = WoodModelParameters()
    candidates = [baseline]
    for absorptivity in (0.55, 0.70, 0.85, 1.0):
        for start_temperature_k in (520.0, 573.15, 620.0):
            for maximum_fraction_s in (0.010, 0.025, 0.050):
                candidates.append(
                    replace(
                        baseline,
                        radiant_absorptivity=absorptivity,
                        pyrolysis_start_temperature_k=start_temperature_k,
                        pyrolysis_full_temperature_k=start_temperature_k + 200.0,
                        pyrolysis_max_fraction_s=maximum_fraction_s,
                    )
                )
    unique = {}
    for candidate in candidates:
        key = (
            candidate.radiant_absorptivity,
            candidate.pyrolysis_start_temperature_k,
            candidate.pyrolysis_full_temperature_k,
            candidate.pyrolysis_max_fraction_s,
        )
        unique[key] = candidate
    return list(unique.values())


def run_nist_plywood_calibration() -> dict:
    reference = load_nist_plywood_reference()
    selection_targets, validation_targets = build_replicate_split_targets(reference)
    selection_baseline = evaluate_parameters(
        reference, WoodModelParameters(), selection_targets
    )
    evaluated = [
        (
            candidate,
            evaluate_parameters(reference, candidate, selection_targets),
        )
        for candidate in calibration_candidates()
    ]
    evaluated.sort(key=lambda item: item[1]["score_rmse_relative"])
    best_parameters, selection_best = evaluated[0]
    ranked = [result for _, result in evaluated]
    baseline = evaluate_parameters(reference, WoodModelParameters())
    best = evaluate_parameters(reference, best_parameters)
    validation_baseline = evaluate_parameters(
        reference, WoodModelParameters(), validation_targets
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
        WoodModelParameters(),
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
            "thickness is inferred from the source roof panel, adhesive layers are omitted, "
            "and the reaction law remains the Phase 3 piecewise-linear model."
        ),
    }


def write_calibration_svg(calibration: dict, destination: Path) -> Path:
    """Write a dependency-free, browser-readable calibration comparison."""

    improvement = calibration["improvement_fraction"] * 100.0
    return _write_comparison_svg(
        calibration["baseline"],
        calibration["best"],
        destination,
        title="Phase 6D — NIST plywood layered-panel calibration",
        subtitle="NISTIR 7094 · nominal 12.7 mm planar specimen · five equal plies",
        summary=(
            "Relative RMSE: baseline "
            f"{calibration['baseline']['score_rmse_relative']:.3f} → calibrated "
            f"{calibration['best']['score_rmse_relative']:.3f} "
            f"({improvement:.1f}% improvement)"
        ),
        scope=(
            "Scope: nominal source-panel thickness and equal-ply geometry; adhesive "
            "layers and Arrhenius kinetics are not yet modeled."
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
        title="Phase 6B — OSB external-material holdout",
        subtitle="NISTIR 7094 Table 2 · plywood-fit parameters applied without refitting",
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
        title="Phase 6D — Layered plywood replicate holdout",
        subtitle="12.7 mm five-ply panel · SAMP.1/2 fit applied to reserved SAMP.3",
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
  <text x="60" y="52" class="title">Phase 6D — Explicit five-ply specimen</text>
  <text x="60" y="82" class="subtitle">0.1 m × 0.1 m × 12.7 mm nominal · five equal 2.54 mm plies · exposed from ply 1</text>
  {''.join(panels)}
  <line x1="60" y1="585" x2="1140" y2="585" stroke="#53483d"/>
  <text x="60" y="620" class="note">Sides and rear are foil-wrapped. The 12.7 mm cone-specimen thickness is inferred from the reported source roof panel.</text>
  <text x="60" y="648" class="muted">Equal ply thickness and alternating 0°/90° grain are explicit assumptions; adhesive layers are not modeled.</text>
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
