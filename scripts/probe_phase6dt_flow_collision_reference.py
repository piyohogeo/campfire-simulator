"""Run NVIDIA Flow 110.0.0 collision reference and isolated ablations.

The NVIDIA source file is never modified.  Numeric variants are flattened to
an artifact-owned stage and fully patched before they are connected to Kit.
Only public Flow NanoVDB readback and bundled NanoVDB accessors are used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import nanovdb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
import omni.volume
from omni.flowusd import _flowusd
from pxr import PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics


CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
SAMPLE_FRAMES = (60, 120, 180, 200)
REFERENCE_CAMERA = Sdf.Path("/OmniverseKit_Persp")
PHASE6DS_CAMERA = Sdf.Path("/World/Cameras/Front")
CAPTURE_RESOLUTION = (1280, 720)
EXTENSIONS = (
    "omni.flowusd",
    "omni.usd.schema.flow",
    "omni.physx",
    "omni.physx.cooking",
    "omni.physx.stageupdate",
    "omni.hydra.rtx",
    "omni.volume",
)


def _settings() -> dict:
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phase6dt/output")).resolve(),
        "mode": settings.get_as_string("/phase6dt/mode"),
        "source": Path(settings.get_as_string("/phase6dt/source")).resolve(),
        "capture": bool(settings.get_as_bool("/phase6dt/capture")),
        "run_index": int(settings.get_as_int("/phase6dt/runIndex")) or 1,
        "app_kind": settings.get_as_string("/phase6dt/appKind") or "reference",
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _get(prim: Usd.Prim, name: str):
    attr = prim.GetAttribute(name)
    return attr.Get() if attr else None


def _set(prim: Usd.Prim, name: str, value) -> None:
    attr = prim.GetAttribute(name)
    if not attr or not attr.Set(value):
        raise RuntimeError(f"Unable to set {prim.GetPath()}.{name}")


def _paths(source_kind: str) -> dict:
    if source_kind == "reference":
        return {
            "collider": "/World/Torus",
            "emitter": "/World/Fire/flowEmitterSphere",
            "simulate": "/World/Fire/flowSimulate",
            "export": "/World/Fire/flowSimulate/nanoVdbExport",
            "offscreen": "/World/Fire/flowOffscreen",
            "render": "/World/Fire/flowRender",
        }
    return {
        "collider": "/World/Collider",
        "emitter": "/World/Flow/Emitter",
        "simulate": "/World/Flow/Simulate",
        "export": "/World/Flow/Simulate/nanoVdbExport",
        "offscreen": "/World/Flow/Offscreen",
        "render": "/World/Flow/Render",
    }


def _source_kind(mode: str) -> str:
    return "reference" if mode.startswith("reference_") else "phase6ds"


def _enable_readback(stage: Usd.Stage, export_path: str) -> None:
    export = stage.GetPrimAtPath(export_path)
    for name in (
        "enabled",
        "temperatureEnabled",
        "fuelEnabled",
        "burnEnabled",
        "smokeEnabled",
        "velocityEnabled",
        "divergenceEnabled",
        "statisticsEnabled",
        "readbackEnabled",
    ):
        _set(export, name, True)


def _apply_reference_collision_schemas(prim: Usd.Prim) -> None:
    """Apply the public collision API bundle authored on PhysicsCollision.usda."""
    for schema in (
        UsdPhysics.CollisionAPI,
        PhysxSchema.PhysxCollisionAPI,
        PhysxSchema.PhysxTriangleMeshCollisionAPI,
        UsdPhysics.MeshCollisionAPI,
        PhysxSchema.PhysxConvexDecompositionCollisionAPI,
    ):
        if not schema.Apply(prim):
            raise RuntimeError(f"{schema.__name__}.Apply failed on {prim.GetPath()}")
    prim.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool).Set(True)
    prim.CreateAttribute("physics:approximation", Sdf.ValueTypeNames.Token).Set(
        "convexDecomposition"
    )


def _apply_usd_mesh_collision_schemas(
    prim: Usd.Prim, approximation: str = "convexDecomposition"
) -> None:
    if not UsdPhysics.CollisionAPI.Apply(prim):
        raise RuntimeError(f"CollisionAPI.Apply failed on {prim.GetPath()}")
    if not UsdPhysics.MeshCollisionAPI.Apply(prim):
        raise RuntimeError(f"MeshCollisionAPI.Apply failed on {prim.GetPath()}")
    prim.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool).Set(True)
    prim.CreateAttribute("physics:approximation", Sdf.ValueTypeNames.Token).Set(approximation)


def _define_box_mesh(stage: Usd.Stage, path: str) -> Usd.Prim:
    """Define a 2 x 2 x 0.25 m box matching the Phase 6DS Cube."""
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(
        [
            (-1.0, -1.0, 0.875),
            (1.0, -1.0, 0.875),
            (1.0, 1.0, 0.875),
            (-1.0, 1.0, 0.875),
            (-1.0, -1.0, 1.125),
            (1.0, -1.0, 1.125),
            (1.0, 1.0, 1.125),
            (-1.0, 1.0, 1.125),
        ]
    )
    mesh.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4])
    mesh.CreateFaceVertexIndicesAttr(
        [0, 3, 2, 1, 4, 5, 6, 7, 0, 1, 5, 4, 1, 2, 6, 5, 2, 3, 7, 6, 3, 0, 4, 7]
    )
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateExtentAttr([(-1.0, -1.0, 0.875), (1.0, 1.0, 1.125)])
    mesh.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
    return mesh.GetPrim()


def _prepare_stage(arguments: dict) -> tuple[Path, dict]:
    source = arguments["source"]
    mode = arguments["mode"]
    source_kind = _source_kind(mode)
    paths = _paths(source_kind)
    if not source.is_file():
        raise RuntimeError(f"Source stage does not exist: {source}")
    source_hash = _sha256(source)
    if mode == "reference_unmodified_on":
        return source, {
            "source_kind": source_kind,
            "source_sha256": source_hash,
            "stage_unmodified": True,
            "offline_changes": [],
        }

    prepared = arguments["output"].with_suffix(".prepared.usda")
    source_stage = Usd.Stage.Open(str(source))
    if source_stage is None or not source_stage.Export(str(prepared)):
        raise RuntimeError(f"Unable to flatten source stage: {source}")
    del source_stage
    stage = Usd.Stage.Open(str(prepared))
    if stage is None:
        raise RuntimeError(f"Unable to reopen prepared stage: {prepared}")
    changes = []
    _enable_readback(stage, paths["export"])
    changes.append("enable_public_nanovdb_readback")
    simulate = stage.GetPrimAtPath(paths["simulate"])
    if mode == "reference_numeric_off":
        _set(simulate, "physicsCollisionEnabled", False)
        changes.append("physicsCollisionEnabled=false")
    elif mode == "reference_numeric_on":
        _set(simulate, "physicsCollisionEnabled", True)
        changes.append("physicsCollisionEnabled=true")
    elif mode == "phase6ds_physx_collision_api":
        collider = stage.GetPrimAtPath(paths["collider"])
        if not PhysxSchema.PhysxCollisionAPI.Apply(collider):
            raise RuntimeError("PhysxCollisionAPI.Apply failed")
        changes.append("apply_PhysxCollisionAPI")
    elif mode == "phase6ds_force_simulate_false":
        _set(simulate, "forceSimulate", False)
        changes.append("forceSimulate=false")
    elif mode == "phase6ds_layer_2":
        for key in ("emitter", "simulate", "offscreen", "render"):
            _set(stage.GetPrimAtPath(paths[key]), "layer", 2)
        changes.append("Flow_layer=2")
    elif mode == "phase6ds_physics_convex_false":
        _set(simulate, "physicsConvexCollision", False)
        changes.append("physicsConvexCollision=false")
    elif mode == "phase6ds_collision_relation":
        collider = stage.GetPrimAtPath(paths["collider"])
        collider.CreateRelationship("physicsCollisionPrim", custom=True)
        changes.append("create_empty_physicsCollisionPrim_relationship")
    elif mode == "phase6ds_cube_reference_schema_bundle":
        collider = stage.GetPrimAtPath(paths["collider"])
        _apply_reference_collision_schemas(collider)
        changes.append("apply_reference_collision_schema_bundle_to_Cube")
    elif mode in (
        "phase6ds_mesh_collision_only",
        "phase6ds_mesh_no_collision_schema",
        "phase6ds_mesh_usd_mesh_collision",
        "phase6ds_mesh_usd_mesh_collision_none",
        "phase6ds_mesh_usd_mesh_collision_convex_hull",
        "phase6ds_mesh_reference_schema_bundle",
        "phase6ds_mesh_reference_collision_disabled",
        "phase6ds_mesh_flow_collision_disabled",
    ):
        collider = stage.GetPrimAtPath(paths["collider"])
        _set(collider, "physics:collisionEnabled", False)
        mesh_path = "/World/ColliderReferenceMesh"
        mesh = _define_box_mesh(stage, mesh_path)
        if mode == "phase6ds_mesh_no_collision_schema":
            changes.append("leave_equivalent_Mesh_without_collision_schema")
        elif mode == "phase6ds_mesh_collision_only":
            if not UsdPhysics.CollisionAPI.Apply(mesh):
                raise RuntimeError("CollisionAPI.Apply failed on equivalent Mesh")
            mesh.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool).Set(True)
            changes.append("apply_PhysicsCollisionAPI_only_to_Mesh")
        elif mode.startswith("phase6ds_mesh_usd_mesh_collision"):
            approximation = {
                "phase6ds_mesh_usd_mesh_collision_none": "none",
                "phase6ds_mesh_usd_mesh_collision_convex_hull": "convexHull",
            }.get(mode, "convexDecomposition")
            _apply_usd_mesh_collision_schemas(mesh, approximation)
            changes.append(
                "apply_USD_collision_and_mesh_collision_APIs_to_Mesh:"
                f"approximation={approximation}"
            )
        else:
            _apply_reference_collision_schemas(mesh)
            changes.append("apply_reference_collision_schema_bundle_to_Mesh")
            if mode == "phase6ds_mesh_reference_collision_disabled":
                mesh.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool).Set(False)
                changes.append("disable_reference_Mesh_collision")
            elif mode == "phase6ds_mesh_flow_collision_disabled":
                _set(simulate, "physicsCollisionEnabled", False)
                changes.append("disable_Flow_physicsCollisionEnabled")
        changes[0:0] = ("disable_original_Cube_collision", "define_equivalent_Mesh")
    elif mode == "phase6dy_prepared_mesh":
        collider = stage.GetPrimAtPath("/World/ColliderReferenceMesh")
        if not collider or not collider.IsValid():
            raise RuntimeError("Phase 6DY prepared Mesh is missing")
        changes.append("preserve_prequalified_phase6dy_mesh_and_enable_readback")
    elif mode == "phase6ds_physx_api_force_false":
        collider = stage.GetPrimAtPath(paths["collider"])
        if not PhysxSchema.PhysxCollisionAPI.Apply(collider):
            raise RuntimeError("PhysxCollisionAPI.Apply failed")
        _set(simulate, "forceSimulate", False)
        changes.extend(("apply_PhysxCollisionAPI", "forceSimulate=false"))
    elif mode != "phase6ds_baseline_on":
        raise RuntimeError(f"Unsupported Phase 6DT mode: {mode}")
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save prepared stage: {prepared}")
    del stage
    return prepared, {
        "source_kind": source_kind,
        "source_sha256": source_hash,
        "stage_unmodified": False,
        "prepared_sha256": _sha256(prepared),
        "offline_changes": changes,
        "audit_collider_path": (
            "/World/ColliderReferenceMesh"
            if mode.startswith("phase6ds_mesh_") or mode == "phase6dy_prepared_mesh"
            else paths["collider"]
        ),
    }


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _audit_stage(stage: Usd.Stage, source_kind: str, collider_path: str | None = None) -> dict:
    paths = _paths(source_kind)
    if collider_path:
        paths["collider"] = collider_path
    collider = stage.GetPrimAtPath(paths["collider"])
    emitter = stage.GetPrimAtPath(paths["emitter"])
    simulate = stage.GetPrimAtPath(paths["simulate"])
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
    )
    aligned = bbox_cache.ComputeWorldBound(collider).ComputeAlignedBox()
    emitter_transform = UsdGeom.XformCache().GetLocalToWorldTransform(emitter)
    emitter_position = emitter_transform.ExtractTranslation()
    return {
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "collider": {
            "path": paths["collider"],
            "type": collider.GetTypeName(),
            "applied_schemas": list(collider.GetAppliedSchemas()),
            "rigid_body_api": any("RigidBodyAPI" in name for name in collider.GetAppliedSchemas()),
            "collision_enabled": _json_safe(_get(collider, "physics:collisionEnabled")),
            "approximation": _json_safe(_get(collider, "physics:approximation")),
            "world_bbox_min": list(aligned.GetMin()),
            "world_bbox_max": list(aligned.GetMax()),
        },
        "emitter": {
            "path": paths["emitter"],
            "type": emitter.GetTypeName(),
            "world_origin": list(emitter_position),
            "radius": _json_safe(_get(emitter, "radius")),
            "allocationScale": _json_safe(_get(emitter, "allocationScale")),
            "applyPostPressure": _json_safe(_get(emitter, "applyPostPressure")),
            "coupleRateVelocity": _json_safe(_get(emitter, "coupleRateVelocity")),
            "physicsVelocityScale": _json_safe(_get(emitter, "physicsVelocityScale")),
            "coupleRateFuel": _json_safe(_get(emitter, "coupleRateFuel")),
            "coupleRateTemperature": _json_safe(_get(emitter, "coupleRateTemperature")),
            "coupleRateSmoke": _json_safe(_get(emitter, "coupleRateSmoke")),
            "coupleRateBurn": _json_safe(_get(emitter, "coupleRateBurn")),
            "target_velocity": _json_safe(_get(emitter, "velocity")),
        },
        "simulate": {
            name: _json_safe(_get(simulate, name))
            for name in (
                "layer",
                "densityCellSize",
                "stepsPerSecond",
                "forceSimulate",
                "simulateWhenPaused",
                "physicsCollisionEnabled",
                "physicsConvexCollision",
                "velocitySubSteps",
            )
        },
        "physics_scene_paths": [
            str(prim.GetPath()) for prim in stage.Traverse() if prim.GetTypeName() == "PhysicsScene"
        ],
        "flow_prim_types": [
            {"path": str(prim.GetPath()), "type": prim.GetTypeName()}
            for prim in stage.Traverse()
            if prim.GetTypeName().startswith("Flow")
        ],
    }


def _reference_rois(audit: dict) -> dict:
    bbox_min = audit["collider"]["world_bbox_min"]
    bbox_max = audit["collider"]["world_bbox_max"]
    emitter = audit["emitter"]["world_origin"]
    radius = float(audit["emitter"]["radius"] or 10.0)
    density_cell = float(audit["simulate"]["densityCellSize"])
    focus_half = max(radius, 12.0 * density_cell)
    bottom = float(bbox_min[1])
    below_min = emitter[1] + radius + 2.0 * density_cell
    below_max = bottom - 2.0 * density_cell
    if below_max <= below_min:
        below_min = emitter[1] + radius
        below_max = bottom
    return {
        "below": {
            "minimum": [emitter[0] - focus_half, below_min, emitter[2] - focus_half],
            "maximum": [emitter[0] + focus_half, below_max, emitter[2] + focus_half],
        },
        "inside": {
            "minimum": [emitter[0] - focus_half, bottom, emitter[2] - focus_half],
            "maximum": [emitter[0] + focus_half, min(bottom + 25.0, bbox_max[1]), emitter[2] + focus_half],
        },
        "inside_core": {
            "minimum": [emitter[0] - focus_half, bottom + 2.0, emitter[2] - focus_half],
            "maximum": [emitter[0] + focus_half, min(bottom + 20.0, bbox_max[1]), emitter[2] + focus_half],
        },
        "above": {
            "minimum": [emitter[0] - focus_half, bottom + 25.0, emitter[2] - focus_half],
            "maximum": [emitter[0] + focus_half, bottom + 50.0, emitter[2] + focus_half],
        },
        "above_far": {
            "minimum": [emitter[0] - focus_half, bottom + 55.0, emitter[2] - focus_half],
            "maximum": [emitter[0] + focus_half, bottom + 100.0, emitter[2] + focus_half],
        },
    }


def _phase6ds_rois() -> dict:
    return {
        "below": {"minimum": [-0.30, -0.30, 0.67], "maximum": [0.30, 0.30, 0.80]},
        "inside": {"minimum": [-0.30, -0.30, 0.875], "maximum": [0.30, 0.30, 1.125]},
        "inside_core": {"minimum": [-0.30, -0.30, 0.93], "maximum": [0.30, 0.30, 1.07]},
        "above": {"minimum": [-0.30, -0.30, 1.125], "maximum": [0.30, 0.30, 1.32]},
        "above_far": {"minimum": [-0.30, -0.30, 1.18], "maximum": [0.30, 0.30, 1.55]},
    }


def _component(value, index: int) -> float:
    try:
        return float(value[index])
    except TypeError:
        return float((value.x, value.y, value.z)[index])


def _sample_grid(grid, roi: dict, vector: bool) -> dict:
    minimum = roi["minimum"]
    maximum = roi["maximum"]
    lo = grid.applyInverseMap(nanovdb.math.Vec3d(*minimum))
    hi = grid.applyInverseMap(nanovdb.math.Vec3d(*maximum))
    index_min = [math.floor(min(_component(lo, i), _component(hi, i))) - 1 for i in range(3)]
    index_max = [math.ceil(max(_component(lo, i), _component(hi, i))) + 1 for i in range(3)]
    accessor = grid.getAccessor()
    values = []
    for i in range(index_min[0], index_max[0] + 1):
        for j in range(index_min[1], index_max[1] + 1):
            for k in range(index_min[2], index_max[2] + 1):
                world = grid.applyMap(nanovdb.math.Vec3d(float(i), float(j), float(k)))
                xyz = [_component(world, axis) for axis in range(3)]
                if not all(minimum[axis] <= xyz[axis] <= maximum[axis] for axis in range(3)):
                    continue
                value = accessor.getValue(i, j, k)
                if vector:
                    value = math.sqrt(sum(_component(value, axis) ** 2 for axis in range(3)))
                else:
                    value = float(value)
                values.append(value)
    if not values:
        return {"available": False, "reason": "ROI contained no grid samples"}
    ordered = sorted(values)
    return {
        "available": True,
        "voxel_count": len(values),
        "nonzero_voxel_count": sum(abs(value) > 1.0e-12 for value in values),
        "mean": statistics.fmean(values),
        "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
        "maximum": max(values),
    }


def _save_and_sample(flow, volume, buffer, channel: str, path: Path, rois: dict) -> dict:
    grid_data = flow.buffer_to_volume(buffer)
    parameters = omni.volume.SaveVolumeParameters()
    parameters.flags = omni.volume.kNanoVDBCodecNone
    if not volume.save_volume(grid_data, str(path), parameters):
        raise RuntimeError(f"Unable to save public readback: {path}")
    handle = nanovdb.io.readGrid(str(path))
    vector = channel == "velocity"
    grid = handle.vec3fGrid() if vector else handle.floatGrid()
    voxel_size = grid.voxelSize()
    result = {
        "active_voxel_count": int(grid.activeVoxelCount()),
        "voxel_size": [_component(voxel_size, axis) for axis in range(3)],
        "rois": {name: _sample_grid(grid, roi, vector) for name, roi in rois.items()},
    }
    path.unlink(missing_ok=True)
    return result


async def _capture(viewport, path: Path) -> dict:
    capture = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await capture.wait_for_result(completion_frames=30):
        raise RuntimeError(f"Viewport capture failed: {path}")
    return {"path": str(path), "bytes": path.stat().st_size if path.is_file() else 0}


def _extension_inventory(app) -> dict:
    manager = app.get_extension_manager()
    result = {}
    for name in EXTENSIONS:
        enabled_id = manager.get_enabled_extension_id(name)
        metadata = manager.get_extension_dict(enabled_id) if enabled_id else None
        result[name] = {
            "enabled": bool(enabled_id),
            "enabled_id": enabled_id or None,
            "version": (metadata or {}).get("package", {}).get("version"),
        }
    return result


async def _run() -> None:
    arguments = _settings()
    output = arguments["output"]
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    flow = None
    volume = None
    report = {
        "schema": "campfire.phase6dt.flow-collision-reference-run.v1",
        "phase": "phase6dt",
        "status": "running",
        "mode": arguments["mode"],
        "run_index": arguments["run_index"],
        "app_kind": arguments["app_kind"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "production_changed": False,
        "lifecycle_marker": "starting",
        "samples": [],
        "captures": [],
    }
    _write(output, report)
    exit_code = 1
    try:
        stage_path, preparation = _prepare_stage(arguments)
        report["preparation"] = preparation
        report["lifecycle_marker"] = "offline_stage_ready"
        offline = Usd.Stage.Open(str(stage_path))
        if offline is None:
            raise RuntimeError("Unable to audit offline stage")
        report["stage_audit"] = _audit_stage(
            offline,
            preparation["source_kind"],
            preparation.get("audit_collider_path"),
        )
        report["rois"] = (
            _reference_rois(report["stage_audit"])
            if preparation["source_kind"] == "reference"
            else _phase6ds_rois()
        )
        if arguments["mode"] == "phase6dy_prepared_mesh":
            # Applied identically to Box and Cylinder runs.  The core cuboid is
            # fully inside the 0.16 m radius Cylinder and 0.30 m from both caps.
            report["rois"].update(
                {
                    "cylinder_core": {
                        "minimum": [-0.60, -0.08, 0.955],
                        "maximum": [0.60, 0.08, 1.115],
                    },
                    "cylinder_above": {
                        "minimum": [-0.60, -0.08, 1.245],
                        "maximum": [0.60, 0.08, 1.40],
                    },
                }
            )
        del offline
        report["extensions"] = _extension_inventory(app)
        _write(output, report)

        report["lifecycle_marker"] = "opening_prebuilt_stage"
        _write(output, report)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Prepared stage did not connect")
        paths = _paths(preparation["source_kind"])
        effective = _audit_stage(
            stage,
            preparation["source_kind"],
            preparation.get("audit_collider_path"),
        )
        report["effective_stage_audit"] = effective

        viewport = None
        for _ in range(240):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport")
        viewport.camera_path = REFERENCE_CAMERA if preparation["source_kind"] == "reference" else PHASE6DS_CAMERA
        viewport.fill_frame = False
        viewport.resolution = CAPTURE_RESOLUTION
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)

        numeric = arguments["mode"] != "reference_unmodified_on"
        flow = _flowusd.acquire_flowusd_interface()
        if numeric:
            volume = omni.volume.get_volume_interface()
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(12):
            await app.next_update_async()
        report["lifecycle_marker"] = "timeline_playing"
        timeline.play()
        _write(output, report)

        capture_frames = SAMPLE_FRAMES if arguments["capture"] else ()
        for frame in range(1, SAMPLE_FRAMES[-1] + 1):
            await app.next_update_async()
            if frame in capture_frames:
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                path = output.parent / "frames" / f"{arguments['mode']}_r{arguments['run_index']}_{frame:04d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                report["captures"].append({"frame": frame, **(await _capture(viewport, path))})
            if not numeric or frame not in SAMPLE_FRAMES:
                continue
            raw = flow.get_latest_nanovdb_readback()
            sample = {
                "frame": frame,
                "active_blocks": int(flow.get_active_block_count()),
                "channels": {},
            }
            if len(raw) < len(CHANNELS):
                raise RuntimeError(f"Expected {len(CHANNELS)} buffers, got {len(raw)}")
            for index, channel in enumerate(CHANNELS):
                array = np.asarray(raw[index])
                if array.size == 0:
                    sample["channels"][channel] = {"available": False, "reason": "empty buffer"}
                    continue
                nvdb = output.parent / f"sample_{frame}_{channel}.nvdb"
                sample["channels"][channel] = {
                    "available": True,
                    "word_count": int(array.size),
                    **_save_and_sample(flow, volume, array, channel, nvdb, report["rois"]),
                }
            report["samples"].append(sample)
            _write(output, report)

        report["active_blocks_final"] = int(flow.get_active_block_count()) if flow is not None else None
        report["measurement_gates"] = {
            "stage_connected": True,
            "source_hash_preserved": _sha256(arguments["source"]) == preparation["source_sha256"],
            "required_extensions_loaded": all(
                report["extensions"][name]["enabled"]
                for name in ("omni.flowusd", "omni.physx.cooking", "omni.physx.stageupdate")
            ),
            "active_blocks_nonzero": (
                report["active_blocks_final"] is not None and report["active_blocks_final"] > 0
            ),
            "numeric_samples_complete": (
                not numeric or len(report["samples"]) == len(SAMPLE_FRAMES)
            ),
            "capture_complete": (
                not arguments["capture"] or len(report["captures"]) == len(SAMPLE_FRAMES)
            ),
        }
        if not all(report["measurement_gates"].values()):
            raise RuntimeError(f"Measurement gates failed: {report['measurement_gates']}")
        report["status"] = "ok"
        report["lifecycle_marker"] = "measurement_complete"
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        try:
            report["lifecycle_marker"] = "timeline_stopping"
            timeline.stop()
            for _ in range(12):
                await app.next_update_async()
            report["lifecycle_marker"] = "stage_closing"
            await context.close_stage_async()
            for _ in range(12):
                await app.next_update_async()
            report["lifecycle_marker"] = "flow_interface_releasing"
            if flow is not None:
                _flowusd.release_flowusd_interface(flow)
                flow = None
            report["lifecycle_marker"] = "shutdown_complete"
        except Exception as shutdown_error:
            report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
            report["status"] = "error"
            exit_code = 1
        _write(output, report)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run())
