"""Qualify a static cylindrical Mesh as a Flow 110 collision proxy.

The complete diagnostic stage is authored before it is connected to Kit.
Only public USD/PhysX APIs, Flow NanoVDB readback, omni.volume conversion,
and the bundled NanoVDB accessor are used.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import statistics
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import nanovdb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.physx
import omni.timeline
import omni.usd
import omni.volume
from omni.flowusd import _flowusd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_phase6ds_flow_collision import (  # noqa: E402
    CAMERA_FRONT,
    CAMERA_SIDE,
    CAPTURE_RESOLUTION,
    CHANNELS,
    DENSITY_CELL_SIZE_M,
    EMITTER_CENTER,
    EMITTER_RADIUS_M,
    FLOW_VERSION,
    STEPS_PER_SECOND,
    _bind,
    _capture,
    _define_camera,
    _define_flow,
    _material,
    _set,
    _translate,
)


RADIUS_M = 0.16
LENGTH_M = 1.8
SEGMENTS = 12
CENTER_M = Gf.Vec3d(0.0, 0.0, 1.0)
EXPECTED_VELOCITY_CELL_M = 0.05
SAMPLE_FRAMES = (60, 90, 120, 150, 180)
CAPTURE_FRAMES = (90, 120, 150, 180)
FORMAL_MODES = frozenset(
    (
        "primitive",
        "mesh_none",
        "mesh_hull",
        "mesh_decomposition",
        "mesh_hull_flow_off",
        "mesh_hull_yaw37",
        "mesh_hull_yaw53",
        "mesh_hull_3d",
        "coexist_both",
        "coexist_proxy_disabled",
        "proxy_disabled_only",
        "render_surface_hull",
    )
)


def _settings() -> dict:
    settings = carb.settings.get_settings()
    mode = settings.get_as_string("/phase6du/mode") or "primitive"
    if mode not in FORMAL_MODES:
        raise RuntimeError(f"Unsupported Phase 6DU mode: {mode}")
    return {
        "output": Path(settings.get_as_string("/phase6du/output")).resolve(),
        "mode": mode,
        "run_index": int(settings.get_as_int("/phase6du/runIndex")) or 1,
        "capture": bool(settings.get_as_bool("/phase6du/capture")),
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


def _mode_contract(mode: str) -> dict:
    result = {
        "yaw_deg": 0.0,
        "pitch_deg": 0.0,
        "flow_collision_enabled": mode != "mesh_hull_flow_off",
        "analytic_collision": mode in ("primitive", "coexist_both", "coexist_proxy_disabled"),
        "proxy_collision": mode not in ("primitive", "mesh_none", "render_surface_hull"),
        "proxy_collision_enabled": mode != "coexist_proxy_disabled" and mode != "proxy_disabled_only",
        "render_surface_collision": mode == "render_surface_hull",
        "approximation": None,
    }
    if mode in (
        "mesh_hull",
        "mesh_hull_flow_off",
        "mesh_hull_yaw37",
        "mesh_hull_yaw53",
        "mesh_hull_3d",
        "coexist_both",
        "coexist_proxy_disabled",
        "proxy_disabled_only",
        "render_surface_hull",
    ):
        result["approximation"] = "convexHull"
    elif mode == "mesh_decomposition":
        result["approximation"] = "convexDecomposition"
    if mode == "mesh_hull_yaw37":
        result["yaw_deg"] = 37.0
    elif mode == "mesh_hull_yaw53":
        result["yaw_deg"] = 53.0
    elif mode == "mesh_hull_3d":
        result["yaw_deg"] = 37.0
        result["pitch_deg"] = 4.0
    return result


def _cylinder_topology() -> tuple[list, list[int], list[int]]:
    points = []
    half = LENGTH_M * 0.5
    for x in (-half, half):
        for segment in range(SEGMENTS):
            angle = 2.0 * math.pi * segment / SEGMENTS
            points.append(Gf.Vec3f(x, RADIUS_M * math.cos(angle), RADIUS_M * math.sin(angle)))
    left_center = len(points)
    points.append(Gf.Vec3f(-half, 0.0, 0.0))
    right_center = len(points)
    points.append(Gf.Vec3f(half, 0.0, 0.0))
    counts = []
    indices = []
    for segment in range(SEGMENTS):
        following = (segment + 1) % SEGMENTS
        counts.append(4)
        indices.extend((segment, following, SEGMENTS + following, SEGMENTS + segment))
    for segment in range(SEGMENTS):
        following = (segment + 1) % SEGMENTS
        counts.append(3)
        indices.extend((left_center, following, segment))
        counts.append(3)
        indices.extend((right_center, SEGMENTS + segment, SEGMENTS + following))
    return points, counts, indices


def _topology_audit(points, counts, indices) -> dict:
    finite = all(math.isfinite(float(component)) for point in points for component in point)
    cursor = 0
    edge_counts: dict[tuple[int, int], int] = {}
    areas = []
    outward = []
    for count in counts:
        face = indices[cursor : cursor + count]
        cursor += count
        origin = Gf.Vec3d(points[face[0]])
        area_vector = Gf.Vec3d(0.0)
        for index in range(1, count - 1):
            a = Gf.Vec3d(points[face[index]]) - origin
            b = Gf.Vec3d(points[face[index + 1]]) - origin
            area_vector += Gf.Cross(a, b) * 0.5
        area = area_vector.GetLength()
        areas.append(area)
        center = sum((Gf.Vec3d(points[index]) for index in face), Gf.Vec3d(0.0)) / count
        if abs(center[0]) > LENGTH_M * 0.49:
            expected = Gf.Vec3d(math.copysign(1.0, center[0]), 0.0, 0.0)
        else:
            expected = Gf.Vec3d(0.0, center[1], center[2]).GetNormalized()
        outward.append(Gf.Dot(area_vector, expected) > 0.0)
        for offset, start in enumerate(face):
            end = face[(offset + 1) % count]
            edge = tuple(sorted((start, end)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    extent_min = [min(float(point[axis]) for point in points) for axis in range(3)]
    extent_max = [max(float(point[axis]) for point in points) for axis in range(3)]
    return {
        "vertex_count": len(points),
        "face_count": len(counts),
        "index_count": len(indices),
        "finite": finite,
        "minimum_face_area_m2": min(areas),
        "degenerate_face_count": sum(area <= 1.0e-10 for area in areas),
        "unique_edge_count": len(edge_counts),
        "nonmanifold_or_open_edge_count": sum(count != 2 for count in edge_counts.values()),
        "closed_manifold": bool(edge_counts) and all(count == 2 for count in edge_counts.values()),
        "outward_winding": all(outward),
        "extent_min_m": extent_min,
        "extent_max_m": extent_max,
        "expected_extent_min_m": [-LENGTH_M * 0.5, -RADIUS_M, -RADIUS_M],
        "expected_extent_max_m": [LENGTH_M * 0.5, RADIUS_M, RADIUS_M],
    }


def _define_mesh(stage: Usd.Stage, path: str, visible: bool) -> tuple[UsdGeom.Mesh, dict]:
    points, counts, indices = _cylinder_topology()
    audit = _topology_audit(points, counts, indices)
    if not (
        audit["finite"]
        and audit["closed_manifold"]
        and audit["outward_winding"]
        and audit["degenerate_face_count"] == 0
    ):
        raise RuntimeError(f"Invalid cylindrical Mesh topology: {audit}")
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(False)
    mesh.CreateExtentAttr(
        [
            Gf.Vec3f(-LENGTH_M * 0.5, -RADIUS_M, -RADIUS_M),
            Gf.Vec3f(LENGTH_M * 0.5, RADIUS_M, RADIUS_M),
        ]
    )
    mesh.CreateVisibilityAttr(UsdGeom.Tokens.inherited if visible else UsdGeom.Tokens.invisible)
    return mesh, audit


def _apply_mesh_collision(prim: Usd.Prim, approximation: str, enabled: bool = True) -> None:
    if not UsdPhysics.CollisionAPI.Apply(prim):
        raise RuntimeError(f"CollisionAPI.Apply failed: {prim.GetPath()}")
    if not UsdPhysics.MeshCollisionAPI.Apply(prim):
        raise RuntimeError(f"MeshCollisionAPI.Apply failed: {prim.GetPath()}")
    UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr(enabled)
    UsdPhysics.MeshCollisionAPI(prim).CreateApproximationAttr(approximation)


def _root_transform(root: UsdGeom.Xform, yaw_deg: float, pitch_deg: float) -> None:
    xform = UsdGeom.Xformable(root.GetPrim())
    xform.AddTranslateOp().Set(CENTER_M)
    if yaw_deg:
        xform.AddRotateZOp().Set(yaw_deg)
    if pitch_deg:
        xform.AddRotateYOp().Set(pitch_deg)


def _signed_distance_local_cylinder(point: Gf.Vec3d) -> float:
    axial = abs(point[0]) - LENGTH_M * 0.5
    radial = math.hypot(point[1], point[2]) - RADIUS_M
    outside = math.hypot(max(axial, 0.0), max(radial, 0.0))
    return outside + min(max(axial, radial), 0.0)


def _matrix_list(matrix: Gf.Matrix4d) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _build_stage(path: Path, mode: str) -> dict:
    contract = _mode_contract(mode)
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Cameras")
    UsdGeom.Xform.Define(stage, "/World/Materials")
    UsdGeom.Xform.Define(stage, "/World/Lights")
    physics = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    physics.CreateGravityMagnitudeAttr(9.81)
    collider_material = _material(stage, "/World/Materials/Collider", (0.08, 0.28, 0.40), 0.35)
    ground_material = _material(stage, "/World/Materials/Ground", (0.045, 0.05, 0.06), 0.8)

    log = UsdGeom.Xform.Define(stage, "/World/Log")
    _root_transform(log, contract["yaw_deg"], contract["pitch_deg"])
    analytic = UsdGeom.Cylinder.Define(stage, "/World/Log/AnalyticCollider")
    analytic.CreateAxisAttr(UsdGeom.Tokens.x)
    analytic.CreateRadiusAttr(RADIUS_M)
    analytic.CreateHeightAttr(LENGTH_M)
    analytic.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
    if contract["analytic_collision"]:
        UsdPhysics.CollisionAPI.Apply(analytic.GetPrim()).CreateCollisionEnabledAttr(True)

    render, render_audit = _define_mesh(stage, "/World/Log/RenderSurface", True)
    render.CreateDisplayColorAttr([Gf.Vec3f(0.08, 0.28, 0.40)])
    render.CreateDisplayOpacityAttr([1.0])
    _bind(render.GetPrim(), collider_material)
    if contract["render_surface_collision"]:
        _apply_mesh_collision(render.GetPrim(), "convexHull", True)

    proxy, proxy_audit = _define_mesh(stage, "/World/Log/FlowCollisionProxy", False)
    if contract["proxy_collision"]:
        _apply_mesh_collision(
            proxy.GetPrim(),
            contract["approximation"],
            contract["proxy_collision_enabled"],
        )

    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground_xform = UsdGeom.Xformable(ground.GetPrim())
    ground_xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.04))
    ground_xform.AddScaleOp().Set(Gf.Vec3f(4.5, 4.5, 0.08))
    _bind(ground.GetPrim(), ground_material)
    _define_camera(stage, CAMERA_FRONT, (2.65, -4.2, 2.35), (0.0, 0.0, 1.0))
    _define_camera(stage, CAMERA_SIDE, (4.2, 0.0, 1.8), (0.0, 0.0, 1.0))
    from pxr import UsdLux

    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(380.0)
    dome.CreateColorAttr(Gf.Vec3f(0.18, 0.23, 0.32))
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(18000.0)
    key.CreateRadiusAttr(0.25)
    key.CreateColorAttr(Gf.Vec3f(1.0, 0.34, 0.10))
    _translate(key.GetPrim(), (-1.2, -1.4, 3.0))
    _define_flow(stage, contract["flow_collision_enabled"])
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(float(SAMPLE_FRAMES[-1]))
    stage.SetTimeCodesPerSecond(STEPS_PER_SECOND)
    stage.GetRootLayer().customLayerData = {
        "campfire:phase": "phase6du",
        "campfire:defaultOff": True,
        "campfire:flowVersion": FLOW_VERSION,
        "campfire:stageBuiltBeforeConnection": True,
    }

    cache = UsdGeom.XformCache()
    root_matrix = cache.GetLocalToWorldTransform(log.GetPrim())
    analytic_matrix = cache.GetLocalToWorldTransform(analytic.GetPrim())
    proxy_matrix = cache.GetLocalToWorldTransform(proxy.GetPrim())
    render_matrix = cache.GetLocalToWorldTransform(render.GetPrim())
    world_to_local = root_matrix.GetInverse()
    emitter_local = world_to_local.Transform(Gf.Vec3d(*EMITTER_CENTER))
    emitter_gap = _signed_distance_local_cylinder(emitter_local) - EMITTER_RADIUS_M
    if emitter_gap < 2.0 * EXPECTED_VELOCITY_CELL_M:
        raise RuntimeError(f"Emitter gap is below two expected velocity cells: {emitter_gap}")
    matrices_match = analytic_matrix == proxy_matrix and proxy_matrix == render_matrix
    if not matrices_match:
        raise RuntimeError("Analytic, render, and proxy world transforms differ")
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save Phase 6DU stage: {path}")
    return {
        "contract": contract,
        "radius_m": RADIUS_M,
        "length_m": LENGTH_M,
        "axis": "X",
        "segments": SEGMENTS,
        "proxy_topology": proxy_audit,
        "render_topology": render_audit,
        "root_world_transform": _matrix_list(root_matrix),
        "analytic_world_transform": _matrix_list(analytic_matrix),
        "proxy_world_transform": _matrix_list(proxy_matrix),
        "render_world_transform": _matrix_list(render_matrix),
        "world_transforms_match": matrices_match,
        "emitter_center_world_m": list(EMITTER_CENTER),
        "emitter_center_local_m": list(emitter_local),
        "emitter_radius_m": EMITTER_RADIUS_M,
        "emitter_signed_distance_m": _signed_distance_local_cylinder(emitter_local),
        "emitter_surface_gap_m": emitter_gap,
        "emitter_outside": emitter_gap > 0.0,
    }


def _roi_definitions(cell: float = EXPECTED_VELOCITY_CELL_M) -> dict:
    half = LENGTH_M * 0.5
    return {
        "below": {"local_min": [-0.35, -0.12, -RADIUS_M - 0.20], "local_max": [0.35, 0.12, -RADIUS_M - cell]},
        "inside": {"local_min": [-0.75, -RADIUS_M, -RADIUS_M], "local_max": [0.75, RADIUS_M, RADIUS_M]},
        "inside_core": {"local_min": [-0.65, -RADIUS_M + cell, -RADIUS_M + cell], "local_max": [0.65, RADIUS_M - cell, RADIUS_M - cell]},
        "inside_side_center": {"local_min": [-0.35, RADIUS_M - cell, -0.10], "local_max": [0.35, RADIUS_M, 0.10]},
        "inside_end": {"local_min": [half - 3.0 * cell, -RADIUS_M + cell, -RADIUS_M + cell], "local_max": [half - cell, RADIUS_M - cell, RADIUS_M - cell]},
        "above": {"local_min": [-0.35, -0.12, RADIUS_M], "local_max": [0.35, 0.12, RADIUS_M + 0.20]},
        "above_far": {"local_min": [-0.35, -0.12, RADIUS_M + cell], "local_max": [0.35, 0.12, RADIUS_M + 0.42]},
        "side_outside": {"local_min": [-0.35, RADIUS_M + cell, -0.12], "local_max": [0.35, RADIUS_M + 0.28, 0.12]},
    }


def _component(value, index: int) -> float:
    try:
        return float(value[index])
    except TypeError:
        return float((value.x, value.y, value.z)[index])


def _local_roi_contains(name: str, local: Gf.Vec3d, bounds: dict) -> bool:
    if not all(bounds["local_min"][axis] <= local[axis] <= bounds["local_max"][axis] for axis in range(3)):
        return False
    radial = math.hypot(local[1], local[2])
    if name in ("inside", "inside_core", "inside_end"):
        return radial <= RADIUS_M
    return True


def _world_aabb(bounds: dict, local_to_world: Gf.Matrix4d) -> tuple[list[float], list[float]]:
    corners = []
    for x in (bounds["local_min"][0], bounds["local_max"][0]):
        for y in (bounds["local_min"][1], bounds["local_max"][1]):
            for z in (bounds["local_min"][2], bounds["local_max"][2]):
                corners.append(local_to_world.Transform(Gf.Vec3d(x, y, z)))
    return (
        [min(point[axis] for point in corners) for axis in range(3)],
        [max(point[axis] for point in corners) for axis in range(3)],
    )


def _sample_grid(grid, rois: dict, local_to_world: Gf.Matrix4d, vector: bool) -> dict:
    world_to_local = local_to_world.GetInverse()
    accessor = grid.getAccessor()
    results = {}
    for name, bounds in rois.items():
        minimum, maximum = _world_aabb(bounds, local_to_world)
        lo = grid.applyInverseMap(nanovdb.math.Vec3d(*minimum))
        hi = grid.applyInverseMap(nanovdb.math.Vec3d(*maximum))
        index_min = [math.floor(min(_component(lo, i), _component(hi, i))) - 1 for i in range(3)]
        index_max = [math.ceil(max(_component(lo, i), _component(hi, i))) + 1 for i in range(3)]
        values = []
        for i in range(index_min[0], index_max[0] + 1):
            for j in range(index_min[1], index_max[1] + 1):
                for k in range(index_min[2], index_max[2] + 1):
                    world = grid.applyMap(nanovdb.math.Vec3d(float(i), float(j), float(k)))
                    point = Gf.Vec3d(*[_component(world, axis) for axis in range(3)])
                    if not _local_roi_contains(name, world_to_local.Transform(point), bounds):
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


def _save_and_sample(flow, volume, buffer, channel: str, path: Path, rois: dict, matrix: Gf.Matrix4d) -> dict:
    grid_data = flow.buffer_to_volume(buffer)
    parameters = omni.volume.SaveVolumeParameters()
    parameters.flags = omni.volume.kNanoVDBCodecNone
    if not volume.save_volume(grid_data, str(path), parameters):
        raise RuntimeError(f"Unable to save public NanoVDB readback: {path}")
    handle = nanovdb.io.readGrid(str(path))
    vector = channel == "velocity"
    grid = handle.vec3fGrid() if vector else handle.floatGrid()
    voxel_size = grid.voxelSize()
    result = {
        "active_voxel_count": int(grid.activeVoxelCount()),
        "voxel_size_m": [_component(voxel_size, axis) for axis in range(3)],
        "rois": _sample_grid(grid, rois, matrix, vector),
    }
    path.unlink(missing_ok=True)
    return result


def _extension_inventory(app) -> dict:
    manager = app.get_extension_manager()
    result = {}
    for name in ("omni.flowusd", "omni.physx", "omni.physx.cooking", "omni.physx.stageupdate", "omni.hydra.rtx"):
        extension_id = manager.get_enabled_extension_id(name)
        metadata = manager.get_extension_dict(extension_id) if extension_id else None
        result[name] = {
            "enabled": bool(extension_id),
            "enabled_id": extension_id or None,
            "version": (metadata or {}).get("package", {}).get("version"),
        }
    return result


def _scene_query_probe() -> dict:
    result = {"public_interface_available": False, "executed": False, "hits": [], "error": None}
    getter = getattr(omni.physx, "get_physx_scene_query_interface", None)
    if getter is None:
        result["error"] = "omni.physx.get_physx_scene_query_interface unavailable"
        return result
    interface = getter()
    result["public_interface_available"] = interface is not None
    result["available_methods"] = [name for name in dir(interface) if "overlap" in name or "raycast" in name]
    method = getattr(interface, "overlap_box", None)
    result["overlap_box_doc"] = inspect.getdoc(method) if method else None
    if method is None:
        result["error"] = "public overlap_box unavailable"
        return result
    hits = []

    def _hit(hit):
        hits.append({key: str(value) for key, value in dict(hit).items()})
        return True

    try:
        count = method(
            carb.Float3(0.30, 0.30, 0.30),
            carb.Float3(*CENTER_M),
            carb.Float4(0.0, 0.0, 0.0, 1.0),
            _hit,
            False,
        )
        result.update({"executed": True, "reported_hit_count": int(count), "hits": hits})
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


async def _run() -> None:
    arguments = _settings()
    output = arguments["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".scene.usda")
    frames_dir = output.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    flow = None
    volume = None
    report = {
        "schema": "campfire.phase6du.static-cylinder-collision-run.v1",
        "phase": "phase6du",
        "status": "running",
        "default_off": True,
        "production_code_changed": False,
        "mode": arguments["mode"],
        "run_index": arguments["run_index"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_marker": "starting",
        "samples": [],
        "captures": [],
    }
    _write(output, report)
    exit_code = 1
    try:
        report["lifecycle_marker"] = "authoring_complete_stage"
        report["geometry"] = _build_stage(stage_path, arguments["mode"])
        report["stage_sha256"] = _sha256(stage_path)
        report["rois"] = _roi_definitions()
        report["extensions"] = _extension_inventory(app)
        report["kit_build"] = str(getattr(app, "get_build_version", lambda: "unavailable")())
        _write(output, report)
        report["lifecycle_marker"] = "opening_prebuilt_stage"
        _write(output, report)
        opened = time.perf_counter()
        await context.open_stage_async(str(stage_path))
        report["stage_open_ms"] = (time.perf_counter() - opened) * 1000.0
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Phase 6DU stage did not connect")
        simulate = stage.GetPrimAtPath("/World/Flow/Simulate")
        report["flow_settings"] = {
            name: simulate.GetAttribute(name).Get()
            for name in (
                "densityCellSize",
                "physicsCollisionEnabled",
                "physicsConvexCollision",
                "stepsPerSecond",
                "velocitySubSteps",
            )
        }
        expected_collision = _mode_contract(arguments["mode"])["flow_collision_enabled"]
        if bool(report["flow_settings"]["physicsCollisionEnabled"]) != expected_collision:
            raise RuntimeError("Effective Flow collision flag differs from request")

        viewport = None
        for _ in range(180):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport for Phase 6DU")
        viewport.camera_path = CAMERA_FRONT
        viewport.fill_frame = False
        viewport.resolution = CAPTURE_RESOLUTION
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
                break

        flow = _flowusd.acquire_flowusd_interface()
        volume = omni.volume.get_volume_interface()
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(12):
            await app.next_update_async()
        report["scene_query"] = _scene_query_probe()
        report["lifecycle_marker"] = "timeline_playing"
        timeline.play()
        _write(output, report)
        matrix = UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath("/World/Log"))
        rois = _roi_definitions()
        for frame in range(1, SAMPLE_FRAMES[-1] + 1):
            await app.next_update_async()
            if arguments["capture"] and frame in CAPTURE_FRAMES:
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                path = frames_dir / f"{arguments['mode']}_r{arguments['run_index']}_{frame:04d}.png"
                report["captures"].append({"frame": frame, "camera": "front", **(await _capture(viewport, path))})
            if frame not in SAMPLE_FRAMES:
                continue
            raw = flow.get_latest_nanovdb_readback()
            if len(raw) < len(CHANNELS):
                raise RuntimeError(f"Expected {len(CHANNELS)} readback buffers, got {len(raw)}")
            sample = {"frame": frame, "active_blocks": int(flow.get_active_block_count()), "channels": {}}
            for index, channel in enumerate(CHANNELS):
                array = np.asarray(raw[index])
                if array.size == 0:
                    sample["channels"][channel] = {"available": False, "reason": "empty public readback buffer"}
                    continue
                path = output.parent / f"sample_{frame}_{channel}.nvdb"
                sample["channels"][channel] = {
                    "available": True,
                    "word_count": int(array.size),
                    **_save_and_sample(flow, volume, array, channel, path, rois, matrix),
                }
            velocity = sample["channels"].get("velocity", {})
            if velocity.get("available"):
                report["velocity_cell_size_m"] = float(velocity["voxel_size_m"][0])
            report["samples"].append(sample)
            _write(output, report)

        if arguments["capture"]:
            timeline.pause()
            for camera_name, camera_path in (("front", CAMERA_FRONT), ("side", CAMERA_SIDE)):
                viewport.camera_path = camera_path
                for _ in range(12):
                    await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                path = frames_dir / f"{arguments['mode']}_r{arguments['run_index']}_final_{camera_name}.png"
                report["captures"].append({"frame": SAMPLE_FRAMES[-1], "camera": camera_name, **(await _capture(viewport, path))})

        topology = report["geometry"]["proxy_topology"]
        velocity_cell = report.get("velocity_cell_size_m", 0.0)
        report["measurement_gates"] = {
            "complete_stage_built_before_connection": True,
            "closed_manifold": topology["closed_manifold"],
            "outward_winding": topology["outward_winding"],
            "finite_non_degenerate": topology["finite"] and topology["degenerate_face_count"] == 0,
            "world_transforms_match": report["geometry"]["world_transforms_match"],
            "emitter_outside": report["geometry"]["emitter_outside"],
            "emitter_gap_two_velocity_cells": velocity_cell > 0.0 and report["geometry"]["emitter_surface_gap_m"] >= 2.0 * velocity_cell,
            "five_time_samples": len(report["samples"]) == len(SAMPLE_FRAMES),
            "active_blocks_nonzero": max(sample["active_blocks"] for sample in report["samples"]) > 0,
            "scalar_readback_available": all(
                sample["channels"][name].get("available", False)
                for sample in report["samples"]
                for name in ("temperature", "fuel", "burn", "smoke", "divergence")
            ),
            "velocity_readback_available": all(sample["channels"]["velocity"].get("available", False) for sample in report["samples"]),
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
