"""Inventory runtime timing and subscriber surfaces in the fixed Kit build.

This Phase 6DE probe is deliberately read-only.  It does not open or edit a
stage, alter profiler capture masks, or change StageUpdate node enablement.  It
records the callable surface that the running application actually exposes so
we do not infer a Flow ingest timer from package names or private binaries.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import carb
import carb.profiler
import omni.activity.profiler
import omni.kit.app
import omni.stageupdate
import omni.flowusd
from omni.flowusd import _flowusd
from pxr import Tf, Usd


TIMING_TERMS = (
    "duration",
    "event",
    "ingest",
    "latency",
    "notice",
    "profile",
    "span",
    "subscriber",
    "timer",
    "trace",
    "zone",
)


def _safe_signature(value) -> str | None:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return None


def _members(value) -> list[dict]:
    result = []
    for name in sorted(member for member in dir(value) if not member.startswith("_")):
        try:
            member = getattr(value, name)
        except Exception as exc:  # pragma: no cover - defensive for native properties
            result.append({"name": name, "error": type(exc).__name__})
            continue
        callable_member = callable(member)
        result.append(
            {
                "name": name,
                "callable": callable_member,
                "signature": _safe_signature(member) if callable_member else None,
                "doc": (
                    inspect.getdoc(member)[:1200]
                    if callable_member and inspect.getdoc(member)
                    else None
                ),
                "type": type(member).__name__,
            }
        )
    return result


def _candidate_names(members: list[dict]) -> list[str]:
    return [
        member["name"]
        for member in members
        if any(term in member["name"].lower() for term in TIMING_TERMS)
    ]


def _surface(value) -> dict:
    members = _members(value)
    return {
        "type": type(value).__name__,
        "members": members,
        "member_names": [member["name"] for member in members],
        "timing_or_subscription_candidates": _candidate_names(members),
    }


def _stage_update_nodes(stage_update) -> list[dict]:
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


async def _run() -> None:
    settings = carb.settings.get_settings()
    output_value = settings.get_as_string("/phase6de/output")
    if not output_value:
        raise RuntimeError("Phase 6DE output path is missing")
    output = Path(output_value)

    app = omni.kit.app.get_app()
    extension_manager = app.get_extension_manager()
    enabled_extensions = {
        extension_id: bool(extension_manager.is_extension_enabled(extension_id))
        for extension_id in (
            "campfire.app",
            "omni.activity.profiler",
            "omni.flowusd",
            "omni.stageupdate",
        )
    }

    carb_profiler = carb.profiler.acquire_profiler_interface()
    carb_profile_monitor = carb.profiler.acquire_profile_monitor_interface()
    activity_profiler = omni.activity.profiler.get_activity_profiler()
    flow_interface = _flowusd.acquire_flowusd_interface()
    stage_update = omni.stageupdate.get_stage_update_interface()
    try:
        capture_mask_before = int(carb_profiler.get_capture_mask())
        report = {
            "schema_version": 1,
            "phase": "phase6de",
            "status": "ok",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "runtime": {
                "kit_version": str(app.get_kit_version()),
                "app_name": str(app.get_app_name()),
                "enabled_extensions": enabled_extensions,
            },
            "surfaces": {
                "carb_profiler_module": _surface(carb.profiler),
                "carb_profiler_interface": _surface(carb_profiler),
                "carb_profile_monitor_interface": _surface(carb_profile_monitor),
                "carb_profile_events": _surface(carb.profiler.ProfileEvents),
                "activity_profiler_module": _surface(omni.activity.profiler),
                "activity_profiler_interface": _surface(activity_profiler),
                "flowusd_public_module": _surface(omni.flowusd),
                "flowusd_internal_interface": _surface(flow_interface),
                "stageupdate_module": _surface(omni.stageupdate),
                "stageupdate_interface": _surface(stage_update),
                "tf_notice": _surface(Tf.Notice),
                "usd_objects_changed": _surface(Usd.Notice.ObjectsChanged),
            },
            "profiler": {
                "capture_mask_before": capture_mask_before,
                "capture_mask_after": int(carb_profiler.get_capture_mask()),
                "capture_mask_changed": False,
            },
            "stage_update": {
                "nodes": _stage_update_nodes(stage_update),
                "node_enablement_changed": False,
            },
            "module_files": {
                "activity_profiler": str(Path(omni.activity.profiler.__file__).resolve()),
                "flowusd_public": str(Path(omni.flowusd.__file__).resolve()),
                "flowusd_internal": str(Path(_flowusd.__file__).resolve()),
            },
            "scope": {
                "default_off": True,
                "read_only": True,
                "stage_opened": False,
                "stage_mutated": False,
                "profiler_capture_enabled": False,
                "production_changed": False,
                "private_flow_interface_is_adoption_surface": False,
            },
        }
    finally:
        _flowusd.release_flowusd_interface(flow_interface)
        release_profiler = getattr(carb.profiler, "release_profiler_interface", None)
        if release_profiler is not None:
            release_profiler(carb_profiler)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    app.post_uncancellable_quit(0)


asyncio.ensure_future(_run())
