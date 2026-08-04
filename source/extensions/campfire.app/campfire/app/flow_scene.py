"""Deterministic Phase 1 NVIDIA Flow technical-spike scene."""

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

from .scene import CAMERA_PATH, export_stage, populate_fixed_scene


FLOW_ROOT_PATH = Sdf.Path("/World/Flow")
FLOW_EMITTER_PATH = Sdf.Path("/World/Flow/Emitter")
FLOW_SIMULATE_PATH = Sdf.Path("/World/Flow/Simulate")
FLOW_VERSION = "110.0.0"
PHASE1_CAPTURE_FRAMES = (90, 220)
PHASE1_TOTAL_FRAMES = PHASE1_CAPTURE_FRAMES[-1]
EMITTER_START = Gf.Vec3f(-0.18, 0.0, 0.48)
EMITTER_END = Gf.Vec3f(0.18, 0.0, 0.48)


def _set(prim: Usd.Prim, name: str, value) -> None:
    """Set an attribute supplied by a registered Flow schema."""

    attribute = prim.GetAttribute(name)
    if not attribute:
        raise RuntimeError(f"Flow schema attribute is unavailable: {prim.GetPath()}.{name}")
    if not attribute.Set(value):
        raise RuntimeError(f"Failed to set Flow attribute: {prim.GetPath()}.{name}")


def emitter_position_for_frame(frame: int) -> Gf.Vec3f:
    """Return the deterministic emitter path used by the movement spike."""

    move_start = 70
    move_end = 140
    if frame <= move_start:
        return Gf.Vec3f(EMITTER_START)
    if frame >= move_end:
        return Gf.Vec3f(EMITTER_END)
    alpha = (frame - move_start) / (move_end - move_start)
    return Gf.Vec3f(
        EMITTER_START[0] + (EMITTER_END[0] - EMITTER_START[0]) * alpha,
        EMITTER_START[1] + (EMITTER_END[1] - EMITTER_START[1]) * alpha,
        EMITTER_START[2] + (EMITTER_END[2] - EMITTER_START[2]) * alpha,
    )


