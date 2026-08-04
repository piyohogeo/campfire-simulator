"""Phase 5 structural support, segmentation, and reignition approximation.

The thermal cell state remains authoritative.  This module reduces each
axial cross-section to a bounded support ratio, releases one prepared joint at
the weakest section, and updates the two resulting rigid bodies in coarse
steps.  The coefficients are explicit hypotheses, not calibrated strength
data.
"""

import math
from dataclasses import dataclass

from pxr import Sdf, Usd, UsdGeom, UsdPhysics

from .air_supply import apply_oxygen_to_model, heat_feedback_factor
from .combustion import WoodThermalModel, create_cylindrical_wood_model


DEFAULT_CHAR_STRENGTH_FACTOR = 0.12
DEFAULT_FAILURE_THRESHOLD = 0.58
PHASE5_PRE_COLLAPSE_OXYGEN = 0.30
PHASE5_POST_COLLAPSE_OXYGEN = 0.82
PHASE5_DT_SECONDS = 0.20
PHASE5_DURATION_SECONDS = 240.0
PHASE5_BASE_HEAT_FLUX_W_M2 = 180_000.0


@dataclass(frozen=True)
class CrossSectionSupport:
    axial_index: int
    center_m: float
    dry_wood_mass_kg: float
    char_mass_kg: float
    ash_mass_kg: float
    support_ratio: float


@dataclass(frozen=True)
class SupportAssessment:
    sections: tuple[CrossSectionSupport, ...]
    weakest_section: int
    weakest_support_ratio: float
    split_index: int
    failure_threshold: float
    failed: bool


@dataclass(frozen=True)
class SegmentPhysicsUpdate:
    path: str
    axial_start: int
    axial_end_exclusive: int
    mass_kg: float
    mass_ratio: float
    collider_radius_m: float


def assess_cross_section_support(
    model: WoodThermalModel,
    failure_threshold: float = DEFAULT_FAILURE_THRESHOLD,
    char_strength_factor: float = DEFAULT_CHAR_STRENGTH_FACTOR,
) -> SupportAssessment:
    """Reduce the cell grid to one structural ratio per axial section."""

    if not 0.0 < failure_threshold < 1.0:
        raise ValueError("failure_threshold must be within (0, 1)")
    if not 0.0 <= char_strength_factor <= 1.0:
        raise ValueError("char_strength_factor must be within [0, 1]")

    spec = model.spec
    cells_per_section = spec.circumferential_cells * spec.radial_cells
    initial_section_dry_mass = (
        math.pi
        * spec.radius_m**2
        * (spec.length_m / spec.axial_cells)
        * model.parameters.dry_wood_density_kg_m3
    )
    sections = []
    for axial_index in range(spec.axial_cells):
        start = axial_index * cells_per_section
        section_cells = model.cells[start : start + cells_per_section]
        dry_mass = sum(cell.dry_wood_mass_kg for cell in section_cells)
        char_mass = sum(cell.char_mass_kg for cell in section_cells)
        ash_mass = sum(cell.ash_mass_kg for cell in section_cells)
        support_ratio = min(
            1.0,
            max(
                0.0,
                (dry_mass + char_strength_factor * char_mass)
                / max(initial_section_dry_mass, 1.0e-12),
            ),
        )
        sections.append(
            CrossSectionSupport(
                axial_index=axial_index,
                center_m=(axial_index + 0.5) * spec.length_m / spec.axial_cells
                - 0.5 * spec.length_m,
                dry_wood_mass_kg=dry_mass,
                char_mass_kg=char_mass,
                ash_mass_kg=ash_mass,
                support_ratio=support_ratio,
            )
        )

    # End faces are exposed in the grid and can become the numerical minimum,
    # but a break at an endpoint would not produce two useful rigid segments.
    interior = sections[1:-1] if len(sections) > 2 else sections
    weakest = min(interior, key=lambda section: section.support_ratio)
    split_index = min(max(weakest.axial_index + 1, 1), spec.axial_cells - 1)
    return SupportAssessment(
        sections=tuple(sections),
        weakest_section=weakest.axial_index,
        weakest_support_ratio=weakest.support_ratio,
        split_index=split_index,
        failure_threshold=failure_threshold,
        failed=weakest.support_ratio <= failure_threshold,
    )


def segment_mass_kg(
    model: WoodThermalModel, axial_start: int, axial_end_exclusive: int
) -> float:
    spec = model.spec
    if not 0 <= axial_start < axial_end_exclusive <= spec.axial_cells:
        raise ValueError("Invalid axial segment range")
    cells_per_section = spec.circumferential_cells * spec.radial_cells
    start = axial_start * cells_per_section
    end = axial_end_exclusive * cells_per_section
    return sum(cell.current_mass_kg for cell in model.cells[start:end])


