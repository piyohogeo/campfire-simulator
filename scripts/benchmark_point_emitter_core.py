"""Qualify a fresh Flow 110 Point emitter scene without a bundled preset.

The complete stage is authored on disk before it is connected to the Kit USD
context.  Once connected, the benchmark mutates only the five pre-existing
Point-emitter arrays/revision attributes requested by the Phase 6CB contract.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdLux, UsdShade, Vt


FLOW_VERSION = "110.0.0"
CAPTURE_RESOLUTION = (1280, 720)
FLOW_ROOT = Sdf.Path("/World/Flow")
SIMULATE_PATH = FLOW_ROOT.AppendChild("Simulate")
OFFSCREEN_PATH = FLOW_ROOT.AppendChild("Offscreen")
RENDER_PATH = FLOW_ROOT.AppendChild("Render")
CAMERA_PATH = Sdf.Path("/World/Camera")
SURFACE_POINTS_PER_LOG = 360


def _settings():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phase6cb/output")),
        "point_count": settings.get_as_int("/phase6cb/pointCount"),
        "emitter_count": settings.get_as_int("/phase6cb/emitterCount"),
        "frames": settings.get_as_int("/phase6cb/frames"),
        "warmup": settings.get_as_int("/phase6cb/warmup"),
    }


def _set(prim, name, value):
    attribute = prim.GetAttribute(name)
    if not attribute:
        raise RuntimeError(f"Flow schema attribute unavailable: {prim.GetPath()}.{name}")
    if not attribute.Set(value):
        raise RuntimeError(f"Flow attribute Set failed: {prim.GetPath()}.{name}")
    return attribute


def _set_transform(prim, *, translate=None, scale=None):
    xformable = UsdGeom.Xformable(prim)
    if translate is not None:
        xformable.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if scale is not None:
        xformable.AddScaleOp().Set(Gf.Vec3f(*scale))


def _surface_points_for_log(log_index):
    axial_cells, circumferential_cells, radial_cells = (24, 12, 4)
    length_m = 0.72
    radius_m = 0.105
    dz = length_m / axial_cells
    dr = radius_m / radial_cells
    row, column = divmod(log_index, 5)
    origin_x = (column - 2.0) * 0.22
    origin_y = (row - 1.5) * 0.22
    origin_z = 0.42 + 0.045 * ((row + column) % 2)
    rotate = (row % 2) == 1
    points = []
    for axial in range(axial_cells):
        axial_position = -0.5 * length_m + (axial + 0.5) * dz
        for circumferential in range(circumferential_cells):
            angle = 2.0 * math.pi * (circumferential + 0.5) / circumferential_cells
            for radial in range(radial_cells):
                if radial != radial_cells - 1 and axial not in (0, axial_cells - 1):
                    continue
                radial_position = (radial + 0.5) * dr
                cross_a = radial_position * math.cos(angle)
                cross_b = radial_position * math.sin(angle)
                if rotate:
                    x = origin_x + cross_a
                    y = origin_y + axial_position
                else:
                    x = origin_x + axial_position
                    y = origin_y + cross_a
                points.append(Gf.Vec3f(x, y, origin_z + cross_b))
    if len(points) != SURFACE_POINTS_PER_LOG:
        raise RuntimeError(f"Unexpected surface point count: {len(points)}")
    return points


def _point_positions(point_count):
    if point_count == 7200:
        return [point for log in range(20) for point in _surface_points_for_log(log)]
    if point_count < 4 or point_count > 128:
        raise ValueError("Small qualification uses 4..128 points; target uses 7200")
    side = math.ceil(point_count ** (1.0 / 3.0))
    spacing = 0.035
    points = []
    for index in range(point_count):
        x = (index % side) - 0.5 * (side - 1)
        y = ((index // side) % side) - 0.5 * (side - 1)
        z = index // (side * side)
        points.append(Gf.Vec3f(x * spacing, y * spacing, 0.48 + z * spacing))
    return points


def _chunks(values, count):
    if count < 1 or count > len(values) or len(values) % count:
        raise ValueError("Emitter count must divide the point count")
    size = len(values) // count
    return tuple(values[index * size : (index + 1) * size] for index in range(count))


def _define_minimal_world(stage):
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())

    ground = UsdGeom.Cylinder.Define(stage, "/World/Ground")
    ground.CreateAxisAttr(UsdGeom.Tokens.z)
    ground.CreateRadiusAttr(2.5)
    ground.CreateHeightAttr(0.08)
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.055, 0.035, 0.02)])
    _set_transform(ground.GetPrim(), translate=(0.0, 0.0, -0.04))

    camera = UsdGeom.Camera.Define(stage, CAMERA_PATH)
    camera.CreateFocalLengthAttr(48.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(2.7, -3.6, 2.15),
        Gf.Vec3d(0.0, 0.0, 0.72),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.AddTransformOp().Set(view.GetInverse())

    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(420.0)
    dome.CreateColorAttr(Gf.Vec3f(0.20, 0.26, 0.38))
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(18000.0)
    key.CreateRadiusAttr(0.2)
    key.CreateColorAttr(Gf.Vec3f(1.0, 0.32, 0.08))
    _set_transform(key.GetPrim(), translate=(0.0, -0.4, 1.7))


def _define_flow_solver(stage):
    UsdGeom.Xform.Define(stage, FLOW_ROOT)
    simulate = stage.DefinePrim(SIMULATE_PATH, "FlowSimulate")
    for name, value in (
        ("layer", 0),
        ("densityCellSize", 0.025),
        ("blockMinLifetime", 4),
        ("enableVariableTimeStep", False),
        ("forceDisableCoreSimulation", False),
        ("forceDisableEmitters", False),
        ("forceSimulate", True),
        ("simulateWhenPaused", False),
        ("maxStepsPerSimulate", 1),
        ("physicsCollisionEnabled", False),
        ("stepsPerSecond", 60.0),
        ("velocitySubSteps", 1),
    ):
        _set(simulate, name, value)

    advection = stage.DefinePrim(
        SIMULATE_PATH.AppendChild("advection"), "FlowAdvectionCombustionParams"
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
    for channel_name in (
        "smoke",
        "velocity",
        "divergence",
        "temperature",
        "fuel",
        "burn",
    ):
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
        SIMULATE_PATH.AppendChild("vorticity"), "FlowVorticityParams"
    )
    _set(vorticity, "enabled", True)
    _set(vorticity, "forceScale", 1.5)
    _set(vorticity, "velocityMask", 1.0)
    pressure = stage.DefinePrim(
        SIMULATE_PATH.AppendChild("pressure"), "FlowPressureParams"
    )
    _set(pressure, "enabled", True)
    allocate = stage.DefinePrim(
        SIMULATE_PATH.AppendChild("summaryAllocate"), "FlowSummaryAllocateParams"
    )
    _set(allocate, "enableNeighborAllocation", True)
    _set(allocate, "smokeThreshold", 0.02)
    _set(allocate, "speedThreshold", 1.0)

    export = stage.DefinePrim(
        SIMULATE_PATH.AppendChild("nanoVdbExport"),
        "FlowSparseNanoVdbExportParams",
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

    offscreen = stage.DefinePrim(OFFSCREEN_PATH, "FlowOffscreen")
    _set(offscreen, "layer", 0)
    colormap = stage.DefinePrim(
        OFFSCREEN_PATH.AppendChild("colormap"), "FlowRayMarchColormapParams"
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
        OFFSCREEN_PATH.AppendChild("shadow"), "FlowShadowParams"
    )
    _set(shadow, "enabled", True)
    _set(shadow, "attenuation", 0.045)
    _set(shadow, "coarsePropagate", True)
    _set(shadow, "lightDirection", Gf.Vec3f(1.0, 1.0, 1.0))

    render = stage.DefinePrim(RENDER_PATH, "FlowRender")
    _set(render, "layer", 0)
    ray_march = stage.DefinePrim(
        RENDER_PATH.AppendChild("rayMarch"), "FlowRayMarchParams"
    )
    _set(ray_march, "attenuation", 0.05)
    _set(ray_march, "colorScale", 1.0)
    _set(ray_march, "shadowFactor", 1.0)
    _set(ray_march, "stepSizeScale", 0.75)


def _define_point_sources(stage, chunks):
    material = UsdShade.Material.Define(stage, "/World/Materials/PointSource")
    shader = UsdShade.Shader.Define(stage, "/World/Materials/PointSource/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(1.0, 0.14, 0.015)
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.35, 0.025, 0.005)
    )
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    handles = []
    for index, positions in enumerate(chunks):
        suffix = "" if len(chunks) == 1 else f"_{index:02d}"
        source_path = Sdf.Path(f"/World/PointSource{suffix}")
        source = UsdGeom.Points.Define(stage, source_path)
        source.CreatePointsAttr(Vt.Vec3fArray(positions))
        source.CreateWidthsAttr(Vt.FloatArray([0.003] * len(positions)))
        source.CreateDisplayColorAttr([Gf.Vec3f(1.0, 0.12, 0.01)])
        binding = UsdShade.MaterialBindingAPI.Apply(source.GetPrim())
        binding.Bind(material)

        emitter_path = FLOW_ROOT.AppendChild(f"EmitterPoint{suffix}")
        emitter = stage.DefinePrim(emitter_path, "FlowEmitterPoint")
        for name, value in (
            ("layer", 0),
            ("enabled", True),
            ("allocateMask", True),
            ("applyPostPressure", False),
            ("levelCount", 1),
            ("numSubSteps", 1),
            ("coupleRateFuel", 10.0),
            ("coupleRateTemperature", 20.0),
            ("coupleRateSmoke", 4.0),
            ("coupleRateVelocity", 2.0),
            ("fuel", 0.8),
            ("temperature", 2.0),
            ("smoke", 0.08),
            ("velocity", Gf.Vec3f(0.0, 0.0, 0.35)),
            ("velocityIsWorldSpace", True),
            ("updateCoarseDensity", True),
            ("enableStreaming", False),
            ("streamOnce", False),
        ):
            _set(emitter, name, value)
        position_array = Vt.Vec3fArray(positions)
        _set(emitter, "pointPositions", position_array)
        _set(emitter, "pointFuels", Vt.FloatArray([0.8] * len(positions)))
        _set(emitter, "pointTemperatures", Vt.FloatArray([2.0] * len(positions)))
        _set(emitter, "pointSmokes", Vt.FloatArray([0.08] * len(positions)))
        _set(
            emitter,
            "pointVelocities",
            Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 0.35)] * len(positions)),
        )
        relationship = emitter.GetRelationship("pointsPrim")
        if not relationship or not relationship.SetTargets([source_path]):
            raise RuntimeError("FlowEmitterPoint pointsPrim relationship failed")
        revision = emitter.CreateAttribute(
            "campfire:residentRevision", Sdf.ValueTypeNames.Int64
        )
        revision.Set(0)
        handles.append(
            {
                "path": emitter_path,
                "source_path": source_path,
                "positions": tuple(positions),
            }
        )
    return tuple(handles)


def _build_stage(path, point_count, emitter_count):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    _define_minimal_world(stage)
    _define_flow_solver(stage)
    positions = _point_positions(point_count)
    handles = _define_point_sources(stage, _chunks(positions, emitter_count))
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(600.0)
    stage.SetTimeCodesPerSecond(60.0)
    stage.GetRootLayer().customLayerData = {
        "campfire:phase": "phase6cb",
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
        raise RuntimeError(f"Failed to save offline Point stage: {path}")
    return handles


def _file_record(path):
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _summary(values, warmup=0):
    measured = list(values[warmup:])
    ordered = sorted(measured)
    return {
        "samples": len(measured),
        "mean_ms": statistics.fmean(measured),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(measured),
    }


async def _capture(viewport, path):
    capture = omni.kit.viewport.utility.capture_viewport_to_file(
        viewport, file_path=str(path)
    )
    if not await capture.wait_for_result(completion_frames=60):
        raise RuntimeError(f"Viewport capture failed: {path}")
    for _ in range(10):
        if path.is_file():
            return _file_record(path)
        await omni.kit.app.get_app().next_update_async()
    raise RuntimeError(f"Viewport capture was not written: {path}")


def _readback(flow_interface):
    names = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
    raw = flow_interface.get_latest_nanovdb_readback()
    result = {}
    for index, name in enumerate(names):
        value = raw[index] if index < len(raw) else []
        result[name] = int(getattr(value, "size", len(value)))
    return result


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".scene.usda")
    exit_code = 1
    flow_interface = None
    listener = None
    timeline_subscription = None
    report = None
    try:
        offline_handles = _build_stage(
            stage_path, arguments["point_count"], arguments["emitter_count"]
        )
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Offline Point stage did not connect to Kit")

        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport for Point Emitter qualification")
        viewport.camera_path = CAMERA_PATH
        viewport.fill_frame = False
        viewport.resolution = CAPTURE_RESOLUTION
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
                break
        if tuple(viewport.resolution) != CAPTURE_RESOLUTION:
            raise RuntimeError(f"Viewport resolution did not settle: {viewport.resolution}")

        emitters = []
        stage_contract = []
        for item in offline_handles:
            prim = stage.GetPrimAtPath(item["path"])
            source = stage.GetPrimAtPath(item["source_path"])
            if not prim or prim.GetTypeName() != "FlowEmitterPoint":
                raise RuntimeError(f"Point emitter missing after connection: {item['path']}")
            if not source or not source.IsA(UsdGeom.Points):
                raise RuntimeError(f"UsdGeomPoints source missing: {item['source_path']}")
            relationship = prim.GetRelationship("pointsPrim")
            bound_material, _ = UsdShade.MaterialBindingAPI(source).ComputeBoundMaterial()
            targets = relationship.GetTargets() if relationship else []
            stage_contract.append(
                {
                    "emitter": str(item["path"]),
                    "source": str(item["source_path"]),
                    "layer": prim.GetAttribute("layer").Get(),
                    "relationship_targets": [str(value) for value in targets],
                    "material": (
                        str(bound_material.GetPath()) if bound_material else None
                    ),
                    "point_count": len(item["positions"]),
                }
            )
            emitters.append(
                {
                    "positions": prim.GetAttribute("pointPositions"),
                    "fuels": prim.GetAttribute("pointFuels"),
                    "temperatures": prim.GetAttribute("pointTemperatures"),
                    "smokes": prim.GetAttribute("pointSmokes"),
                    "revision": prim.GetAttribute("campfire:residentRevision"),
                    "base_positions": item["positions"],
                }
            )

        resynced_paths = []
        publication_notice_count = 0
        emitter_path_prefixes = tuple(str(item["path"]) for item in offline_handles)

        def observe(notice, _sender):
            nonlocal publication_notice_count
            resynced_paths.extend(str(path) for path in notice.GetResyncedPaths())
            changed = tuple(notice.GetChangedInfoOnlyPaths()) + tuple(
                notice.GetResyncedPaths()
            )
            if any(
                str(path).startswith(prefix)
                for path in changed
                for prefix in emitter_path_prefixes
            ):
                publication_notice_count += 1

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe, stage)
        flow_interface = _flowusd.acquire_flowusd_interface()
        timeline_events = []
        timeline_event_names = {
            int(omni.timeline.TimelineEventType.PLAY): "PLAY",
            int(omni.timeline.TimelineEventType.PAUSE): "PAUSE",
            int(omni.timeline.TimelineEventType.STOP): "STOP",
        }

        def observe_timeline(event):
            name = timeline_event_names.get(event.type)
            if name is not None:
                timeline_events.append(name)

        timeline_subscription = (
            timeline.get_timeline_event_stream().create_subscription_to_pop(
                observe_timeline, 0, "phase6cb timeline probe"
            )
        )
        timeline.stop()
        timeline.set_current_time(0.0)
        stopped_state_observed = not timeline.is_playing()
        paused_blocks = []
        for _ in range(8):
            await app.next_update_async()
            paused_blocks.append(int(flow_interface.get_active_block_count()))
        before_capture = await _capture(viewport, output.with_suffix(".before.png"))

        timeline.play()
        playing_state_observed = timeline.is_playing()
        active_blocks = []
        update_times_ms = []
        source_generation_times_ms = []
        boundary_times_ms = []
        usd_set_times_ms = []
        change_block_exit_times_ms = []
        publication_total_times_ms = []
        capture_records = []
        final_channel_values = None
        total_frames = arguments["frames"] + arguments["warmup"]
        capture_frames = {max(1, total_frames // 2), total_frames}
        for frame in range(1, total_frames + 1):
            publication_started = time.perf_counter_ns()
            source_started = time.perf_counter_ns()
            phase = 0.002 * math.sin(frame * 0.12)
            fuel = 0.8 + 0.025 * ((frame % 11) / 10.0)
            temperature = 2.0 + 0.08 * ((frame % 7) / 6.0)
            smoke = 0.08 + 0.02 * ((frame % 5) / 4.0)
            source_values = []
            for emitter in emitters:
                point_count = len(emitter["base_positions"])
                source_values.append(
                    {
                        "positions": [
                            Gf.Vec3f(value[0], value[1], value[2] + phase)
                            for value in emitter["base_positions"]
                        ],
                        "fuels": [fuel] * point_count,
                        "temperatures": [temperature] * point_count,
                        "smokes": [smoke] * point_count,
                    }
                )
            source_generation_times_ms.append(
                (time.perf_counter_ns() - source_started) / 1_000_000.0
            )
            boundary_started = time.perf_counter_ns()
            converted = tuple(
                {
                    "positions": Vt.Vec3fArray(values["positions"]),
                    "fuels": Vt.FloatArray(values["fuels"]),
                    "temperatures": Vt.FloatArray(values["temperatures"]),
                    "smokes": Vt.FloatArray(values["smokes"]),
                }
                for values in source_values
            )
            boundary_times_ms.append(
                (time.perf_counter_ns() - boundary_started) / 1_000_000.0
            )
            block = Sdf.ChangeBlock()
            block.__enter__()
            set_started = time.perf_counter_ns()
            try:
                for emitter, values in zip(emitters, converted):
                    if not emitter["positions"].Set(values["positions"]):
                        raise RuntimeError("pointPositions update failed")
                    if not emitter["fuels"].Set(values["fuels"]):
                        raise RuntimeError("pointFuels update failed")
                    if not emitter["temperatures"].Set(values["temperatures"]):
                        raise RuntimeError("pointTemperatures update failed")
                    if not emitter["smokes"].Set(values["smokes"]):
                        raise RuntimeError("pointSmokes update failed")
                    if not emitter["revision"].Set(frame):
                        raise RuntimeError("Point revision update failed")
            except BaseException:
                block.__exit__(*sys.exc_info())
                raise
            usd_set_times_ms.append(
                (time.perf_counter_ns() - set_started) / 1_000_000.0
            )
            exit_started = time.perf_counter_ns()
            block.__exit__(None, None, None)
            change_block_exit_times_ms.append(
                (time.perf_counter_ns() - exit_started) / 1_000_000.0
            )
            publication_total_times_ms.append(
                (time.perf_counter_ns() - publication_started) / 1_000_000.0
            )
            final_channel_values = {
                "fuel": fuel,
                "temperature": temperature,
                "smoke": smoke,
            }
            update_started = time.perf_counter_ns()
            await app.next_update_async()
            update_times_ms.append(
                (time.perf_counter_ns() - update_started) / 1_000_000.0
            )
            active_blocks.append(int(flow_interface.get_active_block_count()))
            if frame in capture_frames:
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                capture_path = output.with_name(f"{output.stem}.frame_{frame:04d}.png")
                capture_records.append(
                    {"frame": frame, **(await _capture(viewport, capture_path))}
                )

        timeline.pause()
        final_paused_state_observed = not timeline.is_playing()
        await app.next_update_async()
        readback = _readback(flow_interface)
        final_revisions = [int(item["revision"].Get()) for item in emitters]
        final_counts = {
            name: sum(len(item[name].Get()) for item in emitters)
            for name in ("positions", "fuels", "temperatures", "smokes")
        }
        final_channel_sums = {
            name: sum(
                float(value)
                for emitter in emitters
                for value in emitter[name].Get()
            )
            for name in ("fuels", "temperatures", "smokes")
        }
        expected_channel_sums = {
            "fuels": final_channel_values["fuel"] * arguments["point_count"],
            "temperatures": (
                final_channel_values["temperature"] * arguments["point_count"]
            ),
            "smokes": final_channel_values["smoke"] * arguments["point_count"],
        }
        layer_values = {
            "simulate": stage.GetPrimAtPath(SIMULATE_PATH).GetAttribute("layer").Get(),
            "offscreen": stage.GetPrimAtPath(OFFSCREEN_PATH).GetAttribute("layer").Get(),
            "render": stage.GetPrimAtPath(RENDER_PATH).GetAttribute("layer").Get(),
            "emitters": [item["layer"] for item in stage_contract],
        }
        relevant_resyncs = sorted(
            {
                path
                for path in resynced_paths
                if path.startswith(str(FLOW_ROOT)) or path.startswith("/World/PointSource")
            }
        )
        gates = {
            "fresh_stage_without_native_pointcloud_preset": (
                not stage.GetRootLayer().subLayerPaths
                and stage.GetRootLayer().customLayerData.get(
                    "campfire:stageBuiltBeforeConnection"
                )
                is True
            ),
            "flow_core_prims_complete_before_connection": all(
                stage.GetPrimAtPath(path)
                for path in (SIMULATE_PATH, OFFSCREEN_PATH, RENDER_PATH)
            ),
            "single_or_few_array_emitters": (
                len(emitters) == arguments["emitter_count"]
                and arguments["emitter_count"] < arguments["point_count"]
            ),
            "layer_zero_matches": (
                layer_values["simulate"] == 0
                and layer_values["offscreen"] == 0
                and layer_values["render"] == 0
                and all(value == 0 for value in layer_values["emitters"])
            ),
            "points_relationship_exact": all(
                item["relationship_targets"] == [item["source"]]
                for item in stage_contract
            ),
            "source_material_bound": all(
                item["material"] == "/World/Materials/PointSource"
                for item in stage_contract
            ),
            "timeline_play_and_terminal_event_observed": (
                "PLAY" in timeline_events
                and any(name in timeline_events for name in ("PAUSE", "STOP"))
            ),
            "playing_blocks_exceed_stopped_warmup": (
                max(active_blocks, default=0) > max(paused_blocks, default=0)
            ),
            "viewport_camera_and_resolution": (
                str(viewport.camera_path) == str(CAMERA_PATH)
                and tuple(viewport.resolution) == CAPTURE_RESOLUTION
                and len(capture_records) == 2
            ),
            "core_simulation_active": max(active_blocks, default=0) > 0,
            "flow_fields_nonempty": any(value > 0 for value in readback.values()),
            "viewport_output_changed": (
                before_capture["sha256"] != capture_records[-1]["sha256"]
            ),
            "array_channels_exact": all(
                value == arguments["point_count"] for value in final_counts.values()
            ),
            "fuel_temperature_smoke_sums_close": all(
                math.isclose(
                    final_channel_sums[name], expected_channel_sums[name], rel_tol=1e-6
                )
                for name in expected_channel_sums
            ),
            "consumer_revisions_exact": (
                len(set(final_revisions)) == 1 and final_revisions[0] == total_frames
            ),
            "no_live_structural_resync": not relevant_resyncs,
            "one_notice_per_publication": publication_notice_count == total_frames,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6cb",
            "status": "ok" if all(gates.values()) else "failed",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "configuration": {
                "flow_version": FLOW_VERSION,
                "point_count": arguments["point_count"],
                "emitter_count": arguments["emitter_count"],
                "surface_points_per_log": (
                    SURFACE_POINTS_PER_LOG if arguments["point_count"] == 7200 else None
                ),
                "log_count": 20 if arguments["point_count"] == 7200 else None,
                "measured_frames": arguments["frames"],
                "warmup_frames": arguments["warmup"],
                "production_default_changed": False,
                "production_scene_changed": False,
            },
            "stage": {
                "path": str(stage_path),
                "sublayers": list(stage.GetRootLayer().subLayerPaths),
                "contract": stage_contract,
                "layers": layer_values,
                "live_relevant_resync_paths": relevant_resyncs,
            },
            "timeline": {
                "stopped_state_observed": stopped_state_observed,
                "playing_state_observed": playing_state_observed,
                "final_paused_state_observed": final_paused_state_observed,
                "events": timeline_events,
                "event_note": (
                    "This headless benchmark emits PLAY and then STOP at time code zero; "
                    "forceSimulate keeps the explicitly driven update loop active."
                ),
                "paused_active_blocks": paused_blocks,
                "paused_active_blocks_note": (
                    "forceSimulate permits warm-up allocation while the timeline is stopped; "
                    "the gate requires explicit state transitions and a larger playing peak."
                ),
                "playing_active_blocks_peak": max(active_blocks, default=0),
                "playing_active_blocks_final": active_blocks[-1],
                "current_time": timeline.get_current_time(),
            },
            "viewport": {
                "camera": str(viewport.camera_path),
                "resolution": list(viewport.resolution),
                "before": before_capture,
                "captures": capture_records,
            },
            "flow": {
                "readback_word_counts": readback,
                "max_blocks": int(flow_interface.get_max_block_count()),
            },
            "publication": {
                "attributes_per_emitter": [
                    "pointPositions",
                    "pointFuels",
                    "pointTemperatures",
                    "pointSmokes",
                    "campfire:residentRevision",
                ],
                "final_counts": final_counts,
                "final_channel_sums": final_channel_sums,
                "expected_channel_sums": expected_channel_sums,
                "final_revisions": final_revisions,
                "notice_count": publication_notice_count,
                "logical_payload_bytes_per_publication": (
                    arguments["point_count"] * 24 + arguments["emitter_count"] * 8
                ),
                "timing": {
                    "source_generation": _summary(
                        source_generation_times_ms, arguments["warmup"]
                    ),
                    "python_cpp_boundary": _summary(
                        boundary_times_ms, arguments["warmup"]
                    ),
                    "usd_attribute_set": _summary(
                        usd_set_times_ms, arguments["warmup"]
                    ),
                    "change_block_exit": _summary(
                        change_block_exit_times_ms, arguments["warmup"]
                    ),
                    "total": _summary(
                        publication_total_times_ms, arguments["warmup"]
                    ),
                },
            },
            "kit_flow_render_update": _summary(
                update_times_ms, arguments["warmup"]
            ),
            "gates": gates,
        }
        if not all(gates.values()):
            failed = [name for name, value in gates.items() if not value]
            report["failure_boundary"] = (
                "USD/schema/stage contract" if any(
                    name in failed
                    for name in (
                        "fresh_stage_without_native_pointcloud_preset",
                        "flow_core_prims_complete_before_connection",
                        "layer_zero_matches",
                        "points_relationship_exact",
                        "source_material_bound",
                        "array_channels_exact",
                        "consumer_revisions_exact",
                        "no_live_structural_resync",
                    )
                ) else "omni.flowusd ingest/raster/core/render boundary"
            )
            report["failed_gates"] = failed
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError(f"Phase 6CB gates failed: {report['failed_gates']}")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": "phase6cb",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6cb] {type(error).__name__}: {error}")
    finally:
        if listener is not None:
            listener.Revoke()
        timeline_subscription = None
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_settings()))
