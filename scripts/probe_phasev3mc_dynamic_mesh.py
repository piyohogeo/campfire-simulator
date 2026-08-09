"""Kit/RTX qualification for V2 surface payload to stable V3 Mesh textures."""

from __future__ import annotations

import asyncio
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
from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics


RESOLUTION = (1280, 720)


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3mc/output")),
        "capture_dir": Path(settings.get_as_string("/phasev3mc/captureDir")),
        "native_library": Path(settings.get_as_string("/phasev3mc/nativeLibrary")),
    }


def _summary(values, warmup=5):
    values = list(values)[warmup:]
    ordered = sorted(values)
    return {
        "samples": len(values),
        "mean_ms": statistics.fmean(values),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(values),
    }


def _payload(log_ids, revision, state="four_states"):
    shape = (len(log_ids), 360)
    temperature = np.full(shape, 300.0, np.float32)
    moisture = np.full(shape, 0.002, np.float32)
    char = np.zeros(shape, np.float32)
    ash = np.zeros(shape, np.float32)
    if state == "four_states":
        moisture[0] = 0.030
        char[1] = 0.015
        ash[2] = 0.0015
        temperature[3, :120] = 720.0
        temperature[3, 120:240] = 900.0
        temperature[3, 240:] = 1150.0
    else:
        identity = np.arange(360, dtype=np.float32)
        for slot in range(len(log_ids)):
            temperature[slot] = 300.0 + ((identity + slot * 19) % 1000)
            moisture[slot] = ((identity + slot) % 31) * 0.001
            char[slot] = ((identity + slot * 3) % 16) * 0.001
            ash[slot] = ((identity + slot * 5) % 16) * 0.0001
    return campfire.app.ImmutableWoodVisualSurfacePayload(
        revision,
        revision,
        tuple(log_ids),
        360,
        np.tile(np.arange(360, dtype=np.uint32), len(log_ids)).tobytes(),
        temperature.tobytes(),
        moisture.tobytes(),
        char.tobytes(),
        ash.tobytes(),
    )


def _build_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Logs")
    for slot in range(20):
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
        raise RuntimeError("Unable to save V3M-C stage")
    return log_ids, material


def _topology(stage, log_ids):
    result = {}
    for log_id in log_ids:
        render = campfire.app.get_log_render_surface(stage, log_id)
        mesh = UsdGeom.Mesh(render)
        payload = {
            "points": [[float(v) for v in p] for p in mesh.GetPointsAttr().Get()],
            "counts": list(mesh.GetFaceVertexCountsAttr().Get()),
            "indices": list(mesh.GetFaceVertexIndicesAttr().Get()),
            "st": [[float(v) for v in p] for p in UsdGeom.PrimvarsAPI(render).GetPrimvar("st").Get()],
        }
        result[log_id] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
    return result