def release_segment_joint(
    stage: Usd.Stage,
    model: WoodThermalModel,
    assessment: SupportAssessment,
    segment_paths: tuple[str, str],
    joint_path: str,
) -> tuple[SegmentPhysicsUpdate, SegmentPhysicsUpdate]:
    """Release a failed prepared joint and coarsely update mass/colliders."""

    if not assessment.failed:
        raise ValueError("Cannot release a joint before support failure")
    if len(segment_paths) != 2:
        raise ValueError("Exactly two prepared segment paths are required")

    ranges = (
        (0, assessment.split_index),
        (assessment.split_index, model.spec.axial_cells),
    )
    updates = []
    for path, (axial_start, axial_end) in zip(segment_paths, ranges):
        prim = stage.GetPrimAtPath(path)
        if not prim:
            raise ValueError(f"Missing prepared segment prim: {path}")
        current_mass = segment_mass_kg(model, axial_start, axial_end)
        initial_mass_attr = prim.GetAttribute("campfire:initialSegmentMassKg")
        initial_mass = float(initial_mass_attr.Get()) if initial_mass_attr else current_mass
        mass_ratio = min(1.0, max(0.0, current_mass / max(initial_mass, 1.0e-12)))
        collider_radius = model.spec.radius_m * max(0.58, math.sqrt(mass_ratio))

        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(current_mass).Set(current_mass)
        UsdGeom.Cylinder(prim).GetRadiusAttr().Set(collider_radius)
        prim.CreateAttribute("campfire:constraintReleased", Sdf.ValueTypeNames.Bool).Set(
            True
        )
        prim.CreateAttribute("campfire:remainingMassKg", Sdf.ValueTypeNames.Double).Set(
            current_mass
        )
        prim.CreateAttribute("campfire:massRatio", Sdf.ValueTypeNames.Double).Set(
            mass_ratio
        )
        prim.CreateAttribute("campfire:colliderRadiusM", Sdf.ValueTypeNames.Double).Set(
            collider_radius
        )
        updates.append(
            SegmentPhysicsUpdate(
                path=path,
                axial_start=axial_start,
                axial_end_exclusive=axial_end,
                mass_kg=current_mass,
                mass_ratio=mass_ratio,
                collider_radius_m=collider_radius,
            )
        )

    if stage.GetPrimAtPath(joint_path):
        stage.RemovePrim(joint_path)
    return tuple(updates)


def _localized_heat_fluxes(
    model: WoodThermalModel,
    collapsed: bool,
    base_heat_flux_w_m2: float,
    oxygen_factor: float,
) -> list[float]:
    spec = model.spec
    center_left = spec.axial_cells // 2 - 1
    center_right = spec.axial_cells // 2
    fluxes = []
    feedback = heat_feedback_factor(oxygen_factor)
    cells_per_section = spec.circumferential_cells * spec.radial_cells
    for index, cell in enumerate(model.cells):
        axial_index = index // cells_per_section
        if cell.surface_exposure <= 0.0:
            fluxes.append(0.0)
        elif collapsed:
            fluxes.append(base_heat_flux_w_m2 * feedback)
        elif axial_index in (center_left, center_right):
            fluxes.append(base_heat_flux_w_m2 * feedback * 1.45)
        else:
            fluxes.append(base_heat_flux_w_m2 * feedback * 0.16)
    return fluxes


def create_collapse_support_model() -> WoodThermalModel:
    return create_cylindrical_wood_model(
        "CollapseLog",
        0.14,
        1.80,
        0.08,
        axial_cells=12,
        circumferential_cells=8,
        radial_cells=3,
    )


def burn_to_support_failure(
    dt_seconds: float = PHASE5_DT_SECONDS,
    base_heat_flux_w_m2: float = PHASE5_BASE_HEAT_FLUX_W_M2,
    maximum_duration_seconds: float = PHASE5_DURATION_SECONDS,
) -> tuple[WoodThermalModel, SupportAssessment, list[float], list[dict]]:
    """Return the authoritative model at the first failed cross-section."""

    model = create_collapse_support_model()
    gas_rates = []
    support_trace = []
    maximum_steps = int(round(maximum_duration_seconds / dt_seconds))
    for step_index in range(1, maximum_steps + 1):
        apply_oxygen_to_model(model, PHASE5_PRE_COLLAPSE_OXYGEN)
        result = model.step(
            dt_seconds,
            _localized_heat_fluxes(
                model,
                False,
                base_heat_flux_w_m2,
                PHASE5_PRE_COLLAPSE_OXYGEN,
            ),
        )
        gas_rates.append(result.pyrolysis_gas_rate_kg_s)
        assessment = assess_cross_section_support(model)
        if step_index % 10 == 0:
            support_trace.append(
                {
                    "time_seconds": round(result.elapsed_seconds, 6),
                    "weakest_support_ratio": assessment.weakest_support_ratio,
                }
            )
        if assessment.failed:
            return model, assessment, gas_rates, support_trace
    raise RuntimeError("Collapse scenario did not reach the support threshold")


