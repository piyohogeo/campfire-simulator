"""Measure one uninterrupted Resident/Flow playback across viewport and capture work."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.flowusd._flowusd as _flowusd
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd

import campfire.app


POINT_PATH = "/World/Flow/ResidentPointEmitter"
CAPTURE_RESOLUTION = (1280, 720)


async def _wait_for_stage(context):
    for _ in range(2400):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        if stage is not None and stage.GetPrimAtPath(POINT_PATH).IsValid():
            for _ in range(24):
                await omni.kit.app.get_app().next_update_async()
            return context.get_stage()
    raise RuntimeError("Phase 6CY Resident Point stage did not become ready")


async def _get_viewport():
    for _ in range(240):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            viewport.updates_enabled = False
            viewport.camera_path = campfire.app.CAMERA_PATH
            viewport.fill_frame = False
            viewport.resolution = CAPTURE_RESOLUTION
            return viewport
        await omni.kit.app.get_app().next_update_async()
    raise RuntimeError("Phase 6CY has no active viewport")


def _stage_sample(context):
    stage = context.get_stage()
    if stage is None:
        return {"available": False, "root_layer": None, "point_valid": False}
    return {
        "available": True,
        "root_layer": str(stage.GetRootLayer().identifier),
        "point_valid": bool(stage.GetPrimAtPath(POINT_PATH).IsValid()),
    }


async def _sample_segment(
    name, count, timeline, context, flow_interface, samples
):
    for _ in range(count):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        point = stage.GetPrimAtPath(POINT_PATH) if stage is not None else None
        revision_attribute = (
            point.GetAttribute("campfire:residentRevision")
            if point is not None and point.IsValid()
            else None
        )
        samples.append(
            {
                "sample": len(samples) + 1,
                "segment": name,
                "time_s": float(timeline.get_current_time()),
                "playing": bool(timeline.is_playing()),
                "stopped": bool(timeline.is_stopped()),
                "revision": (
                    int(revision_attribute.Get())
                    if revision_attribute is not None
                    and revision_attribute.IsValid()
                    and revision_attribute.HasAuthoredValueOpinion()
                    else None
                ),
                "active_blocks": int(flow_interface.get_active_block_count()),
                "stage": _stage_sample(context),
            }
        )


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6cy/output")).resolve()
    capture_path = Path(settings.get_as_string("/phase6cy/capture")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.unlink(missing_ok=True)
    context = omni.usd.get_context()
    await _wait_for_stage(context)
    viewport = await _get_viewport()
    timeline = omni.timeline.get_timeline_interface()
    flow_interface = _flowusd.acquire_flowusd_interface()
    samples = []
    events = []
    active_segment = "setup"
    event_names = {
        int(omni.timeline.TimelineEventType.PLAY): "play",
        int(omni.timeline.TimelineEventType.PAUSE): "pause",
        int(omni.timeline.TimelineEventType.STOP): "stop",
        int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "tick",
    }

    def observe(event):
        name = event_names.get(int(event.type))
        if name is not None:
            events.append(
                {
                    "segment": active_segment,
                    "event": name,
                    "time_s": float(timeline.get_current_time()),
                    "playing": bool(timeline.is_playing()),
                    "stopped": bool(timeline.is_stopped()),
                }
            )

    subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
        observe, 0, "Campfire Phase 6CY continuous renderer boundary"
    )
    capture = None
    viewport_wait = None
    exit_code = 1
    report = None
    try:
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.set_auto_update(True)
        timeline.set_looping(True)
        timeline.commit()
        await omni.kit.app.get_app().next_update_async()
        stage_before = _stage_sample(context)

        active_segment = "viewport_updates_disabled"
        timeline.play()
        timeline.commit()
        await _sample_segment(
            active_segment, 24, timeline, context, flow_interface, samples
        )

        active_segment = "after_updates_enabled_frame"
        viewport.updates_enabled = True
        started = time.perf_counter()
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        viewport_wait = {
            "wall_seconds": round(time.perf_counter() - started, 4),
            "resolution": list(viewport.resolution),
        }
        await _sample_segment(
            active_segment, 24, timeline, context, flow_interface, samples
        )

        active_segment = "after_capture_callback"
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
        await _sample_segment(
            active_segment, 24, timeline, context, flow_interface, samples
        )
        stage_after = _stage_sample(context)

        measured_events = [event for event in events if event["segment"] != "setup"]
        roots = {
            sample["stage"]["root_layer"]
            for sample in samples
            if sample["stage"]["root_layer"] is not None
        }
        revisions = [
            sample["revision"] for sample in samples if sample["revision"] is not None
        ]
        segments = {
            name: [sample for sample in samples if sample["segment"] == name]
            for name in (
                "viewport_updates_disabled",
                "after_updates_enabled_frame",
                "after_capture_callback",
            )
        }
        gates = {
            "all_three_segments_recorded": all(
                len(segment_samples) == 24
                for segment_samples in segments.values()
            ),
            "viewport_frame_completed": (
                viewport_wait["resolution"] == list(CAPTURE_RESOLUTION)
            ),
            "capture_callback_completed": bool(
                capture["completed"] and capture["file_written"]
            ),
            "stage_available_for_all_samples": all(
                sample["stage"]["available"] and sample["stage"]["point_valid"]
                for sample in samples
            ),
            "single_root_layer_observed": len(roots) == 1,
            "revision_samples_monotonic": revisions == sorted(revisions),
        }
        continuous_play = all(sample["playing"] for sample in samples)
        no_stop_or_pause = not any(
            event["event"] in {"stop", "pause"} for event in measured_events
        )
        report = {
            "schema_version": 1,
            "phase": "phase6cy",
            "status": "ok" if all(gates.values()) else "failed",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "default_off": True,
                "production_changed": False,
                "flow_version": "110.0.0",
                "resident_point_application_enabled": True,
                "fixed_resolution": list(CAPTURE_RESOLUTION),
                "single_play_without_probe_pause_or_time_reset": True,
            },
            "stage_before": stage_before,
            "stage_after": stage_after,
            "viewport_wait": viewport_wait,
            "capture": capture,
            "samples": samples,
            "timeline_events": events,
            "segments": {
                name: {
                    "sample_count": len(segment_samples),
                    "all_playing": all(
                        sample["playing"] for sample in segment_samples
                    ),
                    "time_start_s": segment_samples[0]["time_s"],
                    "time_end_s": segment_samples[-1]["time_s"],
                    "revision_start": segment_samples[0]["revision"],
                    "revision_end": segment_samples[-1]["revision"],
                    "active_blocks_peak": max(
                        sample["active_blocks"] for sample in segment_samples
                    ),
                }
                for name, segment_samples in segments.items()
            },
            "observation": {
                "continuous_play": continuous_play,
                "no_stop_or_pause_during_measurement": no_stop_or_pause,
                "timeline_continuity_qualified": (
                    continuous_play and no_stop_or_pause
                ),
                "active_blocks_peak": max(
                    sample["active_blocks"] for sample in samples
                ),
                "root_layers": sorted(roots),
            },
            "gates": gates,
        }
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        exit_code = 0 if all(gates.values()) else 1
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": "phase6cy",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6cy] {type(error).__name__}: {error}")
    finally:
        active_segment = "teardown"
        timeline.pause()
        timeline.commit()
        viewport.updates_enabled = True
        subscription = None
        _flowusd.release_flowusd_interface(flow_interface)
        settings.set("/app/fastShutdown", True)
        omni.kit.app.get_app().post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run())
