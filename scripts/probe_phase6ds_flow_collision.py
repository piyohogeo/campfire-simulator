"""Measure Flow 110 static-collider occlusion in an isolated, default-off scene.

The complete USD stage is authored before it is connected to Kit.  Numeric
sampling uses only the public Flow readback, omni.volume conversion, and the
NanoVDB Python accessor shipped with the fixed Kit build.
"""

from __future__ import annotations

import asyncio
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
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


FLOW_VERSION = "110.0.0"
DENSITY_CELL_SIZE_M = 0.025
STEPS_PER_SECOND = 60.0
BOX_CENTER_Z_M = 1.0
BOX_DIMENSIONS_M = (2.0, 2.0, 0.25)
EMITTER_CENTER = (0.0, 0.0, 0.55)
EMITTER_RADIUS_M = 0.10
CAPTURE_RESOLUTION = (1280, 720)
CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
SCALAR_CHANNELS = frozenset(("temperature", "fuel", "burn", "smoke", "divergence"))
SAMPLE_FRAMES = (60, 90, 120, 150, 180)
CAPTURE_FRAMES = (90, 120, 150, 180)
CAMERA_FRONT = Sdf.Path("/World/Cameras/Front")
CAMERA_SIDE = Sdf.Path("/World/Cameras/Side")


def _settings() -> dict:
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phase6ds/output")).resolve(),
        "condition": settings.get_as_string("/phase6ds/condition") or "collision_off",
        "collision_enabled": bool(settings.get_as_bool("/phase6ds/collisionEnabled")),
        "box_shift_m": float(settings.get_as_float("/phase6ds/boxShiftM")),
        "capture": bool(settings.get_as_bool("/phase6ds/capture")),
        "run_index": int(settings.get_as_int("/phase6ds/runIndex")) or 1,
    }


def _write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _set(prim: Usd.Prim, name: str, value) -> None:
    attribute = prim.GetAttribute(name)
    if not attribute:
        raise RuntimeError(f"Missing Flow attribute: {prim.GetPath()}.{name}")
    if not attribute.Set(value):
        raise RuntimeError(f"Flow attribute Set failed: {prim.GetPath()}.{name}")


def _translate(prim: Usd.Prim, value) -> None:
    UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3d(*value))


def _material(stage: Usd.Stage, path: str, color, roughness: float = 0.55):
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def _bind(prim: Usd.Prim, material: UsdShade.Material) -> None:
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)


def _define_camera(stage: Usd.Stage, path: Sdf.Path, eye, target) -> None:
    camera = UsdGeom.Camera.Define(stage, path)
    camera.CreateFocalLengthAttr(46.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
    matrix = Gf.Matrix4d(1.0)
    matrix.SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0.0, 0.0, 1.0))
    camera.AddTransformOp().Set(matrix.GetInverse())