def run_collapse_reignition_scenario(
    duration_seconds: float = PHASE5_DURATION_SECONDS,
    dt_seconds: float = PHASE5_DT_SECONDS,
    base_heat_flux_w_m2: float = PHASE5_BASE_HEAT_FLUX_W_M2,
) -> dict:
    """Burn a center section, release it, then expose the fallen fuel to air."""

    if duration_seconds <= 0.0 or dt_seconds <= 0.0:
        raise ValueError("Scenario duration and dt must be positive")
    if base_heat_flux_w_m2 <= 0.0:
        raise ValueError("base_heat_flux_w_m2 must be positive")

    model = create_collapse_support_model()
    initial = assess_cross_section_support(model)
    steps = int(round(duration_seconds / dt_seconds))
    model, collapse_assessment, gas_rates, support_trace = burn_to_support_failure(
        dt_seconds,
        base_heat_flux_w_m2,
        duration_seconds,
    )
    collapse_step = len(gas_rates)
    collapse_time = model.elapsed_seconds

    for step_index in range(collapse_step + 1, steps + 1):
        oxygen = PHASE5_POST_COLLAPSE_OXYGEN
        apply_oxygen_to_model(model, oxygen)
        result = model.step(
            dt_seconds,
            _localized_heat_fluxes(model, True, base_heat_flux_w_m2, oxygen),
        )
        assessment = assess_cross_section_support(model)
        gas_rates.append(result.pyrolysis_gas_rate_kg_s)
        if step_index % 10 == 0:
            support_trace.append(
                {
                    "time_seconds": round(result.elapsed_seconds, 6),
                    "weakest_support_ratio": assessment.weakest_support_ratio,
                }
            )
    window_steps = max(1, int(round(10.0 / dt_seconds)))
    pre_start = max(0, collapse_step - window_steps)
    pre_rates = gas_rates[pre_start:collapse_step]
    post_start = collapse_step
    post_rates = gas_rates[post_start:]
    pre_mean = sum(pre_rates) / len(pre_rates)
    post_peak = max(post_rates, default=0.0)
    final = assess_cross_section_support(model)
    left_mass = segment_mass_kg(model, 0, collapse_assessment.split_index)
    right_mass = segment_mass_kg(
        model, collapse_assessment.split_index, model.spec.axial_cells
    )

    return {
        "duration_seconds": duration_seconds,
        "dt_seconds": dt_seconds,
        "base_heat_flux_w_m2": base_heat_flux_w_m2,
        "initial_support_ratio": initial.weakest_support_ratio,
        "failure_threshold": collapse_assessment.failure_threshold,
        "collapse_time_seconds": collapse_time,
        "failed_section": collapse_assessment.weakest_section,
        "split_index": collapse_assessment.split_index,
        "support_ratio_at_release": collapse_assessment.weakest_support_ratio,
        "final_weakest_support_ratio": final.weakest_support_ratio,
        "pre_collapse_oxygen_factor": PHASE5_PRE_COLLAPSE_OXYGEN,
        "post_collapse_oxygen_factor": PHASE5_POST_COLLAPSE_OXYGEN,
        "pre_collapse_mean_pyrolysis_gas_rate_kg_s": pre_mean,
        "post_collapse_peak_pyrolysis_gas_rate_kg_s": post_peak,
        "reignition_gain": post_peak / max(pre_mean, 1.0e-12),
        "reignited": post_peak > pre_mean * 1.05,
        "initial_mass_kg": model.initial_mass_kg,
        "remaining_mass_kg": model.current_mass_kg,
        "segment_mass_kg": {"left": left_mass, "right": right_mass},
        "segment_mass_sum_kg": left_mass + right_mass,
        "mass_balance_error_kg": model.mass_balance_error_kg,
        "all_values_finite": all(
            math.isfinite(cell.temperature_k)
            and math.isfinite(cell.current_mass_kg)
            for cell in model.cells
        ),
        "support_trace": support_trace,
    }
