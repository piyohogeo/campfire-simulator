"""Probe the extension-owned interactive Resident Point timeline lifecycle."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.stageupdate
import omni.timeline
import omni.usd


POINT_PATH = "/World/Flow/ResidentPointEmitter"


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6cp/output"))
    context = omni.usd.get_context()
    stage = None
    for _ in range(2400):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        if stage is not None and stage.GetPrimAtPath(POINT_PATH).IsValid():
            break
    if stage is None or not stage.GetPrimAtPath(POINT_PATH).IsValid():
        raise RuntimeError("Phase 6CP interactive Point stage did not become ready")
    # The Point Prim is authored before the owner and interactive subscriptions.
    # Allow the remainder of extension initialization to finish.
    for _ in range(24):
        await omni.kit.app.get_app().next_update_async()

    timeline = omni.timeline.get_timeline_interface()
    revision_attribute = stage.GetPrimAtPath(POINT_PATH).GetAttribute(
        "campfire:residentRevision"
    )
    revision_before = int(revision_attribute.Get())
    events = []
    event_names = {
        int(omni.timeline.TimelineEventType.PLAY): "play",
        int(omni.timeline.TimelineEventType.PAUSE): "pause",
        int(omni.timeline.TimelineEventType.STOP): "stop",
        int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "tick",
    }

    def observe_timeline(event):
        name = event_names.get(int(event.type))
        if name is not None:
            events.append(
                {
                    "event": name,
                    "time_s": float(timeline.get_current_time()),
                    "playing": bool(timeline.is_playing()),
                    "stopped": bool(timeline.is_stopped()),
                }
            )

    subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
        observe_timeline, 0, "Campfire Phase 6CP interactive lifecycle"
    )
    try:
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.set_auto_update(True)
        timeline.set_looping(True)
        timeline.commit()
        await omni.kit.app.get_app().next_update_async()
        timeline.play()
        timeline.commit()
        samples = []
        for update_index in range(12):
            await omni.kit.app.get_app().next_update_async()
            samples.append(
                {
                    "update": update_index + 1,
                    "time_s": float(timeline.get_current_time()),
                    "playing": bool(timeline.is_playing()),
                    "revision": int(revision_attribute.Get()),
                }
            )
        await asyncio.sleep(0.25)
        for update_index in range(12, 24):
            await omni.kit.app.get_app().next_update_async()
            samples.append(
                {
                    "update": update_index + 1,
                    "time_s": float(timeline.get_current_time()),
                    "playing": bool(timeline.is_playing()),
                    "revision": int(revision_attribute.Get()),
                }
            )
        revision_after = int(revision_attribute.Get())
    finally:
        timeline.pause()
        timeline.commit()
        subscription = None

    nodes = [
        {
            "index": int(node["index"]),
            "name": str(node["name"]),
            "enabled": bool(node["enabled"]),
            "order": int(node["order"]),
        }
        for node in omni.stageupdate.get_stage_update_interface().get_stage_update_nodes()
    ]
    report = {
        "schema_version": 1,
        "phase": "phase6cp",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "case": "extension_interactive_lifecycle",
        "timeline": {
            "events": events,
            "samples": samples,
            "remained_playing": all(sample["playing"] for sample in samples),
            "advanced_from_zero": any(sample["time_s"] > 0.0 for sample in samples),
            "stop_event_count": sum(event["event"] == "stop" for event in events),
        },
        "owner_evidence": {
            "point_revision_before": revision_before,
            "point_revision_after": revision_after,
            "interactive_step_published": revision_after > revision_before,
        },
        "stage_update_nodes": nodes,
        "scope": {
            "default_off": True,
            "production_changed": False,
            "capture_harness_enabled": False,
            "renderer_enabled": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0)


asyncio.ensure_future(_run())
