"""Production-shaped, default-off Resident Point publication boundary."""

from __future__ import annotations

import ctypes
import hashlib
import math
import sys
import time
from dataclasses import dataclass

from pxr import Sdf, Vt

from .resident_snapshot import RESIDENT_PUBLISHED_FIELD_NAMES
from .performance import summarize_timing_ms


FLOW_FUEL_FIELD = RESIDENT_PUBLISHED_FIELD_NAMES.index("flow_fuel")
FLOW_SMOKE_FIELD = RESIDENT_PUBLISHED_FIELD_NAMES.index("flow_smoke")


@dataclass(frozen=True)
class ImmutableSurfacePayload:
    revision: int
    tick: int
    layout_revision: int
    point_count: int
    positions: bytes
    fuels: bytes
    temperatures: bytes
    smokes: bytes
    layout_origins: tuple = ()
    layout_axes: tuple = ()

    def __post_init__(self):
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (
                self.revision,
                self.tick,
                self.layout_revision,
                self.point_count,
            )
        ):
            raise ValueError("Surface payload metadata must use integers")
        if self.revision <= 0 or self.tick < 0 or self.layout_revision <= 0:
            raise ValueError("Surface payload revisions and tick are invalid")
        if self.point_count <= 0:
            raise ValueError("Surface payload must contain points")
        if any(
            type(value) is not bytes
            for value in (self.positions, self.fuels, self.temperatures, self.smokes)
        ):
            raise TypeError("Surface payload arrays must be immutable bytes")
        if len(self.positions) != self.point_count * 12:
            raise ValueError("Surface position byte count is invalid")
        if any(
            len(value) != self.point_count * 4
            for value in (self.fuels, self.temperatures, self.smokes)
        ):
            raise ValueError("Surface channel byte count is invalid")
        if (
            type(self.layout_origins) is not tuple
            or type(self.layout_axes) is not tuple
        ):
            raise TypeError("Surface payload layout metadata must be immutable tuples")
        if any(type(origin) is not tuple for origin in self.layout_origins):
            raise TypeError("Surface payload layout origins must be immutable tuples")
        if bool(self.layout_origins) != bool(self.layout_axes):
            raise ValueError("Surface payload layout metadata must be paired")
        if self.layout_origins:
            if len(self.layout_origins) != len(self.layout_axes):
                raise ValueError("Surface payload layout metadata count is invalid")
            if any(
                len(origin) != 3
                or not all(math.isfinite(float(component)) for component in origin)
                for origin in self.layout_origins
            ):
                raise ValueError("Surface payload layout origins are invalid")
            if any(
                isinstance(axis, bool)
                or not isinstance(axis, int)
                or axis not in (0, 1)
                for axis in self.layout_axes
            ):
                raise ValueError("Surface payload layout axes are invalid")

    def digest(self):
        digest = hashlib.sha256()
        digest.update(str((self.revision, self.tick, self.layout_revision)).encode("ascii"))
        digest.update(repr((self.layout_origins, self.layout_axes)).encode("ascii"))
        for value in (self.positions, self.fuels, self.temperatures, self.smokes):
            digest.update(value)
        return digest.hexdigest()