def _define_flow_prims(stage: Usd.Stage) -> None:
    UsdGeom.Xform.Define(stage, FLOW_ROOT_PATH)

    emitter = stage.DefinePrim(FLOW_EMITTER_PATH, "FlowEmitterSphere")
    _set(emitter, "layer", 0)
    _set(emitter, "enabled", True)
    _set(emitter, "position", EMITTER_START)
    _set(emitter, "radius", 0.18)
    _set(emitter, "radiusIsWorldSpace", True)
    _set(emitter, "allocationScale", 1.5)
    _set(emitter, "multisample", True)
    _set(emitter, "numSubSteps", 2)
    _set(emitter, "temperature", 2.0)
    _set(emitter, "coupleRateTemperature", 10.0)
    _set(emitter, "fuel", 0.8)
    _set(emitter, "coupleRateFuel", 2.0)
    _set(emitter, "smoke", 0.0)
    _set(emitter, "coupleRateSmoke", 0.0)
    _set(emitter, "velocity", Gf.Vec3f(0.0, 0.0, 0.30))
    _set(emitter, "velocityIsWorldSpace", True)
    _set(emitter, "coupleRateVelocity", 2.0)

    simulate = stage.DefinePrim(FLOW_SIMULATE_PATH, "FlowSimulate")
    _set(simulate, "layer", 0)
    _set(simulate, "densityCellSize", 0.025)
    _set(simulate, "blockMinLifetime", 4)
    _set(simulate, "enableVariableTimeStep", False)
    # Headless validation can advance faster than wall-clock time.  These are
    # the Flow-supported controls for still stepping in that environment.
    _set(simulate, "forceSimulate", True)
    _set(simulate, "simulateWhenPaused", True)
    _set(simulate, "maxStepsPerSimulate", 1)
    _set(simulate, "physicsCollisionEnabled", True)
    _set(simulate, "physicsConvexCollision", True)
    _set(simulate, "stepsPerSecond", 60.0)
    _set(simulate, "velocitySubSteps", 1)

    advection = stage.DefinePrim(
        FLOW_SIMULATE_PATH.AppendChild("advection"), "FlowAdvectionCombustionParams"
    )
    _set(advection, "enabled", True)
    _set(advection, "combustionEnabled", True)
    _set(advection, "buoyancyPerTemp", 6.0)
    _set(advection, "burnPerTemp", 4.0)
    _set(advection, "coolingRate", 1.5)
    _set(advection, "fuelPerBurn", 0.25)
    _set(advection, "gravity", Gf.Vec3f(0.0, 0.0, -9.81))
    _set(advection, "ignitionTemp", 0.05)
    _set(advection, "smokePerBurn", 3.0)
    _set(advection, "tempPerBurn", 5.0)

    for channel_name in ("smoke", "velocity", "divergence", "temperature", "fuel", "burn"):
        channel = stage.DefinePrim(
            advection.GetPath().AppendChild(channel_name), "FlowAdvectionChannelParams"
        )
        if channel_name == "smoke":
            _set(channel, "damping", 0.3)
            _set(channel, "fade", 2.0)
            _set(channel, "secondOrderBlendFactor", 0.9)
        elif channel_name in ("temperature", "fuel", "burn"):
            _set(channel, "secondOrderBlendFactor", 0.9)
        else:
            _set(channel, "damping", 0.01)
            _set(channel, "fade", 1.0)

    vorticity = stage.DefinePrim(
        FLOW_SIMULATE_PATH.AppendChild("vorticity"), "FlowVorticityParams"
    )
    _set(vorticity, "enabled", True)
    _set(vorticity, "forceScale", 1.5)
    _set(vorticity, "velocityMask", 1.0)

    pressure = stage.DefinePrim(
        FLOW_SIMULATE_PATH.AppendChild("pressure"), "FlowPressureParams"
    )
    _set(pressure, "enabled", True)

    summary_allocate = stage.DefinePrim(
        FLOW_SIMULATE_PATH.AppendChild("summaryAllocate"), "FlowSummaryAllocateParams"
    )
    _set(summary_allocate, "enableNeighborAllocation", True)
    _set(summary_allocate, "smokeThreshold", 0.02)
    _set(summary_allocate, "speedThreshold", 1.0)

    nano_vdb = stage.DefinePrim(
        FLOW_SIMULATE_PATH.AppendChild("nanoVdbExport"), "FlowSparseNanoVdbExportParams"
    )
    _set(nano_vdb, "enabled", True)
    _set(nano_vdb, "temperatureEnabled", True)
    _set(nano_vdb, "fuelEnabled", True)
    _set(nano_vdb, "burnEnabled", True)
    _set(nano_vdb, "smokeEnabled", True)
    _set(nano_vdb, "velocityEnabled", True)
    _set(nano_vdb, "statisticsEnabled", True)
    # Phase 1 explicitly measures whether the current Flow build can expose
    # its sparse fields to CPU code.  Keep this enabled for the spike scene.
    _set(nano_vdb, "readbackEnabled", True)

    offscreen = stage.DefinePrim(FLOW_ROOT_PATH.AppendChild("flowOffscreen"), "FlowOffscreen")
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

    render = stage.DefinePrim(FLOW_ROOT_PATH.AppendChild("flowRender"), "FlowRender")
    _set(render, "layer", 0)
    ray_march = stage.DefinePrim(
        render.GetPath().AppendChild("rayMarch"), "FlowRayMarchParams"
    )
    _set(ray_march, "attenuation", 0.05)
    _set(ray_march, "colorScale", 1.0)
    _set(ray_march, "shadowFactor", 1.0)
    _set(ray_march, "stepSizeScale", 0.75)


def populate_flow_scene(stage: Usd.Stage) -> Usd.Stage:
    """Populate ``stage`` with the Phase 0 set plus a standalone Flow fire."""

    populate_fixed_scene(stage)
    stage.RemovePrim("/World/IgnitionSource")

    for log in stage.GetPrimAtPath("/World/Logs").GetChildren():
        UsdPhysics.CollisionAPI.Apply(log)

    camera = UsdGeom.Camera.Get(stage, CAMERA_PATH)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(7.8, -7.8, 5.8),
        Gf.Vec3d(0.0, 0.0, 1.15),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())

    _define_flow_prims(stage)
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(float(PHASE1_TOTAL_FRAMES))
    stage.SetTimeCodesPerSecond(60.0)
    stage.GetRootLayer().customLayerData = {
        "campfire:phase": "phase1",
        "campfire:scene": "flow_technical_spike",
        "campfire:flowVersion": FLOW_VERSION,
        "renderSettings": {
            "rtx:flow:enabled": True,
            "rtx:flow:pathTracingEnabled": True,
            "rtx:flow:rayTracedReflectionsEnabled": True,
            "rtx:flow:rayTracedTranslucencyEnabled": True,
        },
    }
    return stage


def export_flow_stage(stage: Usd.Stage, destination: Path) -> Path:
    return export_stage(stage, destination)
