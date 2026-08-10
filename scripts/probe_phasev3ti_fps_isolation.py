"""Measure the existing visible viewport for Phase V3T-I.

This probe deliberately creates no RenderProduct, HydraTexture, capture, or encoder.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from pxr import Gf, Usd, UsdGeom, UsdLux


MAX_READS = 50000


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3ti/output")).resolve(),
        "condition": settings.get_as_string("/phasev3ti/condition"),
        "width": settings.get_as_int("/phasev3ti/width"),
        "height": settings.get_as_int("/phasev3ti/height"),
        "warmup_seconds": settings.get_as_float("/phasev3ti/warmupSeconds"),
        "measure_seconds": settings.get_as_float("/phasev3ti/measureSeconds"),
        "run": settings.get_as_int("/phasev3ti/run"),
    }


def _camera(stage):
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(35.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(7.8, -7.8, 5.8), Gf.Vec3d(0.0, 0.0, 1.15), Gf.Vec3d(0, 0, 1))
    transform = camera.GetPrim().GetAttribute("xformOp:transform")
    if not transform:
        transform = UsdGeom.Xformable(camera).MakeMatrixXform().GetAttr()
    transform.Set(view.GetInverse())
    return camera


def _build_empty_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")
    _camera(stage)
    light = UsdLux.DistantLight.Define(stage, "/World/KeyLight")
    light.CreateIntensityAttr(1200.0)
    light.CreateAngleAttr(0.53)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.SetEndTimeCode(1000000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("unable to save empty Phase V3T-I stage")
    return stage


def _build_campfire_stage(path, flow_mode):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    import campfire.app
    from campfire.app.flow_scene import populate_flow_scene

    populate_flow_scene(stage)
    stage.RemovePrim("/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Logs")
    for slot in range(20):
        row, column = divmod(slot, 5)
        campfire.app.create_log(
            stage,
            campfire.app.LogSpec(
                f"Log_{slot:02d}", ((column - 2) * 1.15, (row - 1.5) * 1.05, 0.42),
                0.0 if row % 2 == 0 else 90.0, 0.22, 0.92,
            ),
            render_hierarchy=True,
            render_log_slot=slot,
        )
    log_ids = tuple(campfire.app.list_log_ids(stage))
    campfire.app.preauthor_wood_visual_v3(stage, log_ids)
    if flow_mode == "off":
        emitter = stage.GetPrimAtPath("/World/Flow/Emitter")
        if emitter and emitter.GetAttribute("enabled"):
            emitter.GetAttribute("enabled").Set(False)
    elif flow_mode == "simulation":
        # Preserve FlowSimulate and the emitter, but remove renderer-facing prims
        # before the stage is connected to Kit.
        stage.RemovePrim("/World/Flow/flowRender")
        stage.RemovePrim("/World/Flow/flowOffscreen")
    _camera(stage)
    stage.SetEndTimeCode(1000000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("unable to save campfire Phase V3T-I stage")
    return stage


def _build_stage(path, condition):
    if condition == "empty_rtx":
        return _build_empty_stage(path), "off"
    flow_mode = "off"
    if condition == "flow_simulation_only":
        flow_mode = "simulation"
    elif condition == "flow_volume":
        flow_mode = "volume"
    return _build_campfire_stage(path, flow_mode), flow_mode


def _frame_snapshot(viewport):
    info = viewport.frame_info
    return {
        "fps": float(info.get("fps", 0.0)),
        "frame_number": int(info.get("frame_number", -1)),
        "swh_frame_number": int(info.get("swh_frame_number", -1)),
        "subframe_count": int(info.get("subframe_count", 1)),
        "status": int(info.get("status", -1)),
        "resolution": list(info.get("resolution", ())),
    }


def _setting_snapshot():
    settings = carb.settings.get_settings()
    paths = (
        "/app/runLoops/main/rateLimitEnabled",
        "/app/runLoops/main/rateLimitFrequency",
        "/app/runLoops/main/syncToPresent",
        "/app/runLoops/present/rateLimitEnabled",
        "/app/runLoops/present/rateLimitFrequency",
        "/app/runLoops/present/syncToPresent",
        "/app/runLoops/rendering_0/rateLimitEnabled",
        "/app/runLoops/rendering_0/rateLimitFrequency",
        "/app/runLoops/rendering_0/syncToPresent",
        "/app/runLoopsGlobal/syncToPresent",
        "/app/vsync",
        "/renderer/vsync",
        "/persistent/app/viewport/defaults/tickRate",
        "/persistent/simulation/minFrameRate",
        "/rtx/reflections/enabled",
        "/rtx/indirectDiffuse/enabled",
        "/rtx/realtime/optixDenoiser/enabled",
        "/rtx/ecoMode/enabled",
        "/rtx/flow/enabled",
        "/app/window/hideUi",
    )
    return {path: settings.get(path) for path in paths}


async def _period(app, timeline, viewport, duration, record):
    read_times = []
    hud_fps = []
    frame_numbers = []
    swh_frame_numbers = []
    initial = _frame_snapshot(viewport)
    started_wall_ns = time.time_ns()
    started = time.perf_counter_ns()
    deadline = started + int(duration * 1e9)
    update_count = 0
    overflow = 0
    while time.perf_counter_ns() < deadline:
        await app.next_update_async()
        update_count += 1
        if record:
            if len(read_times) >= MAX_READS:
                overflow += 1
                continue
            now = time.perf_counter_ns()
            info = viewport.frame_info
            read_times.append(now)
            hud_fps.append(float(info.get("fps", 0.0)))
            frame_numbers.append(int(info.get("frame_number", -1)))
            swh_frame_numbers.append(int(info.get("swh_frame_number", -1)))
    ended = time.perf_counter_ns()
    ended_wall_ns = time.time_ns()
    return {
        "started_ns": started,
        "ended_ns": ended,
        "started_wall_ns": started_wall_ns,
        "ended_wall_ns": ended_wall_ns,
        "wall_seconds": (ended - started) / 1e9,
        "kit_update_count": update_count,
        "read_timestamps_ns": read_times,
        "hud_fps_values": hud_fps,
        "frame_numbers": frame_numbers,
        "swh_frame_numbers": swh_frame_numbers,
        "read_overflow": overflow,
        "initial_frame_info": initial,
        "final_frame_info": _frame_snapshot(viewport),
        "timeline_seconds_end": float(timeline.get_current_time()),
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    report = {"schema": "campfire.phasev3ti.visible-viewport-process.v1", "status": "error"}
    try:
        allowed = {
            "empty_rtx", "current_flow_off", "reflection_off", "indirect_off",
            "denoiser_on", "resolution_640x360", "resolution_1920x1080",
            "ui_hidden", "flow_simulation_only", "flow_volume",
        }
        if arguments["condition"] not in allowed:
            raise ValueError(f"invalid condition: {arguments['condition']}")
        stage_path = arguments["output"].with_suffix(".usda")
        stage, flow_mode = _build_stage(stage_path, arguments["condition"])
        prim_paths = [str(prim.GetPath()) for prim in stage.Traverse()]
        carb.settings.get_settings().set_bool("/rtx/flow/enabled", flow_mode != "off")
        await context.open_stage_async(str(stage_path))
        viewport = None
        for _ in range(360):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("active visible viewport unavailable")
        viewport.camera_path = "/World/Camera"
        viewport.fill_frame = False
        viewport.resolution = (arguments["width"], arguments["height"])
        # Some extensions author their defaults during startup. Reassert the
        # isolated process condition after startup and before warmup.
        carb.settings.get_settings().set_bool("/rtx/flow/enabled", flow_mode != "off")
        import omni.flowusd._flowusd as _flowusd

        flow_interface = _flowusd.acquire_flowusd_interface()
        timeline.set_current_time(0.0)
        timeline.play()
        warmup = await _period(app, timeline, viewport, arguments["warmup_seconds"], False)
        carb.settings.get_settings().set_bool("/rtx/flow/enabled", flow_mode != "off")
        await app.next_update_async()
        settings_before = _setting_snapshot()
        timeline_start = float(timeline.get_current_time())
        measured = await _period(app, timeline, viewport, arguments["measure_seconds"], True)
        settings_after = _setting_snapshot()
        measured["timeline_seconds_start"] = timeline_start
        measured["flow_active_blocks_final"] = int(flow_interface.get_active_block_count())
        report = {
            "schema": "campfire.phasev3ti.visible-viewport-process.v1",
            "status": "ok",
            "condition": arguments["condition"],
            "run": arguments["run"] + 1,
            "kit": "110.2",
            "flow": "110.0.0",
            "resolution": [arguments["width"], arguments["height"]],
            "log_count": 0 if arguments["condition"] == "empty_rtx" else 20,
            "flow_mode": flow_mode,
            "metric_contract": {
                "average_visible_fps": "visible ViewportAPI.frame_info frame_number delta / measurement wall time",
                "hud_fps": "public ViewportAPI.frame_info['fps']; smoothed HUD-compatible value",
                "display_present_fps_measured": False,
                "raw_visible_frame_timestamps_available": False,
                "frame_pacing_p95_p99_measured": False,
                "additional_render_product_created": False,
                "hydra_texture_created": False,
                "capture_or_encode_used": False,
            },
            "settings_before": settings_before,
            "settings_after": settings_after,
            "warmup": {"wall_seconds": warmup["wall_seconds"], "timeline_seconds_end": warmup["timeline_seconds_end"]},
            "measurement": measured,
            "stage": {
                "prim_count": len(prim_paths),
                "prim_paths_sha256": hashlib.sha256("\n".join(prim_paths).encode()).hexdigest(),
                "topology_changed_during_measurement": False,
            },
            "production_changed": False,
        }
    except Exception as error:
        report = {
            "schema": "campfire.phasev3ti.visible-viewport-process.v1",
            "status": "error",
            "condition": arguments.get("condition"),
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        timeline.stop()
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_arguments()))
