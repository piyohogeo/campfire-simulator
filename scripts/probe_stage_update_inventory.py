"""Inventory Kit StageUpdate nodes and exercise timeline transport.

This default-off Phase 6CP probe opens an already-authored Resident Point
scene without composing an application owner.  It records the public
StageUpdate graph before and after PLAY so the normal and benchmark app
surfaces can be compared without modifying the input layer.
"""

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


def _serialise_nodes(stage_update) -> list[dict]:
    nodes = []
    for node in stage_update.get_stage_update_nodes():
        nodes.append(
            {
                "index": int(node["index"]),
                "name": str(node["name"]),
                "enabled": bool(node["enabled"]),
                "order": int(node["order"]),
                "parallel": bool(node.get("parallel", False)),
            }
        )
    return nodes


async def _run():
    settings = carb.settings.get_settings()
    scene = Path(settings.get_as_string("/phase6cp/scene"))
    output = Path(settings.get_as_string("/phase6cp/output"))
    app_label = settings.get_as_string("/phase6cp/appLabel")
    if not scene.is_file():
        raise RuntimeError(f"Phase 6CP scene is missing: {scene}")

    context = omni.usd.get_context()
    if not await context.open_stage_async(str(scene)):
        raise RuntimeError(f"Phase 6CP scene did not open: {scene}")
    for _ in range(4):
        await omni.kit.app.get_app().next_update_async()

    stage_update = omni.stageupdate.get_stage_update_interface()
    nodes_before = _serialise_nodes(stage_update)
    node_change_count = {"value": 0}

    def observe_node_change():
        node_change_count["value"] += 1

    node_change_subscription = stage_update.subscribe_to_stage_update_node_change_events(
        observe_node_change
    )
    timeline = omni.timeline.get_timeline_interface()
    event_names = {
        int(omni.timeline.TimelineEventType.PLAY): "play",
        int(omni.timeline.TimelineEventType.PAUSE): "pause",
        int(omni.timeline.TimelineEventType.STOP): "stop",
        int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED): "tick",
    }
    events = []

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

    timeline_subscription = (
        timeline.get_timeline_event_stream().create_subscription_to_pop(
            observe_timeline, 0, "Campfire Phase 6CP StageUpdate inventory"
        )
    )
    try:
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.clear_zoom()
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
                    "stopped": bool(timeline.is_stopped()),
                }
            )
        nodes_after = _serialise_nodes(stage_update)
    finally:
        timeline.pause()
        timeline.commit()
        timeline_subscription = None
        node_change_subscription = None

    report = {
        "schema_version": 1,
        "phase": "phase6cp",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_label": app_label,
        "scene": str(scene),
        "stage_update": {
            "nodes_before_play": nodes_before,
            "nodes_after_play": nodes_after,
            "node_change_event_count": node_change_count["value"],
        },
        "timeline": {
            "events": events,
            "samples": samples,
            "advanced_from_zero": any(sample["time_s"] > 0.0 for sample in samples),
            "remained_playing": all(sample["playing"] for sample in samples),
        },
        "scope": {
            "default_off": True,
            "resident_owner_composed": False,
            "production_changed": False,
            "input_layer_mutated": False,
            "stage_update_nodes_disabled": [],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0)


asyncio.ensure_future(_run())
