"""Capture public carb profiler events around Resident Point publications.

The probe runs only with the existing default-off Resident Point translation
qualification.  It temporarily enables capture mask 1, restores the previous
mask, and records completed-frame profiler events without changing production
scene structure or publication contracts.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import carb
import carb.profiler
import omni.flowusd._flowusd as _flowusd
import omni.kit.app
import omni.usd

import campfire.app


MASK = 1
TRIGGER_REVISION = 344
MARKER_PREFIX = "CampfirePhase6DEFrame"
INTEREST_TERMS = (
    "fabric",
    "flow",
    "hydra",
    "notice",
    "physx",
    "stage",
    "usd",
)


def _is_flow_specific_zone(name: str) -> bool:
    """Exclude unrelated names such as Workflow* from Flow-zone detection."""

    lowered = name.lower()
    return (
        "flowusd" in lowered
        or "omni.flowusd" in lowered
        or lowered.startswith("flow ")
    )


def _write(path: Path, report: dict) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _serialise_event(event: dict) -> dict:
    return {
        "name": str(event.get("name", "")),
        "thread_id": int(event.get("thread_id", 0)),
        "start_time": int(event.get("start_time", 0)),
        "duration_ms": float(event.get("duration", 0.0)),
        "indent": int(event.get("indent", 0)),
    }


def _profile_snapshot(snapshot) -> dict:
    events = tuple(snapshot.get_profile_events())
    serialised = [_serialise_event(event) for event in events]
    selected = [
        event
        for event in serialised
        if any(term in event["name"].lower() for term in INTEREST_TERMS)
    ]
    totals = defaultdict(lambda: {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
    for event in serialised:
        item = totals[event["name"]]
        item["count"] += 1
        item["total_ms"] += event["duration_ms"]
        item["max_ms"] = max(item["max_ms"], event["duration_ms"])
    top_names = [
        {
            "name": name,
            "count": values["count"],
            "total_ms": values["total_ms"],
            "max_ms": values["max_ms"],
        }
        for name, values in sorted(
            totals.items(), key=lambda item: item[1]["total_ms"], reverse=True
        )[:100]
    ]
    return {
        "event_count": len(serialised),
        "main_thread_id": int(snapshot.get_main_thread_id()),
        "thread_ids": [int(value) for value in snapshot.get_profile_thread_ids()],
        "marker_events": [
            event for event in serialised if event["name"].startswith(MARKER_PREFIX)
        ],
        "selected_events": selected[:2000],
        "top_names": top_names,
    }


async def _wait_for_stage(context):
    for _ in range(3000):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        point = (
            stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            if stage is not None
            else None
        )
        if point and point.GetAttribute("campfire:residentRevision"):
            return stage
    raise RuntimeError("Phase 6DE Resident Point stage did not become ready")


async def _run() -> None:
    settings = carb.settings.get_settings()
    output_value = settings.get_as_string("/phase6de/flowProfileOutput")
    if not output_value:
        raise RuntimeError("Phase 6DE Flow profile output path is missing")
    output = Path(output_value)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "phase": "phase6de",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "records": [],
    }
    _write(output, report)

    profiler = carb.profiler.acquire_profiler_interface()
    monitor = carb.profiler.acquire_profile_monitor_interface()
    capture_mask_before = int(profiler.get_capture_mask())
    flow_interface = None
    try:
        context = omni.usd.get_context()
        stage = await _wait_for_stage(context)
        flow_interface = _flowusd.acquire_flowusd_interface()
        emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        last_layout_revision = int(
            emitter.GetAttribute("campfire:layoutRevision").Get()
        )
        moved = False
        changed_revision = None
        capture_enabled = False
        last_record_key = None

        for sample_index in range(3000):
            emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            revision_before = int(
                emitter.GetAttribute("campfire:residentRevision").Get()
            )
            if revision_before < 300:
                await omni.kit.app.get_app().next_update_async()
                continue
            if not capture_enabled:
                profiler.set_capture_mask(capture_mask_before | MASK)
                monitor.mark_frame_end()
                capture_enabled = True
            marker_name = f"{MARKER_PREFIX}.before_r{revision_before}"
            carb.profiler.begin(MASK, marker_name)
            carb.profiler.end(MASK)
            await omni.kit.app.get_app().next_update_async()

            stage = context.get_stage()
            if stage is None:
                continue
            emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            if not emitter or not emitter.IsValid():
                continue
            revision = int(emitter.GetAttribute("campfire:residentRevision").Get())
            layout_revision = int(
                emitter.GetAttribute("campfire:layoutRevision").Get()
            )
            layout_changed = layout_revision > last_layout_revision
            record_key = (revision, layout_revision)
            if 320 <= revision <= 390 and record_key != last_record_key:
                profile = _profile_snapshot(monitor.get_last_profile_events())
                report["records"].append(
                    {
                        "sample": sample_index,
                        "revision_before": revision_before,
                        "revision": revision,
                        "layout_revision": layout_revision,
                        "layout_changed": layout_changed,
                        "translation_triggered_before_frame": moved,
                        "active_blocks": int(
                            flow_interface.get_active_block_count()
                        ),
                        "profile": profile,
                    }
                )
                last_record_key = record_key

            if revision >= TRIGGER_REVISION and not moved:
                origin = campfire.app.get_log_world_position(
                    stage, campfire.app.PHASE3_DRY_LOG_ID
                )
                target = (origin[0], origin[1] + 0.02, origin[2])
                campfire.app.move_log(
                    stage, campfire.app.PHASE3_DRY_LOG_ID, target, 0.0
                )
                moved = True
            if layout_changed and moved and changed_revision is None:
                changed_revision = revision
            if changed_revision is not None and revision >= changed_revision + 3:
                break
            last_layout_revision = layout_revision
            _write(output, report)

        all_records = report["records"]
        changed_records = [
            record
            for record in all_records
            if record["layout_changed"]
            and record["translation_triggered_before_frame"]
        ]
        unchanged_records = [
            record for record in all_records if not record["layout_changed"]
        ]
        all_names = {
            event["name"]
            for record in all_records
            for event in record["profile"]["selected_events"]
        }
        gates = {
            "profile_records_captured": len(all_records) >= 4,
            "layout_changed_record_captured": bool(changed_records),
            "unchanged_records_captured": len(unchanged_records) >= 2,
            "frame_markers_correlate_records": all(
                any(
                    event["name"].startswith(
                        f"{MARKER_PREFIX}.before_r{record['revision_before']}"
                    )
                    for event in record["profile"]["marker_events"]
                )
                for record in all_records
            ),
            "no_direct_flow_specific_profiler_zone_observed": not any(
                _is_flow_specific_zone(name) for name in all_names
            ),
            "usd_change_processing_zone_observed": any(
                "notice" in name.lower() or "pendingusd" in name.lower()
                for name in all_names
            ),
            "flow_active_blocks_nonzero": any(
                record["active_blocks"] > 0 for record in all_records
            ),
        }
        report.update(
            {
                "status": "ok" if all(gates.values()) else "failed",
                "capture": {
                    "mask": MASK,
                    "capture_mask_before": capture_mask_before,
                    "capture_mask_during": (
                        int(profiler.get_capture_mask()) if capture_enabled else None
                    ),
                    "capture_mask_restored": None,
                    "trigger_revision": TRIGGER_REVISION,
                    "changed_revision": changed_revision,
                },
                "observed_selected_zone_names": sorted(all_names),
                "gates": gates,
                "scope": {
                    "default_off": True,
                    "flow_version": "110.0.0",
                    "profile_capture_overhead_excluded_from_performance_acceptance": True,
                    "profiler_durations_are_zone_observations_not_subscriber_registration": True,
                    "temporary_capture_mask_restored": True,
                    "production_changed": False,
                },
            }
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        carb.log_error(f"[phase6de-flow-profile] {type(error).__name__}: {error}")
    finally:
        profiler.set_capture_mask(capture_mask_before)
        report.setdefault("capture", {})["capture_mask_restored"] = int(
            profiler.get_capture_mask()
        )
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)
        _write(output, report)


asyncio.ensure_future(_run())
