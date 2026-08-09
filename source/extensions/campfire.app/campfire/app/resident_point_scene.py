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
from .resident_point_sidecar import (
    RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY,
    RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME,
    RESIDENT_POINT_LAYOUT_REPRESENTATIONS,
)
from .wood import get_log_dimensions, get_log_physics_transform


RESIDENT_POINT_APPLICATION_SETTING = (
    "/exts/campfire.app/residentPointApplicationEnabled"
)
RESIDENT_POINT_SOURCE_PATH = Sdf.Path("/World/ResidentPointSource")
RESIDENT_POINT_EMITTER_PATH = Sdf.Path("/World/Flow/ResidentPointEmitter")
RESIDENT_POINT_MATERIAL_PATH = Sdf.Path("/World/Materials/ResidentPointSource")


def resident_point_application_enabled(settings) -> bool:
    """Return the single explicit opt-in controlling the application spike."""

    return bool(settings.get_as_bool(RESIDENT_POINT_APPLICATION_SETTING))


def resident_point_layout_for_logs(stage: Usd.Stage, log_ids) -> dict:
    """Return the cardinal XY layout supported by the native Point ABI."""

    origins = []
    axes = []
    for log_id in log_ids:
        _radius_m, _length_m, axis = get_log_dimensions(stage, log_id)
        if axis != str(UsdGeom.Tokens.x):
            raise ValueError("Resident Point native layout requires local-X logs")
        transform = get_log_physics_transform(stage, log_id)
        origin = transform.ExtractTranslation()
        axial = transform.TransformDir(Gf.Vec3d(1.0, 0.0, 0.0)).GetNormalized()
        if abs(float(axial[2])) > 1.0e-5:
            raise ValueError("Resident Point native layout requires horizontal logs")
        absolute_x = abs(float(axial[0]))
        absolute_y = abs(float(axial[1]))
        if max(absolute_x, absolute_y) < 1.0 - 1.0e-5:
            raise ValueError("Resident Point native layout requires cardinal XY logs")
        origins.append(tuple(float(value) for value in origin))
        axes.append(0 if absolute_x >= absolute_y else 1)
    if not origins:
        raise ValueError("Resident Point layout requires logs")
    return {
        "revision": 1,
        "origins": tuple(origins),
        "axes": tuple(axes),
        "representation": RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY,
    }


def resident_point_frame_layout_for_logs(stage: Usd.Stage, log_ids) -> dict:
    """Return one right-handed rigid frame per log from a single USD sample."""

    origins = []
    frames = []
    for log_id in log_ids:
        _radius_m, _length_m, axis = get_log_dimensions(stage, log_id)
        if axis != str(UsdGeom.Tokens.x):
            raise ValueError("Resident Point frame layout requires local-X logs")
        transform = get_log_physics_transform(stage, log_id)
        origin = transform.ExtractTranslation()
        frame = []
        for local_axis in (
            Gf.Vec3d(1.0, 0.0, 0.0),
            Gf.Vec3d(0.0, 1.0, 0.0),
            Gf.Vec3d(0.0, 0.0, 1.0),
        ):
            transformed = transform.TransformDir(local_axis)
            length = float(transformed.GetLength())
            if not math.isfinite(length) or abs(length - 1.0) > 1.0e-6:
                raise ValueError("Resident Point frame layout requires unit scale")
            normalized = transformed / length
            frame.extend(float(normalized[index]) for index in range(3))
        axis_x, axis_y, axis_z = frame[0:3], frame[3:6], frame[6:9]

        def dot(first, second):
            return sum(left * right for left, right in zip(first, second))

        determinant = (
            axis_x[0] * (axis_y[1] * axis_z[2] - axis_y[2] * axis_z[1])
            - axis_x[1] * (axis_y[0] * axis_z[2] - axis_y[2] * axis_z[0])
            + axis_x[2] * (axis_y[0] * axis_z[1] - axis_y[1] * axis_z[0])
        )
        if (
            any(
                abs(dot(value, value) - 1.0) > 1.0e-6
                for value in (axis_x, axis_y, axis_z)
            )
            or any(
                abs(dot(first, second)) > 1.0e-6
                for first, second in (
                    (axis_x, axis_y),
                    (axis_x, axis_z),
                    (axis_y, axis_z),
                )
            )
            or determinant <= 0.0
            or abs(determinant - 1.0) > 4.0e-6
        ):
            raise ValueError(
                "Resident Point frame layout requires a right-handed rigid transform"
            )
        origins.append(tuple(float(value) for value in origin))
        frames.append(tuple(frame))
    if not origins:
        raise ValueError("Resident Point layout requires logs")
    return {
        "revision": 1,
        "origins": tuple(origins),
        "axes": (),
        "frames": tuple(frames),
        "representation": RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME,
    }


def preauthor_resident_snapshot_consumers(
    stage: Usd.Stage, log_ids, *, initial_revision: int = 0
) -> None:
    """Author the complete primary snapshot schema before stage connection."""

    if (
        isinstance(initial_revision, bool)
        or not isinstance(initial_revision, int)
        or initial_revision < 0
    ):
        raise ValueError("Initial Resident consumer revision must be non-negative")
    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    if not emitter:
        raise RuntimeError("Resident primary emitter is unavailable")
    emitter.CreateAttribute(
        "campfire:residentRevision", Sdf.ValueTypeNames.Int64
    ).Set(initial_revision)
    for log_id in log_ids:
        prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        if not prim:
            raise RuntimeError(f"Resident primary log is unavailable: {log_id}")
        values = (
            ("campfire:surfaceTemperatureK", Sdf.ValueTypeNames.Double, 293.15),
            ("campfire:charFraction", Sdf.ValueTypeNames.Double, 0.0),
            ("campfire:remainingMassRatio", Sdf.ValueTypeNames.Double, 1.0),
            ("campfire:weakestSupportRatio", Sdf.ValueTypeNames.Double, 1.0),
            ("campfire:residentRevision", Sdf.ValueTypeNames.Int64, initial_revision),
        )
        for name, type_name, fallback in values:
            attribute = prim.GetAttribute(name)
            if not attribute:
                attribute = prim.CreateAttribute(name, type_name)
            if not attribute.HasAuthoredValueOpinion() and not attribute.Set(fallback):
                raise RuntimeError(f"Unable to pre-author Resident attribute: {name}")
            if name == "campfire:residentRevision" and not attribute.Set(
                initial_revision
            ):
                raise RuntimeError("Unable to initialize Resident log revision")


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
    layout_representation: str = RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY,
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
    if layout_representation not in RESIDENT_POINT_LAYOUT_REPRESENTATIONS:
        raise ValueError("Resident Point layout representation is invalid")

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
    layout_revision = emitter.CreateAttribute(
        "campfire:layoutRevision", Sdf.ValueTypeNames.Int64
    )
    if not layout_revision.Set(1):
        raise RuntimeError("Unable to initialize Resident Point layout revision")
    representation = emitter.CreateAttribute(
        "campfire:layoutRepresentation", Sdf.ValueTypeNames.Token
    )
    if not representation.Set(layout_representation):
        raise RuntimeError("Unable to initialize Resident Point layout representation")

    layer_data = dict(stage.GetRootLayer().customLayerData)
    layer_data.update(
        {
            "campfire:residentPointApplication": True,
            "campfire:residentPointCount": point_count,
            "campfire:residentPointEmitterCount": 1,
            "campfire:residentPointStructuralAuthoring": "before-stage-connection",
            "campfire:residentPointLayoutRepresentation": layout_representation,
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
        "layout_representation": layout_representation,
    }
