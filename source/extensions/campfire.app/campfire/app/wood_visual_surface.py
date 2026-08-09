"""Immutable visual-only surface payload packed from Resident native SoA."""

from __future__ import annotations

import ctypes
import hashlib
import time
from dataclasses import dataclass

import numpy as np


WOOD_VISUAL_SURFACE_CHANNELS = ("temperature", "moisture", "char", "ash")


@dataclass(frozen=True)
class ImmutableWoodVisualSurfacePayload:
    revision: int
    tick: int
    log_ids: tuple[str, ...]
    points_per_log: int
    local_surface_indices: bytes
    temperatures: bytes
    moistures: bytes
    chars: bytes
    ashes: bytes

    def __post_init__(self):
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (self.revision, self.tick, self.points_per_log)
        ):
            raise ValueError("Wood visual surface metadata must use integers")
        if self.revision <= 0 or self.tick < 0 or self.points_per_log <= 0:
            raise ValueError("Wood visual surface metadata is invalid")
        if not self.log_ids or len(set(self.log_ids)) != len(self.log_ids):
            raise ValueError("Wood visual surface log ids must be non-empty and unique")
        if any(type(value) is not str or not value for value in self.log_ids):
            raise ValueError("Wood visual surface log ids must be strings")
        arrays = (
            self.local_surface_indices,
            self.temperatures,
            self.moistures,
            self.chars,
            self.ashes,
        )
        if any(type(value) is not bytes for value in arrays):
            raise TypeError("Wood visual surface arrays must be immutable bytes")
        point_count = self.point_count
        if any(len(value) != point_count * 4 for value in arrays):
            raise ValueError("Wood visual surface byte counts are invalid")
        indices = np.frombuffer(self.local_surface_indices, dtype=np.uint32).reshape(
            len(self.log_ids), self.points_per_log
        )
        expected = np.arange(self.points_per_log, dtype=np.uint32)
        if not np.all(indices == expected):
            raise ValueError("Wood visual surface identity order is invalid")
        for name, values in zip(
            WOOD_VISUAL_SURFACE_CHANNELS,
            (self.temperatures, self.moistures, self.chars, self.ashes),
        ):
            view = np.frombuffer(values, dtype=np.float32)
            if not np.isfinite(view).all():
                raise ValueError(f"Wood visual {name} values must be finite")
            if name == "temperature":
                if not np.all(view > 0.0):
                    raise ValueError("Wood visual temperatures must be positive")
            elif not np.all(view >= 0.0):
                raise ValueError(f"Wood visual {name} values must be non-negative")

    @property
    def point_count(self):
        return len(self.log_ids) * self.points_per_log

    def digest(self):
        digest = hashlib.sha256()
        digest.update(str((self.revision, self.tick, self.log_ids, self.points_per_log)).encode("utf-8"))
        for value in (
            self.local_surface_indices,
            self.temperatures,
            self.moistures,
            self.chars,
            self.ashes,
        ):
            digest.update(value)
        return digest.hexdigest()


@dataclass(frozen=True)
class WoodVisualSurfacePackProfile:
    revision: int
    point_count: int
    native_pack_ms: float
    boundary_copy_ms: float
    validation_ms: float
    digest_ms: float
    total_ms: float
    digest: str


class ResidentNativeWoodVisualSurfaceProducer:
    """Bulk-pack visual state without changing Point or session consumers."""

    def __init__(self, backend):
        if backend is None:
            raise ValueError("Wood visual surface producer requires a backend")
        self.backend = backend
        self.np = backend._np
        self.library = backend._library
        self.log_ids = tuple(model.spec.log_id for model in backend.models)
        self.log_count = len(self.log_ids)
        self.cells_per_log = len(backend.models[0].cells)
        surface = backend._arrays["surface_exposure"].reshape(
            self.log_count, self.cells_per_log
        )
        counts = self.np.count_nonzero(surface > 0.0, axis=1)
        if not self.np.all(counts == counts[0]) or int(counts[0]) <= 0:
            raise ValueError("Wood visual logs must have one fixed surface count")
        self.points_per_log = int(counts[0])
        self.point_count = self.log_count * self.points_per_log
        self.local_surface_indices = self.np.empty(self.point_count, dtype=self.np.uint32)
        self.temperatures = self.np.empty(self.point_count, dtype=self.np.float32)
        self.moistures = self.np.empty(self.point_count, dtype=self.np.float32)
        self.chars = self.np.empty(self.point_count, dtype=self.np.float32)
        self.ashes = self.np.empty(self.point_count, dtype=self.np.float32)
        self._configure()

    def _configure(self):
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        sizep = ctypes.POINTER(ctypes.c_size_t)
        self.library.campfire_native_visual_surface_pack.argtypes = (
            [dp] * 5
            + [ctypes.c_size_t] * 2
            + [fp] * 4
            + [up, ctypes.c_size_t, sizep]
        )
        self.library.campfire_native_visual_surface_pack.restype = ctypes.c_int32

    def pack(self, revision, tick):
        started = time.perf_counter_ns()
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        count = ctypes.c_size_t()
        arrays = self.backend._arrays
        result = self.library.campfire_native_visual_surface_pack(
            arrays["temperature_k"].ctypes.data_as(dp),
            arrays["moisture_mass_kg"].ctypes.data_as(dp),
            arrays["char_mass_kg"].ctypes.data_as(dp),
            arrays["ash_mass_kg"].ctypes.data_as(dp),
            arrays["surface_exposure"].ctypes.data_as(dp),
            self.log_count,
            self.cells_per_log,
            self.temperatures.ctypes.data_as(fp),
            self.moistures.ctypes.data_as(fp),
            self.chars.ctypes.data_as(fp),
            self.ashes.ctypes.data_as(fp),
            self.local_surface_indices.ctypes.data_as(up),
            self.point_count,
            ctypes.byref(count),
        )
        packed_at = time.perf_counter_ns()
        if result != 0 or count.value != self.point_count:
            raise RuntimeError(
                f"Native wood visual pack failed: code={result}, points={count.value}"
            )
        copied = tuple(
            value.tobytes(order="C")
            for value in (
                self.local_surface_indices,
                self.temperatures,
                self.moistures,
                self.chars,
                self.ashes,
            )
        )
        copied_at = time.perf_counter_ns()
        payload = ImmutableWoodVisualSurfacePayload(
            revision,
            tick,
            self.log_ids,
            self.points_per_log,
            *copied,
        )
        validated_at = time.perf_counter_ns()
        digest = payload.digest()
        finished = time.perf_counter_ns()
        profile = WoodVisualSurfacePackProfile(
            revision,
            self.point_count,
            (packed_at - started) / 1_000_000.0,
            (copied_at - packed_at) / 1_000_000.0,
            (validated_at - copied_at) / 1_000_000.0,
            (finished - validated_at) / 1_000_000.0,
            (finished - started) / 1_000_000.0,
            digest,
        )
        return payload, profile
