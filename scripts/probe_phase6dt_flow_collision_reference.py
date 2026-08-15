"""Run NVIDIA Flow 110.0.0 collision reference and isolated ablations.

The NVIDIA source file is never modified.  Numeric variants are flattened to
an artifact-owned stage and fully patched before they are connected to Kit.
Only public Flow NanoVDB readback and bundled NanoVDB accessors are used.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import math
import statistics
import time
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
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics


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
    spatial_root = settings.get_as_string("/phase6ee/spatialOutputRoot")
    return {
        "output": Path(settings.get_as_string("/phase6dt/output")).resolve(),
        "mode": settings.get_as_string("/phase6dt/mode"),
        "source": Path(settings.get_as_string("/phase6dt/source")).resolve(),
        "capture": bool(settings.get_as_bool("/phase6dt/capture")),
        "capture_start_frame": int(settings.get_as_int("/phase6dt/captureStartFrame")),
        "capture_end_frame": int(settings.get_as_int("/phase6dt/captureEndFrame")),
        "capture_stride": max(1, int(settings.get_as_int("/phase6dt/captureStride")) or 1),
        "run_index": int(settings.get_as_int("/phase6dt/runIndex")) or 1,
        "app_kind": settings.get_as_string("/phase6dt/appKind") or "reference",
        "phase6ee_spatial_enabled": bool(settings.get_as_bool("/phase6ee/spatialEnabled")),
        "phase6ee_spatial_root": Path(spatial_root).resolve() if spatial_root else None,
        "phase6ee_condition": settings.get_as_string("/phase6ee/condition"),
        "phase6ee_spatial_velocity_only": bool(
            settings.get_as_bool("/phase6ee/spatialVelocityOnly")
        ),
        "phase6eg_stage_open_only": bool(
            settings.get_as_bool("/phase6egResourceProbe/stageOpenOnly")
        ),
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
        "phase6eo_box_mesh_collision_on",
        "phase6eo_box_mesh_collision_off",
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
        elif mode.startswith("phase6ds_mesh_usd_mesh_collision") or mode.startswith("phase6eo_box_mesh_collision_"):
            approximation = {
                "phase6ds_mesh_usd_mesh_collision_none": "none",
                "phase6ds_mesh_usd_mesh_collision_convex_hull": "convexHull",
            }.get(mode, "convexDecomposition")
            _apply_usd_mesh_collision_schemas(mesh, approximation)
            changes.append(
                "apply_USD_collision_and_mesh_collision_APIs_to_Mesh:"
                f"approximation={approximation}"
            )
            if mode == "phase6eo_box_mesh_collision_off":
                _set(simulate, "physicsCollisionEnabled", False)
                changes.append("physicsCollisionEnabled=false_for_positive_control")
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
    elif mode in (
        "phase6dy_prepared_mesh",
        "phase6dz_rotated_mesh",
        "phase6ec_rotated_mesh",
        "phase6ec_rotated_mesh_collision_off",
    ):
        collider = stage.GetPrimAtPath("/World/ColliderReferenceMesh")
        if not collider or not collider.IsValid():
            raise RuntimeError("Phase 6DY prepared Mesh is missing")
        changes.append("preserve_prequalified_phase6dy_mesh_and_enable_readback")
        if mode == "phase6ec_rotated_mesh_collision_off":
            _set(simulate, "physicsCollisionEnabled", False)
            changes.append("physicsCollisionEnabled=false_for_positive_control")
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
            if mode.startswith("phase6ds_mesh_")
            or mode.startswith("phase6eo_box_mesh_collision_")
            or mode in (
                "phase6dy_prepared_mesh",
                "phase6dz_rotated_mesh",
                "phase6ec_rotated_mesh",
                "phase6ec_rotated_mesh_collision_off",
            )
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
            "fuel": _json_safe(_get(emitter, "fuel")),
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
        "sum": float(sum(values)),
        "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
        "maximum": max(values),
    }


def _profile_grid(grid, roi: dict, vector: bool, threshold: float) -> dict:
    """Return bounded world-space extent statistics for significant voxels."""

    minimum = roi["minimum"]
    maximum = roi["maximum"]
    lo = grid.applyInverseMap(nanovdb.math.Vec3d(*minimum))
    hi = grid.applyInverseMap(nanovdb.math.Vec3d(*maximum))
    index_min = [math.floor(min(_component(lo, i), _component(hi, i))) - 1 for i in range(3)]
    index_max = [math.ceil(max(_component(lo, i), _component(hi, i))) + 1 for i in range(3)]
    accessor = grid.getAccessor()
    positions = []
    values = []
    vertical = []
    for i in range(index_min[0], index_max[0] + 1):
        for j in range(index_min[1], index_max[1] + 1):
            for k in range(index_min[2], index_max[2] + 1):
                world = grid.applyMap(nanovdb.math.Vec3d(float(i), float(j), float(k)))
                xyz = [_component(world, axis) for axis in range(3)]
                if not all(minimum[axis] <= xyz[axis] <= maximum[axis] for axis in range(3)):
                    continue
                raw = accessor.getValue(i, j, k)
                if vector:
                    value = math.sqrt(sum(_component(raw, axis) ** 2 for axis in range(3)))
                    vz = _component(raw, 2)
                else:
                    value = float(raw)
                    vz = 0.0
                if abs(value) < threshold:
                    continue
                positions.append(xyz)
                values.append(value)
                vertical.append(vz)
    if not positions:
        return {"available": True, "threshold": threshold, "significant_voxel_count": 0}
    array = np.asarray(positions, dtype=np.float64)
    return {
        "available": True,
        "threshold": threshold,
        "significant_voxel_count": int(array.shape[0]),
        "world_minimum": array.min(axis=0).tolist(),
        "world_maximum": array.max(axis=0).tolist(),
        "world_centroid": array.mean(axis=0).tolist(),
        "horizontal_extent_x_m": float(np.ptp(array[:, 0])),
        "horizontal_extent_y_m": float(np.ptp(array[:, 1])),
        "vertical_extent_m": float(np.ptp(array[:, 2])),
        "mean_value": statistics.fmean(values),
        "maximum_value": max(values),
        "mean_positive_vertical_velocity_m_s": (
            statistics.fmean(value for value in vertical if value > 0.0)
            if vector and any(value > 0.0 for value in vertical) else 0.0
        ),
    }


def _phase6dz_local_rois() -> dict:
    center_z = 1.035
    radius = 0.16
    velocity_cell = 0.05
    return {
        "cylinder_inside": {
            "local_min": [-0.75, -radius, center_z - radius],
            "local_max": [0.75, radius, center_z + radius],
            "cylindrical": True,
        },
        "cylinder_core": {
            "local_min": [-0.65, -radius + velocity_cell, center_z - radius + velocity_cell],
            "local_max": [0.65, radius - velocity_cell, center_z + radius - velocity_cell],
            "cylindrical": True,
        },
        "outside_above": {
            "local_min": [-0.35, -0.10, center_z + radius + velocity_cell],
            "local_max": [0.35, 0.10, center_z + radius + 0.42],
            "cylindrical": False,
        },
    }


def _matrix_list(matrix: Gf.Matrix4d) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _local_roi_contains(local: Gf.Vec3d, bounds: dict) -> bool:
    if not all(
        bounds["local_min"][axis] <= local[axis] <= bounds["local_max"][axis]
        for axis in range(3)
    ):
        return False
    if bounds["cylindrical"]:
        return math.hypot(local[1], local[2] - 1.035) <= 0.16
    return True


def _world_aabb(bounds: dict, local_to_world: Gf.Matrix4d) -> tuple[list[float], list[float]]:
    corners = []
    for x in (bounds["local_min"][0], bounds["local_max"][0]):
        for y in (bounds["local_min"][1], bounds["local_max"][1]):
            for z in (bounds["local_min"][2], bounds["local_max"][2]):
                corners.append(local_to_world.Transform(Gf.Vec3d(x, y, z)))
    return (
        [min(float(point[axis]) for point in corners) for axis in range(3)],
        [max(float(point[axis]) for point in corners) for axis in range(3)],
    )


def _sample_local_grid(grid, rois: dict, local_to_world: Gf.Matrix4d, vector: bool) -> dict:
    world_to_local = local_to_world.GetInverse()
    accessor = grid.getAccessor()
    results = {}
    for name, bounds in rois.items():
        minimum, maximum = _world_aabb(bounds, local_to_world)
        lo = grid.applyInverseMap(nanovdb.math.Vec3d(*minimum))
        hi = grid.applyInverseMap(nanovdb.math.Vec3d(*maximum))
        index_min = [math.floor(min(_component(lo, axis), _component(hi, axis))) - 1 for axis in range(3)]
        index_max = [math.ceil(max(_component(lo, axis), _component(hi, axis))) + 1 for axis in range(3)]
        values = []
        for i in range(index_min[0], index_max[0] + 1):
            for j in range(index_min[1], index_max[1] + 1):
                for k in range(index_min[2], index_max[2] + 1):
                    world = grid.applyMap(nanovdb.math.Vec3d(float(i), float(j), float(k)))
                    point = Gf.Vec3d(*[_component(world, axis) for axis in range(3)])
                    if not _local_roi_contains(world_to_local.Transform(point), bounds):
                        continue
                    value = accessor.getValue(i, j, k)
                    if vector:
                        value = math.sqrt(sum(_component(value, axis) ** 2 for axis in range(3)))
                    else:
                        value = float(value)
                    values.append(value)
        if not values:
            results[name] = {"available": False, "reason": "local Cylinder ROI contained no grid samples"}
            continue
        ordered = sorted(values)
        results[name] = {
            "available": True,
            "voxel_count": len(values),
            "nonzero_voxel_count": sum(abs(value) > 1.0e-12 for value in values),
            "mean": statistics.fmean(values),
            "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
            "maximum": max(values),
        }
    return results


def _sample_alignment_grid(grid, bounds: dict, local_to_world: Gf.Matrix4d, vector: bool) -> dict:
    """Compare the transformed solid with its stale axis-aligned position."""

    identity = Gf.Matrix4d(1.0)
    rotated_min, rotated_max = _world_aabb(bounds, local_to_world)
    axis_min, axis_max = _world_aabb(bounds, identity)
    minimum = [min(rotated_min[axis], axis_min[axis]) for axis in range(3)]
    maximum = [max(rotated_max[axis], axis_max[axis]) for axis in range(3)]
    lo = grid.applyInverseMap(nanovdb.math.Vec3d(*minimum))
    hi = grid.applyInverseMap(nanovdb.math.Vec3d(*maximum))
    index_min = [math.floor(min(_component(lo, axis), _component(hi, axis))) - 1 for axis in range(3)]
    index_max = [math.ceil(max(_component(lo, axis), _component(hi, axis))) + 1 for axis in range(3)]
    world_to_rotated = local_to_world.GetInverse()
    samples = {name: [] for name in ("rotated_inside", "axis_inside", "rotated_only", "axis_only", "overlap")}
    accessor = grid.getAccessor()
    for i in range(index_min[0], index_max[0] + 1):
        for j in range(index_min[1], index_max[1] + 1):
            for k in range(index_min[2], index_max[2] + 1):
                world = grid.applyMap(nanovdb.math.Vec3d(float(i), float(j), float(k)))
                point = Gf.Vec3d(*[_component(world, axis) for axis in range(3)])
                in_rotated = _local_roi_contains(world_to_rotated.Transform(point), bounds)
                in_axis = _local_roi_contains(point, bounds)
                if not in_rotated and not in_axis:
                    continue
                value = accessor.getValue(i, j, k)
                if vector:
                    value = math.sqrt(sum(_component(value, axis) ** 2 for axis in range(3)))
                else:
                    value = float(value)
                if in_rotated:
                    samples["rotated_inside"].append(value)
                if in_axis:
                    samples["axis_inside"].append(value)
                if in_rotated and not in_axis:
                    samples["rotated_only"].append(value)
                elif in_axis and not in_rotated:
                    samples["axis_only"].append(value)
                else:
                    samples["overlap"].append(value)

    results = {}
    for name, values in samples.items():
        if not values:
            results[name] = {"available": False, "reason": "alignment ROI contained no grid samples"}
            continue
        ordered = sorted(values)
        results[name] = {
            "available": True,
            "voxel_count": len(values),
            "nonzero_voxel_count": sum(abs(value) > 1.0e-12 for value in values),
            "mean": statistics.fmean(values),
            "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
            "maximum": max(values),
        }
    return results


def _save_and_sample(
    flow,
    volume,
    buffer,
    channel: str,
    path: Path,
    rois: dict,
    local_rois: dict | None = None,
    local_to_world: Gf.Matrix4d | None = None,
    spatial_collector=None,
    spatial_velocity_only: bool = False,
    frame: int | None = None,
    profile_threshold: float | None = None,
    diagnostic_stop_after: str | None = None,
    diagnostic_step_observer=None,
    diagnostic_roi_limit: int | None = None,
) -> dict:
    """Save and sample one public field, with optional diagnostic stop points.

    The default path is the frozen production-neutral diagnostic path.  The
    optional stop/observer arguments expose that same call order to bounded
    one-variable probes; no existing caller supplies them.
    """

    allowed_stops = {None, "conversion", "durability", "file_read", "basic_metadata", "roi_sampling", "profile"}
    if diagnostic_stop_after not in allowed_stops:
        raise ValueError(f"unsupported diagnostic stop point: {diagnostic_stop_after}")
    if diagnostic_roi_limit is not None:
        if type(diagnostic_roi_limit) is not int or not 0 <= diagnostic_roi_limit <= len(rois):
            raise ValueError("diagnostic ROI limit must be an integer within the supplied ROI count")
        if diagnostic_stop_after != "roi_sampling":
            raise ValueError("diagnostic ROI limit is only valid at the ROI-sampling stop")

    def observe(name: str, **values) -> None:
        if diagnostic_step_observer is not None:
            diagnostic_step_observer(name, **values)

    def delete_temporary() -> None:
        observe("velocity_temporary_file_deletion_before", temporary_name=path.name)
        path.unlink(missing_ok=True)
        observe("velocity_temporary_file_deletion_after", temporary_name=path.name, exists=path.exists())

    observe("velocity_second_conversion_before")
    grid_data = flow.buffer_to_volume(buffer)
    observe("velocity_second_conversion_after", python_type=f"{type(grid_data).__module__}.{type(grid_data).__qualname__}")
    if diagnostic_stop_after == "conversion":
        return {"diagnostic_stop_after": "conversion"}

    observe("velocity_save_parameters_before")
    parameters = omni.volume.SaveVolumeParameters()
    parameters.flags = omni.volume.kNanoVDBCodecNone
    observe("velocity_save_parameters_after", codec="kNanoVDBCodecNone")
    observe("velocity_file_save_before", temporary_name=path.name)
    if not volume.save_volume(grid_data, str(path), parameters):
        raise RuntimeError(f"Unable to save public readback: {path}")
    observe("velocity_file_save_after", temporary_name=path.name)
    observe("velocity_file_durability_check_before", temporary_name=path.name)
    deadline = time.monotonic() + 5.0
    while (not path.is_file() or path.stat().st_size == 0) and time.monotonic() < deadline:
        time.sleep(0.01)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Public readback did not become durable within 5 s: {path}")
    observe("velocity_file_durability_check_after", temporary_name=path.name, file_bytes=int(path.stat().st_size))
    if diagnostic_stop_after == "durability":
        file_bytes = int(path.stat().st_size)
        delete_temporary()
        return {"diagnostic_stop_after": "durability", "temporary_file_bytes": file_bytes}

    handle = None
    read_error = None
    observe("velocity_file_read_before", temporary_name=path.name)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            handle = nanovdb.io.readGrid(str(path))
            break
        except RuntimeError as error:
            read_error = error
            time.sleep(0.01)
    if handle is None:
        raise RuntimeError(f"Public readback was not readable within 5 s: {path}: {read_error}")
    observe("velocity_file_read_after", python_type=f"{type(handle).__module__}.{type(handle).__qualname__}")
    if diagnostic_stop_after == "file_read":
        delete_temporary()
        return {"diagnostic_stop_after": "file_read"}

    vector = channel == "velocity"
    observe("velocity_vector_grid_access_before", vector=vector)
    grid = handle.vec3fGrid() if vector else handle.floatGrid()
    observe("velocity_vector_grid_access_after", python_type=f"{type(grid).__module__}.{type(grid).__qualname__}")
    observe("velocity_basic_metadata_before")
    voxel_size = grid.voxelSize()
    active_voxel_count = int(grid.activeVoxelCount())
    bounded_voxel_size = [_component(voxel_size, axis) for axis in range(3)]
    observe(
        "velocity_basic_metadata_after",
        active_voxel_count=active_voxel_count,
        voxel_size=bounded_voxel_size,
    )
    result = {
        "active_voxel_count": active_voxel_count,
        "voxel_size": bounded_voxel_size,
    }
    if diagnostic_stop_after == "basic_metadata":
        delete_temporary()
        return result

    result["rois"] = {}
    roi_items = list(rois.items())
    if diagnostic_roi_limit is not None:
        roi_items = roi_items[:diagnostic_roi_limit]
    for name, roi in roi_items:
        observe("velocity_roi_sampling_before", roi=name)
        sample_result = _sample_grid(grid, roi, vector)
        result["rois"][name] = sample_result
        observe(
            "velocity_roi_sampling_after",
            roi=name,
            available=bool(sample_result.get("available")),
            voxel_count=int(sample_result.get("voxel_count", 0)),
            nonzero_voxel_count=int(sample_result.get("nonzero_voxel_count", 0)),
        )
    if diagnostic_stop_after == "roi_sampling":
        delete_temporary()
        return result

    if profile_threshold is not None and "scene" in rois:
        observe("velocity_profile_before", roi="scene", threshold=float(profile_threshold))
        result["field_profile"] = _profile_grid(grid, rois["scene"], vector, profile_threshold)
        observe("velocity_profile_after", roi="scene", threshold=float(profile_threshold))
    if diagnostic_stop_after == "profile":
        delete_temporary()
        return result
    if local_rois is not None and local_to_world is not None:
        result["local_rois"] = _sample_local_grid(grid, local_rois, local_to_world, vector)
        result["alignment_rois"] = _sample_alignment_grid(
            grid, local_rois["cylinder_inside"], local_to_world, vector
        )
    if spatial_collector is not None and (not spatial_velocity_only or channel == "velocity"):
        if frame is None:
            raise RuntimeError("Phase 6EE spatial capture requires a frame")
        collectors = list(spatial_collector) if isinstance(spatial_collector, (list, tuple)) else [spatial_collector]
        neighborhoods = [
            collector.capture(grid, channel, frame, vector, nanovdb.math.Vec3d)
            for collector in collectors
        ]
        result["phase6ee_neighborhood"] = neighborhoods[0]
        if len(neighborhoods) > 1:
            result["phase6ee_additional_neighborhoods"] = neighborhoods[1:]
    delete_temporary()
    return result


def _load_phase6ee_collector():
    path = Path(__file__).with_name("phase6ee_velocity_distribution.py")
    spec = importlib.util.spec_from_file_location("campfire_phase6ee_velocity_distribution", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Phase 6EE collector: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SpatialNeighborhoodCollector


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
    spatial_collector = None
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
        "lifecycle_history": [],
        "completion_contract": {
            "results_saved": False,
            "timeline_stopped": False,
            "stage_closed": False,
            "renderer_drained": False,
            "shutdown_requested": False,
        },
        "samples": [],
        "captures": [],
        "capture_contract": {
            "start_frame": arguments["capture_start_frame"],
            "end_frame": arguments["capture_end_frame"],
            "stride": arguments["capture_stride"],
        },
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
        if arguments["phase6eg_stage_open_only"]:
            for _ in range(3):
                await app.next_update_async()
            report["measurement_gates"] = {
                "stage_connected": True,
                "source_hash_preserved": _sha256(arguments["source"])
                == preparation["source_sha256"],
                "stage_open_only": True,
            }
            report["status"] = "ok"
            report["completion_contract"]["results_saved"] = True
            report["lifecycle_marker"] = "stage_open_probe_complete"
            report["lifecycle_history"].append(
                {
                    "marker": "stage_open_probe_complete",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
            _write(output, report)
            exit_code = 0
            return
        local_rois = None
        local_to_world = None
        spatial_mesh = None
        rotated_mesh_mode = arguments["mode"] in (
            "phase6dz_rotated_mesh",
            "phase6ec_rotated_mesh",
            "phase6ec_rotated_mesh_collision_off",
        )
        box_mesh_mode = arguments["mode"] in (
            "phase6eo_box_mesh_collision_on",
            "phase6eo_box_mesh_collision_off",
        )
        if rotated_mesh_mode:
            collider = stage.GetPrimAtPath(preparation["audit_collider_path"])
            local_to_world = UsdGeom.XformCache().GetLocalToWorldTransform(collider)
            local_rois = _phase6dz_local_rois()
            report["local_roi_contract"] = {
                "coordinate_space": "qualified Cylinder local space",
                "world_to_local_sampling": True,
                "local_to_world": _matrix_list(local_to_world),
                "definitions": local_rois,
                "scalar_noise_threshold": 1.0e-6,
                "velocity_noise_threshold_m_s": 1.0e-5,
                "alignment_comparison": "transformed Cylinder versus stale axis-aligned Cylinder",
            }
        if arguments["phase6ee_spatial_enabled"]:
            if arguments["phase6ee_spatial_root"] is None or not arguments["phase6ee_condition"]:
                raise RuntimeError("Phase 6EE spatial output root and condition are required")
            if not rotated_mesh_mode and not box_mesh_mode:
                raise RuntimeError("Spatial capture requires an exact authored Mesh mode")
            collider = stage.GetPrimAtPath(preparation["audit_collider_path"])
            if local_to_world is None:
                local_to_world = UsdGeom.XformCache().GetLocalToWorldTransform(collider)
            mesh = UsdGeom.Mesh(collider)
            spatial_mesh = {
                "points": list(mesh.GetPointsAttr().Get() or ()),
                "face_counts": list(mesh.GetFaceVertexCountsAttr().Get() or ()),
                "face_indices": list(mesh.GetFaceVertexIndicesAttr().Get() or ()),
            }
            if not spatial_mesh["points"] or not spatial_mesh["face_counts"]:
                raise RuntimeError("Spatial capture requires the authored collision Mesh topology")

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
        if arguments["phase6ee_spatial_enabled"]:
            if spatial_mesh is None or local_to_world is None:
                raise RuntimeError("Spatial capture is only valid for exact authored Mesh modes")
            collector_type = _load_phase6ee_collector()
            public_members = sorted(name for name in dir(flow) if not name.startswith("_"))
            collision_mask_candidates = [
                name
                for name in public_members
                if any(term in name.lower() for term in ("collision", "mask", "occup"))
            ]
            spatial_collector = collector_type(
                arguments["phase6ee_spatial_root"],
                arguments["phase6ee_condition"],
                spatial_mesh["points"],
                spatial_mesh["face_counts"],
                spatial_mesh["face_indices"],
                _matrix_list(local_to_world),
                public_members,
            )
            report["phase6ee_public_api_audit"] = {
                "public_members": public_members,
                "public_member_count": len(public_members),
                "collision_mask_candidates": collision_mask_candidates,
                "flow_collision_occupancy_mask_readback_available": bool(collision_mask_candidates),
                "reason": (
                    "no public IFlowUsd collision/mask/occupancy member in Flow 110.0.0"
                    if not collision_mask_candidates
                    else "candidate member requires explicit semantic validation"
                ),
            }
        if numeric:
            volume = omni.volume.get_volume_interface()
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(12):
            await app.next_update_async()
        report["lifecycle_marker"] = "timeline_playing"
        timeline.play()
        _write(output, report)

        if arguments["capture"] and arguments["capture_start_frame"] > 0:
            if arguments["capture_end_frame"] < arguments["capture_start_frame"]:
                raise RuntimeError("Capture end frame precedes start frame")
            capture_frames = tuple(
                range(
                    arguments["capture_start_frame"],
                    arguments["capture_end_frame"] + 1,
                    arguments["capture_stride"],
                )
            )
        else:
            capture_frames = SAMPLE_FRAMES if arguments["capture"] else ()
        final_frame = max(SAMPLE_FRAMES[-1], capture_frames[-1] if capture_frames else 0)
        for frame in range(1, final_frame + 1):
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
                    **_save_and_sample(
                        flow,
                        volume,
                        array,
                        channel,
                        nvdb,
                        report["rois"],
                        local_rois,
                        local_to_world,
                        spatial_collector,
                        arguments["phase6ee_spatial_velocity_only"],
                        frame,
                    ),
                }
            report["samples"].append(sample)
            _write(output, report)

        if spatial_collector is not None:
            report["phase6ee_spatial"] = spatial_collector.finalize()
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
                not arguments["capture"] or len(report["captures"]) == len(capture_frames)
            ),
        }
        if not all(report["measurement_gates"].values()):
            raise RuntimeError(f"Measurement gates failed: {report['measurement_gates']}")
        report["status"] = "ok"
        report["completion_contract"]["results_saved"] = True
        report["lifecycle_marker"] = "measurement_complete"
        report["lifecycle_history"].append({"marker": "measurement_complete", "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        _write(output, report)
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
            report["completion_contract"]["timeline_stopped"] = True
            report["lifecycle_marker"] = "timeline_stopped"
            report["lifecycle_history"].append({"marker": "timeline_stopped", "timestamp_utc": datetime.now(timezone.utc).isoformat()})
            _write(output, report)
            report["lifecycle_marker"] = "stage_closing"
            await context.close_stage_async()
            for _ in range(12):
                await app.next_update_async()
            report["completion_contract"]["stage_closed"] = True
            report["completion_contract"]["renderer_drained"] = True
            report["lifecycle_marker"] = "renderer_drain_complete"
            report["lifecycle_history"].append({"marker": "renderer_drain_complete", "timestamp_utc": datetime.now(timezone.utc).isoformat()})
            _write(output, report)
            report["lifecycle_marker"] = "flow_interface_releasing"
            if flow is not None:
                _flowusd.release_flowusd_interface(flow)
                flow = None
            report["completion_contract"]["shutdown_requested"] = True
            report["lifecycle_marker"] = "shutdown_complete"
            report["lifecycle_history"].append({"marker": "shutdown_complete", "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        except Exception as shutdown_error:
            report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
            report["status"] = "error"
            exit_code = 1
        _write(output, report)
        app.post_uncancellable_quit(exit_code)


if __name__ == "__main__":
    asyncio.ensure_future(_run())