class ResidentNativeSurfaceProducer:
    """Build fixed-layout Point arrays directly from one Resident native SoA."""

    def __init__(self, backend, origins, axes):
        if backend is None:
            raise ValueError("Resident surface producer requires a backend")
        self.backend = backend
        self.np = backend._np
        self.library = backend._library
        self.log_count = len(backend.models)
        self.cells_per_log = len(backend.models[0].cells)
        self.published_field_count = len(RESIDENT_PUBLISHED_FIELD_NAMES)
        self._validate_geometry()
        self.origins = self.np.asarray(origins, dtype=self.np.float64).copy(order="C")
        self.axes = self.np.asarray(axes, dtype=self.np.uint32).copy(order="C")
        if self.origins.shape != (self.log_count, 3):
            raise ValueError("Resident Point origins must have shape (log_count, 3)")
        if self.axes.shape != (self.log_count,):
            raise ValueError("Resident Point axes must have shape (log_count,)")
        if not self.np.isfinite(self.origins).all():
            raise ValueError("Resident Point origins must be finite")
        if not self.np.isin(self.axes, (0, 1)).all():
            raise ValueError("Resident Point axes must contain only 0 or 1")
        surface = backend._arrays["surface_exposure"]
        self.point_count = int(self.np.count_nonzero(surface > 0.0))
        if self.point_count <= 0:
            raise ValueError("Resident Point producer requires exposed surface cells")
        self.positions = self.np.empty((self.point_count, 3), dtype=self.np.float32)
        self.fuels = self.np.empty(self.point_count, dtype=self.np.float32)
        self.temperatures = self.np.empty(self.point_count, dtype=self.np.float32)
        self.smokes = self.np.empty(self.point_count, dtype=self.np.float32)
        self._configure()
        self.pointer_identity = self._pointers()

    def _validate_geometry(self):
        reference = self.backend.models[0].spec
        for model in self.backend.models:
            spec = model.spec
            if len(model.cells) != self.cells_per_log:
                raise ValueError("Resident Point logs must have equal cell counts")
            if (
                spec.axial_cells,
                spec.circumferential_cells,
                spec.radial_cells,
                spec.radius_m,
                spec.length_m,
            ) != (
                reference.axial_cells,
                reference.circumferential_cells,
                reference.radial_cells,
                reference.radius_m,
                reference.length_m,
            ):
                raise ValueError("Resident Point logs must share one cell geometry")

    def _configure(self):
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        sizep = ctypes.POINTER(ctypes.c_size_t)
        self.library.campfire_native_surface_layout.argtypes = (
            [dp]
            + [ctypes.c_size_t] * 5
            + [ctypes.c_double] * 2
            + [dp, up, fp, ctypes.c_size_t, sizep]
        )
        self.library.campfire_native_surface_layout.restype = ctypes.c_int32
        self.library.campfire_native_surface_channels.argtypes = (
            [dp, dp, dp]
            + [ctypes.c_size_t] * 5
            + [ctypes.c_double]
            + [fp, fp, fp, ctypes.c_size_t, sizep]
        )
        self.library.campfire_native_surface_channels.restype = ctypes.c_int32

    def _pointers(self):
        return {
            "positions": int(self.positions.ctypes.data),
            "fuels": int(self.fuels.ctypes.data),
            "temperatures": int(self.temperatures.ctypes.data),
            "smokes": int(self.smokes.ctypes.data),
        }

    def _validated_layout(self, origins, axes):
        origins = self.np.asarray(origins, dtype=self.np.float64)
        axes = self.np.asarray(axes, dtype=self.np.uint32)
        if origins.shape != (self.log_count, 3):
            raise ValueError("Resident Point origins must have shape (log_count, 3)")
        if axes.shape != (self.log_count,):
            raise ValueError("Resident Point axes must have shape (log_count,)")
        if not self.np.isfinite(origins).all():
            raise ValueError("Resident Point origins must be finite")
        if not self.np.isin(axes, (0, 1)).all():
            raise ValueError("Resident Point axes must contain only 0 or 1")
        return origins, axes

    def _build_layout_into(self, origins, axes, positions):
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        count = ctypes.c_size_t()
        spec = self.backend.models[0].spec
        result = self.library.campfire_native_surface_layout(
            self.backend._arrays["surface_exposure"].ctypes.data_as(dp),
            self.log_count,
            self.cells_per_log,
            spec.axial_cells,
            spec.circumferential_cells,
            spec.radial_cells,
            spec.radius_m,
            spec.length_m,
            origins.ctypes.data_as(dp),
            axes.ctypes.data_as(up),
            positions.ctypes.data_as(fp),
            self.point_count,
            ctypes.byref(count),
        )
        if result != 0 or count.value != self.point_count:
            raise RuntimeError(
                f"Native surface layout failed: code={result}, points={count.value}"
            )
        return count.value

    def build_layout(self):
        return self._build_layout_into(self.origins, self.axes, self.positions)

    def build_layout_candidate(self, origins, axes):
        """Build an immutable candidate without mutating the committed arrays."""

        origins, axes = self._validated_layout(origins, axes)
        candidate = self.np.empty_like(self.positions)
        self._build_layout_into(origins, axes, candidate)
        return {
            "origins": tuple(
                tuple(float(component) for component in origin) for origin in origins
            ),
            "axes": tuple(int(axis) for axis in axes),
            "positions": candidate.tobytes(order="C"),
        }

    def layout_origins_changed(self, origins, tolerance=1.0e-9):
        """Check translations without allocating or running the native layout kernel."""

        origins, _ = self._validated_layout(origins, self.axes)
        return bool(self.np.any(self.np.abs(origins - self.origins) > tolerance))

    def commit_layout_candidate(self, origins, axes, positions):
        """Commit a previously built candidate without rerunning the native kernel."""

        origins, axes = self._validated_layout(origins, axes)
        converted = self.np.frombuffer(positions, dtype=self.np.float32)
        if converted.size != self.positions.size:
            raise ValueError("Resident Point candidate position count is invalid")
        self.origins[:] = origins
        self.axes[:] = axes
        self.positions[:] = converted.reshape(self.positions.shape)

    def build_channels(self):
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        count = ctypes.c_size_t()
        ambient_values = {
            float(model.parameters.ambient_temperature_k)
            for model in self.backend.models
        }
        if len(ambient_values) != 1 or not all(
            math.isfinite(value) and value > 0.0 for value in ambient_values
        ):
            raise ValueError("Resident Point logs must share one finite ambient temperature")
        result = self.library.campfire_native_surface_channels(
            self.backend._arrays["temperature_k"].ctypes.data_as(dp),
            self.backend._arrays["surface_exposure"].ctypes.data_as(dp),
            self.backend._published_output.ctypes.data_as(dp),
            self.log_count,
            self.cells_per_log,
            self.published_field_count,
            FLOW_FUEL_FIELD,
            FLOW_SMOKE_FIELD,
            ambient_values.pop(),
            self.fuels.ctypes.data_as(fp),
            self.temperatures.ctypes.data_as(fp),
            self.smokes.ctypes.data_as(fp),
            self.point_count,
            ctypes.byref(count),
        )
        if result != 0 or count.value != self.point_count:
            raise RuntimeError(
                f"Native surface channels failed: code={result}, points={count.value}"
            )
        if self._pointers() != self.pointer_identity:
            raise RuntimeError("Resident Point producer reallocated a persistent array")
        return count.value


