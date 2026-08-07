"""Immutable resident publication schema and producer boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass


CHAR_STRENGTH_FACTOR = 0.12
RATIO_ROUNDOFF_TOLERANCE = 1.0e-12
RESIDENT_PUBLISHED_FIELD_NAMES = (
    "surface_mean_temperature_k",
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "char_mass_kg",
    "ash_mass_kg",
    "remaining_mass_ratio",
    "weakest_support_ratio",
    "flow_fuel",
    "flow_temperature",
    "flow_smoke",
    "pyrolysis_gas_rate_kg_s",
)


@dataclass(frozen=True)
class ResidentPublishedRow:
    surface_mean_temperature_k: float
    moisture_mass_kg: float
    dry_wood_mass_kg: float
    char_mass_kg: float
    ash_mass_kg: float
    remaining_mass_ratio: float
    weakest_support_ratio: float
    flow_fuel: float
    flow_temperature: float
    flow_smoke: float
    pyrolysis_gas_rate_kg_s: float

    def __post_init__(self):
        values = tuple(float(value) for value in self.__dict__.values())
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Published resident values must be finite")
        if self.surface_mean_temperature_k <= 0.0:
            raise ValueError("Surface temperature must be positive")
        if min(
            self.moisture_mass_kg,
            self.dry_wood_mass_kg,
            self.char_mass_kg,
            self.ash_mass_kg,
            self.pyrolysis_gas_rate_kg_s,
        ) < 0.0:
            raise ValueError("Published mass values must be non-negative")
        if not (
            -RATIO_ROUNDOFF_TOLERANCE
            <= self.remaining_mass_ratio
            <= 1.0 + RATIO_ROUNDOFF_TOLERANCE
        ):
            raise ValueError("remaining_mass_ratio must be within roundoff of [0, 1]")
        object.__setattr__(
            self,
            "remaining_mass_ratio",
            min(1.0, max(0.0, self.remaining_mass_ratio)),
        )
        for name in (
            "weakest_support_ratio",
            "flow_fuel",
            "flow_smoke",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        if not 0.0 <= self.flow_temperature <= 2.0:
            raise ValueError("flow_temperature must be within [0, 2]")


@dataclass(frozen=True)
class ResidentPublishedSnapshot:
    revision: int
    tick: int
    log_ids: tuple[str, ...]
    rows: tuple[ResidentPublishedRow, ...]

    def __post_init__(self):
        if self.revision <= 0 or self.tick < 0:
            raise ValueError("Snapshot revision must be positive and tick non-negative")
        if not self.log_ids or len(self.log_ids) != len(self.rows):
            raise ValueError("Snapshot log ids and rows must be non-empty and aligned")
        if len(set(self.log_ids)) != len(self.log_ids):
            raise ValueError("Snapshot log ids must be unique")


class ResidentNativeSnapshotProducer:
    """Freeze one native contiguous output buffer into the public schema.

    The producer deliberately owns no revision or commit state.  The resident
    scheduler chooses the revision, while the USD adapter remains the commit
    authority and rejects stale publication.  This keeps a failed conversion
    from advancing either lifecycle.
    """

    field_names = RESIDENT_PUBLISHED_FIELD_NAMES

    def __init__(self, log_ids):
        self._log_ids = tuple(str(log_id) for log_id in log_ids)
        if not self._log_ids or any(not log_id for log_id in self._log_ids):
            raise ValueError("Native snapshot log ids must be non-empty")
        if len(set(self._log_ids)) != len(self._log_ids):
            raise ValueError("Native snapshot log ids must be unique")

    @property
    def log_ids(self):
        return self._log_ids

    def build(self, revision: int, tick: int, values):
        """Copy a C-contiguous native-double buffer into immutable rows."""

        try:
            view = memoryview(values)
        except TypeError as error:
            raise TypeError("Native publication must expose the buffer protocol") from error
        if not view.c_contiguous:
            raise ValueError("Native publication buffer must be C-contiguous")
        if view.itemsize != 8:
            raise ValueError("Native publication buffer must contain 64-bit values")
        flat = view.cast("B").cast("d")
        field_count = len(self.field_names)
        expected_count = len(self._log_ids) * field_count
        if len(flat) != expected_count:
            raise ValueError(
                f"Native publication contains {len(flat)} values; expected {expected_count}"
            )
        rows = tuple(
            ResidentPublishedRow(
                *(float(flat[begin + offset]) for offset in range(field_count))
            )
            for begin in range(0, expected_count, field_count)
        )
        return ResidentPublishedSnapshot(
            revision=int(revision),
            tick=int(tick),
            log_ids=self._log_ids,
            rows=rows,
        )


def published_row_from_python_model(model, metrics, flow_source):
    """Bridge the current Python authority into the immutable 11-value schema."""

    remaining_mass_kg = sum(
        metrics[field]
        for field in (
            "moisture_mass_kg",
            "dry_wood_mass_kg",
            "char_mass_kg",
            "ash_mass_kg",
        )
    )
    cells_per_section = (
        model.spec.circumferential_cells * model.spec.radial_cells
    )
    initial_section_mass_kg = (
        math.pi
        * model.spec.radius_m**2
        * (model.spec.length_m / model.spec.axial_cells)
        * model.parameters.dry_wood_density_kg_m3
    )
    section_ratios = []
    for axial_index in range(model.spec.axial_cells):
        begin = axial_index * cells_per_section
        section = model.cells[begin : begin + cells_per_section]
        dry_mass_kg = sum(cell.dry_wood_mass_kg for cell in section)
        char_mass_kg = sum(cell.char_mass_kg for cell in section)
        section_ratios.append(
            min(
                1.0,
                max(
                    0.0,
                    (dry_mass_kg + CHAR_STRENGTH_FACTOR * char_mass_kg)
                    / max(initial_section_mass_kg, 1.0e-12),
                ),
            )
        )
    interior_ratios = (
        section_ratios[1:-1] if len(section_ratios) > 2 else section_ratios
    )
    return ResidentPublishedRow(
        surface_mean_temperature_k=metrics["surface_mean_temperature_k"],
        moisture_mass_kg=metrics["moisture_mass_kg"],
        dry_wood_mass_kg=metrics["dry_wood_mass_kg"],
        char_mass_kg=metrics["char_mass_kg"],
        ash_mass_kg=metrics["ash_mass_kg"],
        remaining_mass_ratio=min(
            1.0, max(0.0, remaining_mass_kg / model.initial_mass_kg)
        ),
        weakest_support_ratio=min(interior_ratios),
        flow_fuel=flow_source.fuel,
        flow_temperature=flow_source.temperature,
        flow_smoke=flow_source.smoke,
        pyrolysis_gas_rate_kg_s=flow_source.pyrolysis_gas_rate_kg_s,
    )
