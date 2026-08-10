"""Default-off V2 surface payload to fixed V3 Mesh texture observer."""

from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass

import numpy as np
from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdShade

from .wood import get_log_render_surface
from .wood_render_mesh import (
    WOOD_ATLAS_CELL_COLUMNS,
    WOOD_ATLAS_CELL_ROWS,
    WOOD_RENDER_MAX_LOGS,
    WOOD_SURFACE_CELLS_PER_LOG,
    WoodAtlasDescriptor,
    author_wood_render_mesh_uv,
    compact_atlas_descriptor,
)
from .wood_visual_surface import ImmutableWoodVisualSurfacePayload


WOOD_VISUAL_V3_SETTING = "/exts/campfire.app/woodVisualV3Enabled"
WOOD_VISUAL_V3_ROOT = Sdf.Path("/World/Looks/WoodVisualV3")
WOOD_VISUAL_V3_REVISION_ATTRIBUTE = "campfire:committedRevision"
WOOD_VISUAL_V3_RENDER_LOG_IDS_ATTRIBUTE = "campfire:renderLogIds"
WOOD_VISUAL_V3_ATLAS_LOG_COUNT_ATTRIBUTE = "campfire:atlasRenderLogCount"
WOOD_VISUAL_V3_ATLAS_TILE_COLUMNS_ATTRIBUTE = "campfire:atlasTileColumns"
WOOD_VISUAL_V3_ATLAS_TILE_ROWS_ATTRIBUTE = "campfire:atlasTileRows"
WOOD_VISUAL_V3_ATLAS_CELL_STRIDE_ATTRIBUTE = "campfire:atlasCellStridePx"
WOOD_VISUAL_V3_BASE_TEXTURE_NAME = "campfire_wood_visual_v3_base"
WOOD_VISUAL_V3_EMISSION_TEXTURE_NAME = "campfire_wood_visual_v3_emission"
WOOD_VISUAL_V3_BASE_TEXTURE_URI = f"dynamic://{WOOD_VISUAL_V3_BASE_TEXTURE_NAME}"
WOOD_VISUAL_V3_EMISSION_TEXTURE_URI = (
    f"dynamic://{WOOD_VISUAL_V3_EMISSION_TEXTURE_NAME}"
)

_DRY_COLOR = np.array((0.30, 0.12, 0.045), dtype=np.float32)
_WET_COLOR = np.array((0.105, 0.070, 0.050), dtype=np.float32)
_CHAR_COLOR = np.array((0.025, 0.022, 0.020), dtype=np.float32)
_ASH_COLOR = np.array((0.68, 0.66, 0.62), dtype=np.float32)
_MOISTURE_DISPLAY_KG = 0.030
_CHAR_DISPLAY_KG = 0.015
_ASH_DISPLAY_KG = 0.0015


@dataclass(frozen=True)
class WoodVisualV3AtlasPack:
    revision: int
    base_rgba8: np.ndarray
    emission_rgba8: np.ndarray
    pack_ms: float


@dataclass(frozen=True)
class WoodVisualV3PublicationProfile:
    revision: int
    status: str
    total_ms: float
    beauty_pack_ms: float
    boundary_prepare_ms: float
    cpu_upload_ms: float
    revision_commit_ms: float
    upload_count: int
    usd_set_count: int
    notice_count: int
    transferred_bytes: int
    base_changed: bool
    emission_changed: bool


@dataclass(frozen=True)
class WoodVisualV3ScheduleDecision:
    publish: bool
    reason: str
    elapsed_since_publish_seconds: float


