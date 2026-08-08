"""Isolate renderer and capture effects on the Resident Point timeline."""

from __future__ import annotations

import asyncio
import hashlib
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

import campfire.app


POINT_PATH = "/World/Flow/ResidentPointEmitter"
CAPTURE_RESOLUTION = (1280, 720)


async def _wait_for_point_stage(context):
    stage = None
    for _ in range(2400):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        if stage is not None and stage.GetPrimAtPath(POINT_PATH).IsValid():
            break
    if stage is None or not stage.GetPrimAtPath(POINT_PATH).IsValid():
        raise RuntimeError("Phase 6CQ interactive Point stage did not become ready")
    for _ in range(24):
        await omni.kit.app.get_app().next_update_async()
    return stage


async def _get_configured_viewport():
    viewport = None
    for _ in range(240):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await omni.kit.app.get_app().next_update_async()
    if viewport is None:
        raise RuntimeError("Phase 6CQ renderer probe has no active viewport")
    viewport.camera_path = campfire.app.CAMERA_PATH
    viewport.fill_frame = False
    viewport.resolution = CAPTURE_RESOLUTION
    return viewport


async def _wait_for_renderable_viewport(viewport):
    started = time.perf_counter()
    frame_waits = 0
    for frame_waits in range(1, 61):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
            break
        await omni.kit.app.get_app().next_update_async()
    else:
        raise RuntimeError(
            "Phase 6CQ viewport resolution did not settle: "
            f"{tuple(viewport.resolution)}"
        )
    return {
        "frame_wait_count": frame_waits,
        "wall_seconds": round(time.perf_counter() - started, 4),
        "resolution": list(viewport.resolution),
    }


async def _sample_updates(timeline, revision_attribute, count, samples, label):
    for _ in range(count):
        await omni.kit.app.get_app().next_update_async()
        samples.append(
            {
                "sample": len(samples) + 1,
                "segment": label,
                "time_s": float(timeline.get_current_time()),
                "playing": bool(timeline.is_playing()),
                "stopped": bool(timeline.is_stopped()),
                "revision": int(revision_attribute.Get()),
            }
        )


async def _run_case(
    name,
    timeline,
    revision_attribute,
    set_active_case,
    *,
    viewport=None,
    capture_path=None,
):
    timeline.set_current_time(0.0)
    timeline.set_auto_update(True)
    timeline.set_looping(True)
    timeline.commit()
    await omni.kit.app.get_app().next_update_async()
    samples = []
    revision_before = int(revision_attribute.Get())
    set_active_case(name)
    timeline.play()
    timeline.commit()
    await _sample_updates(timeline, revision_attribute, 12, samples, "before_capture")
    capture = None
    if capture_path is not None:
        capture_path.unlink(missing_ok=True)
        started = time.perf_counter()
        request = omni.kit.viewport.utility.capture_viewport_to_file(
            viewport, file_path=str(capture_path)
        )
        completed = bool(await request.wait_for_result(completion_frames=60))
        for _ in range(30):
            if capture_path.is_file():
                break
            await omni.kit.app.get_app().next_update_async()
        capture = {
            "requested": True,
            "completed": completed,
            "file_written": capture_path.is_file(),
            "wall_seconds": round(time.perf_counter() - started, 4),
            "bytes": capture_path.stat().st_size if capture_path.is_file() else 0,
            "sha256": (
                hashlib.sha256(capture_path.read_bytes()).hexdigest()
                if capture_path.is_file()
                else None
            ),
        }
    await asyncio.sleep(0.25)
    await _sample_updates(timeline, revision_attribute, 12, samples, "after_capture")
    result = {
        "name": name,
        "revision_before": revision_before,
        "revision_after": int(revision_attribute.Get()),
        "samples": samples,
        "remained_playing": all(sample["playing"] for sample in samples),
        "advanced_from_zero": any(sample["time_s"] > 0.0 for sample in samples),
        "capture": capture,
    }
    set_active_case("teardown")
    timeline.pause()
    timeline.commit()
    await omni.kit.app.get_app().next_update_async()
    return result


async def _run_disabled_node_case(
    node,
    stage_update,
    timeline,
    revision_attribute,
    set_active_case,
):
    case_name = f"disable_{node['name']}"
    stage_update.set_stage_update_node_enabled(int(node["index"]), False)
    try:
        result = await _run_case(
            case_name,
            timeline,
            revision_attribute,
            set_active_case,
        )
        result["disabled_node"] = str(node["name"])
        result["disabled_node_index"] = int(node["index"])
        result["disabled_during_case"] = not next(
            current["enabled"]
            for current in stage_update.get_stage_update_nodes()
            if int(current["index"]) == int(node["index"])
        )
        return result
    finally:
        stage_update.set_stage_update_node_enabled(int(node["index"]), True)


