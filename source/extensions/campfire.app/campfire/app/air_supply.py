"""Deterministic geometry approximation for Phase 4 air supply.

This is deliberately independent of Flow readback.  It turns log placement,
contact, vertical opening, and wind into a bounded dimensionless oxygen factor
that can later be replaced by verified PhysX scene queries.
"""

import math
from dataclasses import dataclass

from .combustion import WoodThermalModel
from .combustion import create_cylindrical_wood_model


@dataclass(frozen=True)
class LogPlacement:
    log_id: str
    center_m: tuple[float, float, float]
    rotation_z_deg: float
    radius_m: float = 0.16
    length_m: float = 1.8

    @property
    def endpoints(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        angle = math.radians(self.rotation_z_deg)
        half = self.length_m * 0.5
        direction = (math.cos(angle), math.sin(angle), 0.0)
        return (
            tuple(self.center_m[i] - half * direction[i] for i in range(3)),
            tuple(self.center_m[i] + half * direction[i] for i in range(3)),
        )


@dataclass(frozen=True)
class AirSupplyResult:
    oxygen_by_log: dict[str, float]
    contact_count_by_log: dict[str, int]
    contact_pairs: int
    orientation_diversity: float
    clearance_factor: float
    vertical_opening: float
    wind_factor: float
    ventilation_factor: float
    mean_oxygen_factor: float


def _dot(a, b):
    return sum(a[index] * b[index] for index in range(3))


def _subtract(a, b):
    return tuple(a[index] - b[index] for index in range(3))


def _segment_distance(first: LogPlacement, second: LogPlacement) -> float:
    """Shortest distance between finite 3-D centerline segments."""

    p1, q1 = first.endpoints
    p2, q2 = second.endpoints
    d1 = _subtract(q1, p1)
    d2 = _subtract(q2, p2)
    offset = _subtract(p1, p2)
    a = _dot(d1, d1)
    e = _dot(d2, d2)
    f = _dot(d2, offset)
    epsilon = 1.0e-12

    if a <= epsilon and e <= epsilon:
        return math.sqrt(_dot(offset, offset))
    if a <= epsilon:
        first_t = 0.0
        second_t = min(1.0, max(0.0, f / e))
    else:
        c = _dot(d1, offset)
        if e <= epsilon:
            second_t = 0.0
            first_t = min(1.0, max(0.0, -c / a))
        else:
            b = _dot(d1, d2)
            denominator = a * e - b * b
            first_t = (
                min(1.0, max(0.0, (b * f - c * e) / denominator))
                if abs(denominator) > epsilon
                else 0.0
            )
            second_t = (b * first_t + f) / e
            if second_t < 0.0:
                second_t = 0.0
                first_t = min(1.0, max(0.0, -c / a))
            elif second_t > 1.0:
                second_t = 1.0
                first_t = min(1.0, max(0.0, (b - c) / a))

    closest_first = tuple(p1[i] + d1[i] * first_t for i in range(3))
    closest_second = tuple(p2[i] + d2[i] * second_t for i in range(3))
    delta = _subtract(closest_first, closest_second)
    return math.sqrt(_dot(delta, delta))


def _orientation_diversity(logs: list[LogPlacement]) -> float:
    if len(logs) < 2:
        return 0.0
    cross_scores = []
    for index, first in enumerate(logs):
        for second in logs[index + 1 :]:
            difference = math.radians(first.rotation_z_deg - second.rotation_z_deg)
            cross_scores.append(abs(math.sin(difference)))
    return sum(cross_scores) / len(cross_scores)


def estimate_air_supply(
    placements: list[LogPlacement],
    wind_velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0),
    contact_tolerance_m: float = 0.025,
) -> AirSupplyResult:
    if not placements:
        raise ValueError("At least one log placement is required")
    if contact_tolerance_m < 0.0:
        raise ValueError("contact_tolerance_m must be non-negative")
    identifiers = [placement.log_id for placement in placements]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Log IDs must be unique")

    contacts = {placement.log_id: 0 for placement in placements}
    positive_clearances = []
    blocked_upward = set()
    contact_pairs = 0
    for index, first in enumerate(placements):
        for second in placements[index + 1 :]:
            centerline_distance = _segment_distance(first, second)
            surface_gap = centerline_distance - first.radius_m - second.radius_m
            if surface_gap <= contact_tolerance_m:
                contacts[first.log_id] += 1
                contacts[second.log_id] += 1
                contact_pairs += 1
            if surface_gap > 0.0:
                positive_clearances.append(min(surface_gap / 0.45, 1.0))
            vertical_delta = second.center_m[2] - first.center_m[2]
            if abs(surface_gap) < 0.18 and abs(vertical_delta) > 0.05:
                blocked_upward.add(first.log_id if vertical_delta > 0.0 else second.log_id)

    orientation = _orientation_diversity(placements)
    clearance = (
        sum(positive_clearances) / len(positive_clearances)
        if positive_clearances
        else 0.0
    )
    vertical_opening = 1.0 - len(blocked_upward) / len(placements)
    wind_speed = math.sqrt(sum(component**2 for component in wind_velocity_m_s))
    wind_factor = min(wind_speed / 3.0, 1.0)
    ventilation = min(
        1.0,
        max(
            0.0,
            0.10 + 0.45 * orientation + 0.25 * clearance + 0.20 * vertical_opening,
        ),
    )

    oxygen_by_log = {}
    for placement in placements:
        contact_exposure = max(0.25, 1.0 - 0.16 * contacts[placement.log_id])
        oxygen_by_log[placement.log_id] = min(
            1.0,
            max(
                0.05,
                contact_exposure * (0.30 + 0.55 * ventilation + 0.15 * wind_factor),
            ),
        )
    mean_oxygen = sum(oxygen_by_log.values()) / len(oxygen_by_log)
    return AirSupplyResult(
        oxygen_by_log=oxygen_by_log,
        contact_count_by_log=contacts,
        contact_pairs=contact_pairs,
        orientation_diversity=orientation,
        clearance_factor=clearance,
        vertical_opening=vertical_opening,
        wind_factor=wind_factor,
        ventilation_factor=ventilation,
        mean_oxygen_factor=mean_oxygen,
    )


