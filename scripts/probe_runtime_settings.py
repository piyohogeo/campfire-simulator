"""Capture a non-sensitive runtime settings subset for Phase 6CT."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app


ROOTS = (
    "/app/player",
    "/app/runLoops",
    "/app/viewport",
    "/exts/omni.kit.renderer.core",
    "/persistent/app/viewport",
    "/renderer",
    "/rtx/ecoMode",
    "/rtx/hydra",
    "/timeline",
)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _settings_root(settings, root):
    dictionary = settings.get_settings_dictionary(root)
    return _json_safe(dictionary.get_dict() or {}) if dictionary is not None else {}


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6ct/settingsOutput")).resolve()
    label = settings.get_as_string("/phase6ct/label") or "unspecified"
    await omni.kit.app.get_app().next_update_async()
    report = {
        "schema_version": 1,
        "phase": "phase6ct",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "scope": {
            "renderer_enabled": settings.get_as_bool("/renderer/enabled"),
            "production_changed": False,
            "sensitive_roots_excluded": True,
        },
        "settings": {
            root: _settings_root(settings, root)
            for root in ROOTS
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0)


asyncio.ensure_future(_run())
