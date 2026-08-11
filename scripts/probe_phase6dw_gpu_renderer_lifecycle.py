"""Phase 6DW production-neutral GPU and renderer lifecycle probe.

The probe deliberately grows from a renderer-free Kit process to a known-good
Flow scene.  Every condition is selected before startup and writes durable
markers before entering the next public lifecycle boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app


CONDITIONS = frozenset(
    (
        "kit_only",
        "openusd_empty",
        "rtx_empty",
        "box_openusd",
        "box_rtx",
        "flow_load",
        "flow_sim",
    )
)
RTX_CONDITIONS = frozenset(("rtx_empty", "box_rtx", "flow_load", "flow_sim"))
FLOW_CONDITIONS = frozenset(("flow_load", "flow_sim"))
SYNCHRONOUS_CONDITIONS = frozenset(("kit_only", "openusd_empty", "box_openusd"))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _gpu_snapshot() -> dict:
    query = (
        "index,uuid,name,pci.bus_id,pci.device_id,driver_version,display_active,"
        "memory.total,memory.used,utilization.gpu,power.draw,temperature.gpu"
    )
    try:
        completed = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        rows = []
        for line in completed.stdout.splitlines():
            values = [value.strip() for value in line.split(",")]
            if len(values) != 12:
                continue
            rows.append(
                dict(
                    zip(
                        (
                            "index",
                            "uuid",
                            "name",
                            "pci_bus_id",
                            "pci_device_id",
                            "driver_version",
                            "display_active",
                            "memory_total_mib",
                            "memory_used_mib",
                            "utilization_percent",
                            "power_w",
                            "temperature_c",
                        ),
                        values,
                    )
                )
            )
        return {"status": "ok", "gpus": rows}
    except Exception as error:
        return {"status": "unavailable", "error": f"{type(error).__name__}: {error}"}


def _extension_snapshot(app) -> dict:
    manager = app.get_extension_manager()
    result = {}
    for name in (
        "omni.hydra.rtx",
        "omni.hydra.usdrt_delegate",
        "omni.flowusd",
        "omni.physx",
        "omni.physx.stageupdate",
    ):
        extension_id = manager.get_enabled_extension_id(name)
        metadata = manager.get_extension_dict(extension_id) if extension_id else None
        result[name] = {
            "enabled": bool(extension_id),
            "id": extension_id or None,
            "version": (metadata or {}).get("package", {}).get("version"),
        }
    return result


def _setting_snapshot() -> dict:
    settings = carb.settings.get_settings()
    keys = (
        "/renderer/enabled",
        "/renderer/active",
        "/renderer/activeGpu",
        "/renderer/multiGpu/enabled",
        "/renderer/multiGpu/autoEnable",
        "/renderer/gpuEnumeration/glInterop/enabled",
        "/app/useFabricSceneDelegate",
        "/app/asyncRendering",
        "/app/tokens/omni_cache",
        "/rtx/rendermode",
        "/rtx/flow/enabled",
        "/rtx/post/aa/op",
        "/rtx/post/dlss/execMode",
    )
    return {key: settings.get(key) for key in keys}


def _stage_audit(stage) -> dict:
    from pxr import UsdGeom

    prims = list(stage.Traverse())
    return {
        "prim_count": len(prims),
        "default_prim": str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "collision_api_prim_count": sum("PhysicsCollisionAPI" in prim.GetAppliedSchemas() for prim in prims),
        "mesh_collision_api_prim_count": sum("PhysicsMeshCollisionAPI" in prim.GetAppliedSchemas() for prim in prims),
    }


async def _run() -> None:
    settings = carb.settings.get_settings()
    condition = settings.get_as_string("/phase6dw/condition")
    if condition not in CONDITIONS:
        raise RuntimeError(f"Unsupported Phase 6DW condition: {condition}")
    output = Path(settings.get_as_string("/phase6dw/output")).resolve()
    source_text = settings.get_as_string("/phase6dw/source")
    source = Path(source_text).resolve() if source_text else None
    cache_kind = settings.get_as_string("/phase6dw/cacheKind") or "normal"
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6dw.gpu-renderer-lifecycle-run.v1",
        "phase": "phase6dw",
        "status": "running",
        "condition": condition,
        "cache_kind": cache_kind,
        "timestamp_utc": _utc(),
        "lifecycle_marker": "starting",
        "lifecycle_history": [],
        "completion_contract": {
            "results_saved": False,
            "timeline_stopped": False,
            "stage_closed": False,
            "renderer_drained": False,
            "shutdown_requested": False,
        },
        "gpu_start": _gpu_snapshot(),
        "production_code_changed": False,
    }

    def mark(marker: str) -> None:
        report["lifecycle_marker"] = marker
        report["lifecycle_history"].append({"marker": marker, "timestamp_utc": _utc()})
        _write(output, report)

    exit_code = 1
    connected = False
    context = None
    timeline = None
    stage_subscription = None
    _write(output, report)
    try:
        report["kit_build"] = str(getattr(app, "get_build_version", lambda: "unavailable")())
        report["extensions"] = _extension_snapshot(app)
        report["settings"] = _setting_snapshot()
        mark("kit_started")

        for _ in range(4):
            await app.next_update_async()
        mark("kit_updates_complete")

        if condition == "kit_only":
            report["status"] = "ok"
            report["completion_contract"]["results_saved"] = True
            exit_code = 0
            mark("kit_only_complete")
            return

        # omni.app.empty intentionally does not load OpenUSD.  Import it only
        # after the renderer-free Kit-only boundary has been qualified.
        from pxr import Usd, UsdGeom

        stage_path = source
        if condition in ("openusd_empty", "rtx_empty", "flow_load"):
            stage_path = output.with_suffix(".empty.usda")
            mark("stage_create_started")
            stage = Usd.Stage.CreateNew(str(stage_path))
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            stage.DefinePrim("/World", "Xform")
            stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
            if not stage.GetRootLayer().Save():
                raise RuntimeError("Unable to save empty diagnostic stage")
            del stage
            mark("stage_create_complete")
        if stage_path is None or not stage_path.is_file():
            raise RuntimeError(f"Phase 6DW source stage missing: {stage_path}")
        report["source_stage"] = str(stage_path)
        report["source_sha256"] = _sha256(stage_path)

        mark("pure_openusd_open_started")
        offline_stage = Usd.Stage.Open(str(stage_path))
        if offline_stage is None:
            raise RuntimeError("Pure OpenUSD open failed")
        report["offline_stage"] = _stage_audit(offline_stage)
        del offline_stage
        mark("pure_openusd_open_complete")

        if condition in ("openusd_empty", "box_openusd"):
            report["status"] = "ok"
            report["completion_contract"]["results_saved"] = True
            exit_code = 0
            mark("openusd_only_complete")
            return

        viewport_utility = importlib.import_module("omni.kit.viewport.utility")
        timeline_module = importlib.import_module("omni.timeline")
        usd_module = importlib.import_module("omni.usd")

        context = usd_module.get_context()
        timeline = timeline_module.get_timeline_interface()
        stage_events = []
        report["stage_events"] = stage_events

        def on_stage_event(event) -> None:
            stage_events.append({"type": int(event.type), "timestamp_utc": _utc()})
            _write(output, report)

        stage_subscription = context.get_stage_event_stream().create_subscription_to_pop(
            on_stage_event, name="phase6dw-stage-events"
        )
        if condition in FLOW_CONDITIONS:
            flow = report["extensions"].get("omni.flowusd", {})
            if not flow.get("enabled"):
                raise RuntimeError("omni.flowusd was not loaded for Flow condition")
            mark("flow_extension_load_verified")

        mark("renderer_readiness_started")
        viewport = None
        for _ in range(240):
            viewport = viewport_utility.get_active_viewport()
            await app.next_update_async()
            if viewport is not None:
                break
        if viewport is None:
            raise RuntimeError("No active viewport")
        mark("renderer_readiness_complete")

        if condition == "flow_load":
            report["status"] = "ok"
            report["completion_contract"]["results_saved"] = True
            exit_code = 0
            mark("flow_loaded_without_simulation")
            return

        mark("usd_context_connection_started")
        await context.open_stage_async(str(stage_path))
        connected = True
        mark("usd_context_connection_complete")
        if context.get_stage() is None:
            raise RuntimeError("USD context returned without a connected stage")
        get_stage_id = getattr(context, "get_stage_id", None)
        report["stage_id"] = int(get_stage_id()) if callable(get_stage_id) else None
        mark("hydra_delegate_connection_observed")

        mark("first_renderer_update_started")
        await app.next_update_async()
        mark("first_renderer_update_complete")
        mark("first_viewport_frame_started")
        await viewport_utility.next_viewport_frame_async(viewport)
        mark("first_viewport_frame_complete")

        if condition == "flow_sim":
            connected_stage = context.get_stage()
            flow_types = {
                "FlowSimulate": 0,
                "FlowOffscreen": 0,
                "FlowRender": 0,
            }
            for prim in connected_stage.Traverse():
                if prim.GetTypeName() in flow_types:
                    flow_types[prim.GetTypeName()] += 1
            report["flow_prim_counts"] = flow_types
            if not all(flow_types.values()):
                raise RuntimeError(f"Known-good Flow stage is incomplete: {flow_types}")
            timeline.set_start_time(0.0)
            timeline.set_end_time(1000.0)
            timeline.set_current_time(0.0)
            mark("flow_simulation_starting")
            timeline.play()
            for _ in range(120):
                await app.next_update_async()
            report["timeline_time_after_updates"] = float(timeline.get_current_time())
            report["timeline_playing_after_updates"] = bool(timeline.is_playing())
            if report["timeline_time_after_updates"] <= 0.0:
                raise RuntimeError("Flow timeline did not advance")
            mark("flow_simulation_started")

        report["status"] = "ok"
        report["completion_contract"]["results_saved"] = True
        exit_code = 0
        mark("condition_complete")
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        _write(output, report)
    finally:
        try:
            if timeline is not None:
                timeline.stop()
                mark("timeline_stopped")
            report["completion_contract"]["timeline_stopped"] = True
            if connected and context is not None:
                mark("stage_close_started")
                await context.close_stage_async()
                connected = False
                mark("stage_close_complete")
            report["completion_contract"]["stage_closed"] = True
            mark("renderer_drain_started")
            for _ in range(8):
                await app.next_update_async()
            mark("renderer_drain_complete")
            report["completion_contract"]["renderer_drained"] = True
            stage_subscription = None
            report["gpu_before_quit"] = _gpu_snapshot()
            report["completion_contract"]["shutdown_requested"] = True
            mark("shutdown_requested")
        except Exception as error:
            report["shutdown_error"] = f"{type(error).__name__}: {error}"
            report["status"] = "error"
            exit_code = 1
        _write(output, report)
        app.post_uncancellable_quit(exit_code)


def _run_synchronous_renderer_free() -> None:
    """Run conditions supported by omni.app.empty without an asyncio loop."""

    settings = carb.settings.get_settings()
    condition = settings.get_as_string("/phase6dw/condition")
    output = Path(settings.get_as_string("/phase6dw/output")).resolve()
    source_text = settings.get_as_string("/phase6dw/source")
    source = Path(source_text).resolve() if source_text else None
    cache_kind = settings.get_as_string("/phase6dw/cacheKind") or "normal"
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6dw.gpu-renderer-lifecycle-run.v1",
        "phase": "phase6dw",
        "status": "running",
        "condition": condition,
        "cache_kind": cache_kind,
        "timestamp_utc": _utc(),
        "lifecycle_marker": "starting",
        "lifecycle_history": [],
        "completion_contract": {
            "results_saved": False,
            "timeline_stopped": True,
            "stage_closed": True,
            "renderer_drained": True,
            "shutdown_requested": False,
        },
        "gpu_start": _gpu_snapshot(),
        "production_code_changed": False,
    }

    def mark(marker: str) -> None:
        report["lifecycle_marker"] = marker
        report["lifecycle_history"].append({"marker": marker, "timestamp_utc": _utc()})
        _write(output, report)

    exit_code = 1
    _write(output, report)
    try:
        report["kit_build"] = str(getattr(app, "get_build_version", lambda: "unavailable")())
        report["extensions"] = _extension_snapshot(app)
        report["settings"] = _setting_snapshot()
        mark("kit_started")
        if condition == "kit_only":
            report["status"] = "ok"
            report["completion_contract"]["results_saved"] = True
            exit_code = 0
            mark("kit_only_complete")
        else:
            from pxr import Usd, UsdGeom

            stage_path = source
            if condition == "openusd_empty":
                stage_path = output.with_suffix(".empty.usda")
                mark("stage_create_started")
                stage = Usd.Stage.CreateNew(str(stage_path))
                UsdGeom.SetStageMetersPerUnit(stage, 1.0)
                UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
                stage.DefinePrim("/World", "Xform")
                stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
                if not stage.GetRootLayer().Save():
                    raise RuntimeError("Unable to save empty diagnostic stage")
                del stage
                mark("stage_create_complete")
            if stage_path is None or not stage_path.is_file():
                raise RuntimeError(f"Phase 6DW source stage missing: {stage_path}")
            report["source_stage"] = str(stage_path)
            report["source_sha256"] = _sha256(stage_path)
            mark("pure_openusd_open_started")
            offline_stage = Usd.Stage.Open(str(stage_path))
            if offline_stage is None:
                raise RuntimeError("Pure OpenUSD open failed")
            report["offline_stage"] = _stage_audit(offline_stage)
            del offline_stage
            report["status"] = "ok"
            report["completion_contract"]["results_saved"] = True
            exit_code = 0
            mark("openusd_only_complete")
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        report["gpu_before_quit"] = _gpu_snapshot()
        report["completion_contract"]["shutdown_requested"] = True
        mark("shutdown_requested")
        _write(output, report)
        app.post_uncancellable_quit(exit_code)


_startup_condition = carb.settings.get_settings().get_as_string("/phase6dw/condition")
if _startup_condition in SYNCHRONOUS_CONDITIONS:
    _run_synchronous_renderer_free()
else:
    asyncio.ensure_future(_run())