def apply_oxygen_to_model(model: WoodThermalModel, oxygen_factor: float) -> None:
    if not math.isfinite(oxygen_factor) or not 0.0 <= oxygen_factor <= 1.0:
        raise ValueError("oxygen_factor must be finite and within [0, 1]")
    for cell in model.cells:
        cell.oxygen_factor = oxygen_factor * cell.surface_exposure


def heat_feedback_factor(oxygen_factor: float) -> float:
    """Initial one-way flame heat approximation, bounded and dimensionless."""

    if not math.isfinite(oxygen_factor) or not 0.0 <= oxygen_factor <= 1.0:
        raise ValueError("oxygen_factor must be finite and within [0, 1]")
    return 0.55 + 0.45 * oxygen_factor


def dense_stack_placements() -> list[LogPlacement]:
    return [
        LogPlacement(f"Dense_{index:02d}", (0.0, -0.65 + index * 0.26, 0.20), 0.0)
        for index in range(6)
    ]


def log_cabin_placements() -> list[LogPlacement]:
    return [
        LogPlacement("Cabin_00", (0.0, -0.38, 0.18), 0.0),
        LogPlacement("Cabin_01", (0.0, 0.38, 0.18), 0.0),
        LogPlacement("Cabin_02", (-0.38, 0.0, 0.50), 90.0),
        LogPlacement("Cabin_03", (0.38, 0.0, 0.50), 90.0),
    ]


def run_stack_air_comparison(
    duration_seconds: float = 180.0,
    dt_seconds: float = 0.2,
    base_heat_flux_w_m2: float = 150_000.0,
) -> dict:
    """Run equal representative logs under dense and cabin air factors."""

    if duration_seconds <= 0.0 or dt_seconds <= 0.0:
        raise ValueError("Scenario duration and dt must be positive")
    dense_air = estimate_air_supply(dense_stack_placements())
    cabin_air = estimate_air_supply(log_cabin_placements())
    models = {
        "dense": create_cylindrical_wood_model(
            "DenseRepresentative", 0.08, 0.80, 0.12,
            axial_cells=8, circumferential_cells=8, radial_cells=3
        ),
        "cabin": create_cylindrical_wood_model(
            "CabinRepresentative", 0.08, 0.80, 0.12,
            axial_cells=8, circumferential_cells=8, radial_cells=3
        ),
    }
    air = {"dense": dense_air, "cabin": cabin_air}
    ignition = {"dense": None, "cabin": None}
    peak_gas_rate = {"dense": 0.0, "cabin": 0.0}
    steps = int(round(duration_seconds / dt_seconds))
    for name, model in models.items():
        oxygen = air[name].mean_oxygen_factor
        apply_oxygen_to_model(model, oxygen)
        heat_flux = base_heat_flux_w_m2 * heat_feedback_factor(oxygen)
        for _step in range(steps):
            result = model.step(dt_seconds, heat_flux)
            peak_gas_rate[name] = max(
                peak_gas_rate[name], result.pyrolysis_gas_rate_kg_s
            )
            if ignition[name] is None and result.pyrolysis_gas_rate_kg_s > 1.0e-6:
                ignition[name] = result.elapsed_seconds

    return {
        "duration_seconds": duration_seconds,
        "dt_seconds": dt_seconds,
        "base_heat_flux_w_m2": base_heat_flux_w_m2,
        "dense": {
            "oxygen_factor": dense_air.mean_oxygen_factor,
            "ventilation_factor": dense_air.ventilation_factor,
            "ignition_seconds": ignition["dense"],
            "peak_pyrolysis_gas_rate_kg_s": peak_gas_rate["dense"],
            **models["dense"].metrics(),
        },
        "cabin": {
            "oxygen_factor": cabin_air.mean_oxygen_factor,
            "ventilation_factor": cabin_air.ventilation_factor,
            "ignition_seconds": ignition["cabin"],
            "peak_pyrolysis_gas_rate_kg_s": peak_gas_rate["cabin"],
            **models["cabin"].metrics(),
        },
    }
