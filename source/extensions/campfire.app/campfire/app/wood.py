"""Authoritative log identity and rigid-body construction for Phase 2."""

import math
from dataclasses import dataclass

from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

from .wood_render_mesh import WOOD_RENDER_MAX_LOGS, author_wood_render_mesh


LOGS_PATH = Sdf.Path("/World/Logs")
WOOD_MATERIAL_PATH = Sdf.Path("/World/PhysicsMaterials/Wood")
WOOD_DENSITY_KG_M3 = 520.0
WOOD_STATIC_FRICTION = 0.70
WOOD_DYNAMIC_FRICTION = 0.55
WOOD_RESTITUTION = 0.10
WOOD_RENDER_HIERARCHY_SETTING = "/exts/campfire.app/woodRenderHierarchyEnabled"
WOOD_RENDER_REPRESENTATION_ATTRIBUTE = "campfire:renderRepresentation"
WOOD_RENDER_REPRESENTATION_LEGACY = "legacy_cylinder_v1"
WOOD_RENDER_REPRESENTATION_MESH = "uv_mesh_v1"
WOOD_RENDER_ATLAS_SLOT_ATTRIBUTE = "campfire:renderAtlasSlot"
WOOD_COLLIDER_NAME = "Collider"
WOOD_RENDER_SURFACE_NAME = "RenderSurface"


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


def _author_log_metadata(prim: Usd.Prim, spec: LogSpec) -> None:
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


def _apply_log_rigid_body(prim: Usd.Prim, spec: LogSpec) -> None:
    rigid_body = UsdPhysics.RigidBodyAPI.Apply(prim)
    rigid_body.CreateRigidBodyEnabledAttr(True)
    rigid_body.CreateKinematicEnabledAttr(False)
    rigid_body.CreateVelocityAttr(Gf.Vec3f(0.0))
    rigid_body.CreateAngularVelocityAttr(Gf.Vec3f(0.0))
    UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(spec.mass_kg)
    physx_body = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    physx_body.CreateLinearDampingAttr(0.05)
    physx_body.CreateAngularDampingAttr(0.20)


def _bind_wood_physics_material(stage: Usd.Stage, prim: Usd.Prim) -> None:
    binding = UsdShade.MaterialBindingAPI.Apply(prim)
    binding.Bind(
        UsdShade.Material(stage.GetPrimAtPath(WOOD_MATERIAL_PATH)),
        UsdShade.Tokens.weakerThanDescendants,
        "physics",
    )


def create_log(
    stage: Usd.Stage,
    spec: LogSpec,
    *,
    render_hierarchy: bool = False,
    render_log_slot: int | None = None,
) -> Usd.Prim:
    """Create one cylindrical log with identity, mass, collider and rigid body."""

    if not stage.GetPrimAtPath(LOGS_PATH):
        UsdGeom.Xform.Define(stage, LOGS_PATH)
    if not stage.GetPrimAtPath(WOOD_MATERIAL_PATH):
        define_wood_physics_material(stage)

    path = LOGS_PATH.AppendChild(spec.log_id)
    if stage.GetPrimAtPath(path):
        raise ValueError(f"Log ID already exists: {spec.log_id}")

    if render_hierarchy:
        if render_log_slot is None:
            render_log_slot = len(list_log_ids(stage))
        if not 0 <= render_log_slot < WOOD_RENDER_MAX_LOGS:
            raise ValueError("Wood render hierarchy supports at most 20 log slots")
        root = UsdGeom.Xform.Define(stage, path)
        root.AddTranslateOp().Set(Gf.Vec3d(*spec.position_m))
        root.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(
            _orientation_z(spec.rotation_z_deg)
        )
        prim = root.GetPrim()
        prim.CreateAttribute(
            WOOD_RENDER_REPRESENTATION_ATTRIBUTE, Sdf.ValueTypeNames.Token
        ).Set(WOOD_RENDER_REPRESENTATION_MESH)
        prim.CreateAttribute(
            WOOD_RENDER_ATLAS_SLOT_ATTRIBUTE, Sdf.ValueTypeNames.Int
        ).Set(render_log_slot)
        collider = UsdGeom.Cylinder.Define(
            stage, path.AppendChild(WOOD_COLLIDER_NAME)
        )
        collider.CreateAxisAttr(UsdGeom.Tokens.x)
        collider.CreateRadiusAttr(spec.radius_m)
        collider.CreateHeightAttr(spec.length_m)
        collider.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        collider_prim = collider.GetPrim()
        UsdPhysics.CollisionAPI.Apply(collider_prim)
        _bind_wood_physics_material(stage, collider_prim)
        render = UsdGeom.Mesh.Define(
            stage, path.AppendChild(WOOD_RENDER_SURFACE_NAME)
        )
        author_wood_render_mesh(render, spec.radius_m, spec.length_m, render_log_slot)
        render.CreateDisplayColorAttr([Gf.Vec3f(0.30, 0.12, 0.045)])
    else:
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
        UsdPhysics.CollisionAPI.Apply(prim)

    _author_log_metadata(prim, spec)
    _apply_log_rigid_body(prim, spec)
    if not render_hierarchy:
        # Preserve the legacy API-schema authoring order exactly when the
        # render hierarchy is disabled.
        _bind_wood_physics_material(stage, prim)
    return prim


