"""Compare plain saved-stage playback before and after renderer attachment."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.stageupdate
import omni.timeline
import omni.usd


CAPTURE_RESOLUTION = (1280, 720)
CAMERA_PATH = "/World/Camera"


async def _play_case(name, timeline, set_case):
    timeline.set_current_time(0.0)
    timeline.set_auto_update(True)
    timeline.set_looping(True)
    timeline.commit()
    await omni.kit.app.get_app().next_update_async()
    set_case(name)
    timeline.play()
    timeline.commit()
    samples = []
    for index in range(12):
        await omni.kit.app.get_app().next_update_async()
        samples.append(
            {
                "sample": index + 1,
                "time_s": float(timeline.get_current_time()),
                "playing": bool(timeline.is_playing()),
                "stopped": bool(timeline.is_stopped()),
            }
        )
    await asyncio.sleep(0.25)
    for index in range(12, 24):
        await omni.kit.app.get_app().next_update_async()
        samples.append(
            {
                "sample": index + 1,
                "time_s": float(timeline.get_current_time()),
                "playing": bool(timeline.is_playing()),
                "stopped": bool(timeline.is_stopped()),
            }
        )
    set_case("teardown")
    timeline.pause()
    timeline.commit()
    await omni.kit.app.get_app().next_update_async()
    return {
        "name": name,
        "samples": samples,
        "remained_playing": all(sample["playing"] for sample in samples),
        "advanced_from_zero": any(sample["time_s"] > 0.0 for sample in samples),
    }


async def _run():
    settings = carb.settings.get_settings()
    scene = Path(settings.get_as_string("/phase6cr/scene")).resolve()
    output = Path(settings.get_as_string("/phase6cr/output")).resolve()
    probe_app = settings.get_as_string("/phase6cr/probeApp") or "unspecified"
    post_viewport_settle_frames = max(
        0, settings.get_as_int("/phase6cr/postViewportSettleFrames")
    )
    post_viewport_settle_seconds = max(
        0.0, settings.get_as_float("/phase6cr/postViewportSettleSeconds")
    )
    retry_after_stop = settings.get_as_bool("/phase6cr/retryAfterStop")
    if not scene.is_file():
        raise RuntimeError(f"Phase 6CR scene is missing: {scene}")
    context = omni.usd.get_context()
    opened, error = await context.open_stage_async(str(scene))
    if not opened or error:
        raise RuntimeError(f"Phase 6CR scene did not open: {error}")
    for _ in range(8):
        await omni.kit.app.get_app().next_update_async()
    viewport = None
    for _ in range(240):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await omni.kit.app.get_app().next_update_async()
    if viewport is None:
        raise RuntimeError("Phase 6CR has no active viewport")
    viewport.camera_path = CAMERA_PATH
    viewport.fill_frame = False
    viewport.resolution = CAPTURE_RESOLUTION
    timeline = omni.timeline.get_timeline_interface()
    active_case = "setup"
    events = []
    names = {
        int(omni.timeline.TimelineEventType.PLAY): "play",
        int(omni.timeline.TimelineEventType.PAUSE): "pause",
        int(omni.timeline.TimelineEventType.STOP): "stop",
        int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "tick",
    }

    def set_case(value):
        nonlocal active_case
        active_case = value

    def observe(event):
        name = names.get(int(event.type))
        if name is not None:
            events.append(
                {
                    "case": active_case,
                    "event": name,
                    "time_s": float(timeline.get_current_time()),
                    "playing": bool(timeline.is_playing()),
                    "stopped": bool(timeline.is_stopped()),
                }
            )

    subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
        observe, 0, "Campfire Phase 6CR plain renderer boundary"
    )
    try:
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.commit()
        await omni.kit.app.get_app().next_update_async()
        before = await _play_case("before_viewport_frame", timeline, set_case)
        started = time.perf_counter()
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        readiness = {
            "wall_seconds": round(time.perf_counter() - started, 4),
            "resolution": list(viewport.resolution),
        }
        set_case("viewport_settle")
        for _ in range(post_viewport_settle_frames):
            await omni.kit.app.get_app().next_update_async()
        if post_viewport_settle_seconds > 0.0:
            await asyncio.sleep(post_viewport_settle_seconds)
            await omni.kit.app.get_app().next_update_async()
        after = await _play_case("after_viewport_frame", timeline, set_case)
        retry = None
        if retry_after_stop:
            retry = await _play_case(
                "after_viewport_frame_retry", timeline, set_case
            )
    finally:
        set_case("teardown")
        timeline.pause()
        timeline.commit()
        subscription = None
    cases = [before, after]
    if retry is not None:
        cases.append(retry)
    for case in cases:
        case["stop_event_count"] = sum(
            event["case"] == case["name"] and event["event"] == "stop"
            for event in events
        )
    nodes = [
        {
            "index": int(node["index"]),
            "name": str(node["name"]),
            "enabled": bool(node["enabled"]),
            "order": int(node["order"]),
        }
        for node in omni.stageupdate.get_stage_update_interface().get_stage_update_nodes()
    ]
    gates = {
        "plain_stage_only": True,
        "before_case_recorded": len(before["samples"]) == 24,
        "after_case_recorded": len(after["samples"]) == 24,
        "retry_case_recorded": retry is None or len(retry["samples"]) == 24,
        "viewport_frame_completed": (
            readiness["wall_seconds"] >= 0.0
            and len(readiness["resolution"]) == 2
            and all(component > 0 for component in readiness["resolution"])
        ),
        "all_stage_update_nodes_enabled": all(node["enabled"] for node in nodes),
    }
    report = {
        "schema_version": 1,
        "phase": "phase6cr",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": str(scene),
        "scope": {
            "default_off": True,
            "production_changed": False,
            "resident_owner_composed": False,
            "input_layer_mutated": False,
            "renderer_enabled": True,
            "probe_app": probe_app,
        },
        "viewport_readiness": readiness,
        "requested_resolution_retained": (
            readiness["resolution"] == list(CAPTURE_RESOLUTION)
        ),
        "post_viewport_settle": {
            "frames": post_viewport_settle_frames,
            "seconds": post_viewport_settle_seconds,
            "stop_event_count": sum(
                event["case"] == "viewport_settle" and event["event"] == "stop"
                for event in events
            ),
        },
        "cases": cases,
        "timeline_events": events,
        "stage_update_nodes": nodes,
        "gates": gates,
        "decision": {
            "plain_stage_stops_after_viewport_frame": (
                after["stop_event_count"] > 0 and not after["remained_playing"]
            ),
            "plain_stage_stops_on_retry": (
                retry is not None
                and retry["stop_event_count"] > 0
                and not retry["remained_playing"]
            ),
            "resident_owner_is_required_for_stop": None,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0 if all(gates.values()) else 1)


asyncio.ensure_future(_run())
