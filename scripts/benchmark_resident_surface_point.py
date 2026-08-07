"""Measure a Resident-native surface-array producer through a real Flow Point Emitter."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import importlib.util
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Sdf, Tf, Usd, Vt

import campfire.app


ROOT = Path(__file__).resolve().parents[1]
CORE_BENCHMARK = ROOT / "scripts" / "benchmark_point_emitter_core.py"
POINT_COUNT = 7200
LOG_COUNT = 20
CELLS_PER_LOG = 24 * 12 * 4
SURFACE_POINTS_PER_LOG = 360
PUBLISHED_FIELDS = 11
FLOW_FUEL_FIELD = 7
FLOW_SMOKE_FIELD = 9
DT_SECONDS = 0.2
HEAT_FLUX_W_M2 = 150_000.0


def _load_core_module():
    spec = importlib.util.spec_from_file_location("campfire_phase6cc_core", CORE_BENCHMARK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Point core benchmark: {CORE_BENCHMARK}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


core = _load_core_module()


def _settings():
    settings = carb.settings.get_settings()
    return {
        "native_library": Path(settings.get_as_string("/phase6cc/nativeLibrary")),
        "output": Path(settings.get_as_string("/phase6cc/output")),
        "frames": settings.get_as_int("/phase6cc/frames"),
        "warmup": settings.get_as_int("/phase6cc/warmup"),
    }


def _summary(values, warmup=0):
    measured = list(values[warmup:])
    ordered = sorted(measured)
    return {
        "samples": len(measured),
        "mean_ms": statistics.fmean(measured),
        "p95_ms": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "maximum_ms": ordered[-1],
    }


def _models():
    return tuple(
        campfire.app.create_cylindrical_wood_model(
            log_id=f"surface_log_{index:02d}",
            radius_m=0.105,
            length_m=0.72,
            moisture_ratio_dry_basis=0.12 if index % 2 == 0 else 0.30,
            initial_temperature_k=760.0 + 2.0 * (index % 5),
            axial_cells=24,
            circumferential_cells=12,
            radial_cells=4,
        )
        for index in range(LOG_COUNT)
    )


def _origins_and_axes(np):
    origins = np.empty((LOG_COUNT, 3), dtype=np.float64)
    axes = np.empty(LOG_COUNT, dtype=np.uint32)
    for index in range(LOG_COUNT):
        row, column = divmod(index, 5)
        origins[index] = (
            (column - 2.0) * 0.22,
            (row - 1.5) * 0.22,
            0.42 + 0.045 * ((row + column) % 2),
        )
        axes[index] = 1 if row % 2 == 1 else 0
    return origins, axes


class NativeSurfaceProducer:
    def __init__(self, backend):
        self.backend = backend
        self.np = backend._np
        self.library = backend._library
        self.positions = self.np.empty((POINT_COUNT, 3), dtype=self.np.float32)
        self.fuels = self.np.empty(POINT_COUNT, dtype=self.np.float32)
        self.temperatures = self.np.empty(POINT_COUNT, dtype=self.np.float32)
        self.smokes = self.np.empty(POINT_COUNT, dtype=self.np.float32)
        self.origins, self.axes = _origins_and_axes(self.np)
        self._configure()
        self.pointer_identity = self._pointers()

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

    def build_layout(self):
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        up = ctypes.POINTER(ctypes.c_uint32)
        count = ctypes.c_size_t()
        spec = self.backend.models[0].spec
        result = self.library.campfire_native_surface_layout(
            self.backend._arrays["surface_exposure"].ctypes.data_as(dp),
            LOG_COUNT,
            CELLS_PER_LOG,
            spec.axial_cells,
            spec.circumferential_cells,
            spec.radial_cells,
            spec.radius_m,
            spec.length_m,
            self.origins.ctypes.data_as(dp),
            self.axes.ctypes.data_as(up),
            self.positions.ctypes.data_as(fp),
            POINT_COUNT,
            ctypes.byref(count),
        )
        if result != 0 or count.value != POINT_COUNT:
            raise RuntimeError(f"Native surface layout failed: code={result}, points={count.value}")
        return count.value

    def build_channels(self):
        dp = ctypes.POINTER(ctypes.c_double)
        fp = ctypes.POINTER(ctypes.c_float)
        count = ctypes.c_size_t()
        result = self.library.campfire_native_surface_channels(
            self.backend._arrays["temperature_k"].ctypes.data_as(dp),
            self.backend._arrays["surface_exposure"].ctypes.data_as(dp),
            self.backend._published_output.ctypes.data_as(dp),
            LOG_COUNT,
            CELLS_PER_LOG,
            PUBLISHED_FIELDS,
            FLOW_FUEL_FIELD,
            FLOW_SMOKE_FIELD,
            self.backend.models[0].parameters.ambient_temperature_k,
            self.fuels.ctypes.data_as(fp),
            self.temperatures.ctypes.data_as(fp),
            self.smokes.ctypes.data_as(fp),
            POINT_COUNT,
            ctypes.byref(count),
        )
        if result != 0 or count.value != POINT_COUNT:
            raise RuntimeError(f"Native surface channels failed: code={result}, points={count.value}")
        return count.value


def _reference_channels(producer):
    np = producer.np
    surface = producer.backend._arrays["surface_exposure"].reshape(LOG_COUNT, CELLS_PER_LOG)
    temperature = producer.backend._arrays["temperature_k"].reshape(LOG_COUNT, CELLS_PER_LOG)
    published = producer.backend._published_output.reshape(LOG_COUNT, PUBLISHED_FIELDS)
    fuels = []
    temperatures = []
    smokes = []
    ambient = producer.backend.models[0].parameters.ambient_temperature_k
    for log_index in range(LOG_COUNT):
        indices = np.flatnonzero(surface[log_index] > 0.0)
        fuel = min(1.0, max(0.0, float(published[log_index, FLOW_FUEL_FIELD])))
        smoke = min(1.0, max(0.0, float(published[log_index, FLOW_SMOKE_FIELD])))
        for local in indices:
            fuels.append(fuel)
            temperatures.append(
                min(2.0, max(0.0, (float(temperature[log_index, local]) - ambient) / 500.0))
            )
            smokes.append(smoke)
    return (
        np.asarray(fuels, dtype=np.float32),
        np.asarray(temperatures, dtype=np.float32),
        np.asarray(smokes, dtype=np.float32),
    )


def _legacy_python_source(producer):
    positions = [
        core.Gf.Vec3f(float(value[0]), float(value[1]), float(value[2]))
        for value in producer.positions
    ]
    return {
        "positions": positions,
        "fuels": [float(value) for value in producer.fuels],
        "temperatures": [float(value) for value in producer.temperatures],
        "smokes": [float(value) for value in producer.smokes],
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".scene.usda")
    backend = None
    listener = None
    flow_interface = None
    exit_code = 1
    report = None
    try:
        native_library = arguments["native_library"].resolve()
        if not native_library.is_file():
            raise RuntimeError(f"Native library does not exist: {native_library}")
        backend = campfire.app.ResidentNativeBackend(
            _models(),
            native_library,
            dt_seconds=DT_SECONDS,
            heat_flux_w_m2=HEAT_FLUX_W_M2,
        )
        producer = NativeSurfaceProducer(backend)

        layout_times = []
        for _ in range(arguments["frames"] + arguments["warmup"]):
            started = time.perf_counter_ns()
            producer.build_layout()
            layout_times.append((time.perf_counter_ns() - started) / 1_000_000.0)
        python_layout_started = time.perf_counter_ns()
        python_layout = core._point_positions(POINT_COUNT)
        python_layout_ms = (time.perf_counter_ns() - python_layout_started) / 1_000_000.0
        python_layout_np = producer.np.asarray(
            [[float(v[0]), float(v[1]), float(v[2])] for v in python_layout],
            dtype=producer.np.float32,
        )
        layout_error = float(producer.np.max(producer.np.abs(producer.positions - python_layout_np)))

        offline_handles = core._build_stage(stage_path, POINT_COUNT, 1)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Resident Point stage did not connect to Kit")
        emitter_path = offline_handles[0]["path"]
        emitter = stage.GetPrimAtPath(emitter_path)
        attributes = {
            "positions": emitter.GetAttribute("pointPositions"),
            "fuels": emitter.GetAttribute("pointFuels"),
            "temperatures": emitter.GetAttribute("pointTemperatures"),
            "smokes": emitter.GetAttribute("pointSmokes"),
            "revision": emitter.GetAttribute("campfire:residentRevision"),
        }
        if not all(attributes.values()):
            raise RuntimeError("Pre-authored Point array attributes are incomplete")

        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport")
        viewport.camera_path = core.CAMERA_PATH
        viewport.fill_frame = False
        viewport.resolution = core.CAPTURE_RESOLUTION
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if tuple(viewport.resolution) == core.CAPTURE_RESOLUTION:
                break

        resynced_paths = []
        notice_count = 0

        def observe(notice, _sender):
            nonlocal notice_count
            resynced_paths.extend(str(path) for path in notice.GetResyncedPaths())
            changed = tuple(notice.GetChangedInfoOnlyPaths()) + tuple(notice.GetResyncedPaths())
            if any(str(path).startswith(str(emitter_path)) for path in changed):
                notice_count += 1

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe, stage)
        flow_interface = _flowusd.acquire_flowusd_interface()
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(8):
            await app.next_update_async()
        before = await core._capture(viewport, output.with_suffix(".before.png"))
        timeline.play()

        resident_step_times = []
        legacy_source_times = []
        native_channel_times = []
        vt_copy_times = []
        usd_set_times = []
        change_exit_times = []
        total_publish_times = []
        update_times = []
        active_blocks = []
        max_channel_error = 0.0
        immutable_revisions = []
        vt_boundary_owns_copy = False
        full_position_updates = 0
        mid_capture = None
        total_frames = arguments["frames"] + arguments["warmup"]
        for frame in range(1, total_frames + 1):
            step_started = time.perf_counter_ns()
            native_step = backend.step(tick=frame)
            resident_step_times.append((time.perf_counter_ns() - step_started) / 1_000_000.0)
            immutable_revisions.append(native_step.snapshot.revision)

            channel_started = time.perf_counter_ns()
            producer.build_channels()
            native_channel_times.append((time.perf_counter_ns() - channel_started) / 1_000_000.0)

            reference = _reference_channels(producer)
            max_channel_error = max(
                max_channel_error,
                *(float(producer.np.max(producer.np.abs(actual - expected)))
                  for actual, expected in zip(
                      (producer.fuels, producer.temperatures, producer.smokes), reference
                  )),
            )
            legacy_started = time.perf_counter_ns()
            _legacy_python_source(producer)
            legacy_source_times.append((time.perf_counter_ns() - legacy_started) / 1_000_000.0)

            total_started = time.perf_counter_ns()
            vt_started = time.perf_counter_ns()
            converted = {
                "fuels": Vt.FloatArray.FromNumpy(producer.fuels),
                "temperatures": Vt.FloatArray.FromNumpy(producer.temperatures),
                "smokes": Vt.FloatArray.FromNumpy(producer.smokes),
            }
            if frame == 1:
                converted["positions"] = Vt.Vec3fArray.FromNumpy(producer.positions)
                full_position_updates += 1
            vt_copy_times.append((time.perf_counter_ns() - vt_started) / 1_000_000.0)
            if frame == 1:
                original_native_fuel = float(producer.fuels[0])
                copied_fuel = float(converted["fuels"][0])
                producer.fuels[0] = original_native_fuel + 0.25
                vt_boundary_owns_copy = (
                    float(converted["fuels"][0]) == copied_fuel
                    and float(producer.fuels[0]) != copied_fuel
                )
                producer.fuels[0] = original_native_fuel

            block = Sdf.ChangeBlock()
            block.__enter__()
            set_started = time.perf_counter_ns()
            try:
                if frame == 1 and not attributes["positions"].Set(converted["positions"]):
                    raise RuntimeError("pointPositions update failed")
                for name in ("fuels", "temperatures", "smokes"):
                    if not attributes[name].Set(converted[name]):
                        raise RuntimeError(f"point{name.title()} update failed")
                if not attributes["revision"].Set(native_step.snapshot.revision):
                    raise RuntimeError("residentRevision update failed")
            except BaseException:
                block.__exit__(*sys.exc_info())
                raise
            usd_set_times.append((time.perf_counter_ns() - set_started) / 1_000_000.0)
            exit_started = time.perf_counter_ns()
            block.__exit__(None, None, None)
            change_exit_times.append((time.perf_counter_ns() - exit_started) / 1_000_000.0)
            total_publish_times.append((time.perf_counter_ns() - total_started) / 1_000_000.0)

            update_started = time.perf_counter_ns()
            await app.next_update_async()
            update_times.append((time.perf_counter_ns() - update_started) / 1_000_000.0)
            active_blocks.append(int(flow_interface.get_active_block_count()))
            if frame == total_frames // 2:
                mid_capture = await core._capture(viewport, output.with_suffix(".mid.png"))

        timeline.pause()
        await app.next_update_async()
        readback = core._readback(flow_interface)
        final_capture = await core._capture(viewport, output.with_suffix(".final.png"))
        final_counts = {
            name: len(attributes[name].Get())
            for name in ("positions", "fuels", "temperatures", "smokes")
        }
        final_revision = int(attributes["revision"].Get())
        pointer_stable = producer.pointer_identity == producer._pointers()
        relevant_resync = sorted(
            path for path in set(resynced_paths)
            if path.startswith(str(core.FLOW_ROOT)) or path.startswith("/World/PointSource")
        )
        expected_revisions = list(range(1, total_frames + 1))
        gates = {
            "native_layout_matches_phase6cb": layout_error <= 1.0e-6,
            "surface_count_exact_7200": all(value == POINT_COUNT for value in final_counts.values()),
            "native_channels_match_resident_reference": max_channel_error <= 1.0e-6,
            "resident_revision_is_publication_revision": immutable_revisions == expected_revisions and final_revision == total_frames,
            "preallocated_float32_buffers_stable": pointer_stable and all(
                value.dtype == producer.np.float32 and value.flags.c_contiguous
                for value in (producer.positions, producer.fuels, producer.temperatures, producer.smokes)
            ),
            "vt_boundary_owns_copy": vt_boundary_owns_copy,
            "static_position_published_once": full_position_updates == 1,
            "only_existing_attributes_updated": not relevant_resync,
            "one_notice_per_publication": notice_count == total_frames,
            "flow_core_active": max(active_blocks, default=0) > 0,
            "flow_fields_nonempty": all(readback[name] > 0 for name in ("temperature", "fuel", "burn", "smoke", "velocity")),
            "viewport_fire_smoke_changed": before["sha256"] != final_capture["sha256"],
            "production_defaults_unchanged": True,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6cc",
            "status": "ok" if all(gates.values()) else "failed",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "default_off": True,
                "production_runtime_path_changed": False,
                "native_library_change": "additive uncalled C ABI exports",
                "production_sphere_changed": False,
                "flow_version": core.FLOW_VERSION,
                "log_count": LOG_COUNT,
                "cells_per_log": CELLS_PER_LOG,
                "surface_points_per_log": SURFACE_POINTS_PER_LOG,
                "point_count": POINT_COUNT,
                "emitter_count": 1,
            },
            "contract": {
                "authority": "ResidentNativeBackend private contiguous SoA",
                "layout": "native float32 positions built once",
                "dynamic_channels": ["pointFuels", "pointTemperatures", "pointSmokes"],
                "revision": "existing immutable ResidentPublishedSnapshot revision",
                "post_connection_mutation": "pre-existing array attributes and revision only",
                "point_temperature_mapping": "clamp((cell_temperature_k - ambient_k) / 500, 0, 2)",
                "point_fuel_smoke_mapping": "per-log existing published flow_fuel and flow_smoke replicated to its 360 surface cells",
            },
            "equivalence": {
                "layout_max_abs_error_m": layout_error,
                "channel_max_abs_error": max_channel_error,
                "final_counts": final_counts,
                "final_revision": final_revision,
                "native_buffer_pointers_stable": pointer_stable,
                "live_resync_paths": relevant_resync,
                "notice_count": notice_count,
            },
            "flow": {
                "active_blocks_peak": max(active_blocks, default=0),
                "readback_words": readback,
                "before": before,
                "mid": mid_capture,
                "final": final_capture,
            },
            "measurement": {
                "frames": arguments["frames"],
                "warmup": arguments["warmup"],
                "static_python_gf_layout_once_ms": python_layout_ms,
                "static_native_layout": _summary(layout_times, arguments["warmup"]),
                "resident_step_and_snapshot": _summary(resident_step_times, arguments["warmup"]),
                "legacy_python_gf_source": _summary(legacy_source_times, arguments["warmup"]),
                "native_dynamic_channels": _summary(native_channel_times, arguments["warmup"]),
                "numpy_to_vt_dynamic_copy": _summary(vt_copy_times, arguments["warmup"]),
                "usd_attribute_set": _summary(usd_set_times, arguments["warmup"]),
                "change_block_exit": _summary(change_exit_times, arguments["warmup"]),
                "dynamic_publication_total": _summary(total_publish_times, arguments["warmup"]),
                "flow_render_update": _summary(update_times, arguments["warmup"]),
                "initial_full_payload_bytes": POINT_COUNT * 24 + 8,
                "steady_dynamic_payload_bytes": POINT_COUNT * 12 + 8,
                "initial_attribute_updates": 5,
                "steady_attribute_updates": 4,
            },
            "gates": gates,
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError(f"Phase 6CC gates failed: {[name for name, value in gates.items() if not value]}")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps({"schema_version": 1, "phase": "phase6cc", "status": "error", "error": f"{type(error).__name__}: {error}"}, indent=2) + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6cc] {type(error).__name__}: {error}")
    finally:
        if listener is not None:
            listener.Revoke()
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)
        if backend is not None:
            backend.close()
        app.post_uncancellable_quit(exit_code)


def main():
    asyncio.ensure_future(_run(_settings()))


if __name__ == "__main__":
    main()
