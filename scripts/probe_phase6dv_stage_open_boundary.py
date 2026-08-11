"""Classify the Phase 6DU stage-open crash without changing production.

Every stage is fully prepared off-line before it is connected to the Kit USD
context.  The probe can stop after a pure OpenUSD open, or continue through
the public USD-context/Hydra/viewport boundary with durable lifecycle markers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade


OFFLINE_MODES = frozenset(("box_offline", "failed_cylinder_offline"))
HYDRA_MODES = frozenset(
    (
        "box_control",
        "box_hull",
        "cylinder_decomposition",
        "cylinder_hull",
        "cylinder_hull_hierarchy",
        "cylinder_hull_render_surface",
        "cylinder_hull_analytic_sibling",
    )
)
ALL_MODES = OFFLINE_MODES | HYDRA_MODES
COLLIDER_PATH = Sdf.Path("/World/ColliderReferenceMesh")
HIERARCHY_PATH = Sdf.Path("/World/Log/FlowCollisionProxy")
RADIUS_M = 0.16
LENGTH_M = 1.8
SEGMENTS = 12


def _settings() -> dict:
    settings = carb.settings.get_settings()
    phase = "phase6dx" if settings.get_as_string("/phase6dx/mode") else "phase6dv"
    prefix = f"/{phase}"
    mode = settings.get_as_string(f"{prefix}/mode")
    allowed_modes = frozenset(("box_control", "box_hull", "cylinder_decomposition")) if phase == "phase6dx" else ALL_MODES
    if mode not in allowed_modes:
        raise RuntimeError(f"Unsupported {phase} mode: {mode}")
    return {
        "phase": phase,
        "output": Path(settings.get_as_string(f"{prefix}/output")).resolve(),
        "source": Path(settings.get_as_string(f"{prefix}/source")).resolve(),
        "mode": mode,
        "run_index": int(settings.get_as_int(f"{prefix}/runIndex")) or 1,
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _cylinder_topology(center_z: float) -> tuple[list, list[int], list[int]]:
    points = []
    half = LENGTH_M * 0.5
    for x in (-half, half):
        for segment in range(SEGMENTS):
            angle = 2.0 * math.pi * segment / SEGMENTS
            points.append(Gf.Vec3f(x, RADIUS_M * math.cos(angle), center_z + RADIUS_M * math.sin(angle)))
    left_center = len(points)
    points.append(Gf.Vec3f(-half, 0.0, center_z))
    right_center = len(points)
    points.append(Gf.Vec3f(half, 0.0, center_z))
    counts = []
    indices = []
    for segment in range(SEGMENTS):
        following = (segment + 1) % SEGMENTS
        counts.append(4)
        indices.extend((segment, following, SEGMENTS + following, SEGMENTS + segment))
    for segment in range(SEGMENTS):
        following = (segment + 1) % SEGMENTS
        counts.extend((3, 3))
        indices.extend((left_center, following, segment))
        indices.extend((right_center, SEGMENTS + segment, SEGMENTS + following))
    return points, counts, indices


def _set_cylinder_geometry(mesh: UsdGeom.Mesh, center_z: float) -> None:
    points, counts, indices = _cylinder_topology(center_z)
    mesh.GetPointsAttr().Set(points)
    mesh.GetFaceVertexCountsAttr().Set(counts)
    mesh.GetFaceVertexIndicesAttr().Set(indices)
    mesh.GetExtentAttr().Set(
        [(-LENGTH_M * 0.5, -RADIUS_M, center_z - RADIUS_M), (LENGTH_M * 0.5, RADIUS_M, center_z + RADIUS_M)]
    )


def _move_proxy_under_log(stage: Usd.Stage) -> UsdGeom.Mesh:
    layer = stage.GetRootLayer()
    stage.DefinePrim("/World/Log", "Xform")
    edit = Sdf.BatchNamespaceEdit()
    edit.Add(str(COLLIDER_PATH), str(HIERARCHY_PATH))
    if not layer.Apply(edit):
        raise RuntimeError("Unable to move collision proxy under /World/Log")
    log = UsdGeom.Xformable(stage.GetPrimAtPath("/World/Log"))
    log.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 1.0))
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(HIERARCHY_PATH))
    _set_cylinder_geometry(mesh, 0.0)
    return mesh


def _add_render_surface(stage: Usd.Stage) -> None:
    render = UsdGeom.Mesh.Define(stage, "/World/Log/RenderSurface")
    points, counts, indices = _cylinder_topology(0.0)
    render.CreatePointsAttr(points)
    render.CreateFaceVertexCountsAttr(counts)
    render.CreateFaceVertexIndicesAttr(indices)
    render.CreateExtentAttr([(-0.9, -0.16, -0.16), (0.9, 0.16, 0.16)])
    render.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    render.CreateVisibilityAttr(UsdGeom.Tokens.inherited)
    material = UsdShade.Material(stage.GetPrimAtPath("/World/Materials/Collider"))
    if material and material.GetPrim().IsValid():
        UsdShade.MaterialBindingAPI.Apply(render.GetPrim()).Bind(material)


def _add_analytic_sibling(stage: Usd.Stage) -> None:
    cylinder = UsdGeom.Cylinder.Define(stage, "/World/Log/AnalyticCollider")
    cylinder.CreateAxisAttr(UsdGeom.Tokens.x)
    cylinder.CreateHeightAttr(LENGTH_M)
    cylinder.CreateRadiusAttr(RADIUS_M)
    cylinder.CreateVisibilityAttr(UsdGeom.Tokens.invisible)


def _prepare_stage(arguments: dict) -> tuple[Path, list[str]]:
    source = arguments["source"]
    if not source.is_file():
        raise RuntimeError(f"Source stage does not exist: {source}")
    if arguments["mode"] == "failed_cylinder_offline":
        return source, ["unaltered_failed_phase6du_stage_offline_only"]
    prepared = arguments["output"].with_suffix(".prepared.usda")
    source_stage = Usd.Stage.Open(str(source))
    if source_stage is None or not source_stage.Export(str(prepared)):
        raise RuntimeError(f"Unable to flatten source stage: {source}")
    del source_stage
    stage = Usd.Stage.Open(str(prepared))
    if stage is None:
        raise RuntimeError(f"Unable to reopen prepared stage: {prepared}")
    mode = arguments["mode"]
    changes = []
    collider = UsdGeom.Mesh(stage.GetPrimAtPath(COLLIDER_PATH))
    if not collider or not collider.GetPrim().IsValid():
        raise RuntimeError(f"Known-good collider missing: {COLLIDER_PATH}")
    if mode == "box_hull":
        collider.GetPrim().GetAttribute("physics:approximation").Set("convexHull")
        changes.append("approximation:convexDecomposition_to_convexHull")
    elif mode.startswith("cylinder_"):
        _set_cylinder_geometry(collider, 1.0)
        changes.append("geometry_payload:box_to_closed_12_segment_cylinder")
        if mode != "cylinder_decomposition":
            collider.GetPrim().GetAttribute("physics:approximation").Set("convexHull")
            changes.append("approximation:convexDecomposition_to_convexHull")
        if mode in ("cylinder_hull_hierarchy", "cylinder_hull_render_surface", "cylinder_hull_analytic_sibling"):
            collider = _move_proxy_under_log(stage)
            changes.append("hierarchy:/World/ColliderReferenceMesh_to_/World/Log/FlowCollisionProxy")
        if mode in ("cylinder_hull_render_surface", "cylinder_hull_analytic_sibling"):
            _add_render_surface(stage)
            changes.append("visible_render_surface_and_existing_material_binding")
        if mode == "cylinder_hull_analytic_sibling":
            _add_analytic_sibling(stage)
            changes.append("non_collision_analytic_cylinder_sibling")
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save prepared stage: {prepared}")
    del stage
    return prepared, changes


def _value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return str(value)


def _stage_audit(stage: Usd.Stage) -> dict:
    result = []
    selected_attrs = {
        "extent",
        "faceVertexCounts",
        "faceVertexIndices",
        "points",
        "physics:approximation",
        "physics:collisionEnabled",
        "purpose",
        "visibility",
        "xformOp:translate",
        "xformOpOrder",
    }
    for prim in stage.Traverse():
        item = {
            "path": str(prim.GetPath()),
            "type": prim.GetTypeName(),
            "applied_schemas": list(prim.GetAppliedSchemas()),
            "attributes": {},
            "relationships": sorted(rel.GetName() for rel in prim.GetRelationships()),
        }
        for attr in prim.GetAttributes():
            if attr.GetName() not in selected_attrs:
                continue
            value = attr.Get()
            if attr.GetName() in ("points", "faceVertexCounts", "faceVertexIndices"):
                serialized = repr(value).encode("utf-8")
                item["attributes"][attr.GetName()] = {
                    "count": len(value) if value is not None else 0,
                    "sha256": hashlib.sha256(serialized).hexdigest().upper(),
                }
            else:
                item["attributes"][attr.GetName()] = _value(value)
        result.append(item)
    return {
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "default_prim": str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
        "prim_count": len(result),
        "prims": result,
    }


def _extensions(app) -> dict:
    manager = app.get_extension_manager()
    result = {}
    for name in ("omni.flowusd", "omni.physx", "omni.physx.cooking", "omni.hydra.rtx", "usdrt.scenegraph"):
        extension_id = manager.get_enabled_extension_id(name)
        metadata = manager.get_extension_dict(extension_id) if extension_id else None
        result[name] = {
            "enabled": bool(extension_id),
            "id": extension_id or None,
            "version": (metadata or {}).get("package", {}).get("version"),
        }
    return result


async def _run() -> None:
    arguments = _settings()
    output = arguments["output"]
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    report = {
        "schema": f"campfire.{arguments['phase']}.stage-open-boundary-run.v1",
        "phase": arguments["phase"],
        "status": "running",
        "mode": arguments["mode"],
        "run_index": arguments["run_index"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(arguments["source"]),
        "source_sha256": _sha256(arguments["source"]),
        "lifecycle_marker": "starting",
        "lifecycle_history": [],
        "stage_events": [],
        "production_code_changed": False,
    }

    def mark(name: str) -> None:
        report["lifecycle_marker"] = name
        report["lifecycle_history"].append({"marker": name, "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        _write(output, report)

    event_names = {
        int(omni.usd.StageEventType.OPENING): "opening",
        int(omni.usd.StageEventType.OPENED): "opened",
        int(omni.usd.StageEventType.CLOSING): "closing",
        int(omni.usd.StageEventType.CLOSED): "closed",
    }

    def on_stage_event(event) -> None:
        item = {"type": int(event.type), "name": event_names.get(int(event.type), "other")}
        report["stage_events"].append(item)
        mark(f"stage_event_{item['name']}")

    subscription = context.get_stage_event_stream().create_subscription_to_pop(on_stage_event, name="phase6dv-stage-open")
    connected = False
    exit_code = 1
    _write(output, report)
    try:
        mark("renderer_readiness_warmup_started")
        warmup_viewport = None
        for _ in range(120):
            warmup_viewport = omni.kit.viewport.utility.get_active_viewport()
            await app.next_update_async()
            if warmup_viewport is not None:
                break
        if warmup_viewport is None:
            raise RuntimeError("No active viewport for renderer readiness warmup")
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(warmup_viewport)
        report["renderer_readiness_frames"] = 8
        mark("renderer_readiness_warmup_complete")
        mark("offline_prepare_started")
        stage_path, changes = _prepare_stage(arguments)
        report["prepared_stage"] = str(stage_path)
        report["prepared_stage_sha256"] = _sha256(stage_path)
        report["offline_changes"] = changes
        mark("pure_openusd_open_started")
        offline_stage = Usd.Stage.Open(str(stage_path))
        if offline_stage is None:
            raise RuntimeError("Pure OpenUSD stage open failed")
        report["offline_audit"] = _stage_audit(offline_stage)
        del offline_stage
        mark("pure_openusd_open_complete")
        report["extensions"] = _extensions(app)
        report["kit_build"] = str(getattr(app, "get_build_version", lambda: "unavailable")())
        if arguments["mode"] in OFFLINE_MODES:
            report["status"] = "ok"
            exit_code = 0
            mark("offline_only_complete")
            return

        mark("usd_context_open_stage_async_entered")
        await context.open_stage_async(str(stage_path))
        connected = True
        mark("usd_context_open_stage_async_returned")
        connected_stage = context.get_stage()
        if connected_stage is None:
            raise RuntimeError("USD context returned without a stage")
        report["connected_audit"] = _stage_audit(connected_stage)
        get_stage_id = getattr(context, "get_stage_id", None)
        report["stage_cache_id"] = int(get_stage_id()) if callable(get_stage_id) else None
        mark("stage_cache_query_complete")
        viewport = None
        mark("viewport_lookup_started")
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport")
        report["viewport_api_id"] = str(getattr(viewport, "id", "unavailable"))
        mark("viewport_connected")
        mark("first_renderer_update_started")
        await app.next_update_async()
        mark("first_renderer_update_complete")
        mark("first_viewport_frame_started")
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        mark("first_viewport_frame_complete")
        for _ in range(8):
            await app.next_update_async()
        report["status"] = "ok"
        exit_code = 0
        mark("stage_open_classified")
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        try:
            timeline.stop()
            if connected:
                mark("stage_close_started")
                await context.close_stage_async()
                mark("stage_close_returned")
                for _ in range(8):
                    await app.next_update_async()
            subscription = None
            mark("shutdown_complete")
        except Exception as error:
            report["shutdown_error"] = f"{type(error).__name__}: {error}"
            report["status"] = "error"
            exit_code = 1
        _write(output, report)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run())