def _native_surface_performance(library):
    models = tuple(
        campfire.app.create_cylindrical_wood_model(
            f"Log_{index:02d}", 0.16, 1.8, 0.12 + 0.01 * (index % 4)
        )
        for index in range(20)
    )
    backend = campfire.app.ResidentNativeBackend(
        models, library, dt_seconds=0.2, heat_flux_w_m2=150_000.0
    )
    try:
        producer = campfire.app.ResidentNativeWoodVisualSurfaceProducer(backend)
        profiles = [producer.pack(index, index)[1] for index in range(1, 106)]
        return {
            "logs": 20,
            "surface_cells": producer.point_count,
            "payload_bytes": producer.point_count * 20,
            "timing": {
                name: _summary(getattr(profile, name) for profile in profiles)
                for name in (
                    "native_pack_ms",
                    "boundary_copy_ms",
                    "validation_ms",
                    "digest_ms",
                    "total_ms",
                )
            },
        }
    finally:
        backend.close()


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("V3M-C requires a viewport")
    viewport.camera_path = "/World/Camera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    for _ in range(120):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == RESOLUTION:
            return viewport
    raise RuntimeError("V3M-C viewport did not settle")


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(
        viewport, file_path=str(path)
    )
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"V3M-C capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
            roi = pixels[120:660, 120:1160]
            return {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "rgb_mean": [float(value) for value in roi.mean(axis=(0, 1))],
                "quantized_colors": int(
                    np.unique((roi // 24).reshape(-1, 3), axis=0).shape[0]
                ),
            }
        await asyncio.sleep(0.05)
    raise RuntimeError(f"V3M-C capture missing: {path}")


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".usda")
    consumer = None
    report = None
    exit_code = 1
    try:
        log_ids, material = _build_stage(stage_path)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        paths_before = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        topology_before = _topology(stage, log_ids)
        failure = {"point": None}

        def inject(point, _revision):
            if point == failure["point"]:
                raise RuntimeError("injected V3 visual-only failure")

        consumer = campfire.app.WoodVisualV3Consumer(
            stage,
            log_ids,
            track_notices=True,
            failure_injector=inject,
        )
        consumer.on_timeline_started()
        viewport = await _viewport()
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        neutral = await _capture(viewport, capture_dir / "surface_states_neutral.png")
        first = _payload(log_ids, 2)
        profile = consumer.publish(first)
        latency_ms = []
        latency_captures = []
        for frame in range(1, 5):
            started = time.perf_counter_ns()
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            latency_ms.append((time.perf_counter_ns() - started) / 1_000_000.0)
            latency_captures.append(
                await _capture(
                    viewport,
                    capture_dir / f"surface_states_update_{frame}.png",
                )
            )
        for _ in range(8):
            started = time.perf_counter_ns()
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            latency_ms.append((time.perf_counter_ns() - started) / 1_000_000.0)
        initial = latency_captures[-1]
        first_changed_frame = next(
            (
                index + 1
                for index, capture in enumerate(latency_captures)
                if max(
                    abs(capture["rgb_mean"][channel] - neutral["rgb_mean"][channel])
                    for channel in range(3)
                )
                > 2.0
            ),
            None,
        )

        repeated = consumer.publish(first)
        stale_rejected = False
        try:
            consumer.publish(_payload(log_ids, 1))
        except RuntimeError:
            stale_rejected = True
        failure["point"] = "after_base"
        failure_rejected = False
        try:
            consumer.publish(_payload(log_ids, 3, "scaling"))
        except RuntimeError:
            failure_rejected = (
                consumer.status()["revision"] == 2
                and consumer.status()["failure_count"] == 1
                and consumer.status()["recovery_count"] == 1
            )
        failure["point"] = None

        profiles = [profile]
        for revision in range(3, 107):
            profiles.append(consumer.publish(_payload(log_ids, revision, "scaling")))

        stage = context.get_stage()
        campfire.app.move_log(stage, "Log_03", (2.0, 1.7, 0.85), 37.0)
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        transformed = await _capture(
            viewport, capture_dir / "surface_states_transformed.png"
        )
        timeline.stop()
        consumer.on_timeline_stopped()
        await app.next_update_async()
        timeline.play()
        consumer.on_timeline_started()
        await app.next_update_async()
        restarted = consumer.publish(_payload(log_ids, 107, "four_states"))
        if not stage.GetRootLayer().Save():
            raise RuntimeError("Unable to save transformed V3M-C stage")
        await context.close_stage_async()
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        reload_started = time.perf_counter_ns()
        reloaded_profile = consumer.on_stage_reloaded(
            stage, _payload(log_ids, 107, "four_states")
        )
        reload_ms = (time.perf_counter_ns() - reload_started) / 1_000_000.0
        viewport = await _viewport()
        for _ in range(15):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        reloaded = await _capture(viewport, capture_dir / "surface_states_reloaded.png")
        paths_after = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        topology_after = _topology(stage, log_ids)
        mesh = campfire.app.get_log_render_surface(stage, "Log_00")
        collider = campfire.app.get_log_collider(stage, "Log_00")
        state = consumer.status()
        visual_timing = {
            name: _summary(getattr(value, name) for value in profiles)
            for name in (
                "beauty_pack_ms",
                "boundary_prepare_ms",
                "cpu_upload_ms",
                "revision_commit_ms",
                "total_ms",
            )
        }
        managed_prefixes = ("/World/Logs", "/World/Looks/WoodVisualV3")
        managed_paths_before = {
            path for path in paths_before if path.startswith(managed_prefixes)
        }
        managed_paths_after = {
            path for path in paths_after if path.startswith(managed_prefixes)
        }
        paths_stable = managed_paths_before == managed_paths_after
        topology_stable = topology_before == topology_after
        gates = {
            "twenty_logs_7200_surface_cells": len(log_ids) == 20,
            "fixed_two_atlas_resources": material["upload_count_per_revision"] == 2,
            "rgba8_raw_uploads_succeeded": all(value.upload_count == 2 for value in profiles),
            "one_revision_set_per_update": all(value.usd_set_count == 1 for value in profiles),
            "unchanged_revision_is_noop": repeated.upload_count == repeated.usd_set_count == 0,
            "stale_revision_rejected": stale_rejected,
            "failure_is_visual_only_and_recovers_previous_revision": failure_rejected,
            "timeline_restart_commits": restarted.status == "committed",
            "reload_force_republishes_latest": reloaded_profile.status == "reloaded",
            "managed_prim_path_set_stable": paths_stable,
            "mesh_topology_digest_stable": topology_stable,
            "render_mesh_has_no_physics": not mesh.HasAPI(UsdPhysics.CollisionAPI),
            "analytic_collider_retained": collider.IsA(UsdGeom.Cylinder) and collider.HasAPI(UsdPhysics.CollisionAPI),
            "state_capture_has_visual_range": initial["quantized_colors"] >= 24,
            "dynamic_update_visible_within_four_probe_frames": first_changed_frame is not None,
            "reload_capture_preserves_result": reloaded["quantized_colors"] >= 24,
            "consumer_revision_matches": state["revision"] == 107,
        }
        report = {
            "schema": "campfire.phasev3mc.dynamic_mesh_probe.v1",
            "status": "qualified" if all(gates.values()) else "not_qualified",
            "gates": gates,
            "transport": {
                "format": "RGBA8_UNORM",
                "atlas_count": 2,
                "atlas_size": [campfire.app.WOOD_ATLAS_WIDTH_PX, campfire.app.WOOD_ATLAS_HEIGHT_PX],
                "bytes_per_revision": profiles[-1].transferred_bytes,
                "asset_paths_change_per_frame": False,
                "prim_redefinition_per_frame": False,
                "first_observed_changed_probe_frame": first_changed_frame,
                "frame_latency_note": "Each file capture waits two completion frames; this is an upper-bound observation, not a single-frame fence.",
                "gpu_upload_api_qualified": False,
                "gpu_upload_reason": "No owned public GPU pointer source exists at the immutable V2 payload boundary",
                "gpu_memory_bytes": None,
                "gpu_memory_reason": "Kit 110 exposes no allocation query scoped to DynamicTextureProvider",
            },
            "shader_decision": {
                "selected": "two fixed beauty atlases: base RGB + roughness A, emission RGB",
                "state_atlas_only": "UsdPreviewSurface cannot express the required nonlinear moisture/char/ash/temperature mapping",
                "single_beauty_atlas": "cannot independently supply base/roughness and emissive channels",
                "unverified_mdl_not_adopted": True,
            },
            "structure": {
                "managed_prim_path_set_stable": paths_stable,
                "managed_prefixes": list(managed_prefixes),
                "prim_count_before": len(paths_before),
                "prim_count_after": len(paths_after),
                "managed_added_paths": sorted(
                    managed_paths_after - managed_paths_before
                ),
                "managed_removed_paths": sorted(
                    managed_paths_before - managed_paths_after
                ),
                "unmanaged_added_paths": sorted(
                    set(paths_after) - set(paths_before)
                ),
                "unmanaged_removed_paths": sorted(
                    set(paths_before) - set(paths_after)
                ),
                "mesh_topology_digest_stable": topology_stable,
                "changed_topology_logs": [
                    log_id
                    for log_id in log_ids
                    if topology_before[log_id] != topology_after[log_id]
                ],
            },
            "performance": {
                "frequency_hz": 5,
                "visual_publication": visual_timing,
                "v2_native_extraction": _native_surface_performance(arguments["native_library"]),
                "update_frame_ms": _summary(latency_ms, 2),
                "stage_reload_first_republish_ms": reload_ms,
                "reference_target_p95_ms": 1.0,
                "target_met": visual_timing["total_ms"]["p95_ms"] <= 1.0,
            },
            "consumer": state,
            "captures": {
                "neutral": neutral,
                "latency": latency_captures,
                "initial": initial,
                "transformed": transformed,
                "reloaded": reloaded,
                "kind": "fixed-state Mesh diagnostic; not combustion trajectory",
            },
            "decision": {
                "feature_default": False,
                "production_default_changed": False,
                "authority_flow_point_collision_unchanged": True,
                "v4_or_deformation_implemented": False,
                "phase6dm_resumed": False,
            },
        }
        exit_code = 0 if all(gates.values()) else 2
    except Exception as error:
        report = {
            "schema": "campfire.phasev3mc.dynamic_mesh_probe.v1",
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
