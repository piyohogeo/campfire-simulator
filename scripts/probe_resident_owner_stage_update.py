"""Isolate the StageUpdate node that rejects Resident-owner PLAY.

The Phase 6CP probe composes the production Resident backend, snapshot adapter,
Point sidecar, session, and owner over an already-authored stage.  One public
StageUpdate node may be disabled for the duration of the PLAY attempt and is
always restored before shutdown.  No owner step or USD publication is issued.
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

from campfire.app import (
    PHASE3_DRY_LOG_ID,
    PHASE3_WET_LOG_ID,
    ResidentNativeBackend,
    ResidentPointApplicationOwner,
    load_model_from_prim,
    resident_point_layout_for_logs,
)
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)


def _serialise_nodes(stage_update) -> list[dict]:
    return [
        {
            "index": int(node["index"]),
            "name": str(node["name"]),
            "enabled": bool(node["enabled"]),
            "order": int(node["order"]),
            "parallel": bool(node.get("parallel", False)),
        }
        for node in stage_update.get_stage_update_nodes()
    ]


async def _run():
    settings = carb.settings.get_settings()
    scene = Path(settings.get_as_string("/phase6cp/scene"))
    native_library = Path(settings.get_as_string("/phase6cp/nativeLibrary"))
    output = Path(settings.get_as_string("/phase6cp/output"))
    disabled_node_name = settings.get_as_string("/phase6cp/disabledNode")
    if not scene.is_file():
        raise RuntimeError(f"Phase 6CP scene is missing: {scene}")
    if not native_library.is_file():
        raise RuntimeError(f"Phase 6CP native library is missing: {native_library}")

    context = omni.usd.get_context()
    if not await context.open_stage_async(str(scene)):
        raise RuntimeError(f"Phase 6CP scene did not open: {scene}")
    for _ in range(4):
        await omni.kit.app.get_app().next_update_async()
    stage = context.get_stage()
    log_ids = (PHASE3_DRY_LOG_ID, PHASE3_WET_LOG_ID)
    models = tuple(
        load_model_from_prim(stage.GetPrimAtPath(f"/World/Logs/{log_id}"))
        for log_id in log_ids
    )
    backend = ResidentNativeBackend(
        models,
        native_library,
        dt_seconds=PHASE3_MODEL_DT_SECONDS,
        heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    )
    timeline = omni.timeline.get_timeline_interface()
    owner = ResidentPointApplicationOwner.compose(
        backend,
        stage,
        context,
        timeline,
        omni.kit.app.get_app().next_update_async,
        resident_point_layout_for_logs(stage, log_ids),
    )
    stage_update = omni.stageupdate.get_stage_update_interface()
    nodes_before = _serialise_nodes(stage_update)
    disabled_node = next(
        (node for node in nodes_before if node["name"] == disabled_node_name), None
    )
    if disabled_node_name and disabled_node is None:
        owner.close(discard_pending=True)
        raise RuntimeError(
            f"Phase 6CP StageUpdate node was not found: {disabled_node_name}"
        )

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

    timeline_subscription = (
        timeline.get_timeline_event_stream().create_subscription_to_pop(
            observe_timeline, 0, "Campfire Phase 6CP Resident owner isolation"
        )
    )
    disabled_index = disabled_node["index"] if disabled_node is not None else None
    close_result = None
    samples = []
    owner_status_after_play = None
    try:
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.clear_zoom()
        timeline.set_auto_update(True)
        timeline.set_looping(True)
        timeline.commit()
        await omni.kit.app.get_app().next_update_async()
        owner.start()
        if disabled_index is not None:
            stage_update.set_stage_update_node_enabled(disabled_index, False)
        nodes_during = _serialise_nodes(stage_update)

        timeline.play()
        timeline.commit()
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
        owner_status_after_play = owner.status()
    finally:
        timeline.pause()
        timeline.commit()
        if disabled_index is not None:
            stage_update.set_stage_update_node_enabled(disabled_index, True)
        timeline_subscription = None
        close_result = owner.close(discard_pending=True)

    report = {
        "schema_version": 1,
        "phase": "phase6cp",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": str(scene),
        "case": disabled_node_name or "all_enabled",
        "stage_update": {
            "nodes_before": nodes_before,
            "nodes_during": nodes_during,
            "nodes_after_restore": _serialise_nodes(stage_update),
            "disabled_node": disabled_node_name or None,
        },
        "timeline": {
            "events": events,
            "samples": samples,
            "advanced_from_zero": any(sample["time_s"] > 0.0 for sample in samples),
            "remained_playing": all(sample["playing"] for sample in samples),
            "stop_event_count": sum(event["event"] == "stop" for event in events),
        },
        "owner": {
            "composed": True,
            "started": True,
            "status_after_play": owner_status_after_play,
            "close": close_result,
            "steps_issued": 0,
        },
        "scope": {
            "default_off": True,
            "production_changed": False,
            "input_layer_mutated": False,
            "usd_publications_issued": 0,
            "disabled_node_restored": all(
                node["enabled"] for node in _serialise_nodes(stage_update)
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0)


asyncio.ensure_future(_run())
