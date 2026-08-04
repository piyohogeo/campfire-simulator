"""Authoritative log identity and rigid-body construction for Phase 2."""

import math
from dataclasses import dataclass

from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade


LOGS_PATH = Sdf.Path("/World/Logs")
WOOD_MATERIAL_PATH = Sdf.Path("/World/PhysicsMaterials/Wood")
WOOD_DENSITY_KG_M3 = 520.0
WOOD_STATIC_FRICTION = 0.70
WOOD_DYNAMIC_FRICTION = 0.55
WOOD_RESTITUTION = 0.10


@dataclass(frozen=True)
class LogSpec:
    """SI-unit inputs used to construct one persistent log rigid body."""

    log_id: str
    position_m: tuple[float, float, float]
    rotation_z_deg: float = 0.0
    radius_m: float = 0.16
    length_m: float = 1.80
    density_kg_m3: float = WOOD_DENSITY_KG_M3

    @property
    def mass_kg(self) -> float:
        return math.pi * self.radius_m**2 * self.length_m * self.density_kg_m3


def _orientation_z(degrees: float) -> Gf.Quatf:
    half_angle = math.radians(degrees) * 0.5
    return Gf.Quatf(
        math.cos(half_angle), Gf.Vec3f(0.0, 0.0, math.sin(half_angle))
    )


def define_wood_physics_material(stage: Usd.Stage) -> UsdShade.Material:
    """Define the measured-unit wood contact material used by every log."""

    material = UsdShade.Material.Define(stage, WOOD_MATERIAL_PATH)
    physics_material = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    physics_material.CreateStaticFrictionAttr(WOOD_STATIC_FRICTION)
    physics_material.CreateDynamicFrictionAttr(WOOD_DYNAMIC_FRICTION)
    physics_material.CreateRestitutionAttr(WOOD_RESTITUTION)
    return material


def create_log(stage: Usd.Stage, spec: LogSpec) -> Usd.Prim:
    """Create one cylindrical log with identity, mass, collider and rigid body."""

    if not stage.GetPrimAtPath(LOGS_PATH):
        UsdGeom.Xform.Define(stage, LOGS_PATH)
    if not stage.GetPrimAtPath(WOOD_MATERIAL_PATH):
        define_wood_physics_material(stage)

    path = LOGS_PATH.AppendChild(spec.log_id)
    if stage.GetPrimAtPath(path):
        raise ValueError(f"Log ID already exists: {spec.log_id}")

    log = UsdGeom.Cylinder.Define(stage, path)
    log.CreateAxisAttr(UsdGeom.Tokens.x)
    log.CreateRadiusAttr(spec.radius_m)
    log.CreateHeightAttr(spec.length_m)
    log.CreateDisplayColorAttr([Gf.Vec3f(0.30, 0.12, 0.045)])
    log.AddTranslateOp().Set(Gf.Vec3d(*spec.position_m))
    log.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(
        _orientation_z(spec.rotation_z_deg)
    )

    prim = log.GetPrim()
    prim.CreateAttribute("campfire:logId", Sdf.ValueTypeNames.String).Set(spec.log_id)
    prim.CreateAttribute("campfire:radiusM", Sdf.ValueTypeNames.Double).Set(
        spec.radius_m
    )
    prim.CreateAttribute("campfire:lengthM", Sdf.ValueTypeNames.Double).Set(
        spec.length_m
    )
    prim.CreateAttribute("campfire:densityKgM3", Sdf.ValueTypeNames.Double).Set(
        spec.density_kg_m3
    )
    prim.CreateAttribute("campfire:initialMassKg", Sdf.ValueTypeNames.Double).Set(
        spec.mass_kg
    )

    UsdPhysics.CollisionAPI.Apply(prim)
    rigid_body = UsdPhysics.RigidBodyAPI.Apply(prim)
    rigid_body.CreateRigidBodyEnabledAttr(True)
    rigid_body.CreateKinematicEnabledAttr(False)
    rigid_body.CreateVelocityAttr(Gf.Vec3f(0.0))
    rigid_body.CreateAngularVelocityAttr(Gf.Vec3f(0.0))

    mass = UsdPhysics.MassAPI.Apply(prim)
    mass.CreateMassAttr(spec.mass_kg)

    # Mild damping suppresses long-lived numerical jitter without constraining
    # the drop.  Values are dimensionless PhysX coefficients.
    physx_body = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    physx_body.CreateLinearDampingAttr(0.05)
    physx_body.CreateAngularDampingAttr(0.20)

    binding = UsdShade.MaterialBindingAPI.Apply(prim)
    binding.Bind(
        UsdShade.Material(stage.GetPrimAtPath(WOOD_MATERIAL_PATH)),
        UsdShade.Tokens.weakerThanDescendants,
        "physics",
    )
    return prim


def move_log(
    stage: Usd.Stage,
    log_id: str,
    position_m: tuple[float, float, float],
    rotation_z_deg: float = 0.0,
) -> Usd.Prim:
    """Headless/UI shared operation corresponding to grabbing a log."""

    prim = stage.GetPrimAtPath(LOGS_PATH.AppendChild(log_id))
    if not prim:
        raise ValueError(f"Unknown log ID: {log_id}")
    prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*position_m))
    prim.GetAttribute("xformOp:orient").Set(_orientation_z(rotation_z_deg))
    UsdPhysics.RigidBodyAPI(prim).GetVelocityAttr().Set(Gf.Vec3f(0.0))
    UsdPhysics.RigidBodyAPI(prim).GetAngularVelocityAttr().Set(Gf.Vec3f(0.0))
    return prim


def get_log_world_position(stage: Usd.Stage, log_id: str) -> Gf.Vec3d:
    prim = stage.GetPrimAtPath(LOGS_PATH.AppendChild(log_id))
    if not prim:
        raise ValueError(f"Unknown log ID: {log_id}")
    return UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
        Usd.TimeCode.Default()
    ).ExtractTranslation()


def list_log_ids(stage: Usd.Stage) -> list[str]:
    logs = stage.GetPrimAtPath(LOGS_PATH)
    if not logs:
        return []
    return [
        str(child.GetAttribute("campfire:logId").Get())
        for child in logs.GetChildren()
        if child.GetAttribute("campfire:logId")
    ]