async def _run_all_nodes_disabled_case(
    nodes,
    stage_update,
    timeline,
    revision_attribute,
    set_active_case,
):
    for node in nodes:
        stage_update.set_stage_update_node_enabled(int(node["index"]), False)
    try:
        result = await _run_case(
            "disable_all_stage_update_nodes",
            timeline,
            revision_attribute,
            set_active_case,
        )
        result["disabled_nodes"] = [str(node["name"]) for node in nodes]
        result["all_disabled_during_case"] = not any(
            current["enabled"] for current in stage_update.get_stage_update_nodes()
        )
        return result
    finally:
        for node in reversed(nodes):
            stage_update.set_stage_update_node_enabled(int(node["index"]), True)


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6cq/output")).resolve()
    capture_path = Path(settings.get_as_string("/phase6cq/capture")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    context = omni.usd.get_context()
    stage = await _wait_for_point_stage(context)
    viewport = await _get_configured_viewport()
    timeline = omni.timeline.get_timeline_interface()
    stage_update = omni.stageupdate.get_stage_update_interface()
    nodes_before = [dict(node) for node in stage_update.get_stage_update_nodes()]
    revision_attribute = stage.GetPrimAtPath(POINT_PATH).GetAttribute(
        "campfire:residentRevision"
    )
    active_case = "setup"
    events = []
    event_names = {
        int(omni.timeline.TimelineEventType.PLAY): "play",
        int(omni.timeline.TimelineEventType.PAUSE): "pause",
        int(omni.timeline.TimelineEventType.STOP): "stop",
        int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "tick",
    }

    def set_active_case(value):
        nonlocal active_case
        active_case = value

    def observe_timeline(event):
        name = event_names.get(int(event.type))
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
        observe_timeline, 0, "Campfire Phase 6CQ renderer boundary"
    )
    try:
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.commit()
        await omni.kit.app.get_app().next_update_async()
        before_viewport = await _run_case(
            "renderer_before_viewport_frame",
            timeline,
            revision_attribute,
            set_active_case,
        )
        viewport_readiness = await _wait_for_renderable_viewport(viewport)
        viewport.updates_enabled = False
        updates_disabled = await _run_case(
            "viewport_updates_disabled",
            timeline,
            revision_attribute,
            set_active_case,
        )
        viewport.updates_enabled = True
        updates_reenabled = await _run_case(
            "viewport_updates_reenabled",
            timeline,
            revision_attribute,
            set_active_case,
        )
        rendered = await _run_case(
            "renderer_viewport",
            timeline,
            revision_attribute,
            set_active_case,
        )
        captured = await _run_case(
            "capture_callback",
            timeline,
            revision_attribute,
            set_active_case,
            viewport=viewport,
            capture_path=capture_path,
        )
        matrix = []
        for node in nodes_before:
            matrix.append(
                await _run_disabled_node_case(
                    node,
                    stage_update,
                    timeline,
                    revision_attribute,
                    set_active_case,
                )
            )
        all_disabled = await _run_all_nodes_disabled_case(
            nodes_before,
            stage_update,
            timeline,
            revision_attribute,
            set_active_case,
        )
    finally:
        set_active_case("teardown")
        timeline.pause()
        timeline.commit()
        subscription = None

    cases = [
        before_viewport,
        updates_disabled,
        updates_reenabled,
        rendered,
        captured,
        *matrix,
        all_disabled,
    ]
    for case in cases:
        case["stop_event_count"] = sum(
            event["case"] == case["name"] and event["event"] == "stop"
            for event in events
        )
    nodes_after = [
        {
            "index": int(node["index"]),
            "name": str(node["name"]),
            "enabled": bool(node["enabled"]),
            "order": int(node["order"]),
        }
        for node in stage_update.get_stage_update_nodes()
    ]
    matrix_candidates = [
        case["disabled_node"]
        for case in matrix
        if case["remained_playing"] and case["stop_event_count"] == 0
    ]
    gates = {
        "renderer_viewport_ready": viewport_readiness["resolution"]
        == list(CAPTURE_RESOLUTION),
        "pre_viewport_case_recorded": len(before_viewport["samples"]) == 24,
        "viewport_updates_disabled_case_recorded": len(
            updates_disabled["samples"]
        ) == 24,
        "viewport_updates_reenabled_case_recorded": len(
            updates_reenabled["samples"]
        ) == 24,
        "renderer_case_recorded": len(rendered["samples"]) == 24,
        "capture_case_recorded": len(captured["samples"]) == 24,
        "capture_callback_completed": bool(
            captured["capture"]["completed"]
            and captured["capture"]["file_written"]
        ),
        "renderer_stop_reproduced": rendered["stop_event_count"] == 1
        and not rendered["remained_playing"],
        "disable_matrix_complete": len(matrix) == len(nodes_before),
        "one_node_disabled_per_matrix_case": all(
            case["disabled_during_case"] for case in matrix
        ),
        "all_nodes_disabled_together": all_disabled[
            "all_disabled_during_case"
        ],
        "all_stage_update_nodes_restored": all(
            node["enabled"] for node in nodes_after
        ),
    }
    report = {
        "schema_version": 1,
        "phase": "phase6cq",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "production_changed": False,
            "normal_interactive_lifecycle": True,
            "renderer_enabled": True,
            "capture_harness_enabled": False,
            "capture_callback_count": 1,
        },
        "viewport_readiness": viewport_readiness,
        "cases": cases,
        "timeline_events": events,
        "stage_update_nodes_before": nodes_before,
        "stage_update_nodes_after": nodes_after,
        "gates": gates,
        "decision": {
            "renderer_or_viewport_requests_stop": rendered["stop_event_count"] > 0,
            "renderer_before_viewport_frame_requests_stop": (
                before_viewport["stop_event_count"] > 0
            ),
            "disabling_viewport_updates_preserves_play": (
                updates_disabled["remained_playing"]
                and updates_disabled["stop_event_count"] == 0
            ),
            "reenabling_viewport_updates_requests_stop": (
                updates_reenabled["stop_event_count"] > 0
            ),
            "capture_callback_requests_stop": captured["stop_event_count"] > 0,
            "all_stage_update_nodes_disabled_preserves_play": (
                all_disabled["remained_playing"]
                and all_disabled["stop_event_count"] == 0
            ),
            "disable_candidates_that_preserve_play": matrix_candidates,
            "requesting_node_isolated": len(matrix_candidates) == 1,
            "qualification_complete": len(matrix_candidates) == 1,
        },
    }
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0 if all(gates.values()) else 1)


asyncio.ensure_future(_run())