class ResidentPointSidecar:
    """Publish one immutable native surface payload beside a primary snapshot."""

    def __init__(
        self,
        backend,
        stage,
        emitter_path,
        stage_provider,
        origins=None,
        axes=None,
        write_observer=None,
        *,
        initial_revision=0,
        initial_layout=None,
        producer=None,
        translation_provider=None,
        layout_state=None,
        skip_unchanged_translation_layout=False,
    ):
        if stage is None or not callable(stage_provider):
            raise ValueError("Resident Point sidecar requires stage collaborators")
        if initial_layout is not None:
            layout_revision = initial_layout["revision"]
            if isinstance(layout_revision, bool) or not isinstance(layout_revision, int):
                raise ValueError("Resident Point layout revision must be an integer")
            origins = initial_layout["origins"]
            axes = initial_layout["axes"]
        else:
            layout_revision = 1
        self._producer = producer or ResidentNativeSurfaceProducer(
            backend, origins, axes
        )
        self._backend = backend
        self._stage = stage
        self._stage_provider = stage_provider
        self._emitter_path = emitter_path
        self._write_observer = write_observer
        if translation_provider is not None and not callable(translation_provider):
            raise ValueError("Resident Point translation provider must be callable")
        self._translation_provider = translation_provider
        self._skip_unchanged_translation_layout = bool(
            skip_unchanged_translation_layout
        )
        self._layout_state = layout_state
        self._producer.build_layout()
        self._layout_revision = layout_revision
        if self._layout_revision <= 0:
            raise ValueError("Resident Point layout revision must be positive")
        self._positions = self._producer.positions.tobytes(order="C")
        if isinstance(initial_revision, bool) or not isinstance(initial_revision, int):
            raise ValueError("Initial Point revision must be a non-negative integer")
        self._revision = initial_revision
        if self._revision < 0:
            raise ValueError("Initial Point revision must be non-negative")
        self._committed_layout_revision = self._layout_revision if self._revision else 0
        self._last_snapshot = None
        self._last_undo = None
        self._prepare_count = 0
        self._publish_count = 0
        self._rollback_count = 0
        self._failure_count = 0
        self._layout_replace_count = 0
        self._live_translation_prepare_count = 0
        self._live_translation_publish_count = 0
        self._live_translation_unchanged_count = 0
        self._live_translation_timing_ms = {
            "provider": [],
            "candidate_build": [],
            "fuel_vt_conversion": [],
            "temperature_vt_conversion": [],
            "smoke_vt_conversion": [],
            "position_vt_conversion": [],
            "previous_value_snapshot": [],
            "change_block_enter": [],
            "position_usd_set": [],
            "fuel_usd_set": [],
            "temperature_usd_set": [],
            "smoke_usd_set": [],
            "layout_revision_usd_set": [],
            "resident_revision_usd_set": [],
            "change_block_exit": [],
            "publish_transaction": [],
            "producer_commit": [],
        }
        self._closed = False
        self.attempt_payload_ids = []
        self.attempt_payload_digests = []
        self.published_payload_ids = []
        self.published_payload_digests = []
        emitter = stage.GetPrimAtPath(emitter_path)
        if not emitter or emitter.GetTypeName() != "FlowEmitterPoint":
            raise RuntimeError("Point sidecar requires a FlowEmitterPoint Prim")
        points_prim = emitter.GetRelationship("pointsPrim")
        if not points_prim or not points_prim.GetTargets():
            raise RuntimeError("Point sidecar requires a pre-authored pointsPrim target")
        self._attributes = {
            "positions": emitter.GetAttribute("pointPositions"),
            "fuels": emitter.GetAttribute("pointFuels"),
            "temperatures": emitter.GetAttribute("pointTemperatures"),
            "smokes": emitter.GetAttribute("pointSmokes"),
            "revision": emitter.GetAttribute("campfire:residentRevision"),
            "layout_revision": emitter.GetAttribute("campfire:layoutRevision"),
        }
        if not all(self._attributes.values()):
            raise RuntimeError("Point sidecar requires pre-authored attributes")
        stored_revision = self._attributes["revision"].Get()
        if self._revision and stored_revision != self._revision:
            raise ValueError("Initial Point consumer revision does not match")
        stored_layout_revision = self._attributes["layout_revision"].Get()
        if stored_layout_revision != self._layout_revision:
            raise ValueError("Initial Point layout revision does not match")
        self._committed_layout_revision = self._layout_revision

    def prepare(self, snapshot):
        if self._closed:
            raise RuntimeError("Point sidecar is closed")
        if snapshot.revision != self._backend.revision:
            raise RuntimeError("Point sidecar requires current Resident revision")
        self._producer.build_channels()
        layout_revision = self._layout_revision
        positions = self._positions
        layout_origins = ()
        layout_axes = ()
        if self._translation_provider is not None:
            provider_start = time.perf_counter_ns()
            origins = self._translation_provider()
            self._live_translation_timing_ms["provider"].append(
                (time.perf_counter_ns() - provider_start) / 1_000_000.0
            )
            build_candidate = True
            if self._skip_unchanged_translation_layout:
                build_candidate = self._producer.layout_origins_changed(origins)
            candidate = None
            changed = False
            if build_candidate:
                candidate_start = time.perf_counter_ns()
                candidate = self._producer.build_layout_candidate(
                    origins, self._producer.axes
                )
                self._live_translation_timing_ms["candidate_build"].append(
                    (time.perf_counter_ns() - candidate_start) / 1_000_000.0
                )
                changed = any(
                    abs(float(current) - float(previous)) > 1.0e-9
                    for current_origin, previous_origin in zip(
                        candidate["origins"], self._producer.origins
                    )
                    for current, previous in zip(current_origin, previous_origin)
                )
            if changed:
                layout_revision += 1
                positions = candidate["positions"]
                layout_origins = candidate["origins"]
                layout_axes = candidate["axes"]
                self._live_translation_prepare_count += 1
            else:
                self._live_translation_unchanged_count += 1
        payload = ImmutableSurfacePayload(
            revision=snapshot.revision,
            tick=snapshot.tick,
            layout_revision=layout_revision,
            point_count=self._producer.point_count,
            positions=positions,
            fuels=self._producer.fuels.tobytes(order="C"),
            temperatures=self._producer.temperatures.tobytes(order="C"),
            smokes=self._producer.smokes.tobytes(order="C"),
            layout_origins=layout_origins,
            layout_axes=layout_axes,
        )
        self._prepare_count += 1
        return payload

    def _converted(self, payload, *, profile_translation=False):
        np = self._producer.np
        converted = {}
        for name, value, timing_name in (
            ("fuels", payload.fuels, "fuel_vt_conversion"),
            (
                "temperatures",
                payload.temperatures,
                "temperature_vt_conversion",
            ),
            ("smokes", payload.smokes, "smoke_vt_conversion"),
        ):
            conversion_start = time.perf_counter_ns() if profile_translation else None
            converted[name] = Vt.FloatArray.FromNumpy(
                np.frombuffer(value, dtype=np.float32)
            )
            if conversion_start is not None:
                self._live_translation_timing_ms[timing_name].append(
                    (time.perf_counter_ns() - conversion_start) / 1_000_000.0
                )
        if payload.layout_revision != self._committed_layout_revision:
            conversion_start = time.perf_counter_ns()
            converted["positions"] = Vt.Vec3fArray.FromNumpy(
                np.frombuffer(payload.positions, dtype=np.float32).reshape((-1, 3))
            )
            if self._translation_provider is not None:
                self._live_translation_timing_ms["position_vt_conversion"].append(
                    (time.perf_counter_ns() - conversion_start) / 1_000_000.0
                )
        return converted

    def publish(self, payload):
        if self._closed:
            raise RuntimeError("Point sidecar is closed")
        self.attempt_payload_ids.append(id(payload))
        self.attempt_payload_digests.append(payload.digest())
        if self._stage_provider() is not self._stage:
            self._failure_count += 1
            raise RuntimeError("Point sidecar rejected replaced stage")
        if payload.revision <= self._revision:
            raise RuntimeError("Point sidecar revision must increase monotonically")
        has_layout = bool(payload.layout_origins)
        expected_layout_revision = self._layout_revision + (1 if has_layout else 0)
        if payload.layout_revision != expected_layout_revision:
            raise RuntimeError("Point sidecar payload layout revision is not contiguous")
        transaction_start = time.perf_counter_ns() if has_layout else None
        converted = self._converted(payload, profile_translation=has_layout)
        previous_start = time.perf_counter_ns() if has_layout else None
        previous = {name: attribute.Get() for name, attribute in self._attributes.items()}
        if previous_start is not None:
            self._live_translation_timing_ms["previous_value_snapshot"].append(
                (time.perf_counter_ns() - previous_start) / 1_000_000.0
            )
        previous_state = {
            "revision": self._revision,
            "layout_revision": self._layout_revision,
            "committed_layout_revision": self._committed_layout_revision,
            "last_snapshot": self._last_snapshot,
            "values": previous,
            "origins": self._producer.origins.copy(order="C"),
            "axes": self._producer.axes.copy(order="C"),
            "positions": self._positions,
        }
        write_index = 0
        block = Sdf.ChangeBlock()
        block_enter_start = time.perf_counter_ns() if has_layout else None
        block.__enter__()
        if block_enter_start is not None:
            self._live_translation_timing_ms["change_block_enter"].append(
                (time.perf_counter_ns() - block_enter_start) / 1_000_000.0
            )
        try:
            for name in ("positions", "fuels", "temperatures", "smokes"):
                if name not in converted:
                    continue
                set_start = time.perf_counter_ns() if has_layout else None
                if not self._attributes[name].Set(converted[name]):
                    raise RuntimeError(f"Point sidecar {name} Set failed")
                if set_start is not None:
                    timing_name = {
                        "positions": "position_usd_set",
                        "fuels": "fuel_usd_set",
                        "temperatures": "temperature_usd_set",
                        "smokes": "smoke_usd_set",
                    }[name]
                    self._live_translation_timing_ms[timing_name].append(
                        (time.perf_counter_ns() - set_start) / 1_000_000.0
                    )
                if self._write_observer is not None:
                    self._write_observer(write_index, name, payload)
                write_index += 1
            if has_layout:
                layout_revision_start = time.perf_counter_ns()
                if not self._attributes["layout_revision"].Set(
                    payload.layout_revision
                ):
                    raise RuntimeError("Point sidecar layout revision Set failed")
                self._live_translation_timing_ms[
                    "layout_revision_usd_set"
                ].append(
                    (time.perf_counter_ns() - layout_revision_start) / 1_000_000.0
                )
                if self._write_observer is not None:
                    self._write_observer(write_index, "layout_revision", payload)
                write_index += 1
            resident_revision_start = (
                time.perf_counter_ns() if has_layout else None
            )
            if not self._attributes["revision"].Set(payload.revision):
                raise RuntimeError("Point sidecar revision Set failed")
            if resident_revision_start is not None:
                self._live_translation_timing_ms[
                    "resident_revision_usd_set"
                ].append(
                    (time.perf_counter_ns() - resident_revision_start) / 1_000_000.0
                )
            if self._write_observer is not None:
                self._write_observer(write_index, "revision", payload)
        except Exception:
            for name, value in previous.items():
                self._attributes[name].Set(value)
            block.__exit__(*sys.exc_info())
            self._failure_count += 1
            raise
        block_exit_start = time.perf_counter_ns() if has_layout else None
        block.__exit__(None, None, None)
        if block_exit_start is not None:
            self._live_translation_timing_ms["change_block_exit"].append(
                (time.perf_counter_ns() - block_exit_start) / 1_000_000.0
            )
        if transaction_start is not None:
            self._live_translation_timing_ms["publish_transaction"].append(
                (time.perf_counter_ns() - transaction_start) / 1_000_000.0
            )
        self._last_undo = previous_state
        self._revision = payload.revision
        if has_layout:
            producer_commit_start = time.perf_counter_ns()
            self._producer.commit_layout_candidate(
                payload.layout_origins, payload.layout_axes, payload.positions
            )
            self._positions = payload.positions
            self._layout_revision = payload.layout_revision
            self._live_translation_publish_count += 1
            self._update_layout_state()
            self._live_translation_timing_ms["producer_commit"].append(
                (time.perf_counter_ns() - producer_commit_start) / 1_000_000.0
            )
        self._committed_layout_revision = payload.layout_revision
        self._last_snapshot = payload
        self._publish_count += 1
        self.published_payload_ids.append(id(payload))
        self.published_payload_digests.append(payload.digest())

    def rollback_last_commit(self, revision):
        if self._last_undo is None or self._revision != revision:
            raise RuntimeError("Point sidecar has no matching commit to roll back")
        previous_state = self._last_undo
        with Sdf.ChangeBlock():
            for name, value in previous_state["values"].items():
                self._attributes[name].Set(value)
        self._producer.commit_layout_candidate(
            previous_state["origins"],
            previous_state["axes"],
            previous_state["positions"],
        )
        self._positions = previous_state["positions"]
        self._revision = previous_state["revision"]
        self._layout_revision = previous_state["layout_revision"]
        self._committed_layout_revision = previous_state[
            "committed_layout_revision"
        ]
        self._last_snapshot = previous_state["last_snapshot"]
        self._update_layout_state()
        self._last_undo = None
        self._rollback_count += 1

    def _update_layout_state(self):
        layout_state = getattr(self, "_layout_state", None)
        if layout_state is None:
            return
        layout_state.clear()
        layout_state.update(
            {
                "revision": self._layout_revision,
                "origins": tuple(
                    tuple(float(component) for component in origin)
                    for origin in self._producer.origins
                ),
                "axes": tuple(int(axis) for axis in self._producer.axes),
            }
        )

    def replace_layout(self, layout):
        """Transactionally publish a stopped layout without advancing snapshot revision."""

        revision = layout["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError("Point layout revision must be an integer")
        origins = self._producer.np.asarray(
            layout["origins"], dtype=self._producer.np.float64
        )
        axes = self._producer.np.asarray(layout["axes"], dtype=self._producer.np.uint32)
        if revision <= self._layout_revision:
            raise ValueError("Point layout revision must increase")
        if origins.shape != self._producer.origins.shape or axes.shape != self._producer.axes.shape:
            raise ValueError("Point layout shape changed structurally")
        if not self._producer.np.isfinite(origins).all():
            raise ValueError("Point layout origins must be finite")
        previous_origins = self._producer.origins.copy(order="C")
        previous_axes = self._producer.axes.copy(order="C")
        previous_positions = self._positions
        previous_layout_revision = self._layout_revision
        previous_committed_layout_revision = self._committed_layout_revision
        previous_usd_positions = self._attributes["positions"].Get()
        previous_usd_layout_revision = self._attributes["layout_revision"].Get()
        block = Sdf.ChangeBlock()
        block.__enter__()
        try:
            self._producer.origins[:] = origins
            self._producer.axes[:] = axes
            self._producer.build_layout()
            candidate_positions = self._producer.positions.tobytes(order="C")
            converted_positions = Vt.Vec3fArray.FromNumpy(
                self._producer.np.frombuffer(
                    candidate_positions, dtype=self._producer.np.float32
                ).reshape((-1, 3))
            )
            if not self._attributes["positions"].Set(converted_positions):
                raise RuntimeError("Point sidecar layout positions Set failed")
            if not self._attributes["layout_revision"].Set(revision):
                raise RuntimeError("Point sidecar layout revision Set failed")
        except Exception:
            self._producer.origins[:] = previous_origins
            self._producer.axes[:] = previous_axes
            self._producer.build_layout()
            self._positions = previous_positions
            self._layout_revision = previous_layout_revision
            self._committed_layout_revision = previous_committed_layout_revision
            self._attributes["positions"].Set(previous_usd_positions)
            self._attributes["layout_revision"].Set(previous_usd_layout_revision)
            block.__exit__(*sys.exc_info())
            raise
        block.__exit__(None, None, None)
        self._positions = candidate_positions
        self._layout_revision = revision
        self._committed_layout_revision = revision
        self._update_layout_state()
        self._last_undo = None
        self._layout_replace_count += 1
        return revision

    def status(self):
        timing = {
            name: (
                summarize_timing_ms(values)
                if values
                else {
                    "sample_count": 0,
                    "warmup_samples_excluded": 0,
                    "total_ms": 0.0,
                    "mean_ms": None,
                    "p95_ms": None,
                    "max_ms": None,
                }
            )
            for name, values in self._live_translation_timing_ms.items()
        }
        return {
            "revision": self._revision,
            "layout_revision": self._layout_revision,
            "committed_layout_revision": self._committed_layout_revision,
            "point_count": self._producer.point_count,
            "prepare_count": self._prepare_count,
            "publish_count": self._publish_count,
            "rollback_count": self._rollback_count,
            "failure_count": self._failure_count,
            "layout_replace_count": self._layout_replace_count,
            "live_translation_enabled": self._translation_provider is not None,
            "skip_unchanged_translation_layout": (
                self._skip_unchanged_translation_layout
            ),
            "live_translation_prepare_count": self._live_translation_prepare_count,
            "live_translation_publish_count": self._live_translation_publish_count,
            "live_translation_unchanged_count": self._live_translation_unchanged_count,
            "live_translation_timing_ms": timing,
            "closed": self._closed,
        }

    def close(self):
        already_closed = self._closed
        self._closed = True
        return not already_closed
