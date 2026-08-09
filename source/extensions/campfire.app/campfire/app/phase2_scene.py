"""Phase 2 dynamic-log scene and Flow follow adapter."""

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

from .flow_scene import (
    FLOW_EMITTER_PATH,
    FLOW_SIMULATE_PATH,
    PHASE1_TOTAL_FRAMES,
    populate_flow_scene,
)
from .scene import CAMERA_PATH, export_stage
from .wood import (
    LogSpec,
    WOOD_RENDER_REPRESENTATION_MESH,
    WOOD_RENDER_REPRESENTATION_ATTRIBUTE,
    create_log,
    get_log_world_position,
)


PHASE2_ADDED_LOG_ID = "Log_04"
PHASE2_ADD_FRAME = 30
PHASE2_CAPTURE_FRAMES = (45, 600)
PHASE2_TOTAL_FRAMES = PHASE2_CAPTURE_FRAMES[-1]
PHASE2_FIXED_DT_SECONDS = 1.0 / 60.0
PHASE2_EMITTER_OFFSET_M = Gf.Vec3f(0.0, 0.0, 0.12)
PHASE2_SPAWN_POSITION_M = (0.0, 0.0, 2.60)

INITIAL_LOG_SPECS = (
    LogSpec("Log_00", (0.0, -0.34, 0.18), 0.0),
    LogSpec("Log_01", (0.0, 0.34, 0.18), 0.0),
    LogSpec("Log_02", (-0.34, 0.0, 0.50), 90.0),
    LogSpec("Log_03", (0.34, 0.0, 0.50), 90.0),
)
ADDED_LOG_SPEC = LogSpec(PHASE2_ADDED_LOG_ID, PHASE2_SPAWN_POSITION_M, 25.0)


def populate_phase2_scene(
    stage: Usd.Stage, *, render_hierarchy: bool = False
) -> Usd.Stage:
    """Create four dynamic logs; the scenario adds a fifth at runtime."""

    populate_flow_scene(stage)
    stage.RemovePrim("/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Logs")

    for stone in stage.GetPrimAtPath("/World/Stones").GetChildren():
        UsdPhysics.CollisionAPI.Apply(stone)
    for slot, spec in enumerate(INITIAL_LOG_SPECS):
        create_log(
            stage,
            spec,
            render_hierarchy=render_hierarchy,
            render_log_slot=slot,
        )

    # Phase 2 does not consume local fields, so avoid the Phase 1 CPU copy.
    stage.GetPrimAtPath(
        FLOW_SIMULATE_PATH.AppendChild("nanoVdbExport")
    ).GetAttribute("readbackEnabled").Set(False)

    set_emitter_follow(stage, "Log_03")
    camera = UsdGeom.Camera.Get(stage, CAMERA_PATH)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(7.8, -7.8, 5.8),
        Gf.Vec3d(0.0, 0.0, 1.10),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())

    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(float(PHASE2_TOTAL_FRAMES))
    stage.SetTimeCodesPerSecond(60.0)
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:phase": "phase2",
        "campfire:scene": "dynamic_log_mvp",
        "campfire:fixedDtSeconds": PHASE2_FIXED_DT_SECONDS,
        "campfire:woodRenderHierarchy": bool(render_hierarchy),
    }
    return stage


def add_scenario_log(stage: Usd.Stage) -> Usd.Prim:
    """The deterministic add-log operation used by UI and headless scenario."""

    layer_data = stage.GetRootLayer().customLayerData
    render_hierarchy = bool(layer_data.get("campfire:woodRenderHierarchy", False))
    return create_log(
        stage,
        ADDED_LOG_SPEC,
        render_hierarchy=render_hierarchy,
        render_log_slot=len(INITIAL_LOG_SPECS),
    )


def set_emitter_follow(stage: Usd.Stage, log_id: str) -> Gf.Vec3f:
    """Update the Flow source from the authoritative USD rigid transform."""

    position = get_log_world_position(stage, log_id)
    target = Gf.Vec3f(position) + PHASE2_EMITTER_OFFSET_M
    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    emitter.GetAttribute("position").Set(target)
    emitter.GetAttribute("enabled").Set(True)
    return target


def export_phase2_stage(stage: Usd.Stage, destination: Path) -> Path:
    return export_stage(stage, destination)
