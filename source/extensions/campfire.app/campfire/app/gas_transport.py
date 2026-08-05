"""Flow-independent one-dimensional porous-gas transport diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DarcyGasTransportInput:
    """Complete SI input contract for a uniform porous layer."""

    layer_thickness_m: float
    porosity_fraction: float
    permeability_m2: float
    dynamic_viscosity_pa_s: float
    pressure_drop_pa: float


@dataclass(frozen=True)
class DarcyGasTransportResult:
    """One-dimensional Darcy velocity and pore residence time."""

    pressure_gradient_pa_m: float
    superficial_velocity_m_s: float
    interstitial_velocity_m_s: float
    residence_time_s: float


def evaluate_darcy_gas_transport(
    inputs: DarcyGasTransportInput,
) -> DarcyGasTransportResult:
    """Evaluate steady Darcy flow without coupling it to the thermal model.

    The superficial velocity is ``K / mu * delta_p / L``.  Dividing it by
    porosity gives the interstitial velocity used for ``tau = L / u_pore``.
    Every physical input is mandatory so an unavailable plywood property
    cannot silently become a default calibration coefficient.
    """

    values = {
        "layer_thickness_m": inputs.layer_thickness_m,
        "porosity_fraction": inputs.porosity_fraction,
        "permeability_m2": inputs.permeability_m2,
        "dynamic_viscosity_pa_s": inputs.dynamic_viscosity_pa_s,
        "pressure_drop_pa": inputs.pressure_drop_pa,
    }
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("Darcy transport inputs must be finite")
    if inputs.layer_thickness_m <= 0.0:
        raise ValueError("Darcy layer thickness must be positive")
    if inputs.porosity_fraction <= 0.0 or inputs.porosity_fraction > 1.0:
        raise ValueError("Darcy porosity must be within (0, 1]")
    if inputs.permeability_m2 <= 0.0:
        raise ValueError("Darcy permeability must be positive")
    if inputs.dynamic_viscosity_pa_s <= 0.0:
        raise ValueError("Darcy dynamic viscosity must be positive")
    if inputs.pressure_drop_pa <= 0.0:
        raise ValueError("Darcy pressure drop must be positive")

    pressure_gradient_pa_m = inputs.pressure_drop_pa / inputs.layer_thickness_m
    superficial_velocity_m_s = (
        inputs.permeability_m2
        / inputs.dynamic_viscosity_pa_s
        * pressure_gradient_pa_m
    )
    interstitial_velocity_m_s = (
        superficial_velocity_m_s / inputs.porosity_fraction
    )
    residence_time_s = inputs.layer_thickness_m / interstitial_velocity_m_s
    if not all(
        math.isfinite(value) and value > 0.0
        for value in (
            pressure_gradient_pa_m,
            superficial_velocity_m_s,
            interstitial_velocity_m_s,
            residence_time_s,
        )
    ):
        raise ValueError("Darcy transport result must be finite and positive")
    return DarcyGasTransportResult(
        pressure_gradient_pa_m=pressure_gradient_pa_m,
        superficial_velocity_m_s=superficial_velocity_m_s,
        interstitial_velocity_m_s=interstitial_velocity_m_s,
        residence_time_s=residence_time_s,
    )
