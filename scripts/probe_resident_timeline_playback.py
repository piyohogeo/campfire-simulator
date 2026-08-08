"""Probe Kit timeline playback strategies on an already-authored scene.

This is a default-off diagnostic.  It does not compose Resident ownership or
mutate the input layer; it only compares the documented timeline commit paths.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.timeline
import omni.usd


async def _run():
    settings = carb.settings.get_settings()
    scene = Path(settings.get_as_string("/phase6co/scene"))
    output = Path(settings.get_as_string("/phase6co/output"))
    if not scene.is_file():
        raise RuntimeError(f"Phase 6CO scene is missing: {scene}")

    context = omni.usd.get_context()
    if not await context.open_stage_async(str(scene)):
        raise RuntimeError(f"Phase 6CO scene did not open: {scene}")
    await omni.kit.app.get_app().next_update_async()

    timeline = omni.timeline.get_timeline_interface()
    event_names = {
        int(omni.timeline.TimelineEventType.PLAY): "play",
        int(omni.timeline.TimelineEventType.PAUSE): "pause",
        int(omni.timeline.TimelineEventType.STOP): "stop",
        int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "tick",
        int(omni.timeline.TimelineEventType.AUTO_UPDATE_CHANGED): "auto_update_changed",
    }
    events = []
    strategy_name = {"value": "setup"}

    def observe(event):
        name = event_names.get(int(event.type))
        if name is not None:
            events.append(
                {
                    "strategy": strategy_name["value"],
                    "event": name,
                    "time_s": float(timeline.get_current_time()),
                    "playing": bool(timeline.is_playing()),
                    "stopped": bool(timeline.is_stopped()),
                    "auto_updating": bool(timeline.is_auto_updating()),
                }
            )

    subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
        observe, 0, "Campfire Phase 6CO timeline probe"
    )
    results = []
    try:
        strategies = (
            ("implicit_commit", False, False),
            ("explicit_commit", True, False),
            ("explicit_auto_update_and_commit", True, True),
        )
        for name, explicit_commit, explicit_auto_update in strategies:
            strategy_name["value"] = f"{name}:reset"
            timeline.stop()
            timeline.set_current_time(0.0)
            if explicit_auto_update:
                timeline.set_auto_update(True)
            if explicit_commit:
                timeline.commit()
            await omni.kit.app.get_app().next_update_async()

            event_start = len(events)
            strategy_name["value"] = name
            timeline.play()
            if explicit_commit:
                timeline.commit()
            samples = []
            for update_index in range(6):
                await omni.kit.app.get_app().next_update_async()
                samples.append(
                    {
                        "update": update_index + 1,
                        "time_s": float(timeline.get_current_time()),
                        "playing": bool(timeline.is_playing()),
                        "stopped": bool(timeline.is_stopped()),
                    }
                )
            results.append(
                {
                    "name": name,
                    "explicit_commit": explicit_commit,
                    "explicit_auto_update": explicit_auto_update,
                    "samples": samples,
                    "events": events[event_start:],
                    "advanced_from_zero": any(
                        sample["time_s"] > 0.0 for sample in samples
                    ),
                    "remained_playing": all(sample["playing"] for sample in samples),
                }
            )
    finally:
        subscription = None
        timeline.pause()
        timeline.commit()

    report = {
        "schema_version": 1,
        "phase": "phase6co",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": str(scene),
        "timeline": {
            "start_time_s": float(timeline.get_start_time()),
            "end_time_s": float(timeline.get_end_time()),
            "time_codes_per_second": float(timeline.get_time_codes_per_seconds()),
            "strategies": results,
        },
        "scope": {
            "default_off": True,
            "production_changed": False,
            "input_layer_mutated": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    omni.kit.app.get_app().post_quit(0)


asyncio.ensure_future(_run())
