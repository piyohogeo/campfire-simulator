"""Kit/RTX qualification for native V3 beauty packing and change-aware upload."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import statistics
import time
from pathlib import Path

import carb
import campfire.app
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from PIL import Image
from pxr import Gf, Usd, UsdGeom, UsdLux


RESOLUTION = (1280, 720)


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3tb/output")),
        "capture_dir": Path(settings.get_as_string("/phasev3tb/captureDir")),
        "native_library": Path(settings.get_as_string("/phasev3tb/nativeLibrary")),
    }


def _summary(values, warmup=5):
    measured = list(values)[warmup:]
    ordered = sorted(measured)
    return {
        "samples": len(measured),
        "mean_ms": statistics.fmean(measured),
        "p50_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(measured),
    }


def _payload(log_ids, revision, *, seed=0, base_offset=0.0, heat_offset=0.0):
    count = len(log_ids) * 360
    identity = np.arange(count, dtype=np.float32)
    temperature = 300.0 + ((identity * 13.0 + seed * 37.0) % 1000.0)
    temperature += heat_offset
    moisture = ((identity + seed * 3.0) % 31.0) * 0.001 + base_offset
    char = ((identity + seed * 5.0) % 16.0) * 0.001
    ash = ((identity + seed * 7.0) % 16.0) * 0.0001
    return campfire.app.ImmutableWoodVisualSurfacePayload(
        revision,
        revision,
        tuple(log_ids),
        360,
        np.tile(np.arange(360, dtype=np.uint32), len(log_ids)).tobytes(),
        np.asarray(temperature, dtype=np.float32).tobytes(),
        np.asarray(moisture, dtype=np.float32).tobytes(),
        np.asarray(char, dtype=np.float32).tobytes(),
        np.asarray(ash, dtype=np.float32).tobytes(),
    )


def _build_stage(path, log_count=20):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Logs")
    for slot in range(log_count):
        row, column = divmod(slot, 5)
        campfire.app.create_log(
            stage,
            campfire.app.LogSpec(
                f"Log_{slot:02d}",
                ((column - 2) * 1.15, (row - 1.5) * 1.05, 0.42),
                0.0 if row % 2 == 0 else 90.0,
                0.22,
                0.92,
            ),
            render_hierarchy=True,
            render_log_slot=slot,
        )
    log_ids = tuple(campfire.app.list_log_ids(stage))
    material = campfire.app.preauthor_wood_visual_v3(stage, log_ids)
    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3f(4.5, 3.6, 0.08))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.08))
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.035, 0.035, 0.045)])
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(48.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(6.8, -9.6, 7.8),
        Gf.Vec3d(0.0, 0.0, 0.35),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.AddTransformOp().Set(view.GetInverse())
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(650.0)
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(22000.0)
    key.CreateRadiusAttr(0.55)
    key.AddTranslateOp().Set(Gf.Vec3d(-2.0, -3.5, 6.0))
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save V3T-B stage")
    return log_ids, material


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("V3T-B requires a viewport")
    viewport.camera_path = "/World/Camera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    for _ in range(120):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == RESOLUTION:
            return viewport
    raise RuntimeError("V3T-B viewport did not settle")


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(
        viewport, file_path=str(path)
    )
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"V3T-B capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
            return {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mean_rgb": [float(value) for value in rgb.mean(axis=(0, 1))],
            }
        await asyncio.sleep(0.05)
    raise RuntimeError(f"V3T-B capture missing: {path}")


def _native_reference_probe(library, log_count):
    log_ids = tuple(f"Log_{index:02d}" for index in range(log_count))
    descriptor = campfire.app.compact_atlas_descriptor(log_count)
    reference = campfire.app.WoodVisualV3AtlasPacker(log_ids, descriptor=descriptor)
    native = campfire.app.WoodVisualV3NativeAtlasPacker(
        library, log_ids, descriptor=descriptor
    )
    exact = True
    distinct_after_permutation = False
    python_ms = []
    native_ms = []
    base_pointer = native._base_rgba8.ctypes.data
    emission_pointer = native._emission_rgba8.ctypes.data
    for sample in range(105):
        payload = _payload(log_ids, sample + 1, seed=sample)
        expected = reference.pack(payload)
        actual = native.pack(payload)
        python_ms.append(expected.pack_ms)
        native_ms.append(actual.pack_ms)
        exact = exact and np.array_equal(expected.base_rgba8, actual.base_rgba8)
        exact = exact and np.array_equal(
            expected.emission_rgba8, actual.emission_rgba8
        )
    original = _payload(log_ids, 10_000, seed=50)
    original_native = native.pack(original)
    original_base = original_native.base_rgba8.copy()
    original_emission = original_native.emission_rgba8.copy()
    arrays = [
        np.frombuffer(raw, dtype=np.float32).copy()
        for raw in (
            original.temperatures,
            original.moistures,
            original.chars,
            original.ashes,
        )
    ]
    first, second = 123, len(arrays[0]) - 123
    for values in arrays:
        values[[first, second]] = values[[second, first]]
    permuted = campfire.app.ImmutableWoodVisualSurfacePayload(
        10_001,
        10_001,
        original.log_ids,
        original.points_per_log,
        original.local_surface_indices,
        *(values.tobytes() for values in arrays),
    )
    permuted_expected = reference.pack(permuted)
    permuted_actual = native.pack(permuted)
    exact = exact and np.array_equal(
        permuted_expected.base_rgba8, permuted_actual.base_rgba8
    )
    exact = exact and np.array_equal(
        permuted_expected.emission_rgba8, permuted_actual.emission_rgba8
    )
    distinct_after_permutation = (
        not np.array_equal(original_base, permuted_actual.base_rgba8)
        or not np.array_equal(original_emission, permuted_actual.emission_rgba8)
    )
    return {
        "logs": log_count,
        "surface_cells": log_count * 360,
        "all_texels_exact": exact,
        "permutation_visible": distinct_after_permutation,
        "native_buffer_pointer_stable": (
            base_pointer == native._base_rgba8.ctypes.data
            and emission_pointer == native._emission_rgba8.ctypes.data
        ),
        "native_session_allocation_count": native.allocation_count,
        "native_pack_count": native.pack_count,
        "python_pack": _summary(python_ms),
        "native_pack": _summary(native_ms),
    }


def _invalid_native_input_rejected(library):
    log_ids = ("Log_00",)
    native = campfire.app.WoodVisualV3NativeAtlasPacker(library, log_ids)
    count = 360
    temperature = np.full(count, 300.0, np.float32)
    moisture = np.zeros(count, np.float32)
    char = np.zeros(count, np.float32)
    ash = np.zeros(count, np.float32)
    moisture[7] = -1.0
    fp = ctypes.POINTER(ctypes.c_float)
    up = ctypes.POINTER(ctypes.c_uint32)
    bp = ctypes.POINTER(ctypes.c_uint8)
    result = library.campfire_native_wood_visual_rgba8_pack(
        temperature.ctypes.data_as(fp),
        moisture.ctypes.data_as(fp),
        char.ctypes.data_as(fp),
        ash.ctypes.data_as(fp),
        1,
        360,
        native._render_slots.ctypes.data_as(up),
        native.descriptor.slot_capacity,
        native.descriptor.tile_columns,
        native.descriptor.tile_rows,
        native._base_rgba8.ctypes.data_as(bp),
        native._base_rgba8.nbytes,
        native._emission_rgba8.ctypes.data_as(bp),
        native._emission_rgba8.nbytes,
    )
    return result == 4


def _adaptive_probe(log_ids):
    def uniform_payload(revision, temperature):
        count = len(log_ids) * 360
        zero = np.zeros(count, np.float32).tobytes()
        return campfire.app.ImmutableWoodVisualSurfacePayload(
            revision,
            revision,
            tuple(log_ids),
            360,
            np.tile(np.arange(360, dtype=np.uint32), len(log_ids)).tobytes(),
            np.full(count, temperature, np.float32).tobytes(),
            zero,
            zero,
            zero,
        )

    scheduler = campfire.app.WoodVisualV3AdaptiveScheduler()
    decisions = []
    revision = 1
    for tick in range(26):
        payload = uniform_payload(revision, 400.0 + tick)
        decision = scheduler.decide(payload, tick * 0.2)
        decisions.append(decision)
        if decision.publish:
            scheduler.committed(payload, tick * 0.2)
        revision += 1
    rapid = campfire.app.WoodVisualV3AdaptiveScheduler()
    cool = uniform_payload(1000, 630.0)
    rapid.committed(cool, 0.0)
    hot = uniform_payload(1001, 670.0)
    rapid_decision = rapid.decide(hot, 0.2)
    published = [value for value in decisions if value.publish]
    return {
        "source_updates": len(decisions),
        "fixed_5hz_publications": len(decisions),
        "adaptive_publications": len(published),
        "effective_hz": len(published) / 5.0,
        "maximum_publish_interval_seconds": max(
            value.elapsed_since_publish_seconds for value in published[1:]
        ),
        "rapid_heat_keeps_5hz": rapid_decision.publish
        and rapid_decision.reason == "rapid_heat",
        "normal_bound_seconds": scheduler.normal_interval_seconds,
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".usda")
    library = ctypes.CDLL(str(arguments["native_library"].resolve()))
    consumer = None
    report = None
    exit_code = 1
    try:
        four = _native_reference_probe(library, 4)
        twenty = _native_reference_probe(library, 20)
        invalid_rejected = _invalid_native_input_rejected(library)
        log_ids, material = _build_stage(stage_path, 20)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        failure = {"point": None}

        def inject(point, _revision):
            if point == failure["point"]:
                raise RuntimeError("injected native visual failure")

        consumer = campfire.app.WoodVisualV3Consumer(
            stage,
            log_ids,
            track_notices=True,
            failure_injector=inject,
            native_library=library,
        )
        consumer.on_timeline_started()
        viewport = await _viewport()
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        neutral = await _capture(viewport, capture_dir / "native_neutral.png")

        first_payload = _payload(log_ids, 1, seed=1)
        first = consumer.publish(first_payload)
        same_visual = consumer.publish(_payload(log_ids, 2, seed=1))
        capture_republish = consumer.publish_for_capture(
            _payload(log_ids, 2, seed=1)
        )
        base_only = consumer.publish(
            _payload(log_ids, 3, seed=1, base_offset=0.002)
        )
        emission_only = consumer.publish(
            _payload(log_ids, 4, seed=1, base_offset=0.002, heat_offset=40.0)
        )
        repeated = consumer.publish(
            _payload(log_ids, 4, seed=1, base_offset=0.002, heat_offset=40.0)
        )
        stale_rejected = False
        try:
            consumer.publish(_payload(log_ids, 3, seed=1))
        except RuntimeError:
            stale_rejected = True

        failure["point"] = "after_base"
        failed = False
        failed_payload = _payload(log_ids, 5, seed=8)
        try:
            consumer.publish(failed_payload)
        except RuntimeError:
            state = consumer.status()
            failed = state["revision"] == 4 and state["processed_revision"] == 4
        failure["point"] = None
        retry = consumer.publish(failed_payload)

        changing_profiles = []
        for revision in range(6, 111):
            changing_profiles.append(
                consumer.publish(_payload(log_ids, revision, seed=revision))
            )
        unchanged_profiles = []
        for revision in range(111, 216):
            unchanged_profiles.append(
                consumer.publish(_payload(log_ids, revision, seed=110))
            )

        for _ in range(12):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        visible = await _capture(viewport, capture_dir / "native_beauty.png")

        latest_payload = _payload(log_ids, 215, seed=110)
        if not stage.GetRootLayer().Save():
            raise RuntimeError("Unable to save V3T-B stage before reload")
        await context.close_stage_async()
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        reloaded = consumer.on_stage_reloaded(stage, latest_payload)
        state = consumer.status()

        changing_timing = {
            name: _summary(getattr(profile, name) for profile in changing_profiles)
            for name in (
                "beauty_pack_ms",
                "boundary_prepare_ms",
                "cpu_upload_ms",
                "revision_commit_ms",
                "total_ms",
            )
        }
        adaptive = _adaptive_probe(log_ids)
        gates = {
            "four_log_all_texels_match_reference": four["all_texels_exact"],
            "twenty_log_all_texels_match_reference": twenty["all_texels_exact"],
            "surface_permutation_changes_output": four["permutation_visible"]
            and twenty["permutation_visible"],
            "native_rejects_invalid_float_input": invalid_rejected,
            "session_buffers_are_reused": four["native_buffer_pointer_stable"]
            and twenty["native_buffer_pointer_stable"],
            "unchanged_revision_is_noop": repeated.status == "unchanged_revision",
            "unchanged_quantized_atlases_skip_all_writes": (
                same_visual.status == "unchanged_quantized"
                and same_visual.upload_count == 0
                and same_visual.usd_set_count == 0
            ),
            "base_and_emission_skip_independently": (
                base_only.base_changed
                and not base_only.emission_changed
                and emission_only.emission_changed
                and not emission_only.base_changed
            ),
            "stale_revision_rejected": stale_rejected,
            "failure_retains_displayed_and_processed_revision": failed,
            "retry_after_failure_commits": retry.revision == 5,
            "reload_force_republishes_both_channels": reloaded.upload_count == 2,
            "camera_capture_force_republishes_both_channels": (
                capture_republish.status == "capture_republish"
                and capture_republish.upload_count == 2
            ),
            "processed_and_displayed_revision_are_observable": (
                state["processed_revision"] == 215 and state["revision"] == 215
            ),
            "adaptive_normal_delay_bounded_to_500ms": (
                adaptive["maximum_publish_interval_seconds"] <= 0.5
            ),
            "rapid_heat_keeps_5hz": adaptive["rapid_heat_keeps_5hz"],
            "rtx_output_changed": neutral["sha256"] != visible["sha256"],
        }
        report = {
            "schema": "campfire.phasev3tb.native_beauty.v1",
            "status": "qualified" if all(gates.values()) else "not_qualified",
            "gates": gates,
            "reference_comparison": {"four_logs": four, "twenty_logs": twenty},
            "change_aware": {
                "first": first.__dict__,
                "same_visual": same_visual.__dict__,
                "base_only": base_only.__dict__,
                "emission_only": emission_only.__dict__,
                "changing_samples": len(changing_profiles),
                "unchanged_samples": len(unchanged_profiles),
                "unchanged_uploads": sum(p.upload_count for p in unchanged_profiles),
                "unchanged_usd_sets": sum(p.usd_set_count for p in unchanged_profiles),
                "changing_timing": changing_timing,
                "changing_transferred_bytes": sum(
                    profile.transferred_bytes for profile in changing_profiles
                ),
            },
            "adaptive_schedule": adaptive,
            "consumer": state,
            "transport": {
                "atlas": material["atlas"],
                "bytes_two_rgba8": material["atlas_descriptor"][
                    "bytes_per_rgba8_atlas"
                ]
                * 2,
                "native_output_ownership": "session-owned NumPy uint8 arrays; C++ writes synchronously through ctypes and never retains pointers",
                "provider_input_lifetime": "committed and work buffers remain alive until consumer close; public CPU raw upload remains the qualified boundary",
                "gpu_pointer_used": False,
                "asset_path_changes": False,
                "live_prim_redefinition": False,
            },
            "captures": {
                "neutral": neutral,
                "native_beauty": visible,
                "kind": "fixed-state transport diagnostic; not a combustion trajectory",
            },
            "decision": {
                "feature_default": False,
                "v2_payload_changed": False,
                "authority_flow_point_collision_changed": False,
                "continue_to_integrated_v3tc": True,
            },
        }
        exit_code = 0 if all(gates.values()) else 2
    except Exception as error:
        report = {
            "schema": "campfire.phasev3tb.native_beauty.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if consumer is not None:
            consumer.close()
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
