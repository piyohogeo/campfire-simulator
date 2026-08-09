"""Default-off eight-band diagnostic visual derived from stable wood cells."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

from .resident_snapshot import ResidentPublishedRow
from .wood_visual_v0 import (
    WOOD_VISUAL_V0_INPUT_NAMES,
    neutral_wood_visual_uniform,
    wood_visual_uniform_from_row,
)


WOOD_VISUAL_V1_SETTING = "/exts/campfire.app/woodVisualV1Enabled"
WOOD_VISUAL_V1_ROOT = Sdf.Path("/World/WoodVisualV1")
WOOD_VISUAL_V1_LOOKS_ROOT = Sdf.Path("/World/Looks/WoodVisualV1")
WOOD_VISUAL_V1_REVISION_ATTRIBUTE = "campfire:committedRevision"
WOOD_VISUAL_V1_BAND_COUNT = 8


@dataclass(frozen=True)
class WoodVisualBandSnapshot:
    """Immutable visual-only rows ordered by log, then axial band."""

    revision: int
    log_ids: tuple[str, ...]
    rows: tuple[ResidentPublishedRow, ...]

    def __post_init__(self):
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise ValueError("Wood band revision must be an integer")
        if self.revision <= 0 or not self.log_ids:
            raise ValueError("Wood band snapshot metadata is invalid")
        if len(set(self.log_ids)) != len(self.log_ids):
            raise ValueError("Wood band log ids must be unique")
        if len(self.rows) != len(self.log_ids) * WOOD_VISUAL_V1_BAND_COUNT:
            raise ValueError("Wood band rows must contain eight rows per log")


@dataclass(frozen=True)
class WoodVisualBandPublicationProfile:
    revision: int
    status: str
    total_ms: float
    value_generation_ms: float
    usd_set_ms: float
    usd_set_count: int
    skipped_set_count: int


def aggregate_model_into_visual_bands(model) -> tuple[ResidentPublishedRow, ...]:
    """Aggregate stable local cell indices into eight deterministic axial bands."""

    spec = model.spec
    if spec.axial_cells % WOOD_VISUAL_V1_BAND_COUNT:
        raise ValueError("Axial cell count must divide evenly into eight bands")
    cells_per_axial = spec.circumferential_cells * spec.radial_cells
    axial_per_band = spec.axial_cells // WOOD_VISUAL_V1_BAND_COUNT
    rows = []
    for band in range(WOOD_VISUAL_V1_BAND_COUNT):
        first = band * axial_per_band * cells_per_axial
        last = (band + 1) * axial_per_band * cells_per_axial
        surface = [cell for cell in model.cells[first:last] if cell.surface_exposure > 0.0]
        if not surface:
            raise ValueError("Wood visual band contains no exposed cells")
        area = sum(cell.external_area_m2 * cell.surface_exposure for cell in surface)
        temperature = (
            sum(
                cell.temperature_k * cell.external_area_m2 * cell.surface_exposure
                for cell in surface
            )
            / max(area, 1.0e-12)
        )
        masses = tuple(
            sum(getattr(cell, name) for cell in surface)
            for name in (
                "moisture_mass_kg",
                "dry_wood_mass_kg",
                "char_mass_kg",
                "ash_mass_kg",
            )
        )
        rows.append(
            ResidentPublishedRow(
                temperature,
                *masses,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
            )
        )
    return tuple(rows)


def _band_path(log_id, band):
    return WOOD_VISUAL_V1_ROOT.AppendChild(log_id).AppendChild(f"Band_{band:02d}")


def _material_path(log_id, band):
    return WOOD_VISUAL_V1_LOOKS_ROOT.AppendChild(log_id).AppendChild(
        f"Band_{band:02d}"
    )


def preauthor_wood_visual_v1(stage: Usd.Stage, log_ids) -> dict:
    """Pre-author render-only band geometry and materials before stage connection."""

    log_ids = tuple(str(value) for value in log_ids)
    if stage is None or not log_ids or len(set(log_ids)) != len(log_ids):
        raise ValueError("Wood visual V1 requires a stage and unique logs")
    UsdGeom.Scope.Define(stage, WOOD_VISUAL_V1_ROOT)
    UsdGeom.Scope.Define(stage, WOOD_VISUAL_V1_LOOKS_ROOT)
    root = stage.GetPrimAtPath(WOOD_VISUAL_V1_ROOT)
    root.CreateAttribute(WOOD_VISUAL_V1_REVISION_ATTRIBUTE, Sdf.ValueTypeNames.Int64).Set(0)
    neutral = neutral_wood_visual_uniform()
    paths = []
    for log_id in log_ids:
        source = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        if not source or not source.IsA(UsdGeom.Cylinder):
            raise ValueError(f"Wood visual V1 source log is unavailable: {log_id}")
        radius = float(source.GetAttribute("radius").Get())
        height = float(source.GetAttribute("height").Get())
        parent = UsdGeom.Xform.Define(stage, WOOD_VISUAL_V1_ROOT.AppendChild(log_id))
        local_transform = UsdGeom.Xformable(source).GetLocalTransformation()
        parent.AddTransformOp().Set(local_transform)
        UsdGeom.Imageable(source).GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        band_height = height / WOOD_VISUAL_V1_BAND_COUNT
        for band in range(WOOD_VISUAL_V1_BAND_COUNT):
            cylinder = UsdGeom.Cylinder.Define(stage, _band_path(log_id, band))
            cylinder.CreateAxisAttr(UsdGeom.Tokens.x)
            cylinder.CreateRadiusAttr(radius * 1.002)
            cylinder.CreateHeightAttr(band_height * 0.995)
            center = -0.5 * height + (band + 0.5) * band_height
            cylinder.AddTranslateOp().Set(Gf.Vec3d(center, 0.0, 0.0))
            prim = cylinder.GetPrim()
            prim.CreateAttribute("campfire:renderOnly", Sdf.ValueTypeNames.Bool).Set(True)
            prim.CreateAttribute("campfire:localBandIndex", Sdf.ValueTypeNames.Int).Set(band)
            material_path = _material_path(log_id, band)
            material = UsdShade.Material.Define(stage, material_path)
            shader = UsdShade.Shader.Define(stage, material_path.AppendChild("Shader"))
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(*neutral.base_color)
            )
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(neutral.roughness)
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(*neutral.emission_color)
            )
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
            paths.append(str(prim.GetPath()))
    return {
        "root": str(WOOD_VISUAL_V1_ROOT),
        "log_ids": list(log_ids),
        "band_count": WOOD_VISUAL_V1_BAND_COUNT,
        "render_prim_paths": paths,
        "physical_cylinder_split": False,
    }


class WoodVisualV1Consumer:
    """Best-effort V1 diagnostic observer; never participates in physics rollback."""

    def __init__(self, stage, log_ids):
        self._stage = stage
        self._log_ids = tuple(str(value) for value in log_ids)
        self._owner = threading.get_ident()
        self._active = False
        self._closed = False
        self._revision = 0
        root = stage.GetPrimAtPath(WOOD_VISUAL_V1_ROOT)
        if not root:
            raise ValueError("Wood visual V1 must be pre-authored")
        self._revision_attr = root.GetAttribute(WOOD_VISUAL_V1_REVISION_ATTRIBUTE)
        self._inputs = []
        self._values = []
        for log_id in self._log_ids:
            for band in range(WOOD_VISUAL_V1_BAND_COUNT):
                shader = UsdShade.Shader.Get(stage, _material_path(log_id, band).AppendChild("Shader"))
                attrs = tuple(shader.GetInput(name).GetAttr() for name in WOOD_VISUAL_V0_INPUT_NAMES)
                if not shader or not all(attrs):
                    raise ValueError("Wood visual V1 material is incomplete")
                self._inputs.append(attrs)
                self._values.append(tuple(attr.Get() for attr in attrs))

    def _require_owner(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError("Wood visual V1 consumer must run on its owner thread")

    def on_timeline_started(self):
        self._require_owner()
        if self._closed:
            raise RuntimeError("Wood visual V1 consumer is closed")
        self._active = True

    @staticmethod
    def _equal(left, right):
        if isinstance(left, Gf.Vec3f) or isinstance(right, Gf.Vec3f):
            return Gf.IsClose(left, right, 1.0e-7)
        return math.isclose(float(left), float(right), abs_tol=1.0e-7)

    def publish(self, snapshot: WoodVisualBandSnapshot):
        self._require_owner()
        if self._closed or not self._active:
            raise RuntimeError("Wood visual V1 requires an active timeline")
        if snapshot.log_ids != self._log_ids:
            raise ValueError("Wood visual V1 log order does not match")
        if snapshot.revision == self._revision:
            return WoodVisualBandPublicationProfile(snapshot.revision, "unchanged_revision", 0.0, 0.0, 0.0, 0, 0)
        if snapshot.revision < self._revision:
            raise RuntimeError("Wood visual V1 revision must increase monotonically")
        started = time.perf_counter_ns()
        generated = []
        for row in snapshot.rows:
            visual = wood_visual_uniform_from_row(row)
            generated.append((Gf.Vec3f(*visual.base_color), float(visual.roughness), Gf.Vec3f(*visual.emission_color)))
        generated_at = time.perf_counter_ns()
        written = []
        sets = 0
        skipped = 0
        try:
            with Sdf.ChangeBlock():
                for attrs, values, previous in zip(self._inputs, generated, self._values):
                    for attr, value, old in zip(attrs, values, previous):
                        if self._equal(value, old):
                            skipped += 1
                            continue
                        if not attr.Set(value):
                            raise RuntimeError("Wood visual V1 input Set failed")
                        written.append((attr, old))
                        sets += 1
                if not self._revision_attr.Set(snapshot.revision):
                    raise RuntimeError("Wood visual V1 revision Set failed")
                sets += 1
        except Exception:
            with Sdf.ChangeBlock():
                for attr, old in reversed(written):
                    attr.Set(old)
                self._revision_attr.Set(self._revision)
            raise
        finished = time.perf_counter_ns()
        self._values = generated
        self._revision = snapshot.revision
        return WoodVisualBandPublicationProfile(
            snapshot.revision,
            "committed",
            (finished - started) / 1_000_000.0,
            (generated_at - started) / 1_000_000.0,
            (finished - generated_at) / 1_000_000.0,
            sets,
            skipped,
        )

    def close(self):
        self._require_owner()
        if self._closed:
            return False
        self._active = False
        self._closed = True
        return True