class WoodVisualV3AdaptiveScheduler:
    """Bound small-change latency while retaining 5 Hz rapid heat updates."""

    def __init__(
        self,
        *,
        source_interval_seconds=0.2,
        normal_interval_seconds=0.4,
        rapid_temperature_delta_k=25.0,
    ):
        if source_interval_seconds <= 0.0:
            raise ValueError("Wood visual source interval must be positive")
        if not source_interval_seconds <= normal_interval_seconds <= 0.5:
            raise ValueError("Wood visual normal interval must be within 0.5 seconds")
        self.source_interval_seconds = float(source_interval_seconds)
        self.normal_interval_seconds = float(normal_interval_seconds)
        self.rapid_temperature_delta_k = float(rapid_temperature_delta_k)
        self._last_payload = None
        self._last_publish_seconds = None

    def decide(self, payload, model_seconds, *, force=False):
        if not isinstance(payload, ImmutableWoodVisualSurfacePayload):
            raise TypeError("Wood visual scheduler requires the V2 immutable payload")
        model_seconds = float(model_seconds)
        if force or self._last_payload is None:
            return WoodVisualV3ScheduleDecision(True, "full_republish", 0.0)
        elapsed = model_seconds - self._last_publish_seconds
        if elapsed < 0.0:
            raise RuntimeError("Wood visual schedule time must increase monotonically")
        if elapsed + 1.0e-9 < self.source_interval_seconds:
            return WoodVisualV3ScheduleDecision(False, "source_interval", elapsed)
        previous = np.frombuffer(self._last_payload.temperatures, dtype=np.float32)
        current = np.frombuffer(payload.temperatures, dtype=np.float32)
        delta = float(np.max(np.abs(current - previous)))
        crossed = any(
            np.any((previous < threshold) & (current >= threshold))
            for threshold in (650.0, 800.0, 1000.0)
        )
        if crossed or delta >= self.rapid_temperature_delta_k:
            return WoodVisualV3ScheduleDecision(True, "rapid_heat", elapsed)
        if elapsed + 1.0e-9 >= self.normal_interval_seconds:
            return WoodVisualV3ScheduleDecision(True, "normal_bound", elapsed)
        return WoodVisualV3ScheduleDecision(False, "small_change_deferred", elapsed)

    def committed(self, payload, model_seconds):
        self._last_payload = payload
        self._last_publish_seconds = float(model_seconds)

    def reset(self):
        self._last_payload = None
        self._last_publish_seconds = None


def _texture_shader(stage, path, uri):
    texture = UsdShade.Shader.Define(stage, path)
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(uri))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("minFilter", Sdf.ValueTypeNames.Token).Set("nearest")
    texture.CreateInput("magFilter", Sdf.ValueTypeNames.Token).Set("nearest")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    texture.CreateOutput("a", Sdf.ValueTypeNames.Float)
    return texture