def _define_flow(stage: Usd.Stage, collision_enabled: bool) -> None:
    root = Sdf.Path("/World/Flow")
    simulate_path = root.AppendChild("Simulate")
    UsdGeom.Xform.Define(stage, root)
    emitter = stage.DefinePrim(root.AppendChild("Emitter"), "FlowEmitterSphere")
    for name, value in (
        ("layer", 0),
        ("enabled", True),
        ("position", Gf.Vec3f(*EMITTER_CENTER)),
        ("radius", EMITTER_RADIUS_M),
        ("radiusIsWorldSpace", True),
        ("allocationScale", 1.5),
        ("multisample", True),
        ("numSubSteps", 2),
        ("temperature", 2.0),
        ("coupleRateTemperature", 10.0),
        ("fuel", 0.8),
        ("coupleRateFuel", 2.0),
        ("smoke", 0.04),
        ("coupleRateSmoke", 1.0),
        ("velocity", Gf.Vec3f(0.0, 0.0, 0.30)),
        ("velocityIsWorldSpace", True),
        ("coupleRateVelocity", 2.0),
    ):
        _set(emitter, name, value)

    simulate = stage.DefinePrim(simulate_path, "FlowSimulate")
    for name, value in (
        ("layer", 0),
        ("densityCellSize", DENSITY_CELL_SIZE_M),
        ("blockMinLifetime", 4),
        ("enableVariableTimeStep", False),
        ("forceDisableCoreSimulation", False),
        ("forceDisableEmitters", False),
        ("forceSimulate", True),
        ("simulateWhenPaused", False),
        ("maxStepsPerSimulate", 1),
        ("physicsCollisionEnabled", collision_enabled),
        ("physicsConvexCollision", True),
        ("stepsPerSecond", STEPS_PER_SECOND),
        ("velocitySubSteps", 1),
    ):
        _set(simulate, name, value)

    advection = stage.DefinePrim(
        simulate_path.AppendChild("advection"), "FlowAdvectionCombustionParams"
    )
    for name, value in (
        ("enabled", True),
        ("combustionEnabled", True),
        ("buoyancyPerTemp", 6.0),
        ("burnPerTemp", 4.0),
        ("coolingRate", 1.5),
        ("fuelPerBurn", 0.25),
        ("gravity", Gf.Vec3f(0.0, 0.0, -9.81)),
        ("ignitionTemp", 0.05),
        ("smokePerBurn", 3.0),
        ("tempPerBurn", 5.0),
    ):
        _set(advection, name, value)
    for channel_name in CHANNELS:
        channel = stage.DefinePrim(
            advection.GetPath().AppendChild(channel_name),
            "FlowAdvectionChannelParams",
        )
        _set(channel, "secondOrderBlendFactor", 0.9)
        if channel_name == "smoke":
            _set(channel, "damping", 0.3)
            _set(channel, "fade", 2.0)
        elif channel_name in ("velocity", "divergence"):
            _set(channel, "damping", 0.01)
            _set(channel, "fade", 1.0)

    vorticity = stage.DefinePrim(
        simulate_path.AppendChild("vorticity"), "FlowVorticityParams"
    )
    _set(vorticity, "enabled", True)
    _set(vorticity, "forceScale", 1.5)
    _set(vorticity, "velocityMask", 1.0)
    pressure = stage.DefinePrim(
        simulate_path.AppendChild("pressure"), "FlowPressureParams"
    )
    _set(pressure, "enabled", True)
    allocation = stage.DefinePrim(
        simulate_path.AppendChild("summaryAllocate"), "FlowSummaryAllocateParams"
    )
    _set(allocation, "enableNeighborAllocation", True)
    _set(allocation, "smokeThreshold", 0.02)
    _set(allocation, "speedThreshold", 1.0)
    export = stage.DefinePrim(
        simulate_path.AppendChild("nanoVdbExport"), "FlowSparseNanoVdbExportParams"
    )
    for name, value in (
        ("enabled", True),
        ("temperatureEnabled", True),
        ("fuelEnabled", True),
        ("burnEnabled", True),
        ("smokeEnabled", True),
        ("velocityEnabled", True),
        ("statisticsEnabled", True),
        ("readbackEnabled", True),
    ):
        _set(export, name, value)

    offscreen = stage.DefinePrim(root.AppendChild("Offscreen"), "FlowOffscreen")
    _set(offscreen, "layer", 0)
    colormap = stage.DefinePrim(
        offscreen.GetPath().AppendChild("colormap"), "FlowRayMarchColormapParams"
    )
    _set(colormap, "colorScale", 2.5)
    _set(colormap, "resolution", 32)
    _set(colormap, "xPoints", [0.0, 0.05, 0.15, 0.6, 0.85, 1.0])
    _set(colormap, "colorScalePoints", [1.0] * 6)
    _set(
        colormap,
        "rgbaPoints",
        [
            Gf.Vec4f(0.0154, 0.0177, 0.0154, 0.004902),
            Gf.Vec4f(0.03575, 0.03575, 0.03575, 0.504902),
            Gf.Vec4f(0.03575, 0.03575, 0.03575, 0.504902),
            Gf.Vec4f(1.0, 0.1594, 0.0134, 0.8),
            Gf.Vec4f(13.53, 2.99, 0.12599, 0.8),
            Gf.Vec4f(78.0, 39.0, 6.1, 0.7),
        ],
    )
    shadow = stage.DefinePrim(
        offscreen.GetPath().AppendChild("shadow"), "FlowShadowParams"
    )
    _set(shadow, "enabled", True)
    _set(shadow, "attenuation", 0.045)
    _set(shadow, "coarsePropagate", True)
    _set(shadow, "lightDirection", Gf.Vec3f(1.0, 1.0, 1.0))
    render = stage.DefinePrim(root.AppendChild("Render"), "FlowRender")
    _set(render, "layer", 0)
    ray_march = stage.DefinePrim(
        render.GetPath().AppendChild("rayMarch"), "FlowRayMarchParams"
    )
    _set(ray_march, "attenuation", 0.05)
    _set(ray_march, "colorScale", 1.0)
    _set(ray_march, "shadowFactor", 1.0)
    _set(ray_march, "stepSizeScale", 0.75)


