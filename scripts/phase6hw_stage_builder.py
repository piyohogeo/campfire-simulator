"""Pure-Python USDA authoring for the Phase 6HW end-on diagnostic log."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


TOKEN_OFF = b"bool physicsCollisionEnabled = 0"
TOKEN_ON = b"bool physicsCollisionEnabled = 1"
TOKEN_COMMON = b"bool physicsCollisionEnabled = <CONDITION>"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _fmt(value: float) -> str:
    text = f"{value:.9f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def topology(length_m: float, radius_m: float, segments: int = 12) -> tuple[list[tuple[float, float, float]], list[int], list[int]]:
    half = length_m * 0.5
    points: list[tuple[float, float, float]] = []
    for x in (-half, half):
        for segment in range(segments):
            angle = 2.0 * math.pi * segment / segments
            points.append((x, radius_m * math.cos(angle), radius_m * math.sin(angle)))
    left_center, right_center = len(points), len(points) + 1
    points.extend(((-half, 0.0, 0.0), (half, 0.0, 0.0)))
    counts: list[int] = []
    indices: list[int] = []
    for segment in range(segments):
        following = (segment + 1) % segments
        counts.append(4)
        indices.extend((segment, following, segments + following, segments + segment))
    for segment in range(segments):
        following = (segment + 1) % segments
        counts.extend((3, 3))
        indices.extend((left_center, following, segment))
        indices.extend((right_center, segments + segment, segments + following))
    return points, counts, indices


def settings_common(contract: dict) -> dict:
    scene = contract["fixed_scene"]
    return {
        "schema": contract["stage_authoring"]["settings_schema"],
        "diagnostic_single_log": True,
        "log_axis": scene["log_axis"],
        "log_center_m": scene["log_center_m"],
        "log_length_m": scene["diagnostic_log_length_m"],
        "production_log_length_m": scene["production_proxy_length_m"],
        "log_radius_m": scene["log_radius_m"],
        "proxy_topology": [scene["proxy_vertices"], scene["proxy_faces"], scene["proxy_indices"]],
        "source_center_m": scene["source_center_m"],
        "source_radius_m": scene["source_radius_m"],
        "source_surface_gap_m": scene["source_surface_gap_m"],
        "velocity_voxel_m": scene["expected_velocity_voxel_m"],
        "end_clearance_m": scene["source_to_nearest_end_clearance_m"],
        "camera_eye_m": scene["camera_eye_m"],
        "camera_target_m": scene["camera_target_m"],
        "camera_focal_length_mm": scene["camera_focal_length_mm"],
        "resolution": scene["capture_resolution"],
        "preplay_updates": scene["preplay_updates"],
        "simulation_updates": scene["simulation_updates"],
        "active_block_frames": scene["active_block_frames"],
        "stable_capture_frames": scene["stable_capture_frames"],
        "renderer_drain_updates": scene["renderer_drain_updates"],
        "display": scene["display"],
    }


def settings_descriptor(contract: dict, condition: str) -> dict:
    expected = {item["name"]: item["physics_collision_enabled"] for item in contract["condition_order"]}
    if condition not in expected:
        raise ValueError(f"unknown condition: {condition}")
    return {**settings_common(contract), "condition": condition, "physics_collision_enabled": expected[condition]}


def normalized_stage_bytes(data: bytes) -> bytes:
    count = data.count(TOKEN_OFF) + data.count(TOKEN_ON)
    if count != 1:
        raise ValueError(f"physicsCollisionEnabled token count must be one, got {count}")
    return data.replace(TOKEN_OFF, TOKEN_COMMON).replace(TOKEN_ON, TOKEN_COMMON)


def build_stage_bytes(contract: dict, condition: str) -> bytes:
    scene = contract["fixed_scene"]
    collision = {item["name"]: item["physics_collision_enabled"] for item in contract["condition_order"]}
    if condition not in collision:
        raise ValueError(f"unknown condition: {condition}")
    points, counts, indices = topology(scene["diagnostic_log_length_m"], scene["log_radius_m"])
    points_text = ", ".join(f"({_fmt(x)}, {_fmt(y)}, {_fmt(z)})" for x, y, z in points)
    counts_text = ", ".join(str(value) for value in counts)
    indices_text = ", ".join(str(value) for value in indices)
    enabled = "1" if collision[condition] else "0"
    cx, cy, cz = scene["log_center_m"]
    sx, sy, sz = scene["source_center_m"]
    ex, ey, ez = scene["camera_eye_m"]
    text = f'''#usda 1.0
(
    customLayerData = {{
        bool "campfire:defaultOff" = 1
        bool "campfire:diagnosticLongitudinalExtension" = 1
        string "campfire:display" = "flow-only-plus-offline-outline"
        string "campfire:flowVersion" = "110.0.0"
        string "campfire:phase" = "phase6hw"
        bool "campfire:stageBuiltBeforeConnection" = 1
        dictionary renderSettings = {{
            bool "rtx:flow:enabled" = 1
            bool "rtx:flow:pathTracingEnabled" = 1
            bool "rtx:flow:rayTracedReflectionsEnabled" = 1
            bool "rtx:flow:rayTracedTranslucencyEnabled" = 1
        }}
    }}
    defaultPrim = "World"
    endTimeCode = {scene["simulation_updates"]}
    metersPerUnit = 1
    startTimeCode = 0
    timeCodesPerSecond = 60
    upAxis = "Z"
)

def Xform "World"
{{
    def PhysicsScene "PhysicsScene"
    {{
        vector3f physics:gravityDirection = (0, 0, -1)
        float physics:gravityMagnitude = 9.81
    }}

    def Xform "Cameras"
    {{
        def Camera "EndOn"
        {{
            float2 clippingRange = (0.05, 100)
            float focalLength = {scene["camera_focal_length_mm"]}
            float horizontalAperture = {scene["camera_horizontal_aperture_mm"]}
            float verticalAperture = {scene["camera_vertical_aperture_mm"]}
            token projection = "perspective"
            matrix4d xformOp:transform = ( (0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), ({_fmt(ex)}, {_fmt(ey)}, {_fmt(ez)}, 1) )
            uniform token[] xformOpOrder = ["xformOp:transform"]
        }}
    }}

    def Xform "DiagnosticLog"
    {{
        double3 xformOp:translate = ({_fmt(cx)}, {_fmt(cy)}, {_fmt(cz)})
        uniform token[] xformOpOrder = ["xformOp:translate"]

        def Mesh "FlowCollisionProxy" (
            prepend apiSchemas = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]
        )
        {{
            int[] faceVertexCounts = [{counts_text}]
            int[] faceVertexIndices = [{indices_text}]
            point3f[] points = [{points_text}]
            bool doubleSided = 0
            uniform token subdivisionScheme = "none"
            token visibility = "invisible"
            bool physics:collisionEnabled = 1
            uniform token physics:approximation = "convexDecomposition"
        }}
    }}

    def Xform "Flow"
    {{
        def FlowEmitterSphere "Emitter"
        {{
            float allocationScale = 1.5
            float coupleRateFuel = 2
            float coupleRateSmoke = 1
            float coupleRateTemperature = 10
            float coupleRateVelocity = 2
            bool enabled = 1
            float fuel = 0.8
            int layer = 0
            bool multisample = 1
            uint numSubSteps = 2
            float3 position = ({_fmt(sx)}, {_fmt(sy)}, {_fmt(sz)})
            float radius = {scene["source_radius_m"]}
            bool radiusIsWorldSpace = 1
            float smoke = 0.04
            float temperature = 2
            float3 velocity = (0, 0, 0.3)
            bool velocityIsWorldSpace = 1
        }}

        def FlowSimulate "Simulate"
        {{
            uint blockMinLifetime = 4
            float densityCellSize = 0.025
            bool enableVariableTimeStep = 0
            bool forceDisableCoreSimulation = 0
            bool forceDisableEmitters = 0
            bool forceSimulate = 1
            int layer = 0
            uint maxStepsPerSimulate = 1
            bool physicsCollisionEnabled = {enabled}
            bool physicsConvexCollision = 1
            bool simulateWhenPaused = 0
            float stepsPerSecond = 60
            uint velocitySubSteps = 1

            def FlowAdvectionCombustionParams "advection"
            {{
                float buoyancyPerTemp = 6
                float burnPerTemp = 4
                bool combustionEnabled = 1
                float coolingRate = 1.5
                bool enabled = 1
                float fuelPerBurn = 0.25
                float3 gravity = (0, 0, -9.81)
                float ignitionTemp = 0.05
                float smokePerBurn = 3
                float tempPerBurn = 5
                def FlowAdvectionChannelParams "temperature" {{ float secondOrderBlendFactor = 0.9 }}
                def FlowAdvectionChannelParams "fuel" {{ float secondOrderBlendFactor = 0.9 }}
                def FlowAdvectionChannelParams "burn" {{ float secondOrderBlendFactor = 0.9 }}
                def FlowAdvectionChannelParams "smoke" {{ float damping = 0.3; float fade = 2; float secondOrderBlendFactor = 0.9 }}
                def FlowAdvectionChannelParams "velocity" {{ float damping = 0.01; float fade = 1; float secondOrderBlendFactor = 0.9 }}
                def FlowAdvectionChannelParams "divergence" {{ float damping = 0.01; float fade = 1; float secondOrderBlendFactor = 0.9 }}
            }}
            def FlowVorticityParams "vorticity" {{ bool enabled = 1; float forceScale = 1.5; float velocityMask = 1 }}
            def FlowPressureParams "pressure" {{ bool enabled = 1 }}
            def FlowSummaryAllocateParams "summaryAllocate" {{ bool enableNeighborAllocation = 1; float smokeThreshold = 0.02; float speedThreshold = 1 }}
            def FlowSparseNanoVdbExportParams "nanoVdbExport"
            {{
                bool burnEnabled = 1
                bool enabled = 1
                bool fuelEnabled = 1
                bool readbackEnabled = 1
                bool smokeEnabled = 1
                bool statisticsEnabled = 1
                bool temperatureEnabled = 1
                bool velocityEnabled = 1
            }}
        }}

        def FlowOffscreen "Offscreen"
        {{
            int layer = 0
            def FlowRayMarchColormapParams "colormap"
            {{
                float colorScale = 2.5
                float[] colorScalePoints = [1, 1, 1, 1, 1, 1]
                uint resolution = 32
                float4[] rgbaPoints = [(0.0154, 0.0177, 0.0154, 0.004902), (0.03575, 0.03575, 0.03575, 0.504902), (0.03575, 0.03575, 0.03575, 0.504902), (1, 0.1594, 0.0134, 0.8), (13.53, 2.99, 0.12599, 0.8), (78, 39, 6.1, 0.7)]
                float[] xPoints = [0, 0.05, 0.15, 0.6, 0.85, 1]
            }}
            def FlowShadowParams "shadow" {{ float attenuation = 0.045; bool coarsePropagate = 1; bool enabled = 1; float3 lightDirection = (1, 1, 1) }}
        }}
        def FlowRender "Render"
        {{
            int layer = 0
            def FlowRayMarchParams "rayMarch" {{ float attenuation = 0.05; float colorScale = 1; float shadowFactor = 1; float stepSizeScale = 0.75 }}
        }}
    }}
}}
'''
    return text.encode("utf-8")


def write_stage(path: Path, contract: dict, condition: str) -> bytes:
    data = build_stage_bytes(contract, condition)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Phase 6HW refuses stage reuse: {path}")
    path.write_bytes(data)
    return data
