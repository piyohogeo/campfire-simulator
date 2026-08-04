"""Deterministic Phase 0 scene construction."""

import math
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics


CAMERA_PATH = Sdf.Path("/World/Camera")
WORLD_PATH = Sdf.Path("/World")


def _set_transform(prim, *, translate=None, rotate_xyz=None, scale=None):
    xformable = UsdGeom.Xformable(prim)
    if translate is not None:
        xformable.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if rotate_xyz is not None:
        xformable.AddRotateXYZOp().Set(Gf.Vec3f(*rotate_xyz))
    if scale is not None:
        xformable.AddScaleOp().Set(Gf.Vec3f(*scale))


def _set_display_color(gprim, color):
    gprim.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def populate_fixed_scene(stage: Usd.Stage) -> Usd.Stage:
    """Populate ``stage`` with a deterministic campfire placeholder scene."""

    if stage.GetPrimAtPath(WORLD_PATH):
        stage.RemovePrim(WORLD_PATH)

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    world = UsdGeom.Xform.Define(stage, WORLD_PATH)
    stage.SetDefaultPrim(world.GetPrim())

    physics_scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    physics_scene.CreateGravityMagnitudeAttr(9.81)

    ground = UsdGeom.Cylinder.Define(stage, "/World/Ground")
    ground.CreateAxisAttr(UsdGeom.Tokens.z)
    ground.CreateRadiusAttr(5.0)
    ground.CreateHeightAttr(0.2)
    _set_transform(ground.GetPrim(), translate=(0.0, 0.0, -0.1))
    _set_display_color(ground, (0.08, 0.055, 0.035))
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim())

    stones = UsdGeom.Xform.Define(stage, "/World/Stones")
    del stones
    for index in range(12):
        angle = index * 30.0
        radians = angle * 3.141592653589793 / 180.0
        x = 1.55 * math.cos(radians)
        y = 1.55 * math.sin(radians)
        stone = UsdGeom.Sphere.Define(stage, f"/World/Stones/Stone_{index:02d}")
        stone.CreateRadiusAttr(0.42)
        _set_transform(
            stone.GetPrim(),
            translate=(x, y, 0.22),
            scale=(1.15, 0.85, 0.65),
        )
        _set_display_color(stone, (0.22, 0.20, 0.18))

    UsdGeom.Xform.Define(stage, "/World/Logs")
    log_specs = (
        ("Log_00", (0.0, -0.42, 0.34), 0.0),
        ("Log_01", (0.0, 0.42, 0.34), 0.0),
        ("Log_02", (-0.42, 0.0, 0.78), 90.0),
        ("Log_03", (0.42, 0.0, 0.78), 90.0),
    )
    for name, position, rotation_z in log_specs:
        log = UsdGeom.Cylinder.Define(stage, f"/World/Logs/{name}")
        log.CreateAxisAttr(UsdGeom.Tokens.x)
        log.CreateRadiusAttr(0.23)
        log.CreateHeightAttr(2.7)
        _set_transform(
            log.GetPrim(),
            translate=position,
            rotate_xyz=(0.0, 0.0, rotation_z),
        )
        _set_display_color(log, (0.30, 0.12, 0.045))

    ignition = UsdGeom.Cone.Define(stage, "/World/IgnitionSource")
    ignition.CreateAxisAttr(UsdGeom.Tokens.z)
    ignition.CreateRadiusAttr(0.38)
    ignition.CreateHeightAttr(1.25)
    _set_transform(ignition.GetPrim(), translate=(0.0, 0.0, 0.68))
    _set_display_color(ignition, (1.0, 0.18, 0.015))

    camera = UsdGeom.Camera.Define(stage, CAMERA_PATH)
    camera.CreateFocalLengthAttr(42.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(7.2, -7.2, 5.3),
        Gf.Vec3d(0.0, 0.0, 0.55),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.AddTransformOp().Set(view.GetInverse())

    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(650.0)
    dome.CreateColorAttr(Gf.Vec3f(0.42, 0.50, 0.70))

    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(24000.0)
    key.CreateRadiusAttr(0.35)
    key.CreateColorAttr(Gf.Vec3f(1.0, 0.35, 0.08))
    _set_transform(key.GetPrim(), translate=(0.0, 0.0, 2.5))

    stage.GetRootLayer().customLayerData = {
        "campfire:phase": "phase0",
        "campfire:scene": "fixed_bootstrap",
    }
    return stage


def export_stage(stage: Usd.Stage, destination: Path) -> Path:
    """Export the current root layer as an ASCII USD file."""

    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not stage.GetRootLayer().Export(str(destination)):
        raise RuntimeError(f"Failed to export Phase 0 scene to {destination}")
    return destination
