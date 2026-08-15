"""Registered-schema stage authoring and validation for Phase 6IB.

The module is importable without Kit.  pxr is imported only by the actual
authoring/validation boundary executed in the app-ready Kit process.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
from pathlib import Path

SPEC_SCHEMA = "campfire.phase6ib.stage-spec.v1"
FLOAT3_EVIDENCE_SCHEMA = "campfire.phase6id.float3-evidence.v1"
FLOAT3_ULP_BUDGET = 0
_TOPOLOGY = None


def configure_repository_dependencies(topology_callable) -> None:
    """Inject the exact-loaded repository-local topology boundary once."""
    global _TOPOLOGY
    if not callable(topology_callable):
        raise TypeError("topology_dependency_not_callable")
    if _TOPOLOGY is not None and _TOPOLOGY is not topology_callable:
        raise RuntimeError("topology_dependency_conflict")
    _TOPOLOGY = topology_callable


def _topology(length: float, radius: float):
    if _TOPOLOGY is None:
        raise RuntimeError("topology_dependency_not_configured")
    return _TOPOLOGY(length, radius)
CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
REQUIRED_PRIMS = {
    "/World": "Xform",
    "/World/PhysicsScene": "PhysicsScene",
    "/World/Cameras": "Xform",
    "/World/Cameras/EndOn": "Camera",
    "/World/DiagnosticLog": "Xform",
    "/World/DiagnosticLog/FlowCollisionProxy": "Mesh",
    "/World/Flow": "Xform",
    "/World/Flow/Emitter": "FlowEmitterSphere",
    "/World/Flow/Simulate": "FlowSimulate",
    "/World/Flow/Simulate/advection": "FlowAdvectionCombustionParams",
    **{f"/World/Flow/Simulate/advection/{name}": "FlowAdvectionChannelParams" for name in CHANNELS},
    "/World/Flow/Simulate/vorticity": "FlowVorticityParams",
    "/World/Flow/Simulate/pressure": "FlowPressureParams",
    "/World/Flow/Simulate/summaryAllocate": "FlowSummaryAllocateParams",
    "/World/Flow/Simulate/nanoVdbExport": "FlowSparseNanoVdbExportParams",
    "/World/Flow/Offscreen": "FlowOffscreen",
    "/World/Flow/Offscreen/colormap": "FlowRayMarchColormapParams",
    "/World/Flow/Offscreen/shadow": "FlowShadowParams",
    "/World/Flow/Render": "FlowRender",
    "/World/Flow/Render/rayMarch": "FlowRayMarchParams",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _finite(value: object) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (list, tuple)):
        return all(_finite(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite(item) for key, item in value.items())
    return False


def stage_spec(frozen: dict, condition: str) -> dict:
    states = {item["name"]: item["physics_collision_enabled"] for item in frozen["condition_order"]}
    if condition not in states:
        raise ValueError("unknown_condition:" + condition)
    scene = frozen["fixed_scene"]
    points, counts, indices = _topology(scene["diagnostic_log_length_m"], scene["log_radius_m"])
    return {
        "schema": SPEC_SCHEMA,
        "condition": condition,
        "physics_collision_enabled": states[condition],
        "prims": [{"path": path, "type": type_name} for path, type_name in REQUIRED_PRIMS.items()],
        "scene": {
            "log_center_m": scene["log_center_m"],
            "log_length_m": scene["diagnostic_log_length_m"],
            "log_radius_m": scene["log_radius_m"],
            "proxy_topology": [len(points), len(counts), len(indices)],
            "source_center_m": scene["source_center_m"],
            "source_radius_m": scene["source_radius_m"],
            "source_surface_gap_m": scene["source_surface_gap_m"],
            "end_clearance_m": scene["source_to_nearest_end_clearance_m"],
            "camera_eye_m": scene["camera_eye_m"],
            "camera_target_m": scene["camera_target_m"],
            "camera_image_up": scene["camera_image_up"],
            "camera_focal_length_mm": scene["camera_focal_length_mm"],
            "capture_resolution": scene["capture_resolution"],
            "stable_capture_frames": scene["stable_capture_frames"],
            "roi": frozen["temporal_measurement"]["rois_normalized"],
            "numeric_gates": frozen["temporal_measurement"]["hard_gates"],
        },
        "advection": {
            "temperature": {"secondOrderBlendFactor": 0.9},
            "fuel": {"secondOrderBlendFactor": 0.9},
            "burn": {"secondOrderBlendFactor": 0.9},
            "smoke": {"damping": 0.3, "fade": 2.0, "secondOrderBlendFactor": 0.9},
            "velocity": {"damping": 0.01, "fade": 1.0, "secondOrderBlendFactor": 0.9},
            "divergence": {"damping": 0.01, "fade": 1.0, "secondOrderBlendFactor": 0.9},
        },
        "readback_calls": 0,
        "capture_calls": 0,
        "timeline_play_calls": 0,
    }


def validate_spec(spec: dict, frozen: dict, condition: str) -> dict:
    def reject(reason: str) -> dict:
        return {"accepted": False, "reason": reason}

    if not isinstance(spec, dict) or spec.get("schema") != SPEC_SCHEMA:
        return reject("schema_mismatch")
    if spec.get("condition") != condition:
        return reject("condition_mismatch")
    if not _finite(spec):
        return reject("nonfinite_value")
    prims = spec.get("prims")
    if not isinstance(prims, list):
        return reject("prim_list_type_invalid")
    paths = [item.get("path") for item in prims if isinstance(item, dict)]
    if len(paths) != len(prims):
        return reject("prim_entry_type_invalid")
    if len(set(paths)) != len(paths):
        return reject("duplicate_prim_path")
    expected = stage_spec(frozen, condition)
    expected_types = {item["path"]: item["type"] for item in expected["prims"]}
    actual_types = {item.get("path"): item.get("type") for item in prims}
    missing = sorted(set(expected_types) - set(actual_types))
    unknown = sorted(set(actual_types) - set(expected_types))
    if missing:
        return reject("required_prim_missing:" + missing[0])
    if unknown:
        return reject("unknown_prim:" + unknown[0])
    for path, type_name in expected_types.items():
        if actual_types[path] != type_name:
            return reject("prim_type_mismatch:" + path)
    if spec != expected:
        return reject("frozen_value_mismatch")
    return {"accepted": True, "reason": "pass", "spec_sha256": sha256_bytes(canonical_bytes(spec))}


def reject_legacy_inline_usda(data: bytes) -> bool:
    return b'FlowAdvectionChannelParams "temperature" { float secondOrderBlendFactor = 0.9 }' in data


def _set_registered(prim, name: str, value, expected_type: str | None = None) -> None:
    attribute = prim.GetAttribute(name)
    if not attribute:
        raise RuntimeError(f"registered_attribute_missing:{prim.GetPath()}.{name}")
    if expected_type is not None and str(attribute.GetTypeName()) != expected_type:
        raise RuntimeError(f"registered_attribute_type_mismatch:{prim.GetPath()}.{name}:{attribute.GetTypeName()}")
    if not attribute.Set(value):
        raise RuntimeError(f"registered_attribute_set_failed:{prim.GetPath()}.{name}")


def author_stage(path: Path, frozen: dict, condition: str):
    """Author the frozen diagnostic stage only through registered Kit schemas."""
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    spec = stage_spec(frozen, condition)
    validation = validate_spec(spec, frozen, condition)
    if not validation["accepted"]:
        raise RuntimeError("stage_spec_invalid:" + validation["reason"])
    path = Path(path)
    if path.exists():
        raise RuntimeError("stage_path_reuse_refused:" + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    if stage is None:
        raise RuntimeError("stage_create_failed")
    scene = frozen["fixed_scene"]
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(scene["simulation_updates"])
    stage.SetTimeCodesPerSecond(60)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world = UsdGeom.Xform.Define(stage, "/World").GetPrim()
    stage.SetDefaultPrim(world)
    stage.GetRootLayer().customLayerData = {
        "campfire:defaultOff": True,
        "campfire:diagnosticLongitudinalExtension": True,
        "campfire:display": "flow-only-plus-offline-outline",
        "campfire:flowVersion": "110.0.0",
        "campfire:phase": "phase6ib",
        "campfire:stageBuiltBeforeConnection": True,
        "renderSettings": {
            "rtx:flow:enabled": True,
            "rtx:flow:pathTracingEnabled": True,
            "rtx:flow:rayTracedReflectionsEnabled": True,
            "rtx:flow:rayTracedTranslucencyEnabled": True,
        },
    }
    physics = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    physics.CreateGravityMagnitudeAttr(9.81)

    UsdGeom.Xform.Define(stage, "/World/Cameras")
    camera = UsdGeom.Camera.Define(stage, "/World/Cameras/EndOn")
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
    camera.CreateFocalLengthAttr(scene["camera_focal_length_mm"])
    camera.CreateHorizontalApertureAttr(scene["camera_horizontal_aperture_mm"])
    camera.CreateVerticalApertureAttr(scene["camera_vertical_aperture_mm"])
    camera.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    ex, ey, ez = scene["camera_eye_m"]
    matrix = Gf.Matrix4d(1.0)
    for index, row in enumerate(((0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (ex, ey, ez, 1))):
        matrix.SetRow(index, Gf.Vec4d(*row))
    UsdGeom.Xformable(camera.GetPrim()).AddTransformOp().Set(matrix)

    log = UsdGeom.Xform.Define(stage, "/World/DiagnosticLog")
    log.AddTranslateOp().Set(Gf.Vec3d(*scene["log_center_m"]))
    points, counts, indices = _topology(scene["diagnostic_log_length_m"], scene["log_radius_m"])
    proxy = UsdGeom.Mesh.Define(stage, scene["proxy_path"])
    proxy.CreatePointsAttr([Gf.Vec3f(*point) for point in points])
    proxy.CreateFaceVertexCountsAttr(counts)
    proxy.CreateFaceVertexIndicesAttr(indices)
    proxy.CreateDoubleSidedAttr(False)
    proxy.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    proxy.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
    UsdPhysics.CollisionAPI.Apply(proxy.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(proxy.GetPrim()).CreateApproximationAttr("convexDecomposition")

    UsdGeom.Xform.Define(stage, "/World/Flow")
    emitter = stage.DefinePrim("/World/Flow/Emitter", "FlowEmitterSphere")
    emitter_values = {
        "allocationScale": 1.5, "coupleRateFuel": 2.0, "coupleRateSmoke": 1.0,
        "coupleRateTemperature": 10.0, "coupleRateVelocity": 2.0, "enabled": True,
        "fuel": 0.8, "layer": 0, "multisample": True, "numSubSteps": 2,
        "position": Gf.Vec3f(*scene["source_center_m"]), "radius": scene["source_radius_m"],
        "radiusIsWorldSpace": True, "smoke": 0.04, "temperature": 2.0,
        "velocity": Gf.Vec3f(0.0, 0.0, 0.3), "velocityIsWorldSpace": True,
    }
    for name, value in emitter_values.items():
        _set_registered(emitter, name, value)

    simulate = stage.DefinePrim("/World/Flow/Simulate", "FlowSimulate")
    simulate_values = {
        "blockMinLifetime": 4, "densityCellSize": 0.025, "enableVariableTimeStep": False,
        "forceDisableCoreSimulation": False, "forceDisableEmitters": False, "forceSimulate": True,
        "layer": 0, "maxStepsPerSimulate": 1, "physicsCollisionEnabled": spec["physics_collision_enabled"],
        "physicsConvexCollision": True, "simulateWhenPaused": False, "stepsPerSecond": 60.0,
        "velocitySubSteps": 1,
    }
    for name, value in simulate_values.items():
        _set_registered(simulate, name, value)

    advection = stage.DefinePrim("/World/Flow/Simulate/advection", "FlowAdvectionCombustionParams")
    for name, value in {
        "buoyancyPerTemp": 6.0, "burnPerTemp": 4.0, "combustionEnabled": True,
        "coolingRate": 1.5, "enabled": True, "fuelPerBurn": 0.25,
        "gravity": Gf.Vec3f(0.0, 0.0, -9.81), "ignitionTemp": 0.05,
        "smokePerBurn": 3.0, "tempPerBurn": 5.0,
    }.items():
        _set_registered(advection, name, value)
    for channel_name, values in spec["advection"].items():
        channel = stage.DefinePrim(f"/World/Flow/Simulate/advection/{channel_name}", "FlowAdvectionChannelParams")
        for name, value in values.items():
            _set_registered(channel, name, value, "float")

    vorticity = stage.DefinePrim("/World/Flow/Simulate/vorticity", "FlowVorticityParams")
    for name, value in {"enabled": True, "forceScale": 1.5, "velocityMask": 1.0}.items(): _set_registered(vorticity, name, value)
    pressure = stage.DefinePrim("/World/Flow/Simulate/pressure", "FlowPressureParams")
    _set_registered(pressure, "enabled", True)
    summary = stage.DefinePrim("/World/Flow/Simulate/summaryAllocate", "FlowSummaryAllocateParams")
    for name, value in {"enableNeighborAllocation": True, "smokeThreshold": 0.02, "speedThreshold": 1.0}.items(): _set_registered(summary, name, value)
    export = stage.DefinePrim("/World/Flow/Simulate/nanoVdbExport", "FlowSparseNanoVdbExportParams")
    for name in ("burnEnabled", "enabled", "fuelEnabled", "readbackEnabled", "smokeEnabled", "statisticsEnabled", "temperatureEnabled", "velocityEnabled"):
        _set_registered(export, name, True)

    offscreen = stage.DefinePrim("/World/Flow/Offscreen", "FlowOffscreen")
    _set_registered(offscreen, "layer", 0)
    colormap = stage.DefinePrim("/World/Flow/Offscreen/colormap", "FlowRayMarchColormapParams")
    _set_registered(colormap, "colorScale", 2.5)
    _set_registered(colormap, "colorScalePoints", [1.0] * 6)
    _set_registered(colormap, "resolution", 32)
    _set_registered(colormap, "rgbaPoints", [Gf.Vec4f(*value) for value in ((0.0154,0.0177,0.0154,0.004902),(0.03575,0.03575,0.03575,0.504902),(0.03575,0.03575,0.03575,0.504902),(1,0.1594,0.0134,0.8),(13.53,2.99,0.12599,0.8),(78,39,6.1,0.7))])
    _set_registered(colormap, "xPoints", [0.0, 0.05, 0.15, 0.6, 0.85, 1.0])
    shadow = stage.DefinePrim("/World/Flow/Offscreen/shadow", "FlowShadowParams")
    for name, value in {"attenuation": 0.045, "coarsePropagate": True, "enabled": True, "lightDirection": Gf.Vec3f(1,1,1)}.items(): _set_registered(shadow, name, value)
    render = stage.DefinePrim("/World/Flow/Render", "FlowRender")
    _set_registered(render, "layer", 0)
    ray = stage.DefinePrim("/World/Flow/Render/rayMarch", "FlowRayMarchParams")
    for name, value in {"attenuation": 0.05, "colorScale": 1.0, "shadowFactor": 1.0, "stepSizeScale": 0.75}.items(): _set_registered(ray, name, value)

    if not stage.GetRootLayer().Save():
        raise RuntimeError("stage_save_failed")
    return stage


def _plain(value):
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        try:
            return [_plain(item) for item in value]
        except TypeError:
            pass
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    return str(value)


def _float32(value: float) -> tuple[float, int]:
    packed = struct.pack(">f", float(value))
    return struct.unpack(">f", packed)[0], struct.unpack(">I", packed)[0]


def _ordered_float32_bits(bits: int) -> int:
    if bits in (0, 0x80000000):
        return 0x80000000
    return ((~bits) & 0xFFFFFFFF) if bits & 0x80000000 else (bits | 0x80000000)


def _numeric_vector3(value, role: str) -> list[float]:
    if value is None:
        raise ValueError(role + "_missing")
    if isinstance(value, (str, bytes, bool)):
        raise TypeError(role + "_vector_type_invalid")
    try:
        items = list(value)
    except TypeError as error:
        raise TypeError(role + "_vector_type_invalid") from error
    if len(items) != 3:
        raise ValueError(role + "_component_count_invalid")
    result = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(role + "_component_type_invalid")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise ValueError(role + "_component_nonfinite")
        result.append(numeric)
    return result


def canonical_float3_evidence(attribute_path: str, declared_type: str, expected, actual, ulp_budget: int = FLOAT3_ULP_BUDGET) -> dict:
    """Compare a registered USD float3 using its binary32 storage semantics."""
    evidence = {
        "schema": FLOAT3_EVIDENCE_SCHEMA,
        "attribute_path": attribute_path,
        "declared_usd_type": declared_type,
        "expected_original": _plain(expected),
        "actual_python_type": f"{type(actual).__module__}.{type(actual).__qualname__}" if actual is not None else None,
        "ulp_budget": ulp_budget,
        "signed_zero_policy": "equivalent",
        "accepted": False,
        "reason": None,
    }
    try:
        if declared_type != "float3":
            raise TypeError("declared_type_not_float3")
        if type(ulp_budget) is not int or ulp_budget < 0 or ulp_budget > 4:
            raise ValueError("ulp_budget_invalid")
        expected_values = _numeric_vector3(expected, "expected")
        actual_values = _numeric_vector3(actual, "actual")
        expected_quantized, expected_bits, actual_bits, distances, differences = [], [], [], [], []
        for expected_value, actual_value in zip(expected_values, actual_values):
            quantized, expected_bit = _float32(expected_value)
            actual_quantized, actual_bit = _float32(actual_value)
            expected_quantized.append(quantized)
            expected_bits.append(f"0x{expected_bit:08X}")
            actual_bits.append(f"0x{actual_bit:08X}")
            distances.append(abs(_ordered_float32_bits(expected_bit) - _ordered_float32_bits(actual_bit)))
            differences.append(abs(actual_value - quantized))
        evidence.update({
            "expected_float32": expected_quantized,
            "actual_elements": actual_values,
            "expected_float32_bits": expected_bits,
            "actual_float32_bits": actual_bits,
            "absolute_difference": differences,
            "ulp_distance": distances,
            "maximum_ulp_distance": max(distances),
        })
        evidence["accepted"] = all(distance <= ulp_budget for distance in distances)
        evidence["reason"] = "pass" if evidence["accepted"] else "float3_ulp_budget_exceeded"
    except (OverflowError, TypeError, ValueError, struct.error) as error:
        evidence["reason"] = str(error)
    return evidence


def validate_stage(stage, frozen: dict, condition: str, float3_evidence_callback=None) -> dict:
    spec = stage_spec(frozen, condition)
    required = {item["path"]: item["type"] for item in spec["prims"]}
    actual = {str(prim.GetPath()): prim.GetTypeName() for prim in stage.Traverse()}
    if set(actual) != set(required):
        missing, unknown = sorted(set(required)-set(actual)), sorted(set(actual)-set(required))
        raise RuntimeError("stage_prim_set_mismatch:" + json.dumps({"missing": missing, "unknown": unknown}))
    for path, type_name in required.items():
        if actual[path] != type_name:
            raise RuntimeError("stage_prim_type_mismatch:" + path)
    expected_collision = spec["physics_collision_enabled"]
    checks = {
        "/World/Flow/Simulate.physicsCollisionEnabled": ("bool", expected_collision),
        "/World/Flow/Emitter.position": ("float3", frozen["fixed_scene"]["source_center_m"]),
        "/World/Flow/Emitter.radius": ("float", frozen["fixed_scene"]["source_radius_m"]),
        "/World/Flow/Emitter.fuel": ("float", 0.8),
        "/World/Flow/Emitter.temperature": ("float", 2.0),
        "/World/Cameras/EndOn.focalLength": ("float", frozen["fixed_scene"]["camera_focal_length_mm"]),
    }
    channel_evidence = {}
    for channel, values in spec["advection"].items():
        for name, value in values.items():
            checks[f"/World/Flow/Simulate/advection/{channel}.{name}"] = ("float", value)
    evidence = {}
    for key, (type_name, expected) in checks.items():
        path, name = key.rsplit(".", 1)
        attribute = stage.GetPrimAtPath(path).GetAttribute(name)
        if not attribute or not attribute.HasAuthoredValueOpinion():
            raise RuntimeError("required_attribute_missing:" + key)
        if str(attribute.GetTypeName()) != type_name:
            raise RuntimeError("attribute_type_mismatch:" + key)
        raw_value = attribute.Get()
        value = _plain(raw_value)
        if not _finite(value):
            raise RuntimeError("attribute_nonfinite:" + key)
        expected_plain = _plain(expected)
        if type_name == "float3":
            float3 = canonical_float3_evidence(key, type_name, expected, raw_value)
            if float3_evidence_callback is not None:
                float3_evidence_callback(float3)
            if not float3["accepted"]:
                raise RuntimeError("attribute_value_mismatch:" + key + ":" + str(float3["reason"]))
        elif isinstance(expected_plain, float):
            if abs(float(value) - expected_plain) > 1e-6:
                raise RuntimeError("attribute_value_mismatch:" + key)
        elif value != expected_plain:
            raise RuntimeError("attribute_value_mismatch:" + key)
        evidence[key] = {"type": type_name, "value": value}
        if type_name == "float3":
            evidence[key]["canonical_float3"] = float3
        if "/advection/" in key:
            channel_evidence[key] = evidence[key]
    proxy = stage.GetPrimAtPath(frozen["fixed_scene"]["proxy_path"])
    points = proxy.GetAttribute("points").Get()
    counts = proxy.GetAttribute("faceVertexCounts").Get()
    indices = proxy.GetAttribute("faceVertexIndices").Get()
    topology_value = [len(points), len(counts), len(indices)]
    if topology_value != [26, 36, 120]:
        raise RuntimeError("proxy_topology_mismatch")
    if proxy.GetAttribute("physics:collisionEnabled").Get() is not True or proxy.GetAttribute("physics:approximation").Get() != "convexDecomposition":
        raise RuntimeError("proxy_collision_schema_mismatch")
    children = {child.GetName() for child in stage.GetPrimAtPath("/World/Flow/Simulate/advection").GetChildren()}
    if children != set(CHANNELS):
        raise RuntimeError("advection_channel_set_mismatch")
    return {
        "condition": condition,
        "root_layer_identifier": stage.GetRootLayer().identifier,
        "required_prim_count": len(required),
        "proxy_topology": topology_value,
        "attribute_evidence": evidence,
        "advection_evidence": channel_evidence,
        "spec_sha256": sha256_bytes(canonical_bytes(spec)),
    }


def semantic_snapshot(stage, normalize_collision: bool = False) -> list[dict]:
    rows = []
    for prim in stage.Traverse():
        attributes = []
        for attribute in sorted(prim.GetAttributes(), key=lambda item: item.GetName()):
            if not attribute.HasAuthoredValueOpinion():
                continue
            value = _plain(attribute.Get())
            if normalize_collision and str(prim.GetPath()) == "/World/Flow/Simulate" and attribute.GetName() == "physicsCollisionEnabled":
                value = "<CONDITION>"
            attributes.append({"name": attribute.GetName(), "type": str(attribute.GetTypeName()), "value": value})
        rows.append({"path": str(prim.GetPath()), "type": prim.GetTypeName(), "apis": sorted(prim.GetAppliedSchemas()), "attributes": attributes})
    return rows


def one_variable_diff(off_stage, on_stage) -> dict:
    off = semantic_snapshot(off_stage)
    on = semantic_snapshot(on_stage)
    changes = []
    for off_prim, on_prim in zip(off, on):
        if off_prim == on_prim:
            continue
        off_attrs = {item["name"]: item for item in off_prim["attributes"]}
        on_attrs = {item["name"]: item for item in on_prim["attributes"]}
        for name in sorted(set(off_attrs) | set(on_attrs)):
            if off_attrs.get(name) != on_attrs.get(name):
                changes.append({"path": off_prim["path"], "attribute": name, "off": off_attrs.get(name), "on": on_attrs.get(name)})
    common_off = sha256_bytes(canonical_bytes(semantic_snapshot(off_stage, True)))
    common_on = sha256_bytes(canonical_bytes(semantic_snapshot(on_stage, True)))
    accepted = len(changes) == 1 and changes[0]["path"] == "/World/Flow/Simulate" and changes[0]["attribute"] == "physicsCollisionEnabled" and common_off == common_on
    return {"accepted": accepted, "changes": changes, "normalized_common_sha256": common_off, "normalized_common_match": common_off == common_on}


def mutate_spec(base: dict, mutation: str) -> dict:
    value = copy.deepcopy(base)
    if mutation == "missing": value["prims"].pop()
    elif mutation == "duplicate": value["prims"].append(copy.deepcopy(value["prims"][0]))
    elif mutation == "type": value["prims"][0]["type"] = "Scope"
    elif mutation == "nan": value["scene"]["source_radius_m"] = float("nan")
    elif mutation == "unknown_schema": value["schema"] = "future.schema"
    else: raise ValueError("unknown_mutation")
    return value
