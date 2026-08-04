"""Phase 5 jointed-log scene for deterministic collapse validation."""

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

from .combustion import WoodThermalModel
from .flow_scene import FLOW_EMITTER_PATH
from .phase2_scene import populate_phase2_scene
from .scene import CAMERA_PATH, export_stage
from .support import (
    SupportAssessment,
    create_collapse_support_model,
    release_segment_joint,
)
from .wood import LogSpec, create_log


PHASE5_LOG_ID = "CollapseLog"
PHASE5_SEGMENT_PATHS = (
    "/World/Logs/CollapseLog_A",
    "/World/Logs/CollapseLog_B",
)
PHASE5_JOINT_PATH = "/World/Joints/CollapseLogJoint"
PHASE5_FIXED_DT_SECONDS = 1.0 / 60.0
PHASE5_PRE_CAPTURE_FRAME = 20
PHASE5_RELEASE_FRAME = 30
PHASE5_POST_CAPTURE_FRAME = 260


def create_phase5_model() -> WoodThermalModel:
    return create_collapse_support_model()


def _make_kinematic(prim: Usd.Prim) -> None:
    UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Set(True)


def populate_phase5_scene(stage: Usd.Stage) -> Usd.Stage:
    """Create a two-segment bridge log held by one physical fixed joint."""

    populate_phase2_scene(stage)
    stage.RemovePrim("/World/Logs")
    stage.RemovePrim("/World/Stones")
    stage.RemovePrim("/World/Lights/Key")
    stage.GetPrimAtPath("/World/Lights/Dome").GetAttribute("inputs:intensity").Set(
        1200.0
    )
    UsdGeom.Xform.Define(stage, "/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Joints")

    for index, x_position in enumerate((-0.68, 0.68)):
        support = create_log(
            stage,
            LogSpec(
                f"Support_{index:02d}",
                (x_position, 0.0, 0.18),
                90.0,
                radius_m=0.16,
                length_m=1.25,
            ),
        )
        _make_kinematic(support)
        support.CreateAttribute("campfire:role", Sdf.ValueTypeNames.String).Set(
            "support"
        )
        UsdGeom.Gprim(support).GetDisplayColorAttr().Set(
            [Gf.Vec3f(0.22, 0.075, 0.025)]
        )

    model = create_phase5_model()
    cells_per_section = (
        model.spec.circumferential_cells * model.spec.radial_cells
    )
    segment_ranges = ((0, 6), (6, 12))
    for index, (path, center_x, axial_range) in enumerate(
        zip(PHASE5_SEGMENT_PATHS, (-0.45, 0.45), segment_ranges)
    ):
        log_id = path.rsplit("/", 1)[-1]
        segment = create_log(
            stage,
            LogSpec(
                log_id,
                (center_x, 0.0, 0.49),
                0.0,
                radius_m=model.spec.radius_m,
                length_m=0.90,
            ),
        )
        start = axial_range[0] * cells_per_section
        end = axial_range[1] * cells_per_section
        segment_mass = sum(cell.current_mass_kg for cell in model.cells[start:end])
        UsdPhysics.MassAPI(segment).GetMassAttr().Set(segment_mass)
        segment.CreateAttribute("campfire:role", Sdf.ValueTypeNames.String).Set(
            "burningSegment"
        )
        segment.CreateAttribute("campfire:parentLogId", Sdf.ValueTypeNames.String).Set(
            PHASE5_LOG_ID
        )
        segment.CreateAttribute("campfire:segmentIndex", Sdf.ValueTypeNames.Int).Set(
            index
        )
        segment.CreateAttribute("campfire:axialStart", Sdf.ValueTypeNames.Int).Set(
            axial_range[0]
        )
        segment.CreateAttribute(
            "campfire:axialEndExclusive", Sdf.ValueTypeNames.Int
        ).Set(axial_range[1])
        segment.CreateAttribute(
            "campfire:initialSegmentMassKg", Sdf.ValueTypeNames.Double
        ).Set(segment_mass)
        segment.CreateAttribute(
            "campfire:constraintReleased", Sdf.ValueTypeNames.Bool
        ).Set(False)
        UsdGeom.Gprim(segment).GetDisplayColorAttr().Set(
            [Gf.Vec3f(0.34, 0.11, 0.035)]
        )

    joint = UsdPhysics.FixedJoint.Define(stage, PHASE5_JOINT_PATH)
    joint.CreateBody0Rel().SetTargets([Sdf.Path(PHASE5_SEGMENT_PATHS[0])])
    joint.CreateBody1Rel().SetTargets([Sdf.Path(PHASE5_SEGMENT_PATHS[1])])
    joint.CreateLocalPos0Attr(Gf.Vec3f(0.45, 0.0, 0.0))
    joint.CreateLocalPos1Attr(Gf.Vec3f(-0.45, 0.0, 0.0))
    joint.CreateLocalRot0Attr(Gf.Quatf(1.0))
    joint.CreateLocalRot1Attr(Gf.Quatf(1.0))
    joint.GetPrim().CreateAttribute(
        "campfire:releaseReason", Sdf.ValueTypeNames.String
    ).Set("crossSectionSupport")

    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    emitter.GetAttribute("position").Set(Gf.Vec3f(0.0, 0.0, 0.38))
    emitter.GetAttribute("fuel").Set(0.08)
    emitter.GetAttribute("temperature").Set(0.55)
    emitter.GetAttribute("smoke").Set(0.05)
    emitter.GetAttribute("enabled").Set(True)

    camera = UsdGeom.Camera.Get(stage, CAMERA_PATH)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(4.8, -6.6, 3.6),
        Gf.Vec3d(0.0, 0.0, 0.42),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(float(PHASE5_POST_CAPTURE_FRAME))
    stage.SetTimeCodesPerSecond(60.0)
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:phase": "phase5",
        "campfire:scene": "collapse_reignition",
        "campfire:fixedDtSeconds": PHASE5_FIXED_DT_SECONDS,
    }
    return stage


def release_phase5_structure(
    stage: Usd.Stage,
    model: WoodThermalModel,
    assessment: SupportAssessment,
):
    updates = release_segment_joint(
        stage,
        model,
        assessment,
        PHASE5_SEGMENT_PATHS,
        PHASE5_JOINT_PATH,
    )
    colors = (Gf.Vec3f(0.10, 0.035, 0.018), Gf.Vec3f(0.13, 0.045, 0.020))
    angular_velocities = (Gf.Vec3f(0.0, 8.0, 0.0), Gf.Vec3f(0.0, -8.0, 0.0))
    for path, color, angular_velocity in zip(
        PHASE5_SEGMENT_PATHS, colors, angular_velocities
    ):
        prim = stage.GetPrimAtPath(path)
        UsdGeom.Gprim(prim).GetDisplayColorAttr().Set([color])
        body = UsdPhysics.RigidBodyAPI(prim)
        body.GetVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, -0.05))
        body.GetAngularVelocityAttr().Set(angular_velocity)

    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    emitter.GetAttribute("fuel").Set(0.72)
    emitter.GetAttribute("temperature").Set(1.0)
    emitter.GetAttribute("smoke").Set(0.18)
    emitter.GetAttribute("enabled").Set(True)
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:constraintReleased": True,
        "campfire:failedSection": assessment.weakest_section,
        "campfire:supportAtRelease": assessment.weakest_support_ratio,
    }
    return updates


def export_phase5_stage(stage: Usd.Stage, destination: Path) -> Path:
    return export_stage(stage, destination)