def get_log_root(stage: Usd.Stage, log_id: str) -> Usd.Prim:
    prim = stage.GetPrimAtPath(LOGS_PATH.AppendChild(log_id))
    if not prim or prim.GetAttribute("campfire:logId").Get() != log_id:
        raise ValueError(f"Unknown log ID: {log_id}")
    return prim


def get_log_collider(stage: Usd.Stage, log_id: str) -> Usd.Prim:
    root = get_log_root(stage, log_id)
    if root.GetAttribute(WOOD_RENDER_REPRESENTATION_ATTRIBUTE).Get() == WOOD_RENDER_REPRESENTATION_MESH:
        collider = root.GetChild(WOOD_COLLIDER_NAME)
        if not collider or not collider.IsA(UsdGeom.Cylinder):
            raise RuntimeError(f"Wood hierarchy collider is invalid: {log_id}")
        return collider
    if not root.IsA(UsdGeom.Cylinder):
        raise RuntimeError(f"Legacy wood collider is invalid: {log_id}")
    return root


def get_log_render_surface(stage: Usd.Stage, log_id: str) -> Usd.Prim:
    root = get_log_root(stage, log_id)
    if root.GetAttribute(WOOD_RENDER_REPRESENTATION_ATTRIBUTE).Get() == WOOD_RENDER_REPRESENTATION_MESH:
        render = root.GetChild(WOOD_RENDER_SURFACE_NAME)
        if not render or not render.IsA(UsdGeom.Mesh):
            raise RuntimeError(f"Wood hierarchy render surface is invalid: {log_id}")
        return render
    if not root.IsA(UsdGeom.Cylinder):
        raise RuntimeError(f"Legacy wood render surface is invalid: {log_id}")
    return root


def get_log_dimensions(stage: Usd.Stage, log_id: str) -> tuple[float, float, str]:
    root = get_log_root(stage, log_id)
    collider = UsdGeom.Cylinder(get_log_collider(stage, log_id))
    return (
        float(collider.GetRadiusAttr().Get()),
        float(collider.GetHeightAttr().Get()),
        str(collider.GetAxisAttr().Get()),
    )


def get_log_physics_transform(stage: Usd.Stage, log_id: str) -> Gf.Matrix4d:
    return UsdGeom.Xformable(get_log_root(stage, log_id)).ComputeLocalToWorldTransform(
        Usd.TimeCode.Default()
    )


def get_log_material_target(stage: Usd.Stage, log_id: str) -> Usd.Prim:
    return get_log_render_surface(stage, log_id)


def move_log(
    stage: Usd.Stage,
    log_id: str,
    position_m: tuple[float, float, float],
    rotation_z_deg: float = 0.0,
) -> Usd.Prim:
    """Headless/UI shared operation corresponding to grabbing a log."""

    prim = get_log_root(stage, log_id)
    prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*position_m))
    prim.GetAttribute("xformOp:orient").Set(_orientation_z(rotation_z_deg))
    UsdPhysics.RigidBodyAPI(prim).GetVelocityAttr().Set(Gf.Vec3f(0.0))
    UsdPhysics.RigidBodyAPI(prim).GetAngularVelocityAttr().Set(Gf.Vec3f(0.0))
    return prim


def get_log_world_position(stage: Usd.Stage, log_id: str) -> Gf.Vec3d:
    return get_log_physics_transform(stage, log_id).ExtractTranslation()


def list_log_ids(stage: Usd.Stage) -> list[str]:
    logs = stage.GetPrimAtPath(LOGS_PATH)
    if not logs:
        return []
    return [
        str(child.GetAttribute("campfire:logId").Get())
        for child in logs.GetChildren()
        if child.GetAttribute("campfire:logId")
    ]