def preauthor_wood_visual_v3(stage: Usd.Stage, log_ids) -> dict:
    """Author one stable two-atlas material before connecting the stage."""

    log_ids = tuple(str(value) for value in log_ids)
    if stage is None or not log_ids or len(set(log_ids)) != len(log_ids):
        raise ValueError("Wood visual V3 requires a stage and unique logs")
    if len(log_ids) > WOOD_RENDER_MAX_LOGS:
        raise ValueError("Wood visual V3 supports at most 20 logs")
    descriptor = compact_atlas_descriptor(len(log_ids))
    if not stage.GetPrimAtPath("/World/Looks"):
        UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, WOOD_VISUAL_V3_ROOT)
    root = material.GetPrim()
    root.CreateAttribute(
        WOOD_VISUAL_V3_REVISION_ATTRIBUTE, Sdf.ValueTypeNames.Int64
    ).Set(0)
    root.CreateAttribute(
        WOOD_VISUAL_V3_RENDER_LOG_IDS_ATTRIBUTE, Sdf.ValueTypeNames.StringArray
    ).Set(list(log_ids))
    root.CreateAttribute(
        WOOD_VISUAL_V3_ATLAS_LOG_COUNT_ATTRIBUTE, Sdf.ValueTypeNames.Int
    ).Set(descriptor.render_log_count)
    root.CreateAttribute(
        WOOD_VISUAL_V3_ATLAS_TILE_COLUMNS_ATTRIBUTE, Sdf.ValueTypeNames.Int
    ).Set(descriptor.tile_columns)
    root.CreateAttribute(
        WOOD_VISUAL_V3_ATLAS_TILE_ROWS_ATTRIBUTE, Sdf.ValueTypeNames.Int
    ).Set(descriptor.tile_rows)
    root.CreateAttribute(
        WOOD_VISUAL_V3_ATLAS_CELL_STRIDE_ATTRIBUTE, Sdf.ValueTypeNames.Int
    ).Set(descriptor.cell_stride_px)
    surface = UsdShade.Shader.Define(stage, WOOD_VISUAL_V3_ROOT.AppendChild("Surface"))
    surface.CreateIdAttr("UsdPreviewSurface")
    reader = UsdShade.Shader.Define(
        stage, WOOD_VISUAL_V3_ROOT.AppendChild("PrimvarReader")
    )
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateInput("fallback", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(0.0))
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    base = _texture_shader(
        stage,
        WOOD_VISUAL_V3_ROOT.AppendChild("BaseTexture"),
        WOOD_VISUAL_V3_BASE_TEXTURE_URI,
    )
    emission = _texture_shader(
        stage,
        WOOD_VISUAL_V3_ROOT.AppendChild("EmissionTexture"),
        WOOD_VISUAL_V3_EMISSION_TEXTURE_URI,
    )
    for texture in (base, emission):
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            reader.ConnectableAPI(), "result"
        )
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        base.ConnectableAPI(), "rgb"
    )
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(
        base.ConnectableAPI(), "a"
    )
    surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        emission.ConnectableAPI(), "rgb"
    )
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    bindings = {}
    for expected_slot, log_id in enumerate(log_ids):
        render = get_log_render_surface(stage, log_id)
        if not render.IsA(UsdGeom.Mesh):
            raise ValueError(f"Wood visual V3 requires the render Mesh: {log_id}")
        root_prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        actual_slot = int(root_prim.GetAttribute("campfire:renderAtlasSlot").Get())
        if actual_slot != expected_slot:
            raise ValueError("Wood visual V3 requires contiguous stable render log slots")
        author_wood_render_mesh_uv(UsdGeom.Mesh(render), actual_slot, descriptor)
        UsdShade.MaterialBindingAPI.Apply(render).Bind(material)
        bindings[log_id] = str(render.GetPath())
    return {
        "root": str(WOOD_VISUAL_V3_ROOT),
        "log_ids": list(log_ids),
        "bindings": bindings,
        "atlas": [descriptor.width_px, descriptor.height_px],
        "atlas_descriptor": {
            "render_log_count": descriptor.render_log_count,
            "slot_capacity": descriptor.slot_capacity,
            "tile_columns": descriptor.tile_columns,
            "tile_rows": descriptor.tile_rows,
            "cell_stride_px": descriptor.cell_stride_px,
            "bytes_per_rgba8_atlas": descriptor.bytes_per_rgba8_atlas,
        },
        "base_uri": WOOD_VISUAL_V3_BASE_TEXTURE_URI,
        "emission_uri": WOOD_VISUAL_V3_EMISSION_TEXTURE_URI,
        "upload_count_per_revision": 2,
        "initial_revision": 0,
    }


def _mix(left, right, amount):
    return left + (right - left) * amount[..., None]


