"""Opt-in USD consumer adapter for immutable resident wood snapshots."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Callable

from pxr import Gf, Sdf, Usd, UsdGeom

from .flow_scene import FLOW_EMITTER_PATH


CHAR_STRENGTH_FACTOR = 0.12
RATIO_ROUNDOFF_TOLERANCE = 1.0e-12


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


@dataclass
class _AttributeRestore:
    prim: Usd.Prim
    name: str
    attribute: Usd.Attribute
    property_existed: bool
    authored_value_existed: bool
    previous_value: object

    def rollback(self):
        if not self.property_existed:
            self.prim.RemoveProperty(self.name)
        elif self.authored_value_existed:
            self.attribute.Set(self.previous_value)
        else:
            self.attribute.Clear()


class UsdResidentSnapshotAdapter:
    """Publish one immutable revision to Flow, visual, and support consumers."""

    def __init__(
        self,
        stage: Usd.Stage,
        log_ids: tuple[str, ...],
        initial_dry_mass_kg: dict[str, float],
        *,
        write_observer: Callable[[int, str], None] | None = None,
    ):
        if stage is None:
            raise ValueError("A USD stage is required")
        if not log_ids or set(log_ids) != set(initial_dry_mass_kg):
            raise ValueError("Initial dry mass must cover every log exactly")
        if any(value <= 0.0 for value in initial_dry_mass_kg.values()):
            raise ValueError("Initial dry masses must be positive")
        self._stage = stage
        self._log_ids = tuple(log_ids)
        self._initial_dry_mass_kg = dict(initial_dry_mass_kg)
        self._write_observer = write_observer
        self._owner_thread_id = threading.get_ident()
        self._active = False
        self._closed = False
        self._revision = 0
        self._publish_count = 0
        self._start_count = 0
        self._stop_count = 0

    def _require_owner(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Resident USD adapter must run on its owner thread")

    def _require_publishable(self, snapshot):
        self._require_owner()
        if self._closed:
            raise RuntimeError("Resident USD adapter is closed")
        if not self._active:
            raise RuntimeError("Resident USD adapter requires an active timeline")
        if snapshot.log_ids != self._log_ids:
            raise ValueError("Snapshot log order does not match the adapter")
        if snapshot.revision <= self._revision:
            raise RuntimeError("Resident snapshot revision must increase monotonically")

    def on_timeline_started(self):
        self._require_owner()
        if self._closed:
            raise RuntimeError("Resident USD adapter is closed")
        if not self._active:
            self._active = True
            self._start_count += 1

    def on_timeline_stopped(self):
        self._require_owner()
        if self._closed:
            return
        if self._active:
            self._active = False
            self._stop_count += 1

    @staticmethod
    def _visual_color(row, initial_dry_mass_kg):
        char_fraction = min(
            1.0,
            (row.char_mass_kg + row.ash_mass_kg)
            / max(initial_dry_mass_kg, 1.0e-12),
        )
        heat_fraction = min(
            1.0,
            max(0.0, (row.surface_mean_temperature_k - 500.0) / 700.0),
        )
        wood = Gf.Vec3f(0.30, 0.12, 0.045)
        char = Gf.Vec3f(0.035, 0.025, 0.020)
        ember = Gf.Vec3f(0.55, 0.075, 0.015)
        color = wood * (1.0 - char_fraction) + char * char_fraction
        return color * (1.0 - 0.35 * heat_fraction) + ember * (
            0.35 * heat_fraction
        )

    def _set_attribute(self, prim, name, type_name, value, restores):
        property_existed = bool(prim.GetProperty(name))
        attribute = prim.GetAttribute(name)
        if not attribute:
            attribute = prim.CreateAttribute(name, type_name)
        authored_value_existed = attribute.HasAuthoredValueOpinion()
        previous_value = attribute.Get() if authored_value_existed else None
        restores.append(
            _AttributeRestore(
                prim,
                name,
                attribute,
                property_existed,
                authored_value_existed,
                previous_value,
            )
        )
        if not attribute.Set(value):
            raise RuntimeError(f"Unable to publish USD attribute {prim.GetPath()}.{name}")
        if self._write_observer is not None:
            self._write_observer(len(restores), name)

    def publish(self, snapshot: ResidentPublishedSnapshot):
        self._require_publishable(snapshot)
        emitter = self._stage.GetPrimAtPath(FLOW_EMITTER_PATH)
        if not emitter:
            raise RuntimeError("Flow emitter prim is unavailable")
        log_prims = [
            self._stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            for log_id in self._log_ids
        ]
        if not all(log_prims):
            raise RuntimeError("One or more wood log prims are unavailable")

        restores = []
        try:
            flow_row = snapshot.rows[0]
            flow_values = {
                "fuel": flow_row.flow_fuel,
                "temperature": flow_row.flow_temperature,
                "smoke": flow_row.flow_smoke,
                "coupleRateFuel": 2.0 if flow_row.flow_fuel > 0.0 else 0.0,
                "coupleRateTemperature": (
                    10.0 if flow_row.flow_temperature > 0.0 else 0.0
                ),
                "coupleRateSmoke": 1.0 if flow_row.flow_smoke > 0.0 else 0.0,
            }
            for name, value in flow_values.items():
                self._set_attribute(
                    emitter, name, Sdf.ValueTypeNames.Float, value, restores
                )
            self._set_attribute(
                emitter,
                "campfire:residentRevision",
                Sdf.ValueTypeNames.Int64,
                snapshot.revision,
                restores,
            )

            for log_id, prim, row in zip(self._log_ids, log_prims, snapshot.rows):
                char_fraction = min(
                    1.0,
                    (row.char_mass_kg + row.ash_mass_kg)
                    / max(self._initial_dry_mass_kg[log_id], 1.0e-12),
                )
                color = self._visual_color(row, self._initial_dry_mass_kg[log_id])
                display_color = UsdGeom.Gprim(prim).GetDisplayColorAttr()
                if not display_color:
                    raise RuntimeError(f"Log {log_id} has no displayColor attribute")
                self._set_attribute(
                    prim,
                    display_color.GetName(),
                    display_color.GetTypeName(),
                    [color],
                    restores,
                )
                values = {
                    "campfire:surfaceTemperatureK": row.surface_mean_temperature_k,
                    "campfire:charFraction": char_fraction,
                    "campfire:remainingMassRatio": row.remaining_mass_ratio,
                    "campfire:weakestSupportRatio": row.weakest_support_ratio,
                }
                for name, value in values.items():
                    self._set_attribute(
                        prim, name, Sdf.ValueTypeNames.Double, value, restores
                    )
                self._set_attribute(
                    prim,
                    "campfire:residentRevision",
                    Sdf.ValueTypeNames.Int64,
                    snapshot.revision,
                    restores,
                )
        except Exception:
            for restore in reversed(restores):
                restore.rollback()
            raise
        self._revision = snapshot.revision
        self._publish_count += 1

    def status(self):
        self._require_owner()
        return {
            "active": self._active,
            "closed": self._closed,
            "revision": self._revision,
            "publish_count": self._publish_count,
            "start_count": self._start_count,
            "stop_count": self._stop_count,
            "owner_thread_id": self._owner_thread_id,
        }

    def close(self):
        self._require_owner()
        if self._closed:
            return False
        if self._active:
            self.on_timeline_stopped()
        self._closed = True
        return True
