"""Probe whether Flow USD can be detached as a narrow runtime boundary.

This default-off diagnostic never opens a USD stage.  It requests immediate
disablement of the already-loaded ``omni.flowusd`` extension, records the
public extension and StageUpdate state, and restores the original enabled
set before quitting.  Production configuration is not modified.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.stageupdate


EXTENSION_NAMES = (
    "campfire.app",
    "omni.flowusd",
    "omni.usd.schema.flow",
)
FLOW_NODE_NAME = "FlowUsd"


def _write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _extension_state(manager) -> dict:
    return {
        name: {
            "enabled": bool(manager.is_extension_enabled(name)),
            "enabled_id": manager.get_enabled_extension_id(name) or None,
        }
        for name in EXTENSION_NAMES
    }


def _stage_update_state(interface) -> dict:
    nodes = [
        {
            "index": int(node["index"]),
            "name": str(node["name"]),
            "enabled": bool(node["enabled"]),
            "order": int(node["order"]),
        }
        for node in interface.get_stage_update_nodes()
    ]
    flow_nodes = [node for node in nodes if node["name"] == FLOW_NODE_NAME]
    return {
        "node_count": len(nodes),
        "flow_node_count": len(flow_nodes),
        "flow_nodes": flow_nodes,
    }


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6dg/output")).resolve()
    app = omni.kit.app.get_app()
    manager = app.get_extension_manager()
    stage_update = omni.stageupdate.get_stage_update_interface()
    report = {
        "schema_version": 1,
        "phase": "phase6dg",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "stage_opened": False,
            "production_configuration_changed": False,
            "public_api": "ExtensionManager.set_extension_enabled_immediate",
        },
    }

    try:
        await app.next_update_async()
        before = {
            "extensions": _extension_state(manager),
            "stage_update": _stage_update_state(stage_update),
            "flowusd_module_loaded": "omni.flowusd" in sys.modules,
        }
        flow_id = before["extensions"]["omni.flowusd"]["enabled_id"]
        if not flow_id:
            raise RuntimeError("omni.flowusd was not enabled at probe start")

        disable_result = bool(
            manager.set_extension_enabled_immediate(flow_id, False)
        )
        await app.next_update_async()
        after_disable = {
            "extensions": _extension_state(manager),
            "stage_update": _stage_update_state(stage_update),
            "flowusd_module_loaded": "omni.flowusd" in sys.modules,
        }

        restore_requests = []
        for name in ("omni.flowusd", "campfire.app"):
            if (
                before["extensions"][name]["enabled"]
                and not manager.is_extension_enabled(name)
            ):
                restored = bool(
                    manager.set_extension_enabled_immediate(
                        before["extensions"][name]["enabled_id"], True
                    )
                )
                restore_requests.append({"extension": name, "result": restored})
        await app.next_update_async()
        after_restore = {
            "extensions": _extension_state(manager),
            "stage_update": _stage_update_state(stage_update),
            "flowusd_module_loaded": "omni.flowusd" in sys.modules,
        }

        restored_exactly = all(
            after_restore["extensions"][name]["enabled"]
            == before["extensions"][name]["enabled"]
            for name in EXTENSION_NAMES
        ) and (
            after_restore["stage_update"]["flow_node_count"]
            == before["stage_update"]["flow_node_count"]
        )
        report.update(
            {
                "status": "ok" if restored_exactly else "error",
                "before": before,
                "disable_request": {
                    "extension_id": flow_id,
                    "result": disable_result,
                },
                "after_disable": after_disable,
                "restore_requests": restore_requests,
                "after_restore": after_restore,
                "conclusions": {
                    "flowusd_disabled": not after_disable["extensions"][
                        "omni.flowusd"
                    ]["enabled"],
                    "campfire_app_remained_enabled": after_disable["extensions"][
                        "campfire.app"
                    ]["enabled"],
                    "schema_remained_enabled": after_disable["extensions"][
                        "omni.usd.schema.flow"
                    ]["enabled"],
                    "flow_stageupdate_node_removed": after_disable[
                        "stage_update"
                    ]["flow_node_count"]
                    == 0,
                    "restored_exactly": restored_exactly,
                },
            }
        )
    except Exception as exc:  # pragma: no cover - Kit runtime evidence
        report.update(
            {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    finally:
        _write(output, report)
        settings.set("/app/fastShutdown", True)
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run())