class WoodVisualV3AtlasPacker:
    """Vectorized beauty pack; never iterates over 7,200 cells in Python."""

    def __init__(self, log_ids, *, descriptor=None, log_slots=None):
        self.log_ids = tuple(str(value) for value in log_ids)
        if not self.log_ids or len(set(self.log_ids)) != len(self.log_ids):
            raise ValueError("Wood visual V3 atlas packer requires unique logs")
        if len(self.log_ids) > WOOD_RENDER_MAX_LOGS:
            raise ValueError("Wood visual V3 atlas supports at most 20 logs")
        self.descriptor = (
            compact_atlas_descriptor(len(self.log_ids))
            if descriptor is None
            else descriptor
        )
        if not isinstance(self.descriptor, WoodAtlasDescriptor):
            raise TypeError("Wood visual V3 requires a WoodAtlasDescriptor")
        self.log_slots = tuple(range(len(self.log_ids))) if log_slots is None else tuple(
            int(value) for value in log_slots
        )
        if len(self.log_slots) != len(self.log_ids) or len(set(self.log_slots)) != len(
            self.log_slots
        ):
            raise ValueError("Wood visual V3 requires one unique slot per modeled log")
        if any(
            slot < 0 or slot >= self.descriptor.render_log_count
            for slot in self.log_slots
        ):
            raise ValueError("Wood visual V3 modeled log slot is outside the descriptor")

    def _atlas_from_tiles(self, tiles):
        pixels = tiles
        if self.descriptor.cell_stride_px > 1:
            pixels = np.repeat(
                np.repeat(tiles, self.descriptor.cell_stride_px, axis=1),
                self.descriptor.cell_stride_px,
                axis=2,
            )
        return np.ascontiguousarray(
            pixels.reshape(
                self.descriptor.tile_rows,
                self.descriptor.tile_columns,
                WOOD_ATLAS_CELL_ROWS * self.descriptor.cell_stride_px,
                WOOD_ATLAS_CELL_COLUMNS * self.descriptor.cell_stride_px,
                4,
            )
            .transpose(0, 2, 1, 3, 4)
            .reshape(self.descriptor.height_px, self.descriptor.width_px, 4)
        )

    def neutral_atlases(self):
        base = np.empty(
            (self.descriptor.slot_capacity, WOOD_ATLAS_CELL_ROWS, WOOD_ATLAS_CELL_COLUMNS, 4),
            dtype=np.uint8,
        )
        base[..., :3] = np.rint(_DRY_COLOR * 255.0).astype(np.uint8)
        base[..., 3] = int(round(0.62 * 255.0))
        emission = np.zeros_like(base)
        emission[..., 3] = 255
        return self._atlas_from_tiles(base), self._atlas_from_tiles(emission)

    def pack(self, payload: ImmutableWoodVisualSurfacePayload) -> WoodVisualV3AtlasPack:
        if not isinstance(payload, ImmutableWoodVisualSurfacePayload):
            raise TypeError("Wood visual V3 requires an immutable V2 surface payload")
        if payload.log_ids != self.log_ids:
            raise ValueError("Wood visual V3 payload log order does not match")
        if payload.points_per_log != WOOD_SURFACE_CELLS_PER_LOG:
            raise ValueError("Wood visual V3 requires 360 surface states per log")
        started = time.perf_counter_ns()
        shape = (len(self.log_ids), WOOD_ATLAS_CELL_ROWS, WOOD_ATLAS_CELL_COLUMNS)
        temperature = np.frombuffer(payload.temperatures, dtype=np.float32).reshape(shape)
        moisture = np.frombuffer(payload.moistures, dtype=np.float32).reshape(shape)
        char = np.frombuffer(payload.chars, dtype=np.float32).reshape(shape)
        ash = np.frombuffer(payload.ashes, dtype=np.float32).reshape(shape)
        wet_amount = np.clip(moisture / _MOISTURE_DISPLAY_KG, 0.0, 1.0)
        char_amount = np.clip(char / _CHAR_DISPLAY_KG, 0.0, 1.0)
        ash_amount = np.clip(ash / _ASH_DISPLAY_KG, 0.0, 1.0)
        color = _mix(_DRY_COLOR, _WET_COLOR, wet_amount)
        color = _mix(color, _CHAR_COLOR, char_amount)
        color = _mix(color, _ASH_COLOR, ash_amount)
        roughness = 0.62 + (0.43 - 0.62) * wet_amount
        roughness += (0.86 - roughness) * char_amount
        roughness += (0.98 - roughness) * ash_amount

        emission = np.zeros((*shape, 3), dtype=np.float32)
        low = (temperature >= 650.0) & (temperature < 800.0)
        mid = (temperature >= 800.0) & (temperature < 1000.0)
        high = temperature >= 1000.0
        if np.any(low):
            emission[low] = _mix(
                np.array((0.06, 0.001, 0.0), np.float32),
                np.array((0.65, 0.035, 0.002), np.float32),
                (temperature[low] - 650.0) / 150.0,
            )
        if np.any(mid):
            emission[mid] = _mix(
                np.array((0.65, 0.035, 0.002), np.float32),
                np.array((1.0, 0.36, 0.018), np.float32),
                (temperature[mid] - 800.0) / 200.0,
            )
        if np.any(high):
            emission[high] = _mix(
                np.array((1.0, 0.36, 0.018), np.float32),
                np.array((1.0, 0.85, 0.55), np.float32),
                np.clip((temperature[high] - 1000.0) / 300.0, 0.0, 1.0),
            )
        emission *= (1.0 - 0.85 * ash_amount)[..., None]

        base_tiles = np.empty(
            (self.descriptor.slot_capacity, WOOD_ATLAS_CELL_ROWS, WOOD_ATLAS_CELL_COLUMNS, 4),
            dtype=np.uint8,
        )
        base_tiles[..., :3] = np.rint(_DRY_COLOR * 255.0).astype(np.uint8)
        base_tiles[..., 3] = int(round(0.62 * 255.0))
        emission_tiles = np.zeros_like(base_tiles)
        emission_tiles[..., 3] = 255
        slots = np.asarray(self.log_slots, dtype=np.intp)
        base_tiles[slots, ..., :3] = np.rint(np.clip(color, 0.0, 1.0) * 255.0).astype(np.uint8)
        base_tiles[slots, ..., 3] = np.rint(np.clip(roughness, 0.0, 1.0) * 255.0).astype(np.uint8)
        emission_tiles[slots, ..., :3] = np.rint(
            np.clip(emission, 0.0, 1.0) * 255.0
        ).astype(np.uint8)
        base_atlas = self._atlas_from_tiles(base_tiles)
        emission_atlas = self._atlas_from_tiles(emission_tiles)
        return WoodVisualV3AtlasPack(
            payload.revision,
            base_atlas,
            emission_atlas,
            (time.perf_counter_ns() - started) / 1_000_000.0,
        )


