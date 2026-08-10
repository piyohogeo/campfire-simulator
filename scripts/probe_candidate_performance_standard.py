"""Verify the effective temporary Candidate Performance startup standard."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility


PATHS = (
    "/rtx/rendermode",
    "/rtx/post/aa/op",
    "/rtx/post/dlss/execMode",
    "/rtx/rtpt/maxBounces",
    "/rtx/ambientOcclusion/enabled",
    "/rtx/flow/enabled",
    "/renderer/vsync",
    "/app/vsync",
    "/app/runLoops/main/rateLimitEnabled",
    "/app/runLoops/main/rateLimitFrequency",
    "/app/runLoops/main/syncToPresent",
    "/app/runLoops/present/rateLimitEnabled",
    "/app/runLoops/present/rateLimitFrequency",
    "/app/runLoops/present/syncToPresent",
    "/app/runLoops/rendering_0/rateLimitEnabled",
    "/app/runLoops/rendering_0/rateLimitFrequency",
    "/app/runLoops/rendering_0/syncToPresent",
    "/persistent/app/viewport/defaults/tickRate",
    "/persistent/simulation/minFrameRate",
    "/exts/campfire.app/woodVisualV3Enabled",
)


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return str(value)


async def _run():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/campfire/candidatePerformance/output")).resolve()
    app_kind = settings.get_as_string("/campfire/candidatePerformance/appKind")
    viewport = omni.kit.viewport.utility.get_active_viewport()
    viewport.resolution = (1280, 720)
    deadline = time.monotonic() + 60.0
    last_frame = int(dict(viewport.frame_info).get("frame_number", -1))
    consecutive = 0
    while consecutive < 8:
        await app.next_update_async()
        current = int(dict(viewport.frame_info).get("frame_number", -1))
        consecutive = consecutive + 1 if current > last_frame else 0
        last_frame = current
        if time.monotonic() > deadline:
            raise RuntimeError("visible viewport did not reach the 8-frame readiness gate")
    values = {path: _json_safe(settings.get(path)) for path in PATHS}
    final_frame_info = dict(viewport.frame_info)
    gates = {
        "rtx_real_time_2": values["/rtx/rendermode"] == "RealTimePathTracing",
        "dlss_enabled": values["/rtx/post/aa/op"] == 3,
        "dlss_performance": values["/rtx/post/dlss/execMode"] == 0,
        "max_bounces_2": values["/rtx/rtpt/maxBounces"] == 2,
        "output_resolution_1280x720": list(viewport.resolution) == [1280, 720],
    }
    report = {
        "schema": "campfire.candidate-performance-effective-settings.v1",
        "status": "ok" if all(gates.values()) else "failed",
        "app_kind": app_kind,
        "captured_unix_ns": time.time_ns(),
        "effective_settings": values,
        "output_resolution": list(viewport.resolution),
        "visible_frame_info": {
            "frame_number": int(final_frame_info.get("frame_number", -1)),
            "resolution": list(final_frame_info.get("resolution", viewport.resolution)),
            "status": int(final_frame_info.get("status", -1)),
        },
        "internal_render_resolution": None,
        "internal_render_resolution_status": "unavailable through public ViewportAPI/settings in Kit 110.2",
        "display_present_fps": None,
        "gates": gates,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run())
