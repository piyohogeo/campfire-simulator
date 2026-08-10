"""Enumerate public omni.stats nodes and correlate them with the visible viewport FPS HUD source."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.stats
import omni.timeline
import omni.usd
from pxr import Gf, Usd, UsdGeom


RESOLUTION = (1280, 720)


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3th/output")).resolve(),
        "warmup_seconds": settings.get_as_float("/phasev3th/warmupSeconds"),
        "sample_seconds": settings.get_as_float("/phasev3th/sampleSeconds"),
    }


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items() if key != "scopeId"}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return repr(value)


def _build_stage(path):
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
    camera = UsdGeom.Camera.Get(stage, "/World/Camera")
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(7.8, -7.8, 5.8), Gf.Vec3d(0.0, 0.0, 1.15), Gf.Vec3d(0, 0, 1))
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())
    stage.SetEndTimeCode(1000000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("unable to save Phase V3T-H inventory stage")


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    report = {"schema": "campfire.phasev3th.stats-inventory.v1", "status": "error"}
    try:
        stage_path = arguments["output"].with_suffix(".usda")
        _build_stage(stage_path)
        await context.open_stage_async(str(stage_path))
        viewport = None
        for _ in range(240):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("active viewport unavailable")
        viewport.camera_path = "/World/Camera"
        viewport.fill_frame = False
        viewport.resolution = RESOLUTION
        timeline.set_current_time(0.0)
        timeline.play()
        deadline = time.perf_counter() + arguments["warmup_seconds"]
        while time.perf_counter() < deadline:
            await app.next_update_async()

        stats = omni.stats.get_stats_interface()
        snapshots = []
        deadline = time.perf_counter() + arguments["sample_seconds"]
        next_sample = time.perf_counter()
        while time.perf_counter() < deadline:
            await app.next_update_async()
            now = time.perf_counter()
            if now < next_sample:
                continue
            scopes = []
            for scope in stats.get_scopes():
                nodes = stats.get_stats_nested(scope["scopeId"])
                scopes.append({
                    "scope": _json_value(scope),
                    "root_count": stats.get_stats_count(scope["scopeId"]),
                    "total_count": stats.get_total_stats_count(scope["scopeId"]),
                    "nodes": [_json_value(node) for node in nodes],
                })
            frame_info = _json_value(dict(viewport.frame_info))
            fps = float(viewport.fps)
            snapshots.append({
                "elapsed_seconds": arguments["sample_seconds"] - max(0.0, deadline - now),
                "viewport_fps": fps,
                "overlay_frame_time_ms": 1000.0 / fps if fps > 0.0 else 0.0,
                "viewport_frame_info": frame_info,
                "scopes": scopes,
            })
            next_sample = now + 0.5
        report = {
            "schema": "campfire.phasev3th.stats-inventory.v1",
            "status": "ok",
            "kit": "110.2",
            "flow": "110.0.0",
            "resolution": list(RESOLUTION),
            "log_count": 20,
            "warmup_seconds": arguments["warmup_seconds"],
            "sample_seconds": arguments["sample_seconds"],
            "public_api": "omni.stats.IStats.get_scopes/get_stats_nested + active ViewportAPI.fps/frame_info",
            "overlay_source_audit": "ViewportFPS reads round(update_info['viewport_api'].fps, 2) and derives Frame time as 1000 / FPS in bundled omni.kit.viewport.window 110.0.0.",
            "additional_render_product_created": False,
            "snapshots": snapshots,
        }
    except Exception as error:
        report = {
            "schema": "campfire.phasev3th.stats-inventory.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        timeline.stop()
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_arguments()))
