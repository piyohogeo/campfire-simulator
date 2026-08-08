"""Exercise the public carb profile monitor with a reversible custom zone."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import carb.profiler
import omni.kit.app


MASK = 1
ZONE_NAME = "CampfirePhase6DEProfileMonitorProbe"
INTEREST_TERMS = ("campfire", "change", "flow", "notice", "stage", "usd")


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _matching_events(events: tuple) -> list[dict]:
    matches = []
    for event in events:
        serialised = _json_value(event)
        searchable = json.dumps(serialised, ensure_ascii=False).lower()
        if any(term in searchable for term in INTEREST_TERMS):
            matches.append(serialised)
    return matches[:500]


def _emit_probe_zone(name: str) -> None:
    carb.profiler.begin(MASK, name)
    deadline = time.perf_counter_ns() + 500_000
    while time.perf_counter_ns() < deadline:
        pass
    carb.profiler.end(MASK)


def _snapshot_record(label: str, snapshot) -> dict:
    events = tuple(snapshot.get_profile_events())
    custom_events = [
        _json_value(event)
        for event in events
        if ZONE_NAME.lower()
        in json.dumps(_json_value(event), ensure_ascii=False).lower()
    ]
    return {
        "label": label,
        "main_thread_id": int(snapshot.get_main_thread_id()),
        "thread_ids": [
            int(value) for value in snapshot.get_profile_thread_ids()
        ],
        "event_count": len(events),
        "event_keys": sorted(
            {
                str(key)
                for event in events
                if isinstance(event, dict)
                for key in event
            }
        ),
        "custom_events": custom_events,
        "matching_events": _matching_events(events),
    }


async def _run() -> None:
    settings = carb.settings.get_settings()
    output_value = settings.get_as_string("/phase6de/monitorOutput")
    if not output_value:
        raise RuntimeError("Phase 6DE monitor output path is missing")
    output = Path(output_value)
    app = omni.kit.app.get_app()
    profiler = carb.profiler.acquire_profiler_interface()
    monitor = carb.profiler.acquire_profile_monitor_interface()
    capture_mask_before = int(profiler.get_capture_mask())
    report = {
        "schema_version": 1,
        "phase": "phase6de",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        profiler.set_capture_mask(capture_mask_before | MASK)
        monitor.mark_frame_end()
        _emit_probe_zone(f"{ZONE_NAME}.ExplicitMark")
        monitor.mark_frame_end()
        explicit_record = _snapshot_record(
            "explicit_mark", monitor.get_last_profile_events()
        )
        _emit_probe_zone(f"{ZONE_NAME}.ApplicationUpdate")
        await app.next_update_async()
        update_record = _snapshot_record(
            "application_update", monitor.get_last_profile_events()
        )
        records = [explicit_record, update_record]
        custom_events = [
            event for record in records for event in record["custom_events"]
        ]
        report.update(
            {
                "status": "ok" if custom_events else "failed",
                "capture": {
                    "mask": MASK,
                    "capture_mask_before": capture_mask_before,
                    "capture_mask_during": int(profiler.get_capture_mask()),
                    "capture_mask_restored": None,
                    "custom_zone_name": ZONE_NAME,
                    "custom_events": custom_events,
                    "snapshots": records,
                },
                "scope": {
                    "default_off": True,
                    "stage_opened": False,
                    "stage_mutated": False,
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
        carb.log_error(f"[phase6de-monitor] {type(error).__name__}: {error}")
    finally:
        profiler.set_capture_mask(capture_mask_before)
        report.setdefault("capture", {})["capture_mask_restored"] = int(
            profiler.get_capture_mask()
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        settings.set("/app/fastShutdown", True)
        app.post_uncancellable_quit(0)


asyncio.ensure_future(_run())