def _build_stage(path: Path, collision_enabled: bool, shift_m: float) -> dict:
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Cameras")
    UsdGeom.Xform.Define(stage, "/World/Materials")

    physics = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    physics.CreateGravityMagnitudeAttr(9.81)

    collider_material = _material(stage, "/World/Materials/Collider", (0.06, 0.22, 0.38), 0.35)
    ground_material = _material(stage, "/World/Materials/Ground", (0.045, 0.05, 0.06), 0.8)
    box = UsdGeom.Cube.Define(stage, "/World/Collider")
    box.CreateSizeAttr(1.0)
    box.CreateDisplayColorAttr([Gf.Vec3f(0.06, 0.22, 0.38)])
    box.CreateDisplayOpacityAttr([1.0])
    xform = UsdGeom.Xformable(box.GetPrim())
    xform.AddTranslateOp().Set(Gf.Vec3d(shift_m, 0.0, BOX_CENTER_Z_M))
    xform.AddScaleOp().Set(Gf.Vec3f(*BOX_DIMENSIONS_M))
    collision = UsdPhysics.CollisionAPI.Apply(box.GetPrim())
    collision.CreateCollisionEnabledAttr(True)
    _bind(box.GetPrim(), collider_material)

    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground_xform = UsdGeom.Xformable(ground.GetPrim())
    ground_xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.04))
    ground_xform.AddScaleOp().Set(Gf.Vec3f(4.5, 4.5, 0.08))
    _bind(ground.GetPrim(), ground_material)

    _define_camera(stage, CAMERA_FRONT, (2.65, -4.2, 2.35), (0.0, 0.0, 1.05))
    _define_camera(stage, CAMERA_SIDE, (4.2, 0.0, 1.8), (0.0, 0.0, 1.05))
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(380.0)
    dome.CreateColorAttr(Gf.Vec3f(0.18, 0.23, 0.32))
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(18000.0)
    key.CreateRadiusAttr(0.25)
    key.CreateColorAttr(Gf.Vec3f(1.0, 0.34, 0.10))
    _translate(key.GetPrim(), (-1.2, -1.4, 3.0))
    _define_flow(stage, collision_enabled)
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(float(SAMPLE_FRAMES[-1]))
    stage.SetTimeCodesPerSecond(STEPS_PER_SECOND)
    stage.GetRootLayer().customLayerData = {
        "campfire:phase": "phase6ds",
        "campfire:defaultOff": True,
        "campfire:flowVersion": FLOW_VERSION,
        "campfire:stageBuiltBeforeConnection": True,
        "renderSettings": {
            "rtx:flow:enabled": True,
            "rtx:flow:pathTracingEnabled": True,
            "rtx:flow:rayTracedReflectionsEnabled": True,
            "rtx:flow:rayTracedTranslucencyEnabled": True,
        },
    }
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save Phase 6DS stage: {path}")
    half = tuple(value * 0.5 for value in BOX_DIMENSIONS_M)
    emitter_box_distance = BOX_CENTER_Z_M - half[2] - (EMITTER_CENTER[2] + EMITTER_RADIUS_M)
    return {
        "collider_path": str(box.GetPath()),
        "type": "UsdGeomCube + UsdPhysics.CollisionAPI",
        "rigid_body": False,
        "dimensions_m": list(BOX_DIMENSIONS_M),
        "center_m": [shift_m, 0.0, BOX_CENTER_Z_M],
        "axis_aligned": True,
        "collision_api_applied": box.GetPrim().HasAPI(UsdPhysics.CollisionAPI),
        "collision_enabled_attr": bool(collision.GetCollisionEnabledAttr().Get()),
        "emitter_center_m": list(EMITTER_CENTER),
        "emitter_radius_m": EMITTER_RADIUS_M,
        "emitter_minimum_distance_m": emitter_box_distance,
        "emitter_samples_outside_analytical_box": emitter_box_distance > 0.0,
    }


