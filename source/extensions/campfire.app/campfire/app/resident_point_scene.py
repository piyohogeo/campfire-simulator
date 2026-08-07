"""Pre-author the default-off Resident Point application scene boundary.

This module only performs structural authoring.  Callers must invoke
``configure_resident_point_application_scene`` before the stage is connected
to a live Kit USD context.  Once connected, ``ResidentPointSidecar`` updates
the existing array attributes and revision without redefining Prim structure.
"""

from __future__ import annotations

import math

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

from .flow_scene import FLOW_EMITTER_PATH, FLOW_SIMULATE_PATH


RESIDENT_POINT_APPLICATION_SETTING = (
    "/exts/campfire.app/residentPointApplicationEnabled"
)
RESIDENT_POINT_SOURCE_PATH = Sdf.Path("/World/ResidentPointSource")
RESIDENT_POINT_EMITTER_PATH = Sdf.Path("/World/Flow/ResidentPointEmitter")
RESIDENT_POINT_MATERIAL_PATH = Sdf.Path("/World/Materials/ResidentPointSource")


def resident_point_application_enabled(settings) -> bool:
    """Return the single explicit opt-in controlling the application spike."""

    return bool(settings.get_as_bool(RESIDENT_POINT_APPLICATION_SETTING))


def _set_existing(prim: Usd.Prim, name: str, value) -> None:
    attribute = prim.GetAttribute(name)
    if not attribute:
        raise RuntimeError(f"Flow schema attribute unavailable: {prim.GetPath()}.{name}")
    if not attribute.Set(value):
        raise RuntimeError(f"Flow attribute Set failed: {prim.GetPath()}.{name}")


def _validated_positions(positions) -> Vt.Vec3fArray:
    converted = []
    for value in positions:
        point = Gf.Vec3f(*(float(component) for component in value))
        if not all(math.isfinite(float(component)) for component in point):
            raise ValueError("Resident Point positions must be finite")
        converted.append(point)
    if not converted:
        raise ValueError("Resident Point application scene requires points")
    return Vt.Vec3fArray(converted)


def configure_resident_point_application_scene(
    stage: Usd.Stage,
    positions,
    *,
    initial_revision: int = 0,
) -> dict:
    """Add one fully-authored Point source while the stage is still offline.

    The existing Sphere emitter remains present for the primary snapshot
    consumer and rollback diagnostics, but is disabled as a Flow source.  This
    is an opt-in technical boundary and does not alter the canonical Phase 3
    scene or its default path.
    """

    if stage is None:
        raise ValueError("Resident Point application scene requires a stage")
    if (
        isinstance(initial_revision, bool)
        or not isinstance(initial_revision, int)
        or initial_revision < 0
    ):
        raise ValueError("Initial Resident Point revision must be non-negative")

    point_positions = _validated_positions(positions)
    point_count = len(point_positions)
    sphere = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    if not sphere or sphere.GetTypeName() != "FlowEmitterSphere":
        raise RuntimeError("Resident Point application requires the fallback Sphere")
    for name, value in (
        ("enabled", False),
        ("fuel", 0.0),
        ("temperature", 0.0),
        ("smoke", 0.0),
        ("coupleRateFuel", 0.0),
        ("coupleRateTemperature", 0.0),
        ("coupleRateSmoke", 0.0),
    ):
        _set_existing(sphere, name, value)

    nano_vdb_export = stage.GetPrimAtPath(
        FLOW_SIMULATE_PATH.AppendChild("nanoVdbExport")
    )
    _set_existing(nano_vdb_export, "readbackEnabled", True)

    material = UsdShade.Material.Define(stage, RESIDENT_POINT_MATERIAL_PATH)
    shader = UsdShade.Shader.Define(
        stage, RESIDENT_POINT_MATERIAL_PATH.AppendChild("Shader")
    )
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(1.0, 0.14, 0.015)
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.35, 0.025, 0.005)
    )
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    source = UsdGeom.Points.Define(stage, RESIDENT_POINT_SOURCE_PATH)
    source.CreatePointsAttr(point_positions)
    source.CreateWidthsAttr(Vt.FloatArray([0.003] * point_count))
    source.CreateDisplayColorAttr([Gf.Vec3f(1.0, 0.12, 0.01)])
    UsdShade.MaterialBindingAPI.Apply(source.GetPrim()).Bind(material)

    emitter = stage.DefinePrim(RESIDENT_POINT_EMITTER_PATH, "FlowEmitterPoint")
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
        ("fuel", 0.0),
        ("temperature", 0.0),
        ("smoke", 0.0),
        ("velocity", Gf.Vec3f(0.0, 0.0, 0.35)),
        ("velocityIsWorldSpace", True),
        ("updateCoarseDensity", True),
        ("enableStreaming", False),
        ("streamOnce", False),
    ):
        _set_existing(emitter, name, value)
    zeros = Vt.FloatArray([0.0] * point_count)
    _set_existing(emitter, "pointPositions", point_positions)
    _set_existing(emitter, "pointFuels", zeros)
    _set_existing(emitter, "pointTemperatures", zeros)
    _set_existing(emitter, "pointSmokes", zeros)
    _set_existing(
        emitter,
        "pointVelocities",
        Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 0.35)] * point_count),
    )
    points_prim = emitter.GetRelationship("pointsPrim")
    if not points_prim or not points_prim.SetTargets([RESIDENT_POINT_SOURCE_PATH]):
        raise RuntimeError("FlowEmitterPoint pointsPrim relationship failed")
    revision = emitter.CreateAttribute(
        "campfire:residentRevision", Sdf.ValueTypeNames.Int64
    )
    if not revision.Set(initial_revision):
        raise RuntimeError("Unable to initialize Resident Point revision")

    layer_data = dict(stage.GetRootLayer().customLayerData)
    layer_data.update(
        {
            "campfire:residentPointApplication": True,
            "campfire:residentPointCount": point_count,
            "campfire:residentPointEmitterCount": 1,
            "campfire:residentPointStructuralAuthoring": "before-stage-connection",
        }
    )
    stage.GetRootLayer().customLayerData = layer_data
    return {
        "enabled": True,
        "point_count": point_count,
        "emitter_count": 1,
        "source_path": str(RESIDENT_POINT_SOURCE_PATH),
        "emitter_path": str(RESIDENT_POINT_EMITTER_PATH),
        "fallback_sphere_path": str(FLOW_EMITTER_PATH),
    }
