"""Opt-in USD consumer adapter for immutable resident wood snapshots."""

from __future__ import annotations

import math
import threading
import time
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


@dataclass(frozen=True)
class ResidentUsdTransactionProfile:
    """Opt-in timings for one transactional USD publication."""

    status: str
    total_ms: float
    validation_ms: float
    prim_lookup_ms: float
    payload_preparation_ms: float
    attribute_lookup_ms: float
    old_value_capture_ms: float
    journal_append_ms: float
    attribute_set_ms: float
    value_audit_ms: float
    write_observer_ms: float
    commit_ms: float
    rollback_ms: float
    unattributed_ms: float
    write_count: int
    changed_write_count: int
    unchanged_write_count: int
    existing_property_count: int
    created_property_count: int
    authored_old_value_count: int
    group_ms: tuple[tuple[str, float], ...]
    attribute_ms: tuple[tuple[str, float], ...]
    attribute_set_detail_ms: tuple[tuple[str, float], ...]
    group_write_disposition: tuple[tuple[str, int, int], ...]
    attribute_write_disposition: tuple[tuple[str, str], ...]


class UsdResidentSnapshotAdapter:
    """Publish one immutable revision to Flow, visual, and support consumers."""

    def __init__(
        self,
        stage: Usd.Stage,
        log_ids: tuple[str, ...],
        initial_dry_mass_kg: dict[str, float],
        *,
        write_observer: Callable[[int, str], None] | None = None,
        profile_transactions: bool = False,
        cache_usd_handles: bool = False,
        lightweight_commits: bool = False,
        skip_unchanged_derived: bool = False,
    ):
        if stage is None:
            raise ValueError("A USD stage is required")
        if not log_ids or set(log_ids) != set(initial_dry_mass_kg):
            raise ValueError("Initial dry mass must cover every log exactly")
        if any(value <= 0.0 for value in initial_dry_mass_kg.values()):
            raise ValueError("Initial dry masses must be positive")
        if lightweight_commits and profile_transactions:
            raise ValueError(
                "Lightweight commits cannot use transactional detail profiling"
            )
        if skip_unchanged_derived and not lightweight_commits:
            raise ValueError(
                "Skipping unchanged derived values requires lightweight commits"
            )
        self._stage = stage
        self._log_ids = tuple(log_ids)
        self._initial_dry_mass_kg = dict(initial_dry_mass_kg)
        self._write_observer = write_observer
        self._profile_transactions = bool(profile_transactions)
        self._cache_usd_handles = bool(cache_usd_handles)
        self._lightweight_commits = bool(lightweight_commits)
        self._skip_unchanged_derived = bool(skip_unchanged_derived)
        self._transaction_profiles: list[ResidentUsdTransactionProfile] = []
        self._cached_emitter = None
        self._cached_log_prims = ()
        self._attribute_cache = {}
        self._prim_cache_hit_count = 0
        self._prim_cache_miss_count = 0
        self._attribute_cache_hit_count = 0
        self._attribute_cache_miss_count = 0
        self._last_committed_snapshot = None
        self._lightweight_commit_count = 0
        self._lightweight_failure_count = 0
        self._lightweight_recovery_count = 0
        self._lightweight_write_count = 0
        self._skipped_unchanged_write_count = 0
        self._faulted = False
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
        if self._faulted:
            raise RuntimeError("Resident USD adapter requires explicit reconstruction")
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

    def _set_attribute(
        self,
        prim,
        name,
        type_name,
        value,
        restores,
        *,
        profile=None,
        group="payload",
        label=None,
    ):
        attribute_label = label or name
        if profile is not None:
            self._set_attribute_profiled(
                prim,
                name,
                type_name,
                value,
                restores,
                profile,
                group,
                attribute_label,
            )
            return
        property_existed, attribute = self._resolve_attribute(
            prim, name, type_name, attribute_label
        )
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

    def _resolve_attribute(self, prim, name, type_name, cache_key):
        if self._cache_usd_handles:
            attribute = self._attribute_cache.get(cache_key)
            if attribute:
                self._attribute_cache_hit_count += 1
                return True, attribute
            self._attribute_cache.pop(cache_key, None)
            self._attribute_cache_miss_count += 1
        property_existed = bool(prim.GetProperty(name))
        attribute = prim.GetAttribute(name)
        if not attribute:
            attribute = prim.CreateAttribute(name, type_name)
        if self._cache_usd_handles:
            self._attribute_cache[cache_key] = attribute
        return property_existed, attribute

    def _resolve_publish_prims(self):
        if (
            self._cache_usd_handles
            and self._cached_emitter
            and len(self._cached_log_prims) == len(self._log_ids)
            and all(self._cached_log_prims)
        ):
            self._prim_cache_hit_count += 1
            return self._cached_emitter, self._cached_log_prims
        if self._cache_usd_handles:
            self._prim_cache_miss_count += 1
        emitter = self._stage.GetPrimAtPath(FLOW_EMITTER_PATH)
        if not emitter:
            raise RuntimeError("Flow emitter prim is unavailable")
        log_prims = tuple(
            self._stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            for log_id in self._log_ids
        )
        if not all(log_prims):
            raise RuntimeError("One or more wood log prims are unavailable")
        if self._cache_usd_handles:
            self._cached_emitter = emitter
            self._cached_log_prims = log_prims
        return emitter, log_prims

    def _prune_invalid_attribute_handles(self):
        if self._cache_usd_handles:
            self._attribute_cache = {
                key: attribute
                for key, attribute in self._attribute_cache.items()
                if attribute
            }

    def _set_attribute_lightweight(
        self,
        prim,
        name,
        type_name,
        value,
        write_index,
        *,
        label,
        notify_observer,
    ):
        _, attribute = self._resolve_attribute(prim, name, type_name, label)
        if not attribute.Set(value):
            raise RuntimeError(f"Unable to publish USD attribute {prim.GetPath()}.{name}")
        self._lightweight_write_count += 1
        write_index += 1
        if notify_observer and self._write_observer is not None:
            self._write_observer(write_index, name)
        return write_index

    def _set_derived_attribute_lightweight(
        self,
        prim,
        name,
        type_name,
        value,
        previous_value,
        write_index,
        *,
        label,
        notify_observer,
        skip_unchanged,
    ):
        if skip_unchanged and self._usd_values_equal(value, previous_value):
            self._skipped_unchanged_write_count += 1
            return write_index
        return self._set_attribute_lightweight(
            prim,
            name,
            type_name,
            value,
            write_index,
            label=label,
            notify_observer=notify_observer,
        )

    @staticmethod
    def _flow_payload(row):
        return {
            "fuel": row.flow_fuel,
            "temperature": row.flow_temperature,
            "smoke": row.flow_smoke,
            "coupleRateFuel": 2.0 if row.flow_fuel > 0.0 else 0.0,
            "coupleRateTemperature": 10.0 if row.flow_temperature > 0.0 else 0.0,
            "coupleRateSmoke": 1.0 if row.flow_smoke > 0.0 else 0.0,
        }

    def _log_payload(self, log_id, row):
        char_fraction = min(
            1.0,
            (row.char_mass_kg + row.ash_mass_kg)
            / max(self._initial_dry_mass_kg[log_id], 1.0e-12),
        )
        return {
            "campfire:surfaceTemperatureK": row.surface_mean_temperature_k,
            "campfire:charFraction": char_fraction,
            "campfire:remainingMassRatio": row.remaining_mass_ratio,
            "campfire:weakestSupportRatio": row.weakest_support_ratio,
        }

    def _write_snapshot_lightweight(
        self, snapshot, emitter, log_prims, *, notify_observer, skip_unchanged=False
    ):
        """Write a complete derived snapshot without reading USD old values."""

        write_index = 0
        previous_snapshot = self._last_committed_snapshot if skip_unchanged else None
        flow_values = self._flow_payload(snapshot.rows[0])
        previous_flow_values = (
            self._flow_payload(previous_snapshot.rows[0])
            if previous_snapshot is not None
            else {}
        )
        for name, value in flow_values.items():
            write_index = self._set_derived_attribute_lightweight(
                emitter,
                name,
                Sdf.ValueTypeNames.Float,
                value,
                previous_flow_values.get(name),
                write_index,
                label=f"Emitter.{name}",
                notify_observer=notify_observer,
                skip_unchanged=skip_unchanged,
            )

        revision_writes = []
        for row_index, (log_id, prim, row) in enumerate(
            zip(self._log_ids, log_prims, snapshot.rows)
        ):
            values = self._log_payload(log_id, row)
            previous_row = (
                previous_snapshot.rows[row_index]
                if previous_snapshot is not None
                else None
            )
            previous_values = (
                self._log_payload(log_id, previous_row)
                if previous_row is not None
                else {}
            )
            display_color = UsdGeom.Gprim(prim).GetDisplayColorAttr()
            if not display_color:
                raise RuntimeError(f"Log {log_id} has no displayColor attribute")
            color = [self._visual_color(row, self._initial_dry_mass_kg[log_id])]
            previous_color = (
                [
                    self._visual_color(
                        previous_row, self._initial_dry_mass_kg[log_id]
                    )
                ]
                if previous_row is not None
                else None
            )
            write_index = self._set_derived_attribute_lightweight(
                prim,
                display_color.GetName(),
                display_color.GetTypeName(),
                color,
                previous_color,
                write_index,
                label=f"{log_id}.{display_color.GetName()}",
                notify_observer=notify_observer,
                skip_unchanged=skip_unchanged,
            )
            for name, value in values.items():
                write_index = self._set_derived_attribute_lightweight(
                    prim,
                    name,
                    Sdf.ValueTypeNames.Double,
                    value,
                    previous_values.get(name),
                    write_index,
                    label=f"{log_id}.{name}",
                    notify_observer=notify_observer,
                    skip_unchanged=skip_unchanged,
                )
            revision_writes.append((log_id, prim))

        # Revisions are commit markers: payload first, log revisions next, and the
        # emitter revision last so a reader can reject an incomplete publication.
        for log_id, prim in revision_writes:
            write_index = self._set_attribute_lightweight(
                prim,
                "campfire:residentRevision",
                Sdf.ValueTypeNames.Int64,
                snapshot.revision,
                write_index,
                label=f"{log_id}.campfire:residentRevision",
                notify_observer=notify_observer,
            )
        self._set_attribute_lightweight(
            emitter,
            "campfire:residentRevision",
            Sdf.ValueTypeNames.Int64,
            snapshot.revision,
            write_index,
            label="Emitter.campfire:residentRevision",
            notify_observer=notify_observer,
        )

    def _publish_lightweight(self, snapshot, emitter, log_prims):
        previous_snapshot = self._last_committed_snapshot
        try:
            self._write_snapshot_lightweight(
                snapshot,
                emitter,
                log_prims,
                notify_observer=True,
                skip_unchanged=self._skip_unchanged_derived,
            )
        except Exception:
            self._lightweight_failure_count += 1
            try:
                self._write_snapshot_lightweight(
                    previous_snapshot,
                    emitter,
                    log_prims,
                    notify_observer=False,
                    skip_unchanged=False,
                )
            except Exception as recovery_error:
                self._faulted = True
                raise RuntimeError(
                    "Resident lightweight publication and snapshot recovery failed"
                ) from recovery_error
            self._lightweight_recovery_count += 1
            raise
        self._revision = snapshot.revision
        self._publish_count += 1
        self._lightweight_commit_count += 1
        self._last_committed_snapshot = snapshot

    @staticmethod
    def _add_elapsed(profile, name, started_ns):
        profile[name] += (time.perf_counter_ns() - started_ns) / 1_000_000.0

    @classmethod
    def _usd_values_equal(cls, previous_value, stored_value):
        if previous_value is stored_value:
            return True
        if previous_value is None or stored_value is None:
            return False
        if isinstance(previous_value, (str, bytes)) or isinstance(
            stored_value, (str, bytes)
        ):
            return previous_value == stored_value
        try:
            previous_length = len(previous_value)
            stored_length = len(stored_value)
        except TypeError:
            try:
                return bool(previous_value == stored_value)
            except (TypeError, ValueError):
                return False
        if previous_length != stored_length:
            return False
        return all(
            cls._usd_values_equal(previous_item, stored_item)
            for previous_item, stored_item in zip(previous_value, stored_value)
        )

    def _set_attribute_profiled(
        self, prim, name, type_name, value, restores, profile, group, label
    ):
        operation_started = time.perf_counter_ns()
        started = time.perf_counter_ns()
        property_existed, attribute = self._resolve_attribute(
            prim, name, type_name, label
        )
        self._add_elapsed(profile, "attribute_lookup_ms", started)
        if property_existed:
            profile["existing_property_count"] += 1
        else:
            profile["created_property_count"] += 1

        started = time.perf_counter_ns()
        authored_value_existed = attribute.HasAuthoredValueOpinion()
        previous_value = attribute.Get() if authored_value_existed else None
        self._add_elapsed(profile, "old_value_capture_ms", started)
        if authored_value_existed:
            profile["authored_old_value_count"] += 1

        started = time.perf_counter_ns()
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
        self._add_elapsed(profile, "journal_append_ms", started)

        started = time.perf_counter_ns()
        if not attribute.Set(value):
            raise RuntimeError(f"Unable to publish USD attribute {prim.GetPath()}.{name}")
        set_elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        profile["attribute_set_ms"] += set_elapsed_ms
        profile["attribute_set_detail_ms"][label] = set_elapsed_ms
        profile["write_count"] += 1

        started = time.perf_counter_ns()
        stored_value = attribute.Get()
        unchanged = authored_value_existed and self._usd_values_equal(
            previous_value, stored_value
        )
        self._add_elapsed(profile, "value_audit_ms", started)
        disposition = "unchanged" if unchanged else "changed"
        profile[f"{disposition}_write_count"] += 1
        group_disposition = profile["group_write_disposition"].setdefault(
            group, {"changed": 0, "unchanged": 0}
        )
        group_disposition[disposition] += 1
        profile["attribute_write_disposition"][label] = disposition
        if self._write_observer is not None:
            started = time.perf_counter_ns()
            self._write_observer(len(restores), name)
            self._add_elapsed(profile, "write_observer_ms", started)
        operation_ms = (time.perf_counter_ns() - operation_started) / 1_000_000.0
        profile["group_ms"][group] = profile["group_ms"].get(group, 0.0) + operation_ms
        profile["attribute_ms"][label] = operation_ms

    @staticmethod
    def _new_profile():
        return {
            "validation_ms": 0.0,
            "prim_lookup_ms": 0.0,
            "payload_preparation_ms": 0.0,
            "attribute_lookup_ms": 0.0,
            "old_value_capture_ms": 0.0,
            "journal_append_ms": 0.0,
            "attribute_set_ms": 0.0,
            "value_audit_ms": 0.0,
            "write_observer_ms": 0.0,
            "commit_ms": 0.0,
            "rollback_ms": 0.0,
            "write_count": 0,
            "changed_write_count": 0,
            "unchanged_write_count": 0,
            "existing_property_count": 0,
            "created_property_count": 0,
            "authored_old_value_count": 0,
            "group_ms": {},
            "attribute_ms": {},
            "attribute_set_detail_ms": {},
            "group_write_disposition": {},
            "attribute_write_disposition": {},
        }

    def _finish_profile(self, profile, status, transaction_started_ns):
        total_ms = (time.perf_counter_ns() - transaction_started_ns) / 1_000_000.0
        attributed_ms = sum(
            profile[name]
            for name in (
                "validation_ms",
                "prim_lookup_ms",
                "payload_preparation_ms",
                "attribute_lookup_ms",
                "old_value_capture_ms",
                "journal_append_ms",
                "attribute_set_ms",
                "value_audit_ms",
                "write_observer_ms",
                "commit_ms",
                "rollback_ms",
            )
        )
        self._transaction_profiles.append(
            ResidentUsdTransactionProfile(
                status=status,
                total_ms=total_ms,
                validation_ms=profile["validation_ms"],
                prim_lookup_ms=profile["prim_lookup_ms"],
                payload_preparation_ms=profile["payload_preparation_ms"],
                attribute_lookup_ms=profile["attribute_lookup_ms"],
                old_value_capture_ms=profile["old_value_capture_ms"],
                journal_append_ms=profile["journal_append_ms"],
                attribute_set_ms=profile["attribute_set_ms"],
                value_audit_ms=profile["value_audit_ms"],
                write_observer_ms=profile["write_observer_ms"],
                commit_ms=profile["commit_ms"],
                rollback_ms=profile["rollback_ms"],
                unattributed_ms=max(0.0, total_ms - attributed_ms),
                write_count=profile["write_count"],
                changed_write_count=profile["changed_write_count"],
                unchanged_write_count=profile["unchanged_write_count"],
                existing_property_count=profile["existing_property_count"],
                created_property_count=profile["created_property_count"],
                authored_old_value_count=profile["authored_old_value_count"],
                group_ms=tuple(sorted(profile["group_ms"].items())),
                attribute_ms=tuple(sorted(profile["attribute_ms"].items())),
                attribute_set_detail_ms=tuple(
                    sorted(profile["attribute_set_detail_ms"].items())
                ),
                group_write_disposition=tuple(
                    sorted(
                        (name, counts["changed"], counts["unchanged"])
                        for name, counts in profile[
                            "group_write_disposition"
                        ].items()
                    )
                ),
                attribute_write_disposition=tuple(
                    sorted(profile["attribute_write_disposition"].items())
                ),
            )
        )

    def publish(self, snapshot: ResidentPublishedSnapshot):
        profile = self._new_profile() if self._profile_transactions else None
        transaction_started = time.perf_counter_ns() if profile is not None else 0
        started = time.perf_counter_ns() if profile is not None else 0
        self._require_publishable(snapshot)
        if profile is not None:
            self._add_elapsed(profile, "validation_ms", started)
            started = time.perf_counter_ns()
        emitter, log_prims = self._resolve_publish_prims()
        if profile is not None:
            self._add_elapsed(profile, "prim_lookup_ms", started)

        if self._lightweight_commits and self._last_committed_snapshot is not None:
            self._publish_lightweight(snapshot, emitter, log_prims)
            return

        restores = []
        try:
            started = time.perf_counter_ns() if profile is not None else 0
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
            if profile is not None:
                self._add_elapsed(profile, "payload_preparation_ms", started)
            for name, value in flow_values.items():
                self._set_attribute(
                    emitter,
                    name,
                    Sdf.ValueTypeNames.Float,
                    value,
                    restores,
                    profile=profile,
                    group="emitter_payload",
                    label=f"Emitter.{name}",
                )
            self._set_attribute(
                emitter,
                "campfire:residentRevision",
                Sdf.ValueTypeNames.Int64,
                snapshot.revision,
                restores,
                profile=profile,
                group="revision",
                label="Emitter.campfire:residentRevision",
            )

            for log_id, prim, row in zip(self._log_ids, log_prims, snapshot.rows):
                started = time.perf_counter_ns() if profile is not None else 0
                char_fraction = min(
                    1.0,
                    (row.char_mass_kg + row.ash_mass_kg)
                    / max(self._initial_dry_mass_kg[log_id], 1.0e-12),
                )
                color = self._visual_color(row, self._initial_dry_mass_kg[log_id])
                values = {
                    "campfire:surfaceTemperatureK": row.surface_mean_temperature_k,
                    "campfire:charFraction": char_fraction,
                    "campfire:remainingMassRatio": row.remaining_mass_ratio,
                    "campfire:weakestSupportRatio": row.weakest_support_ratio,
                }
                if profile is not None:
                    self._add_elapsed(profile, "payload_preparation_ms", started)
                    started = time.perf_counter_ns()
                display_color = UsdGeom.Gprim(prim).GetDisplayColorAttr()
                if not display_color:
                    raise RuntimeError(f"Log {log_id} has no displayColor attribute")
                if profile is not None:
                    self._add_elapsed(profile, "attribute_lookup_ms", started)
                self._set_attribute(
                    prim,
                    display_color.GetName(),
                    display_color.GetTypeName(),
                    [color],
                    restores,
                    profile=profile,
                    group="visual_payload",
                    label=f"{log_id}.{display_color.GetName()}",
                )
                for name, value in values.items():
                    self._set_attribute(
                        prim,
                        name,
                        Sdf.ValueTypeNames.Double,
                        value,
                        restores,
                        profile=profile,
                        group="diagnostic_payload",
                        label=f"{log_id}.{name}",
                    )
                self._set_attribute(
                    prim,
                    "campfire:residentRevision",
                    Sdf.ValueTypeNames.Int64,
                    snapshot.revision,
                    restores,
                    profile=profile,
                    group="revision",
                    label=f"{log_id}.campfire:residentRevision",
                )
        except Exception:
            started = time.perf_counter_ns() if profile is not None else 0
            for restore in reversed(restores):
                restore.rollback()
            self._prune_invalid_attribute_handles()
            if profile is not None:
                self._add_elapsed(profile, "rollback_ms", started)
                self._finish_profile(profile, "rolled_back", transaction_started)
            raise
        started = time.perf_counter_ns() if profile is not None else 0
        self._revision = snapshot.revision
        self._publish_count += 1
        if self._lightweight_commits:
            self._last_committed_snapshot = snapshot
        if profile is not None:
            self._add_elapsed(profile, "commit_ms", started)
            self._finish_profile(profile, "committed", transaction_started)

    def transaction_profiles(self):
        self._require_owner()
        return tuple(self._transaction_profiles)

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
            "transaction_profiling_enabled": self._profile_transactions,
            "transaction_profile_count": len(self._transaction_profiles),
            "handle_cache_enabled": self._cache_usd_handles,
            "cached_attribute_count": len(self._attribute_cache),
            "prim_cache_hit_count": self._prim_cache_hit_count,
            "prim_cache_miss_count": self._prim_cache_miss_count,
            "attribute_cache_hit_count": self._attribute_cache_hit_count,
            "attribute_cache_miss_count": self._attribute_cache_miss_count,
            "lightweight_commit_enabled": self._lightweight_commits,
            "lightweight_commit_count": self._lightweight_commit_count,
            "lightweight_failure_count": self._lightweight_failure_count,
            "lightweight_recovery_count": self._lightweight_recovery_count,
            "skip_unchanged_derived_enabled": self._skip_unchanged_derived,
            "lightweight_write_count": self._lightweight_write_count,
            "skipped_unchanged_write_count": self._skipped_unchanged_write_count,
            "faulted": self._faulted,
        }

    def close(self):
        self._require_owner()
        if self._closed:
            return False
        if self._active:
            self.on_timeline_stopped()
        self._attribute_cache.clear()
        self._cached_emitter = None
        self._cached_log_prims = ()
        self._last_committed_snapshot = None
        self._closed = True
        return True