def _roi_definitions(velocity_cell_m: float | None = None) -> dict:
    # The core/far regions stay at least one expected 0.05 m velocity cell from
    # the relevant collider surface.  The recorded effective size verifies it.
    half_z = BOX_DIMENSIONS_M[2] * 0.5
    bottom = BOX_CENTER_Z_M - half_z
    top = BOX_CENTER_Z_M + half_z
    return {
        "below": {"minimum": [-0.30, -0.30, 0.67], "maximum": [0.30, 0.30, 0.80]},
        "inside": {"minimum": [-0.30, -0.30, bottom], "maximum": [0.30, 0.30, top]},
        "inside_core": {"minimum": [-0.30, -0.30, bottom + 0.055], "maximum": [0.30, 0.30, top - 0.055]},
        "above": {"minimum": [-0.30, -0.30, top], "maximum": [0.30, 0.30, 1.32]},
        "above_far": {"minimum": [-0.30, -0.30, top + 0.055], "maximum": [0.30, 0.30, 1.55]},
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
                world = grid.applyMap(
                    nanovdb.math.Vec3d(float(i), float(j), float(k))
                )
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
        raise RuntimeError(f"ROI did not contain any grid sample: {roi}")
    ordered = sorted(values)
    return {
        "voxel_count": len(values),
        "nonzero_voxel_count": sum(abs(value) > 1.0e-12 for value in values),
        "mean": statistics.fmean(values),
        "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
        "maximum": max(values),
    }


def _save_and_sample(
    flow_interface, volume_interface, buffer, channel: str, path: Path, rois: dict
) -> dict:
    grid_data = flow_interface.buffer_to_volume(buffer)
    parameters = omni.volume.SaveVolumeParameters()
    parameters.flags = omni.volume.kNanoVDBCodecNone
    if not volume_interface.save_volume(grid_data, str(path), parameters):
        raise RuntimeError(f"Unable to save public NanoVDB readback: {path}")
    handle = nanovdb.io.readGrid(str(path))
    vector = channel == "velocity"
    grid = handle.vec3fGrid() if vector else handle.floatGrid()
    voxel_size = grid.voxelSize()
    result = {
        "grid_name": grid.gridName(),
        "grid_type": str(grid.gridType()),
        "active_voxel_count": int(grid.activeVoxelCount()),
        "voxel_size_m": [_component(voxel_size, axis) for axis in range(3)],
        "world_bbox": str(grid.worldBBox()),
        "rois": {name: _sample_grid(grid, roi, vector) for name, roi in rois.items()},
    }
    path.unlink(missing_ok=True)
    return result


async def _capture(viewport, path: Path) -> dict:
    capture = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await capture.wait_for_result(completion_frames=30):
        raise RuntimeError(f"Viewport capture failed: {path}")
    for _ in range(20):
        if path.is_file():
            return {"path": str(path), "bytes": path.stat().st_size}
        await omni.kit.app.get_app().next_update_async()
    raise RuntimeError(f"Viewport capture missing: {path}")


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
    flow_interface = None
    volume_interface = None
    report = {
        "schema": "campfire.phase6ds.flow-collision-run.v1",
        "phase": "phase6ds",
        "status": "running",
        "default_off": True,
        "production_code_changed": False,
        "condition": arguments["condition"],
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
        report["collider"] = _build_stage(
            stage_path, arguments["collision_enabled"], arguments["box_shift_m"]
        )
        report["flow_settings"] = {
            "version": FLOW_VERSION,
            "density_cell_size_m": DENSITY_CELL_SIZE_M,
            "velocity_cell_size_m": None,
            "physics_collision_enabled": arguments["collision_enabled"],
            "physics_convex_collision": True,
            "steps_per_second": STEPS_PER_SECOND,
            "seed": "Flow 110 deterministic fixed scene; no exposed seed authored",
        }
        report["rois"] = _roi_definitions()
        _write(output, report)
        report["lifecycle_marker"] = "opening_prebuilt_stage"
        _write(output, report)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Phase 6DS stage did not connect")
        simulate = stage.GetPrimAtPath("/World/Flow/Simulate")
        effective = {
            name: simulate.GetAttribute(name).Get()
            for name in (
                "densityCellSize",
                "physicsCollisionEnabled",
                "physicsConvexCollision",
                "stepsPerSecond",
                "velocitySubSteps",
            )
        }
        report["flow_settings"]["effective_usd"] = effective
        if bool(effective["physicsCollisionEnabled"]) != arguments["collision_enabled"]:
            raise RuntimeError("Effective collision flag differs from requested condition")
        if not bool(effective["physicsConvexCollision"]):
            raise RuntimeError("physicsConvexCollision effective value is false")

        viewport = None
        for _ in range(180):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport for Phase 6DS")
        viewport.camera_path = CAMERA_FRONT
        viewport.fill_frame = False
        viewport.resolution = CAPTURE_RESOLUTION
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
                break
        if tuple(viewport.resolution) != CAPTURE_RESOLUTION:
            raise RuntimeError(f"Viewport did not settle: {viewport.resolution}")

        flow_interface = _flowusd.acquire_flowusd_interface()
        volume_interface = omni.volume.get_volume_interface()
        report["lifecycle_marker"] = "timeline_playing"
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(8):
            await app.next_update_async()
        timeline.play()
        _write(output, report)
        rois = _roi_definitions()
        for frame in range(1, SAMPLE_FRAMES[-1] + 1):
            await app.next_update_async()
            if arguments["capture"] and frame in CAPTURE_FRAMES:
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                capture_path = frames_dir / f"{arguments['condition']}_r{arguments['run_index']}_{frame:04d}.png"
                report["captures"].append({"frame": frame, **(await _capture(viewport, capture_path))})
            if frame not in SAMPLE_FRAMES:
                continue
            raw = flow_interface.get_latest_nanovdb_readback()
            if len(raw) < len(CHANNELS):
                raise RuntimeError(f"Expected {len(CHANNELS)} readback buffers, got {len(raw)}")
            sample = {
                "frame": frame,
                "simulation_time_s": frame / STEPS_PER_SECOND,
                "active_blocks": int(flow_interface.get_active_block_count()),
                "channels": {},
            }
            for index, channel in enumerate(CHANNELS):
                array = np.asarray(raw[index])
                if array.size == 0:
                    sample["channels"][channel] = {
                        "available": False,
                        "reason": "empty public readback buffer",
                    }
                    continue
                path = output.parent / f"sample_{arguments['condition']}_{frame}_{channel}.nvdb"
                sample["channels"][channel] = {
                    "available": True,
                    "word_count": int(array.size),
                    **_save_and_sample(flow_interface, volume_interface, array, channel, path, rois),
                }
            velocity = sample["channels"].get("velocity", {})
            if velocity.get("available"):
                velocity_cell = float(velocity["voxel_size_m"][0])
                report["flow_settings"]["velocity_cell_size_m"] = velocity_cell
                report["collider"]["thickness_velocity_cells"] = BOX_DIMENSIONS_M[2] / velocity_cell
                report["collider"]["emitter_gap_velocity_cells"] = (
                    report["collider"]["emitter_minimum_distance_m"] / velocity_cell
                )
                report["collider"]["shift_velocity_cells"] = arguments["box_shift_m"] / velocity_cell
                report["rois"] = _roi_definitions(velocity_cell)
            report["samples"].append(sample)
            _write(output, report)

        if arguments["capture"]:
            timeline.pause()
            for camera_name, camera_path in (("front", CAMERA_FRONT), ("side", CAMERA_SIDE)):
                viewport.camera_path = camera_path
                for _ in range(12):
                    await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                path = frames_dir / f"{arguments['condition']}_r{arguments['run_index']}_final_{camera_name}.png"
                report["captures"].append({"frame": SAMPLE_FRAMES[-1], "camera": camera_name, **(await _capture(viewport, path))})

        unavailable_velocity = all(
            not sample["channels"].get("velocity", {}).get("available", False)
            for sample in report["samples"]
        )
        report["velocity_readback"] = {
            "available": not unavailable_velocity,
            "private_api_attempted": False,
            "note": None if not unavailable_velocity else "Public readback was empty; no private API used.",
        }
        report["measurement_gates"] = {
            "complete_stage_built_before_connection": True,
            "emitter_outside_collider": report["collider"]["emitter_samples_outside_analytical_box"],
            "five_time_samples": len(report["samples"]) == len(SAMPLE_FRAMES),
            "active_blocks_nonzero": max((sample["active_blocks"] for sample in report["samples"]), default=0) > 0,
            "scalar_readback_available": all(
                sample["channels"][name].get("available", False)
                for sample in report["samples"]
                for name in ("temperature", "fuel", "burn", "smoke")
            ),
            "collider_thickness_at_least_four_velocity_cells": report["collider"].get("thickness_velocity_cells", 0.0) >= 4.0,
            "emitter_gap_at_least_two_velocity_cells": report["collider"].get("emitter_gap_velocity_cells", 0.0) >= 2.0,
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
            if flow_interface is not None:
                _flowusd.release_flowusd_interface(flow_interface)
                flow_interface = None
            report["lifecycle_marker"] = "shutdown_complete"
        except Exception as shutdown_error:
            report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
            report["status"] = "error"
            exit_code = 1
        _write(output, report)
        app.post_uncancellable_quit(exit_code)


if carb.settings.get_settings().get_as_string("/phase6ds/output"):
    # Keep the historical Phase 6DS --exec entry point unchanged while making
    # its stage-authoring helpers reusable by later production-neutral probes.
    asyncio.ensure_future(_run())