class WoodVisualV3NativeAtlasPacker:
    """Pack final RGBA8 texels into two session-owned reusable arrays."""

    def __init__(self, library, log_ids, *, descriptor=None, log_slots=None):
        if library is None:
            raise ValueError("Native wood visual packer requires a loaded library")
        reference = WoodVisualV3AtlasPacker(
            log_ids, descriptor=descriptor, log_slots=log_slots
        )
        self.library = library
        self.log_ids = reference.log_ids
        self.descriptor = reference.descriptor
        self.log_slots = reference.log_slots
        self._render_slots = np.asarray(self.log_slots, dtype=np.uint32)
        shape = (self.descriptor.height_px, self.descriptor.width_px, 4)
        self._base_rgba8 = np.empty(shape, dtype=np.uint8)
        self._emission_rgba8 = np.empty(shape, dtype=np.uint8)
        self.allocation_count = 3
        self.pack_count = 0
        self._neutral = reference.neutral_atlases()
        self._configure()

    def _configure(self):
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        bp = ctypes.POINTER(ctypes.c_uint8)
        self.library.campfire_native_wood_visual_rgba8_pack.argtypes = (
            [fp] * 4
            + [ctypes.c_size_t] * 2
            + [up]
            + [ctypes.c_size_t] * 3
            + [bp, ctypes.c_size_t, bp, ctypes.c_size_t]
        )
        self.library.campfire_native_wood_visual_rgba8_pack.restype = ctypes.c_int32

    def neutral_atlases(self):
        return tuple(value.copy() for value in self._neutral)

    def pack(self, payload: ImmutableWoodVisualSurfacePayload) -> WoodVisualV3AtlasPack:
        if not isinstance(payload, ImmutableWoodVisualSurfacePayload):
            raise TypeError("Wood visual V3 requires an immutable V2 surface payload")
        if payload.log_ids != self.log_ids:
            raise ValueError("Wood visual V3 payload log order does not match")
        if payload.points_per_log != WOOD_SURFACE_CELLS_PER_LOG:
            raise ValueError("Wood visual V3 requires 360 surface states per log")
        started = time.perf_counter_ns()
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        bp = ctypes.POINTER(ctypes.c_uint8)
        channels = tuple(
            np.frombuffer(value, dtype=np.float32)
            for value in (
                payload.temperatures,
                payload.moistures,
                payload.chars,
                payload.ashes,
            )
        )
        result = self.library.campfire_native_wood_visual_rgba8_pack(
            *(value.ctypes.data_as(fp) for value in channels),
            len(self.log_ids),
            payload.points_per_log,
            self._render_slots.ctypes.data_as(up),
            self.descriptor.slot_capacity,
            self.descriptor.tile_columns,
            self.descriptor.tile_rows,
            self._base_rgba8.ctypes.data_as(bp),
            self._base_rgba8.nbytes,
            self._emission_rgba8.ctypes.data_as(bp),
            self._emission_rgba8.nbytes,
        )
        if result != 0:
            raise RuntimeError(f"Native wood visual beauty pack failed with code {result}")
        self.pack_count += 1
        return WoodVisualV3AtlasPack(
            payload.revision,
            self._base_rgba8,
            self._emission_rgba8,
            (time.perf_counter_ns() - started) / 1_000_000.0,
        )


def _pointer_capsule(array):
    capsule_new = ctypes.pythonapi.PyCapsule_New
    capsule_new.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p)
    capsule_new.restype = ctypes.py_object
    return capsule_new(ctypes.c_void_p(array.ctypes.data), None, None)


