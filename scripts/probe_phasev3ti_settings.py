"""Inventory public frame-limit and RTX quality settings for Phase V3T-I."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility


ROOTS = (
    "/app",
    "/renderer",
    "/rtx",
    "/persistent",
    "/exts/omni.kit.renderer.core",
    "/exts/omni.kit.viewport.window",
    "/timeline",
)
TOKENS = (
    "vsync",
    "rate",
    "limit",
    "fps",
    "frame",
    "syncinterval",
    "present",
    "reflection",
    "indirect",
    "denois",
    "quality",
    "preset",
    "dlss",
    "eco",
)


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _walk(value, path):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_walk(item, f"{path}/{key}"))
    elif any(token in path.lower() for token in TOKENS):
        rows.append({"path": path, "value": _json_safe(value), "type": type(value).__name__})
    return rows


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phasev3ti/settingsOutput")).resolve()
    app = omni.kit.app.get_app()
    for _ in range(12):
        await app.next_update_async()
    viewport = None
    for _ in range(240):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    rows = []
    roots = {}
    for root in ROOTS:
        dictionary = settings.get_settings_dictionary(root)
        payload = dictionary.get_dict() if dictionary is not None else {}
        roots[root] = bool(payload)
        rows.extend(_walk(payload, root))
    unique = {row["path"]: row for row in rows}
    extension_manager = app.get_extension_manager()
    versions = {}
    for extension_id in ("omni.flowusd", "omni.hydra.rtx", "omni.kit.viewport.window"):
        enabled = extension_manager.get_enabled_extension_id(extension_id)
        metadata = extension_manager.get_extension_dict(enabled) if enabled else None
        versions[extension_id] = {
            "enabled_id": enabled or None,
            "version": (metadata or {}).get("package", {}).get("version"),
        }
    report = {
        "schema": "campfire.phasev3ti.settings-inventory.v1",
        "status": "ok",
        "kit": "110.2",
        "roots_present": roots,
        "matching_settings": [unique[path] for path in sorted(unique)],
        "viewport": {
            "available": viewport is not None,
            "fps": float(viewport.fps) if viewport is not None else None,
            "frame_info": _json_safe(viewport.frame_info) if viewport is not None else None,
        },
        "extensions": versions,
        "additional_render_product_created": False,
        "production_changed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    app.post_uncancellable_quit(0)


asyncio.ensure_future(_run())
