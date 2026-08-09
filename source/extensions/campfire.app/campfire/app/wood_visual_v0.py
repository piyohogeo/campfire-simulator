"""Default-off per-log beauty material derived from Resident snapshots."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdShade

from .resident_snapshot import ResidentPublishedRow, ResidentPublishedSnapshot


WOOD_VISUAL_V0_SETTING = "/exts/campfire.app/woodVisualV0Enabled"
WOOD_VISUAL_V0_ROOT = Sdf.Path("/World/Looks/WoodVisualV0")
WOOD_VISUAL_V0_REVISION_ATTRIBUTE = "campfire:committedRevision"
WOOD_VISUAL_V0_INPUT_NAMES = ("diffuseColor", "roughness", "emissiveColor")

_DRY_COLOR = (0.30, 0.12, 0.045)
_CHAR_COLOR = (0.025, 0.022, 0.020)
_ASH_COLOR = (0.68, 0.66, 0.62)
_EPSILON_KG = 1.0e-12


@dataclass(frozen=True)
class WoodVisualUniform:
    """Three shader uniforms generated deterministically from one log row."""

    base_color: tuple[float, float, float]
    roughness: float
    emission_color: tuple[float, float, float]
    moisture_fraction: float
    char_fraction: float
    ash_fraction: float

    def __post_init__(self):
        values = (
            *self.base_color,
            self.roughness,
            *self.emission_color,
            self.moisture_fraction,
            self.char_fraction,
            self.ash_fraction,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Wood visual uniforms must be finite")
        if not all(0.0 <= value <= 1.0 for value in self.base_color):
            raise ValueError("Wood visual base color must be within [0, 1]")
        if not 0.0 <= self.roughness <= 1.0:
            raise ValueError("Wood visual roughness must be within [0, 1]")
        if not all(0.0 <= value <= 4.0 for value in self.emission_color):
            raise ValueError("Wood visual emission must be within [0, 4]")
        for value in (
            self.moisture_fraction,
            self.char_fraction,
            self.ash_fraction,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError("Wood visual fractions must be within [0, 1]")


@dataclass(frozen=True)
class WoodVisualPublicationProfile:
    revision: int
    status: str
    total_ms: float
    value_generation_ms: float
    usd_set_ms: float
    usd_set_count: int
    skipped_set_count: int
    notice_count: int


def _mix(left, right, amount):
    return tuple(
        float(left[index] * (1.0 - amount) + right[index] * amount)
        for index in range(3)
    )


def _clamp01(value):
    return min(1.0, max(0.0, float(value)))


def neutral_wood_visual_uniform() -> WoodVisualUniform:
    return WoodVisualUniform(
        base_color=_DRY_COLOR,
        roughness=0.62,
        emission_color=(0.0, 0.0, 0.0),
        moisture_fraction=0.0,
        char_fraction=0.0,
        ash_fraction=0.0,
    )


def wood_visual_uniform_from_row(row: ResidentPublishedRow) -> WoodVisualUniform:
    """Map authoritative aggregate values to bounded beauty-only uniforms."""

    masses = (
        float(row.moisture_mass_kg),
        float(row.dry_wood_mass_kg),
        float(row.char_mass_kg),
        float(row.ash_mass_kg),
    )
    if not all(math.isfinite(value) and value >= 0.0 for value in masses):
        raise ValueError("Wood visual mass inputs must be finite and non-negative")
    temperature_k = float(row.surface_mean_temperature_k)
    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("Wood visual temperature must be finite and positive")

    moisture, dry_wood, char, ash = masses
    condensed = moisture + dry_wood + char + ash
    non_moisture = dry_wood + char + ash
    moisture_fraction = _clamp01(moisture / max(condensed, _EPSILON_KG))
    char_fraction = _clamp01(char / max(non_moisture, _EPSILON_KG))
    ash_fraction = _clamp01(ash / max(non_moisture, _EPSILON_KG))

    # Moisture first darkens and slightly desaturates the normal wood tone.
    wet_amount = _clamp01(moisture_fraction / 0.38)
    wet_color = _mix(_DRY_COLOR, (0.105, 0.070, 0.050), wet_amount)
    # Composition priority is ash > char > wet/dry wood.
    base_color = _mix(wet_color, _CHAR_COLOR, char_fraction)
    base_color = _mix(base_color, _ASH_COLOR, ash_fraction)

    roughness = 0.62 + (0.43 - 0.62) * wet_amount
    roughness += (0.86 - roughness) * char_fraction
    roughness += (0.98 - roughness) * ash_fraction
    roughness = _clamp01(roughness)

    if temperature_k < 650.0:
        emission = (0.0, 0.0, 0.0)
    elif temperature_k < 800.0:
        amount = (temperature_k - 650.0) / 150.0
        emission = _mix((0.06, 0.001, 0.0), (0.65, 0.035, 0.002), amount)
    elif temperature_k < 1000.0:
        amount = (temperature_k - 800.0) / 200.0
        emission = _mix((0.65, 0.035, 0.002), (1.8, 0.36, 0.018), amount)
    else:
        amount = _clamp01((temperature_k - 1000.0) / 300.0)
        emission = _mix((1.8, 0.36, 0.018), (4.0, 2.2, 0.65), amount)
    combustible_mask = 1.0 - 0.85 * ash_fraction
    emission = tuple(value * combustible_mask for value in emission)

    return WoodVisualUniform(
        base_color=tuple(_clamp01(value) for value in base_color),
        roughness=roughness,
        emission_color=emission,
        moisture_fraction=moisture_fraction,
        char_fraction=char_fraction,
        ash_fraction=ash_fraction,
    )


def _material_path(log_id: str) -> Sdf.Path:
    return WOOD_VISUAL_V0_ROOT.AppendChild(log_id)


def preauthor_wood_visual_v0(stage: Usd.Stage, log_ids) -> dict:
    """Create stable render materials before a stage is connected to Kit."""

    log_ids = tuple(str(log_id) for log_id in log_ids)
    if stage is None or not log_ids or len(set(log_ids)) != len(log_ids):
        raise ValueError("Wood visual pre-authoring requires a stage and unique logs")
    if not stage.GetPrimAtPath("/World/Looks"):
        UsdGeom.Scope.Define(stage, "/World/Looks")
    root = UsdGeom.Scope.Define(stage, WOOD_VISUAL_V0_ROOT).GetPrim()
    root.CreateAttribute(
        WOOD_VISUAL_V0_REVISION_ATTRIBUTE, Sdf.ValueTypeNames.Int64
    ).Set(0)
    neutral = neutral_wood_visual_uniform()
    bindings = {}
    for log_id in log_ids:
        log_prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        if not log_prim or not log_prim.IsA(UsdGeom.Gprim):
            raise ValueError(f"Wood visual log is unavailable: {log_id}")
        material_path = _material_path(log_id)
        material = UsdShade.Material.Define(stage, material_path)
        shader = UsdShade.Shader.Define(stage, material_path.AppendChild("Shader"))
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*neutral.base_color)
        )
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(
            neutral.roughness
        )
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*neutral.emission_color)
        )
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )
        UsdShade.MaterialBindingAPI.Apply(log_prim).Bind(material)
        bindings[log_id] = str(material_path)
    return {
        "root": str(WOOD_VISUAL_V0_ROOT),
        "log_ids": list(log_ids),
        "bindings": bindings,
        "initial_revision": 0,
    }


class WoodVisualV0Consumer:
    """Owner-thread, best-effort visual observer with independent rollback."""

    def __init__(self, stage: Usd.Stage, log_ids, *, track_notices=False, write_observer=None):
        self._stage = stage
        self._log_ids = tuple(str(log_id) for log_id in log_ids)
        if stage is None or not self._log_ids or len(set(self._log_ids)) != len(self._log_ids):
            raise ValueError("Wood visual consumer requires a stage and unique logs")
        self._owner_thread_id = threading.get_ident()
        self._write_observer = write_observer
        root = stage.GetPrimAtPath(WOOD_VISUAL_V0_ROOT)
        if not root:
            raise ValueError("Wood visual materials must be pre-authored")
        self._revision_attribute = root.GetAttribute(WOOD_VISUAL_V0_REVISION_ATTRIBUTE)
        if not self._revision_attribute:
            raise ValueError("Wood visual revision marker is unavailable")
        self._inputs = {}
        self._committed_values = {}
        for log_id in self._log_ids:
            shader = UsdShade.Shader.Get(
                stage, _material_path(log_id).AppendChild("Shader")
            )
            inputs = tuple(shader.GetInput(name) for name in WOOD_VISUAL_V0_INPUT_NAMES)
            if not shader or not all(inputs):
                raise ValueError(f"Wood visual material is incomplete: {log_id}")
            attributes = tuple(value.GetAttr() for value in inputs)
            self._inputs[log_id] = attributes
            self._committed_values[log_id] = tuple(
                value.Get() for value in attributes
            )
        self._revision = int(self._revision_attribute.Get() or 0)
        self._active = False
        self._closed = False
        self._publish_count = 0
        self._skip_count = 0
        self._failure_count = 0
        self._recovery_count = 0
        self._usd_set_count = 0
        self._notice_count = 0
        self._publication_notice_count = 0
        self._notice_active = False
        self._profiles = []
        self._listener = (
            Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._observe_notice, stage)
            if track_notices
            else None
        )

    def _require_owner(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Wood visual consumer must run on its owner thread")

    def _observe_notice(self, _notice, _sender):
        if self._notice_active:
            self._notice_count += 1

    def on_timeline_started(self):
        self._require_owner()
        if self._closed:
            raise RuntimeError("Wood visual consumer is closed")
        self._active = True

    def on_timeline_stopped(self):
        self._require_owner()
        self._active = False

    @staticmethod
    def _uniform_values(uniform):
        return (
            Gf.Vec3f(*uniform.base_color),
            float(uniform.roughness),
            Gf.Vec3f(*uniform.emission_color),
        )

    @staticmethod
    def _equal(left, right):
        if isinstance(left, Gf.Vec3f) or isinstance(right, Gf.Vec3f):
            return Gf.IsClose(left, right, 1.0e-7)
        return abs(float(left) - float(right)) <= 1.0e-7

    def publish(self, snapshot: ResidentPublishedSnapshot):
        self._require_owner()
        if self._closed or not self._active:
            raise RuntimeError("Wood visual consumer requires an active timeline")
        if snapshot.log_ids != self._log_ids:
            raise ValueError("Wood visual snapshot log order does not match")
        if snapshot.revision == self._revision:
            self._skip_count += 1
            profile = WoodVisualPublicationProfile(
                snapshot.revision, "unchanged_revision", 0.0, 0.0, 0.0, 0, 0, 0
            )
            self._profiles.append(profile)
            return profile
        if snapshot.revision < self._revision:
            raise RuntimeError("Wood visual revision must increase monotonically")

        started_ns = time.perf_counter_ns()
        generated = tuple(
            self._uniform_values(wood_visual_uniform_from_row(row))
            for row in snapshot.rows
        )
        generated_ns = time.perf_counter_ns()
        written = []
        skipped = 0
        sets = 0
        notice_before = self._notice_count
        self._notice_active = True
        try:
            with Sdf.ChangeBlock():
                for log_id, values in zip(self._log_ids, generated):
                    previous_values = self._committed_values[log_id]
                    for input_handle, value, previous in zip(
                        self._inputs[log_id], values, previous_values
                    ):
                        if self._equal(value, previous):
                            skipped += 1
                            continue
                        if not input_handle.Set(value):
                            raise RuntimeError(
                                f"Unable to update wood visual input: {log_id}.{input_handle.GetName()}"
                            )
                        written.append((input_handle, previous))
                        sets += 1
                        if self._write_observer is not None:
                            self._write_observer(sets, log_id, input_handle.GetName())
                if not self._revision_attribute.Set(snapshot.revision):
                    raise RuntimeError("Unable to commit wood visual revision")
                sets += 1
        except Exception:
            self._failure_count += 1
            with Sdf.ChangeBlock():
                for input_handle, previous in reversed(written):
                    input_handle.Set(previous)
                self._revision_attribute.Set(self._revision)
            self._recovery_count += 1
            raise
        finally:
            self._notice_active = False

        finished_ns = time.perf_counter_ns()
        self._committed_values = {
            log_id: values for log_id, values in zip(self._log_ids, generated)
        }
        self._revision = snapshot.revision
        self._publish_count += 1
        self._usd_set_count += sets
        notice_count = self._notice_count - notice_before
        self._publication_notice_count += notice_count
        profile = WoodVisualPublicationProfile(
            revision=snapshot.revision,
            status="committed",
            total_ms=(finished_ns - started_ns) / 1_000_000.0,
            value_generation_ms=(generated_ns - started_ns) / 1_000_000.0,
            usd_set_ms=(finished_ns - generated_ns) / 1_000_000.0,
            usd_set_count=sets,
            skipped_set_count=skipped,
            notice_count=notice_count,
        )
        self._profiles.append(profile)
        return profile

    def profiles(self):
        self._require_owner()
        return tuple(self._profiles)

    def status(self):
        self._require_owner()
        return {
            "enabled": True,
            "active": self._active,
            "closed": self._closed,
            "revision": self._revision,
            "publish_count": self._publish_count,
            "skip_count": self._skip_count,
            "failure_count": self._failure_count,
            "recovery_count": self._recovery_count,
            "usd_set_count": self._usd_set_count,
            "notice_count": self._publication_notice_count,
            "log_ids": list(self._log_ids),
        }

    def close(self):
        self._require_owner()
        if self._closed:
            return False
        self._active = False
        if self._listener is not None:
            self._listener.Revoke()
            self._listener = None
        self._closed = True
        return True
