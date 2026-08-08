"""Capture non-sensitive public Kit application identity for Phase 6CW."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app


EXTENSIONS = (
    "campfire.app",
    "omni.flowusd",
    "omni.kit.viewport.window",
    "omni.kit.window.extensions",
)


def _option_names(arguments: list[str]) -> list[str]:
    names = []
    for argument in arguments:
        if argument.startswith("--"):
            names.append(argument.split("=", 1)[0])
    return sorted(set(names))


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6cw/output")).resolve()
    label = settings.get_as_string("/phase6cw/label") or "unspecified"
    app = omni.kit.app.get_app()
    await app.next_update_async()
    manager = app.get_extension_manager()
    report = {
        "schema_version": 1,
        "phase": "phase6cw",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "identity": {
            "app_filename": app.get_app_filename(),
            "app_name": app.get_app_name(),
            "app_environment": app.get_app_environment(),
            "app_version": app.get_app_version(),
            "app_version_short": app.get_app_version_short(),
            "build_version": app.get_build_version(),
            "kernel_version": app.get_kernel_version(),
            "kit_version": app.get_kit_version(),
            "platform": app.get_platform_info().get("platform"),
            "is_app_external": app.is_app_external(),
            "is_debug_build": app.is_debug_build(),
        },
        "settings": {
            "app_name": settings.get_as_string("/app/name"),
            "environment_name": settings.get_as_string("/app/environment/name"),
            "window_title": settings.get_as_string("/app/window/title"),
            "fill_viewport": settings.get_as_bool(
                "/app/viewport/defaults/fillViewport"
            ),
        },
        "command_line": {
            "app_argument_basename": Path(sys.argv[0]).name,
            "option_names": _option_names(sys.argv[1:]),
            "argument_count": len(sys.argv),
            "values_redacted": True,
        },
        "enabled_extensions": {
            name: manager.get_enabled_extension_id(name) or None
            for name in EXTENSIONS
        },
        "scope": {
            "sensitive_values_excluded": True,
            "production_changed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.set("/app/fastShutdown", True)
    app.post_uncancellable_quit(0)


asyncio.ensure_future(_run())