class WoodVisualV3Consumer:
    """Production CPU-source observer with visual-only recovery."""

    def __init__(
        self,
        stage,
        log_ids,
        *,
        track_notices=False,
        provider_factory=None,
        texture_format=None,
        failure_injector=None,
        native_library=None,
    ):
        self._owner = threading.get_ident()
        self._stage = stage
        self._log_ids = tuple(str(value) for value in log_ids)
        self._packer = None
        self._provider_factory = provider_factory
        self._texture_format = texture_format
        self._failure_injector = failure_injector
        self._active = False
        self._closed = False
        self._revision = 0
        self._processed_revision = 0
        self._publish_count = 0
        self._skip_count = 0
        self._quantized_skip_count = 0
        self._visual_commit_count = 0
        self._base_skip_count = 0
        self._emission_skip_count = 0
        self._failure_count = 0
        self._recovery_count = 0
        self._upload_count = 0
        self._usd_set_count = 0
        self._notice_count = 0
        self._notice_active = False
        self._profiles = []
        self._last_payload = None
        self._base_provider = None
        self._emission_provider = None
        self._revision_attr = None
        self._listener = None
        self._bind_stage(stage, track_notices)
        packer_type = (
            WoodVisualV3AtlasPacker
            if native_library is None
            else WoodVisualV3NativeAtlasPacker
        )
        packer_args = () if native_library is None else (native_library,)
        self._packer = packer_type(
            *packer_args,
            self._log_ids,
            descriptor=self._atlas_descriptor,
            log_slots=self._log_slots,
        )
        self._packer_kind = "numpy" if native_library is None else "native"
        self._create_providers()
        self._last_base, self._last_emission = self._packer.neutral_atlases()
        self._upload_pair(self._last_base, self._last_emission)

    def _require_owner(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError("Wood visual V3 consumer must run on its owner thread")

    def _bind_stage(self, stage, track_notices):
        if stage is None:
            raise ValueError("Wood visual V3 requires a stage")
        root = stage.GetPrimAtPath(WOOD_VISUAL_V3_ROOT)
        if not root:
            raise ValueError("Wood visual V3 material must be pre-authored")
        revision = root.GetAttribute(WOOD_VISUAL_V3_REVISION_ATTRIBUTE)
        if not revision:
            raise ValueError("Wood visual V3 revision marker is unavailable")
        render_log_ids = tuple(
            str(value)
            for value in root.GetAttribute(WOOD_VISUAL_V3_RENDER_LOG_IDS_ATTRIBUTE).Get()
        )
        descriptor = WoodAtlasDescriptor(
            int(root.GetAttribute(WOOD_VISUAL_V3_ATLAS_LOG_COUNT_ATTRIBUTE).Get()),
            int(root.GetAttribute(WOOD_VISUAL_V3_ATLAS_TILE_COLUMNS_ATTRIBUTE).Get()),
            int(root.GetAttribute(WOOD_VISUAL_V3_ATLAS_TILE_ROWS_ATTRIBUTE).Get()),
            int(root.GetAttribute(WOOD_VISUAL_V3_ATLAS_CELL_STRIDE_ATTRIBUTE).Get()),
        )
        if len(render_log_ids) != descriptor.render_log_count:
            raise ValueError("Wood visual V3 render log descriptor is malformed")
        try:
            log_slots = tuple(render_log_ids.index(log_id) for log_id in self._log_ids)
        except ValueError as exc:
            raise ValueError("Wood visual V3 modeled log is not renderable") from exc
        previous_descriptor = getattr(self, "_atlas_descriptor", None)
        previous_render_logs = getattr(self, "_render_log_ids", None)
        if previous_descriptor is not None and (
            descriptor != previous_descriptor or render_log_ids != previous_render_logs
        ):
            raise ValueError("Wood visual V3 atlas descriptor changed across reload")
        base_uri = (
            stage.GetPrimAtPath(WOOD_VISUAL_V3_ROOT.AppendChild("BaseTexture"))
            .GetAttribute("inputs:file")
            .Get()
            .path
        )
        emission_uri = (
            stage.GetPrimAtPath(WOOD_VISUAL_V3_ROOT.AppendChild("EmissionTexture"))
            .GetAttribute("inputs:file")
            .Get()
            .path
        )
        if (
            base_uri != WOOD_VISUAL_V3_BASE_TEXTURE_URI
            or emission_uri != WOOD_VISUAL_V3_EMISSION_TEXTURE_URI
        ):
            raise ValueError("Wood visual V3 dynamic texture URI changed")
        self._stage = stage
        self._revision_attr = revision
        self._atlas_descriptor = descriptor
        self._render_log_ids = render_log_ids
        self._log_slots = log_slots
        if self._listener is not None:
            self._listener.Revoke()
        self._listener = (
            Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._observe_notice, stage)
            if track_notices
            else None
        )

    def _create_providers(self):
        if self._provider_factory is None:
            import omni.ui as ui
            from omni.gpu_foundation_factory import TextureFormat

            self._provider_factory = ui.DynamicTextureProvider
            self._texture_format = TextureFormat.RGBA8_UNORM
        self._base_provider = self._provider_factory(WOOD_VISUAL_V3_BASE_TEXTURE_NAME)
        self._emission_provider = self._provider_factory(
            WOOD_VISUAL_V3_EMISSION_TEXTURE_NAME
        )

    def _destroy_providers(self):
        for name in ("_emission_provider", "_base_provider"):
            provider = getattr(self, name)
            if provider is not None:
                provider.destroy()
                setattr(self, name, None)

    def _upload(self, provider, atlas):
        provider.set_raw_bytes_data(
            _pointer_capsule(atlas),
            [self._atlas_descriptor.width_px, self._atlas_descriptor.height_px],
            self._texture_format,
            strict=True,
        )

    def _upload_pair(self, base, emission):
        self._upload(self._base_provider, base)
        self._upload(self._emission_provider, emission)

    def _inject(self, point, revision):
        if self._failure_injector is not None:
            self._failure_injector(point, revision)

    def _observe_notice(self, _notice, _sender):
        if self._notice_active:
            self._notice_count += 1

    def on_timeline_started(self):
        self._require_owner()
        if self._closed:
            raise RuntimeError("Wood visual V3 consumer is closed")
        self._active = True

    def on_timeline_stopped(self):
        self._require_owner()
        self._active = False

    def publish(self, payload: ImmutableWoodVisualSurfacePayload):
        return self._publish(payload, force=False, status="committed")

    def publish_for_capture(self, payload: ImmutableWoodVisualSurfacePayload):
        """Force both atlases immediately before a requested camera capture."""

        return self._publish(payload, force=True, status="capture_republish")

    def _publish(self, payload, *, force, status):
        self._require_owner()
        if self._closed or not self._active:
            raise RuntimeError("Wood visual V3 requires an active timeline")
        if payload.log_ids != self._log_ids:
            raise ValueError("Wood visual V3 payload log order does not match")
        if not force and payload.revision == self._processed_revision:
            self._skip_count += 1
            profile = WoodVisualV3PublicationProfile(
                payload.revision, "unchanged_revision", 0.0, 0.0, 0.0, 0.0,
                0.0, 0, 0, 0, 0, False, False
            )
            self._profiles.append(profile)
            return profile
        if payload.revision < self._processed_revision:
            raise RuntimeError("Wood visual V3 revision must increase monotonically")

        started = time.perf_counter_ns()
        packed = self._packer.pack(payload)
        packed_at = time.perf_counter_ns()
        base_changed = force or not np.array_equal(packed.base_rgba8, self._last_base)
        emission_changed = force or not np.array_equal(
            packed.emission_rgba8, self._last_emission
        )
        boundary_at = time.perf_counter_ns()
        if not base_changed and not emission_changed:
            finished = time.perf_counter_ns()
            self._processed_revision = payload.revision
            self._last_payload = payload
            self._publish_count += 1
            self._skip_count += 1
            self._quantized_skip_count += 1
            self._base_skip_count += 1
            self._emission_skip_count += 1
            profile = WoodVisualV3PublicationProfile(
                payload.revision,
                "unchanged_quantized",
                (finished - started) / 1_000_000.0,
                packed.pack_ms,
                (boundary_at - packed_at) / 1_000_000.0,
                0.0,
                0.0,
                0,
                0,
                0,
                0,
                False,
                False,
            )
            self._profiles.append(profile)
            return profile
        base_capsule = _pointer_capsule(packed.base_rgba8) if base_changed else None
        emission_capsule = (
            _pointer_capsule(packed.emission_rgba8) if emission_changed else None
        )
        notice_before = self._notice_count
        uploads = 0
        sets = 0
        base_uploaded = False
        emission_uploaded = False
        self._notice_active = True
        try:
            if base_changed:
                self._inject("before_base", payload.revision)
                self._base_provider.set_raw_bytes_data(
                    base_capsule,
                    [self._atlas_descriptor.width_px, self._atlas_descriptor.height_px],
                    self._texture_format,
                    strict=True,
                )
                uploads += 1
                base_uploaded = True
                self._inject("after_base", payload.revision)
            if emission_changed:
                self._emission_provider.set_raw_bytes_data(
                    emission_capsule,
                    [self._atlas_descriptor.width_px, self._atlas_descriptor.height_px],
                    self._texture_format,
                    strict=True,
                )
                uploads += 1
                emission_uploaded = True
            uploaded_at = time.perf_counter_ns()
            self._inject("after_emission", payload.revision)
            if not self._revision_attr.Set(payload.revision):
                raise RuntimeError("Wood visual V3 revision Set failed")
            sets = 1
            self._inject("after_revision", payload.revision)
        except Exception:
            self._failure_count += 1
            try:
                if base_uploaded:
                    self._upload(self._base_provider, self._last_base)
                if emission_uploaded:
                    self._upload(self._emission_provider, self._last_emission)
                self._revision_attr.Set(self._revision)
                self._recovery_count += 1
            finally:
                self._notice_active = False
            raise
        finally:
            self._notice_active = False
        finished = time.perf_counter_ns()
        if base_changed:
            np.copyto(self._last_base, packed.base_rgba8)
        else:
            self._base_skip_count += 1
        if emission_changed:
            np.copyto(self._last_emission, packed.emission_rgba8)
        else:
            self._emission_skip_count += 1
        self._last_payload = payload
        self._revision = payload.revision
        self._processed_revision = payload.revision
        self._publish_count += 1
        self._visual_commit_count += 1
        self._upload_count += uploads
        self._usd_set_count += sets
        notice_count = self._notice_count - notice_before
        profile = WoodVisualV3PublicationProfile(
            payload.revision,
            status,
            (finished - started) / 1_000_000.0,
            packed.pack_ms,
            (boundary_at - packed_at) / 1_000_000.0,
            (uploaded_at - boundary_at) / 1_000_000.0,
            (finished - uploaded_at) / 1_000_000.0,
            uploads,
            sets,
            notice_count,
            uploads * self._atlas_descriptor.bytes_per_rgba8_atlas,
            base_changed,
            emission_changed,
        )
        self._profiles.append(profile)
        return profile

    def on_stage_reloaded(self, stage, latest_payload):
        self._require_owner()
        if self._closed:
            raise RuntimeError("Wood visual V3 consumer is closed")
        was_active = self._active
        self._active = False
        self._destroy_providers()
        self._bind_stage(stage, self._listener is not None)
        self._create_providers()
        self._revision = int(self._revision_attr.Get() or 0)
        self._processed_revision = self._revision
        self._active = True
        try:
            return self._publish(latest_payload, force=True, status="reloaded")
        finally:
            self._active = was_active

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
            "processed_revision": self._processed_revision,
            "publish_count": self._publish_count,
            "skip_count": self._skip_count,
            "quantized_skip_count": self._quantized_skip_count,
            "visual_commit_count": self._visual_commit_count,
            "base_skip_count": self._base_skip_count,
            "emission_skip_count": self._emission_skip_count,
            "failure_count": self._failure_count,
            "recovery_count": self._recovery_count,
            "upload_count": self._upload_count,
            "usd_set_count": self._usd_set_count,
            "notice_count": self._notice_count,
            "log_ids": list(self._log_ids),
            "render_log_ids": list(self._render_log_ids),
            "atlas": [
                self._atlas_descriptor.width_px,
                self._atlas_descriptor.height_px,
            ],
            "atlas_cell_stride_px": self._atlas_descriptor.cell_stride_px,
            "bytes_per_revision": 2
            * self._atlas_descriptor.bytes_per_rgba8_atlas,
            "packer": self._packer_kind,
            "packer_allocation_count": getattr(self._packer, "allocation_count", None),
            "last_payload_revision": (
                self._last_payload.revision if self._last_payload is not None else None
            ),
        }

    def close(self):
        self._require_owner()
        if self._closed:
            return False
        self._active = False
        if self._listener is not None:
            self._listener.Revoke()
            self._listener = None
        self._destroy_providers()
        self._closed = True
        return True
