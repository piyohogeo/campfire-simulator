"""Stopped-timeline hierarchy boundary for one diagnostic FlowCollisionProxy."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import carb
import campfire.app
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Gf, Usd, UsdGeom, UsdPhysics


PROXY_PATH = "/World/Logs/Log_00/FlowCollisionProxy"
RADIUS_M = 0.16
LENGTH_M = 1.8
SEGMENTS = 12


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _topology():
    half = LENGTH_M * 0.5
    points = []
    for x in (-half, half):
        for segment in range(SEGMENTS):
            angle = 2.0 * math.pi * segment / SEGMENTS
            points.append(Gf.Vec3f(x, RADIUS_M * math.cos(angle), RADIUS_M * math.sin(angle)))
    left_center = len(points)
    points.append(Gf.Vec3f(-half, 0.0, 0.0))
    right_center = len(points)
    points.append(Gf.Vec3f(half, 0.0, 0.0))
    counts, indices = [], []
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


def _geometry_audit(points, counts, indices) -> dict:
    edges = Counter()
    signed_volume = 0.0
    degenerate = 0
    cursor = 0
    for count in counts:
        face = indices[cursor : cursor + count]
        cursor += count
        for offset, first in enumerate(face):
            edges[tuple(sorted((first, face[(offset + 1) % count])))] += 1
        origin = points[face[0]]
        area_twice = 0.0
        for offset in range(1, count - 1):
            second, third = points[face[offset]], points[face[offset + 1]]
            cross = Gf.Cross(second - origin, third - origin)
            area_twice += float(cross.GetLength())
            signed_volume += float(Gf.Dot(origin, Gf.Cross(second, third))) / 6.0
        degenerate += int(area_twice <= 1.0e-10)
    return {
        "vertex_count": len(points),
        "face_count": len(counts),
        "index_count": len(indices),
        "closed_manifold": bool(edges) and all(value == 2 for value in edges.values()),
        "degenerate_face_count": degenerate,
        "signed_volume": signed_volume,
        "outward_winding": signed_volume > 0.0,
    }


def _stage_digest(stage: Usd.Stage, excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    digest = hashlib.sha256()
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if path in excluded:
            continue
        digest.update(f"P|{path}|{prim.GetTypeName()}|{sorted(prim.GetAppliedSchemas())}\n".encode())
        for attribute in sorted(prim.GetAttributes(), key=lambda item: item.GetName()):
            digest.update(f"A|{attribute.GetName()}|{attribute.GetTypeName()}|{repr(attribute.Get())}\n".encode())
        for relationship in sorted(prim.GetRelationships(), key=lambda item: item.GetName()):
            digest.update(f"R|{relationship.GetName()}|{[str(value) for value in relationship.GetTargets()]}\n".encode())
    return digest.hexdigest().upper()


def _matrix(stage: Usd.Stage, path: str) -> list[float]:
    matrix = UsdGeom.Xformable(stage.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


def _build(path: Path, add_proxy: bool) -> tuple[Usd.Stage, dict]:
    if path.exists():
        raise RuntimeError(f"Phase 6HK refuses stage reuse: {path}")
    stage = Usd.Stage.CreateNew(str(path))
    campfire.app.populate_phase2_scene(stage, render_hierarchy=True)
    geometry = None
    if add_proxy:
        points, counts, indices = _topology()
        geometry = _geometry_audit(points, counts, indices)
        proxy = UsdGeom.Mesh.Define(stage, PROXY_PATH)
        proxy.CreatePointsAttr(points)
        proxy.CreateFaceVertexCountsAttr(counts)
        proxy.CreateFaceVertexIndicesAttr(indices)
        proxy.CreateExtentAttr([Gf.Vec3f(-0.9, -0.16, -0.16), Gf.Vec3f(0.9, 0.16, 0.16)])
        proxy.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        proxy.CreateDoubleSidedAttr(False)
        proxy.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        UsdPhysics.CollisionAPI.Apply(proxy.GetPrim()).CreateCollisionEnabledAttr(True)
        UsdPhysics.MeshCollisionAPI.Apply(proxy.GetPrim()).CreateApproximationAttr("convexDecomposition")
        stage.GetRootLayer().customLayerData = {
            **stage.GetRootLayer().customLayerData,
            "campfire:phase6hkDiagnosticFlowProxy": True,
            "campfire:phase6hkDefaultOff": True,
        }
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save Phase 6HK stage: {path}")
    return stage, {"geometry": geometry, "prim_paths": [str(prim.GetPath()) for prim in stage.Traverse()]}


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6hk/output")).resolve()
    markers = Path(settings.get_as_string("/phase6hk/markers")).resolve()
    stage_dir = output.parent / "stages"
    stage_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "campfire.phase6hk.flow-proxy-hierarchy-boundary-run.v1",
        "phase": "phase6hk",
        "status": "running",
        "timestamp_utc": _utc(),
        "readback_calls": 0,
        "timeline_play_calls": 0,
        "production_code_changed": False,
        "latest_demo_changed": False,
        "lifecycle": {},
    }
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    flow = None
    held = {}
    exit_code = 1

    def mark(name: str, **values) -> None:
        record = {"timestamp_utc": _utc(), "name": name, **values}
        markers.parent.mkdir(parents=True, exist_ok=True)
        with markers.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        report["last_marker"] = name
        _write(output, report)

    try:
        mark("contract_started")
        baseline, baseline_info = _build(stage_dir / "baseline.usda", False)
        candidate, candidate_info = _build(stage_dir / "candidate.usda", True)
        baseline_digest = _stage_digest(baseline)
        candidate_without_proxy = _stage_digest(candidate, {PROXY_PATH})
        added = sorted(set(candidate_info["prim_paths"]) - set(baseline_info["prim_paths"]))
        proxy = candidate.GetPrimAtPath(PROXY_PATH)
        geometry = candidate_info["geometry"]
        matrices = {
            "root": _matrix(candidate, "/World/Logs/Log_00"),
            "collider": _matrix(candidate, "/World/Logs/Log_00/Collider"),
            "render_surface": _matrix(candidate, "/World/Logs/Log_00/RenderSurface"),
            "flow_proxy": _matrix(candidate, PROXY_PATH),
        }
        point_prims = [str(prim.GetPath()) for prim in candidate.Traverse() if "Point" in prim.GetTypeName()]
        revision_attrs = [
            f"{prim.GetPath()}.{attr.GetName()}"
            for prim in candidate.Traverse()
            for attr in prim.GetAttributes()
            if "revision" in attr.GetName().lower()
        ]
        gates = {
            "baseline_digest_unchanged_after_proxy_exclusion": baseline_digest == candidate_without_proxy,
            "only_proxy_prim_added": added == [PROXY_PATH],
            "proxy_mesh_type": proxy.GetTypeName() == "Mesh",
            "proxy_collision_api": proxy.HasAPI(UsdPhysics.CollisionAPI),
            "proxy_mesh_collision_api": proxy.HasAPI(UsdPhysics.MeshCollisionAPI),
            "proxy_approximation": proxy.GetAttribute("physics:approximation").Get() == "convexDecomposition",
            "proxy_invisible": UsdGeom.Imageable(proxy).GetVisibilityAttr().Get() == UsdGeom.Tokens.invisible,
            "proxy_no_rigid_body": not proxy.HasAPI(UsdPhysics.RigidBodyAPI),
            "topology_26_36_120": (geometry["vertex_count"], geometry["face_count"], geometry["index_count"]) == (26, 36, 120),
            "topology_closed_outward": geometry["closed_manifold"] and geometry["outward_winding"] and geometry["degenerate_face_count"] == 0,
            "world_matrices_equal": len({tuple(value) for value in matrices.values()}) == 1,
            "point_prim_count_zero": len(point_prims) == 0,
            "revision_attribute_count_zero": len(revision_attrs) == 0,
        }
        report["offline"] = {
            "baseline_digest": baseline_digest,
            "candidate_without_proxy_digest": candidate_without_proxy,
            "added_prims": added,
            "geometry": geometry,
            "matrices": matrices,
            "point_prims": point_prims,
            "revision_attributes": revision_attrs,
            "gates": gates,
        }
        if not all(gates.values()):
            raise RuntimeError(f"Offline hierarchy gate failed: {gates}")
        del baseline, candidate
        mark("offline_contract_complete")
        await context.open_stage_async(str(stage_dir / "candidate.usda"))
        held["stage"] = context.get_stage()
        mark("stage_open_complete", stage_identity=id(held["stage"]))
        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("Active viewport unavailable")
        held["viewport"] = viewport
        for index in range(30):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if index in (0, 29):
                mark("renderer_update", index=index + 1)
        flow = _flowusd.acquire_flowusd_interface()
        held["flow"] = flow
        report["runtime"] = {
            "renderer_updates": 30,
            "timeline_playing": bool(timeline.is_playing()),
            "active_blocks_stopped": int(flow.get_active_block_count()),
            "flow_identity": id(flow),
            "stage_identity": id(held["stage"]),
            "viewport_identity": id(viewport),
        }
        if timeline.is_playing():
            raise RuntimeError("Phase 6HK timeline must remain stopped")
        mark("operation_complete", active_blocks=report["runtime"]["active_blocks_stopped"])
        report["status"] = "operation_pass"
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        try:
            mark("timeline_stop_started")
            timeline.stop()
            mark("timeline_stop_complete")
            for index in range(8):
                await app.next_update_async()
                mark("renderer_drain_update", index=index + 1)
            mark("stage_close_started", held_references=sorted(held))
            await asyncio.wait_for(context.close_stage_async(), timeout=180.0)
            if context.get_stage() is not None:
                raise RuntimeError("USD context still exposes a stage after close")
            mark("stage_close_complete")
            for index in range(4):
                await app.next_update_async()
                mark("post_close_update", index=index + 1)
            if flow is not None:
                _flowusd.release_flowusd_interface(flow)
                flow = None
            held.clear()
            mark("references_released")
            report["lifecycle"] = {"stage_close_complete": True, "shutdown_complete": True}
            if report["status"] == "operation_pass":
                report["status"] = "qualified"
            mark("shutdown_complete")
        except Exception as shutdown_error:
            report["lifecycle"] = {"stage_close_complete": False, "shutdown_complete": False}
            report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
            report["status"] = "error"
            exit_code = 1
            _write(output, report)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run())
