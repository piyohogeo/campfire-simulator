"""Default-off PointEmitter/closed-Mesh coexistence probe for Phase 6EP."""

from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import os
import sys
import time
import tracemalloc
import traceback
import weakref
from datetime import datetime, timezone
from pathlib import Path

import carb
import nanovdb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
import omni.volume
from omni.flowusd import _flowusd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import benchmark_point_emitter_core as point_core
from phase6ep_point_collision_geometry import plan_payload
from phase6er_point_collision_geometry import corrected_plan_payload
from phase6ee_velocity_distribution import SpatialNeighborhoodCollector
from phase6eu_process_memory import process_memory_snapshot
from phase6fc_startup_contract import classify_startup
from probe_phase6dt_flow_collision_reference import CHANNELS, SAMPLE_FRAMES, _capture, _save_and_sample


CAMERA_PATH = Sdf.Path("/World/Camera")
CAPTURE_RESOLUTION = (1280, 720)
P3_CHANNELS = ("velocity", "temperature", "smoke", "fuel")


def _phase6fp_allocation_state(level, output, plan, point_summary, public_members, collectors):
    """Build only the bounded pre-readback state frozen by Phase 6FP.

    The real Phase 6FO neighborhood arrays require public NanoVDB grid metadata
    and are therefore lazy readback allocations.  Level 4 records their dtype
    and ownership plan without inventing a grid or allocating a field body.
    """
    state = {
        "schema": "campfire.phase6fp.pre-readback-allocation-state.v1",
        "level": int(level),
        "owned_python_objects": [],
        "logical_buffer_bytes": 0,
        "weak_references": [],
        "steps": [],
    }
    if level >= 1:
        state["owned_python_objects"].extend(collectors)
        state["weak_references"].extend(
            reference for reference in (weakref.ref(value) for value in collectors) if reference is not None
        )
        state["steps"].append({
            "step": "collector_object",
            "collector_count": len(collectors),
            "collector_cache_entries": sum(len(value.cache) for value in collectors),
        })
    if level >= 2:
        state["spatial_region_metadata"] = _p3_world_rois()
        state["steps"].append({
            "step": "spatial_region_metadata",
            "region_count": len(state["spatial_region_metadata"]),
        })
    if level >= 3:
        state["channel_metadata"] = [
            {"name": name, "conversion": "deferred_until_public_readback", "field_body_allocated": False}
            for name in P3_CHANNELS
        ]
        state["steps"].append({"step": "channel_metadata", "channel_count": len(P3_CHANNELS)})
    if level >= 4:
        state["buffer_plan"] = {
            "field_body_allocated": False,
            "reason": "public NanoVDB origin, basis and shape do not exist before readback",
            "planned_arrays": [
                {"name": "indices", "dtype": "int32", "shape": [None, 3]},
                {"name": "world", "dtype": "float64", "shape": [None, 3]},
                {"name": "local", "dtype": "float64", "shape": [None, 3]},
                {"name": "signed_distance", "dtype": "float64", "shape": [None]},
                {"name": "channel_value", "dtype": "float32", "shape": [None]},
            ],
            "logical_bytes": 0,
        }
        state["steps"].append({"step": "near_mesh_control_volume_buffer_plan", "logical_bytes": 0})
    if level >= 5:
        state["capture_preparation"] = {
            "enabled": False,
            "frame_count": 0,
            "output_directory": str(output.parent / "captures"),
            "resolution": list(CAPTURE_RESOLUTION),
            "renderer_capture_calls": 0,
            "pixel_buffers_allocated": 0,
        }
        state["steps"].append({"step": "capture_video_preparation", "logical_bytes": 0})
    if level >= 6:
        state["s93_equivalence"] = {
            "scenario": "production_four",
            "geometry_variant": "phase6er_corrected",
            "policy": "allow_self_center",
            "active_point_count": int(plan["active"].sum()),
            "payload_sha256": point_summary["payload_sha256"],
            "note": "Phase 6FN baseline is already the S93 configuration; this step is a zero-delta identity control",
        }
        state["steps"].append({"step": "s93_stage_point_identity_control", "logical_bytes": 0})
    if level >= 7:
        state["phase6fo_pre_readback_equivalence"] = {
            "representative_spatial_collector_count": len(collectors),
            "readback_channels": list(P3_CHANNELS),
            "readback_calls": 0,
            "capture_enabled": False,
            "field_bodies_allocated": False,
            "flow_public_member_count": len(public_members),
        }
        state["steps"].append({"step": "phase6fo_pre_readback_equivalent", "logical_bytes": 0})
    state["owned_object_count"] = len(state["owned_python_objects"])
    state["weak_reference_count"] = len(state["weak_references"])
    state["live_weak_reference_count"] = sum(reference() is not None for reference in state["weak_references"])
    return state


def _p3_world_rois():
    """Fixed corrected-four regions used by the Phase 6FO comparison.

    These are public-field sampling regions.  They do not claim to expose a
    Flow occupancy mask or source ownership.
    """
    return {
        "scene": {"minimum": [-1.1, -1.1, 0.2], "maximum": [1.1, 1.1, 2.1]},
        "inter_log_gap": {"minimum": [-0.18, -0.18, 0.50], "maximum": [0.18, 0.18, 0.72]},
        "flame_rise": {"minimum": [-0.55, -0.55, 0.72], "maximum": [0.55, 0.55, 2.10]},
        "opposite_above": {"minimum": [-0.50, -0.50, 0.82], "maximum": [0.50, 0.50, 1.35]},
        "side_control": {"minimum": [-0.78, -0.78, 0.38], "maximum": [0.78, 0.78, 1.20]},
    }


def _settings():
    settings = carb.settings.get_settings()
    policy = settings.get_as_string("/phase6ep/policy") or "strict_all"
    report_phase = settings.get_as_string("/phase6ep/reportPhase") or "phase6ep"
    sample_text = settings.get_as_string("/phase6ep/sampleFrames")
    scalar_collider_text = settings.get_as_string("/phase6ep/spatialScalarColliderIndices")
    spatial_collider_text = settings.get_as_string("/phase6ep/spatialColliderIndices")
    readback_text = settings.get_as_string("/phase6ep/readbackChannels")
    readback_frame_text = settings.get_as_string("/phase6ep/readbackFrames")
    operation_frame_text = settings.get_as_string("/phase6ep/operationFrames")
    settling_end_text = settings.get_as_string("/phase6ep/settlingEndFrames")
    startup_pre_update_value = settings.get("/phase6ep/startupPreTimelineUpdateCount")
    startup_extra_update_value = settings.get("/phase6ep/startupExtraUpdateBeforePlayCount")
    sample_frames = tuple(int(value.strip()) for value in sample_text.split(",") if value.strip()) if sample_text else tuple(SAMPLE_FRAMES)
    return {
        "output": Path(settings.get_as_string("/phase6ep/output")).resolve(),
        "scenario": settings.get_as_string("/phase6ep/scenario"),
        "offset_m": float(settings.get_as_float("/phase6ep/offsetM")),
        "support_radius_m": float(settings.get_as_float("/phase6ep/supportRadiusM")),
        "filtering": bool(settings.get_as_bool("/phase6ep/filtering")),
        "collision": bool(settings.get_as_bool("/phase6ep/collision")),
        "policy": policy,
        "report_phase": report_phase,
        "sample_frames": sample_frames,
        "readback_channels": (
            tuple() if readback_text.strip().lower() == "none" else
            tuple(value.strip() for value in readback_text.split(",") if value.strip())
            if readback_text else tuple(CHANNELS)
        ),
        "readback_mode": settings.get_as_string("/phase6ep/readbackMode") or "legacy",
        "readback_frames": (
            tuple(int(value.strip()) for value in readback_frame_text.split(",") if value.strip())
            if readback_frame_text else sample_frames
        ),
        "operation_frames": (
            tuple(int(value.strip()) for value in operation_frame_text.split(",") if value.strip())
            if operation_frame_text else sample_frames
        ),
        "settling_end_frames": (
            tuple(int(value.strip()) for value in settling_end_text.split(",") if value.strip())
            if settling_end_text else tuple()
        ),
        "reference_disposal": settings.get_as_string("/phase6ep/referenceDisposal") or "natural",
        "synchronous_memory_markers": bool(settings.get_as_bool("/phase6ep/synchronousMemoryMarkers")),
        "python_memory_telemetry": bool(settings.get_as_bool("/phase6ep/pythonMemoryTelemetry")),
        "bounded_jsonl_path": (
            Path(settings.get_as_string("/phase6ep/boundedJsonlPath")).resolve()
            if settings.get_as_string("/phase6ep/boundedJsonlPath") else None
        ),
        "spatial_collectors_enabled": bool(settings.get_as_bool("/phase6ep/spatialCollectorsEnabled")),
        "spatial_collider_indices": (
            tuple(int(value.strip()) for value in spatial_collider_text.split(",") if value.strip())
            if spatial_collider_text else None
        ),
        "spatial_all_channels": bool(settings.get_as_bool("/phase6ep/spatialAllChannels")),
        "spatial_scalar_collider_indices": (
            tuple(int(value.strip()) for value in scalar_collider_text.split(",") if value.strip())
            if scalar_collider_text else None
        ),
        "run_index": int(settings.get_as_int("/phase6ep/runIndex")) or 1,
        "allocation_calibration_level": int(settings.get_as_int("/phase6ep/allocationCalibrationLevel")),
        "capture": bool(settings.get_as_bool("/phase6ep/capture")),
        "capture_start": int(settings.get_as_int("/phase6ep/captureStart")),
        "capture_end": int(settings.get_as_int("/phase6ep/captureEnd")),
        "geometry_variant": settings.get_as_string("/phase6ep/geometryVariant") or "legacy_phase6ep",
        "fuel_scale": float(settings.get_as_float("/phase6ep/fuelScale")),
        "temperature_scale": float(settings.get_as_float("/phase6ep/temperatureScale")),
        "smoke_scale": float(settings.get_as_float("/phase6ep/smokeScale")),
        "resource_marker_path": (
            Path(settings.get_as_string("/phase6ep/resourceMarkerPath")).resolve()
            if settings.get_as_string("/phase6ep/resourceMarkerPath") else None
        ),
        "lifecycle_calibration": bool(settings.get_as_bool("/phase6ep/lifecycleCalibration")),
        "renderer_drain_updates": max(0, int(settings.get_as_int("/phase6ep/rendererDrainUpdates"))),
        "lifecycle_reference_release_order": (
            settings.get_as_string("/phase6ep/lifecycleReferenceReleaseOrder") or "before_stage_close"
        ),
        "capture_preparation_mode": settings.get_as_string("/phase6ep/capturePreparationMode") or "none",
        "stage_close_timeout_seconds": max(0.0, float(settings.get_as_float("/phase6ep/stageCloseTimeoutSeconds"))),
        "stability_observation_start_frame": max(
            0, int(settings.get_as_int("/phase6ep/stabilityObservationStartFrame"))
        ),
        "stability_observation_extra_seconds": max(
            0.0, float(settings.get_as_float("/phase6ep/stabilityObservationExtraSeconds"))
        ),
        "stability_active_block_sample_seconds": max(
            0.05, float(settings.get_as_float("/phase6ep/stabilityActiveBlockSampleSeconds")) or 0.5
        ),
        "flow_liveness_audit": bool(settings.get_as_bool("/phase6ep/flowLivenessAudit")),
        "fuel_liveness_decode": bool(settings.get_as_bool("/phase6ep/fuelLivenessDecode")),
        "startup_probe": bool(settings.get_as_bool("/phase6ep/startupProbe")),
        "startup_probe_label": settings.get_as_string("/phase6ep/startupProbeLabel") or "",
        "startup_flow_acquire_position": (
            settings.get_as_string("/phase6ep/startupFlowAcquirePosition") or "before_updates"
        ),
        "startup_pre_timeline_update_count": max(
            0, int(startup_pre_update_value) if startup_pre_update_value is not None else 12
        ),
        "startup_extra_update_before_play_count": max(
            0, int(startup_extra_update_value) if startup_extra_update_value is not None else 0
        ),
        "startup_liveness_gate": bool(settings.get_as_bool("/phase6ep/startupLivenessGate")),
        "startup_expected_fuel_sum": float(settings.get_as_float("/phase6ep/startupExpectedFuelSum")),
        "startup_expected_temperature_sum": float(settings.get_as_float("/phase6ep/startupExpectedTemperatureSum")),
        "startup_expected_smoke_sum": float(settings.get_as_float("/phase6ep/startupExpectedSmokeSum")),
        "startup_source_sum_tolerance": max(
            0.0, float(settings.get_as_float("/phase6ep/startupSourceSumTolerance")) or 1.0e-6
        ),
    }


def _startup_identity_and_source_gate(history, source, arguments):
    """Return the bounded pre-readback identity/source evidence for Phase 6FD."""
    if not history:
        return {"pass": False, "failures": ["history_missing"]}
    first = history[0]
    identity_keys = (
        "stage_identity", "flow_identity", "stage_sha256", "payload_sha256",
        "stage_python_identity", "emitter_path", "emitter_python_identity",
        "points_prim_python_identity", "viewport_identity",
    )
    failures = []
    for key in identity_keys:
        if any(row.get(key) != first.get(key) for row in history):
            failures.append(f"{key}_changed")
    if not all(bool(row.get("renderer_ready")) and bool(row.get("flow_interface_ready")) for row in history):
        failures.append("readiness")
    if not all(bool(row.get("emitter_enabled")) for row in history):
        failures.append("emitter_disabled")
    if int(source.get("revision", -1)) != 1:
        failures.append("point_revision")
    if int(source.get("total_point_count", 0)) != 1440:
        failures.append("total_point_count")
    if int(source.get("active_point_count", 0)) != 1344:
        failures.append("active_point_count")
    sums = source.get("source_sums") or {}
    tolerance = float(arguments["startup_source_sum_tolerance"])
    for key, expected_key in (
        ("fuel", "startup_expected_fuel_sum"),
        ("temperature", "startup_expected_temperature_sum"),
        ("smoke", "startup_expected_smoke_sum"),
    ):
        expected = float(arguments[expected_key])
        actual = float(sums.get(key, float("nan")))
        if not np.isfinite(actual) or abs(actual - expected) > tolerance:
            failures.append(f"{key}_sum")
    return {"pass": not failures, "failures": failures, "identity_reference": {key: first.get(key) for key in identity_keys}}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _python_memory_snapshot():
    if not tracemalloc.is_tracing():
        return {"available": False}
    current, peak = tracemalloc.get_traced_memory()
    return {"available": True, "current_bytes": int(current), "peak_bytes": int(peak)}


def _append_resource_marker(path, marker, synchronous_memory=False, **values):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "campfire.phase6et.resource-marker.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "perf_counter_ns": time.perf_counter_ns(),
        "pid": os.getpid(),
        "marker": marker,
        **values,
    }
    if synchronous_memory:
        payload["process_memory"] = process_memory_snapshot()
        payload["python_memory"] = _python_memory_snapshot()
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _lifecycle_state(timeline, context, flow, volume, emitter, collectors):
    """Return bounded public state for durable Phase 6EV lifecycle markers."""
    stage = None
    stage_identity = None
    try:
        stage = context.get_stage() if context is not None else None
        if stage is not None:
            root = stage.GetRootLayer()
            stage_identity = str(root.identifier) if root is not None else f"stage:{id(stage)}"
    except Exception as error:
        stage_identity = f"unavailable:{type(error).__name__}"
    try:
        timeline_playing = bool(timeline.is_playing()) if timeline is not None else None
        timeline_time = float(timeline.get_current_time()) if timeline is not None else None
    except Exception:
        timeline_playing = None
        timeline_time = None
    return {
        "timeline_playing": timeline_playing,
        "timeline_time": timeline_time,
        "stage_present": stage is not None,
        "stage_identity": stage_identity,
        "flow_reference_present": flow is not None,
        "volume_reference_present": volume is not None,
        "emitter_reference_present": emitter is not None,
        "collector_reference_count": len(collectors) if collectors is not None else 0,
    }


def _type_name(value):
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _bounded_object_metadata(value):
    metadata = {"type": _type_name(value), "identity": int(id(value))}
    for name in ("dtype", "shape", "strides", "size", "nbytes"):
        try:
            item = getattr(value, name)
            if name in ("shape", "strides"):
                item = [int(component) for component in item]
            elif name in ("size", "nbytes"):
                item = int(item)
            else:
                item = str(item)
            metadata[name] = item
        except Exception:
            metadata[name] = None
    try:
        metadata["c_contiguous"] = bool(value.flags.c_contiguous)
        metadata["f_contiguous"] = bool(value.flags.f_contiguous)
    except Exception:
        metadata["c_contiguous"] = None
        metadata["f_contiguous"] = None
    # NumPy's public array interface exposes the address of the first byte of
    # the logical data buffer.  Keep this separate from Python object identity:
    # equal identities imply the same live wrapper, while equal data pointers
    # establish that two wrappers address the same buffer.  Non-array channel
    # wrappers may not expose this interface, so absence remains explicit.
    try:
        data = value.__array_interface__.get("data")
        metadata["data_pointer"] = int(data[0]) if data and type(data[0]) is int and data[0] > 0 else None
    except Exception:
        metadata["data_pointer"] = None
    return metadata


def _nanovdb_component(value, axis):
    """Read a NanoVDB vector component without relying on another probe's private helper."""
    try:
        return float(value[axis])
    except TypeError:
        return float((value.x, value.y, value.z)[axis])


def _fuel_liveness_decode(flow, volume, source, positions, path):
    """Decode one public fuel buffer and sample bounded emitter positions.

    The temporary NanoVDB file is deleted before return.  This is diagnostic
    evidence that the public field contains meaningful scalar values, not an
    assertion about a private Flow occupancy mask.
    """
    path.unlink(missing_ok=True)
    try:
        grid_data = flow.buffer_to_volume(source)
        parameters = omni.volume.SaveVolumeParameters()
        parameters.flags = omni.volume.kNanoVDBCodecNone
        if not volume.save_volume(grid_data, str(path), parameters):
            raise RuntimeError(f"Unable to save fuel liveness decode: {path}")
        deadline = time.monotonic() + 5.0
        while (not path.is_file() or path.stat().st_size == 0) and time.monotonic() < deadline:
            time.sleep(0.01)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("fuel liveness NanoVDB did not become durable")
        handle = nanovdb.io.readGrid(str(path))
        grid = handle.floatGrid()
        accessor = grid.getAccessor()
        values = []
        for position in positions:
            index = grid.applyInverseMap(nanovdb.math.Vec3d(*(float(value) for value in position)))
            coordinate = tuple(int(round(_nanovdb_component(index, axis))) for axis in range(3))
            values.append(float(accessor.getValue(*coordinate)))
        voxel = grid.voxelSize()
        nonzero = sum(abs(value) > 1.0e-6 for value in values)
        return {
            "public_decode": "flow.buffer_to_volume + omni.volume.save_volume + bundled nanovdb accessor",
            "private_api_used": False,
            "flow_occupancy_mask_claimed": False,
            "active_voxel_count": int(grid.activeVoxelCount()),
            "voxel_size": [_nanovdb_component(voxel, axis) for axis in range(3)],
            "emitter_position_sample_count": len(values),
            "emitter_position_nonzero_count_1e_6": int(nonzero),
            "emitter_position_minimum": min(values) if values else None,
            "emitter_position_mean": float(np.mean(values, dtype=np.float64)) if values else None,
            "emitter_position_maximum": max(values) if values else None,
            "temporary_file_bytes": int(path.stat().st_size),
        }
    finally:
        path.unlink(missing_ok=True)


def _append_bounded_jsonl(path, payload):
    if path is None:
        raise RuntimeError("bounded JSONL output is required for fuel_jsonl mode")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 16 * 1024:
        raise RuntimeError("bounded JSONL record exceeded 16 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded + "\n")
        stream.flush()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _define_collision_meshes(stage, plan):
    records = []
    for index, (pose, points, counts, indices, _geometry) in enumerate(plan["geometries"]):
        path = Sdf.Path(f"/World/CollisionProxies/{pose.name}")
        mesh = UsdGeom.Mesh.Define(stage, path)
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*value) for value in points]))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray(counts.tolist()))
        mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(indices.tolist()))
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(False)
        mesh.CreateDisplayColorAttr([Gf.Vec3f(0.22, 0.07 + 0.035 * index, 0.025)])
        collision_api = UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
        collision_api.CreateCollisionEnabledAttr(True)
        mesh_api = UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim())
        mesh_api.CreateApproximationAttr().Set(UsdPhysics.Tokens.convexDecomposition)
        records.append({
            "path": str(path), "name": pose.name, "vertex_count": len(points),
            "face_count": len(counts), "index_count": len(indices),
            "center": list(pose.center), "yaw_degrees": pose.yaw_degrees,
            "emits": pose.emits,
        })
    return records


def _stage_path(output):
    return output.with_suffix(".scene.usda")


def _build_stage(arguments):
    output = arguments["output"]
    path = _stage_path(output)
    path.unlink(missing_ok=True)
    planning_started = time.perf_counter_ns()
    planner = corrected_plan_payload if arguments["geometry_variant"] == "phase6er_corrected" else plan_payload
    plan = planner(
        arguments["scenario"], arguments["offset_m"],
        arguments["support_radius_m"], arguments["filtering"], arguments["policy"],
    )
    planning_ms = (time.perf_counter_ns() - planning_started) / 1_000_000.0
    stage = Usd.Stage.CreateNew(str(path))
    point_core._define_minimal_world(stage)
    point_core._define_flow_solver(stage)
    simulate = stage.GetPrimAtPath(point_core.SIMULATE_PATH)
    point_core._set(simulate, "physicsCollisionEnabled", arguments["collision"])
    point_core._set(simulate, "physicsConvexCollision", True)
    collision_records = _define_collision_meshes(stage, plan)
    publication_started = time.perf_counter_ns()
    handles = point_core._define_point_sources(
        stage, (tuple(Gf.Vec3f(*(float(component) for component in value)) for value in plan["positions"]),)
    )
    emitter = stage.GetPrimAtPath(handles[0]["path"])
    active = plan["active"].astype(np.float32)
    point_core._set(emitter, "pointFuels", Vt.FloatArray((active * 0.8 * arguments["fuel_scale"]).tolist()))
    point_core._set(emitter, "pointTemperatures", Vt.FloatArray((active * 2.0 * arguments["temperature_scale"]).tolist()))
    point_core._set(emitter, "pointSmokes", Vt.FloatArray((active * 0.08 * arguments["smoke_scale"]).tolist()))
    publication_ms = (time.perf_counter_ns() - publication_started) / 1_000_000.0
    revision = emitter.GetAttribute("campfire:residentRevision")
    revision.Set(1)
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(600.0)
    stage.SetTimeCodesPerSecond(60.0)
    stage.GetRootLayer().customLayerData = {
        "campfire:phase": arguments["report_phase"], "campfire:defaultOff": True,
        "campfire:productionConnected": False,
    }
    if not stage.GetRootLayer().Save():
        raise RuntimeError("failed to save Phase 6EP offline stage")
    payload_path = output.parent / "point_payload.npz"
    records = plan["records"]
    np.savez_compressed(
        payload_path,
        positions=plan["positions"], active=plan["active"],
        owner_index=np.asarray([item["owner_index"] for item in records], dtype=np.int16),
        signed_distance_m=np.asarray([item["signed_distance_m"] for item in records], dtype=np.float32),
        support_clearance_m=np.asarray([item["support_clearance_m"] for item in records], dtype=np.float32),
        nearest_collider_index=np.asarray([item["nearest_collider_index"] for item in records], dtype=np.int16),
        nearest_face_class=np.asarray([item["nearest_face_class"] for item in records], dtype=np.uint8),
        surface_identity=np.asarray([item["surface_identity"] for item in records], dtype=np.int16),
        self_signed_distance_m=np.asarray([item["self_signed_distance_m"] for item in records], dtype=np.float32),
        other_min_signed_distance_m=np.asarray([item["other_min_signed_distance_m"] for item in records], dtype=np.float32),
        self_center_inside=np.asarray([item["self_center_inside"] for item in records], dtype=bool),
        other_center_inside=np.asarray([item["other_center_inside"] for item in records], dtype=bool),
        self_support_intersects=np.asarray([item["self_support_intersects"] for item in records], dtype=bool),
        other_support_intersects=np.asarray([item["other_support_intersects"] for item in records], dtype=bool),
        enabled_reason=np.asarray([item["enabled_reason"] for item in records], dtype="U32"),
        original_supply=np.asarray([[item["original_fuel"], item["original_temperature"], item["original_smoke"]] for item in records], dtype=np.float32),
        enabled_supply=np.asarray([[item["enabled_fuel"], item["enabled_temperature"], item["enabled_smoke"]] for item in records], dtype=np.float32),
    )
    summary = {key: plan[key] for key in (
        "scenario", "policy", "poses", "original_point_count", "active_point_count",
        "disabled_point_count", "supply_efficiency", "minimum_support_clearance_m",
        "minimum_active_support_clearance_m", "support_intersection_count",
        "active_support_intersection_count", "self_inside_count", "other_inside_count",
        "self_center_inside_count", "other_center_inside_count",
        "self_support_intersection_count", "other_support_intersection_count",
        "active_other_support_intersection_count", "disable_reason_counts", "weighted_supply",
    )}
    summary.update({
        "planning_ms": planning_ms, "usd_publication_ms": publication_ms,
        "payload_path": str(payload_path), "payload_sha256": _sha256(payload_path),
        "payload_bytes": payload_path.stat().st_size,
        "colliders": collision_records,
    })
    return path, summary, plan


def _stats_attributes(prim):
    values = []
    for attribute in prim.GetAttributes():
        name = attribute.GetName()
        lowered = name.lower()
        if any(token in lowered for token in ("radius", "support", "smooth", "alloc", "level", "substep")):
            try:
                value = attribute.Get()
                if hasattr(value, "__len__") and not isinstance(value, str):
                    value = str(value) if len(value) < 16 else f"array[{len(value)}]"
                values.append({"name": name, "type": str(attribute.GetTypeName()), "value": value})
            except Exception as error:
                values.append({"name": name, "error": f"{type(error).__name__}: {error}"})
    return values


def _array_contract(value, dtype):
    array = np.asarray(value, dtype=dtype)
    contiguous = np.ascontiguousarray(array)
    return {
        "python_identity": int(id(value)),
        "shape": [int(component) for component in contiguous.shape],
        "dtype": str(contiguous.dtype),
        "logical_bytes": int(contiguous.nbytes),
        "sha256": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest().upper(),
    }


def _live_point_emitter_contract(stage, emitter):
    relationship = emitter.GetRelationship("pointsPrim")
    targets = [str(path) for path in relationship.GetTargets()]
    if len(targets) != 1:
        raise RuntimeError(f"startup probe expected one pointsPrim target, got {targets}")
    points_prim = stage.GetPrimAtPath(targets[0])
    points = UsdGeom.Points(points_prim).GetPointsAttr().Get()
    fuels = emitter.GetAttribute("pointFuels").Get()
    temperatures = emitter.GetAttribute("pointTemperatures").Get()
    smokes = emitter.GetAttribute("pointSmokes").Get()
    enabled_attribute = emitter.GetAttribute("enabled")
    enabled = enabled_attribute.Get() if enabled_attribute else None
    revision = emitter.GetAttribute("campfire:residentRevision").Get()
    fuel_values = np.asarray(fuels, dtype=np.float32)
    temperature_values = np.asarray(temperatures, dtype=np.float32)
    smoke_values = np.asarray(smokes, dtype=np.float32)
    return {
        "stage_python_identity": int(id(stage)),
        "emitter_path": str(emitter.GetPath()),
        "emitter_type": emitter.GetTypeName(),
        "emitter_python_identity": int(id(emitter)),
        "points_prim_path": targets[0],
        "points_prim_type": points_prim.GetTypeName(),
        "points_prim_python_identity": int(id(points_prim)),
        "relationship_targets": targets,
        "enabled": bool(enabled),
        "revision": int(revision),
        "total_point_count": int(len(fuels)),
        "active_point_count": int(np.count_nonzero(fuel_values > 0.0)),
        "source_sums": {
            "fuel": float(np.sum(fuel_values, dtype=np.float64)),
            "temperature": float(np.sum(temperature_values, dtype=np.float64)),
            "smoke": float(np.sum(smoke_values, dtype=np.float64)),
        },
        "arrays": {
            "points": _array_contract(points, np.float32),
            "fuel": _array_contract(fuels, np.float32),
            "temperature": _array_contract(temperatures, np.float32),
            "smoke": _array_contract(smokes, np.float32),
        },
        "identity_scope_note": "Python identities describe the live wrappers returned in this process, not a provider-owned native allocation.",
    }


def _readback_boundary(flow, volume, arguments, frame, output, liveness_positions=None, operation_state=None):
    """Exercise exactly one declared public-readback boundary and return only bounded metadata."""
    marker_path = arguments["resource_marker_path"]
    synchronous = arguments["synchronous_memory_markers"]
    mode = arguments["readback_mode"]
    operation_state = operation_state or {}
    mark = lambda name, **values: _append_resource_marker(
        marker_path, name, synchronous_memory=synchronous, frame=frame,
        active_blocks=int(flow.get_active_block_count()), **operation_state, **values
    )
    mark("readback_call_before", mode=mode)
    raw = flow.get_latest_nanovdb_readback()
    mark("readback_call_after", mode=mode, returned_channel_count=len(raw))
    result = {
        "mode": mode,
        "returned_type": _type_name(raw),
        "returned_channel_count": len(raw),
        "returned_identity": int(id(raw)),
        "channel_objects": [_bounded_object_metadata(value) for value in raw],
        "public_release_method_used": False,
        "public_release_method_available": False,
        "explicit_release_note": "No public release method is exposed by the returned Python objects; no private or inferred release is called.",
    }
    mark("tuple_elements_checked", channel_object_count=len(result["channel_objects"]))
    weak_references = []
    value = None
    for value in raw:
        try:
            weak_references.append(weakref.ref(value))
        except TypeError:
            weak_references.append(None)
    # Do not let the loop variable retain the final channel past an exact
    # lifetime marker.  Historical modes retain their original semantics.
    del value

    if arguments["fuel_liveness_decode"]:
        if liveness_positions is None or len(liveness_positions) == 0:
            raise RuntimeError("fuel liveness decode requires active emitter positions")
        fuel_index = CHANNELS.index("fuel")
        liveness_source = raw[fuel_index]
        mark("fuel_liveness_decode_before", source_identity=int(id(liveness_source)))
        result["fuel_liveness"] = _fuel_liveness_decode(
            flow, volume, liveness_source, liveness_positions,
            output.parent / f"fuel_liveness_{frame}.nvdb",
        )
        mark("fuel_liveness_decode_after", **result["fuel_liveness"])
        del liveness_source

    exact_release_mode = mode in ("acquire_discard_release", "fuel_convert_release")
    if exact_release_mode:
        result["operation_counts"] = {
            "public_readback_calls": 1,
            "fuel_handle_selections": 0,
            "numpy_asarray_calls": 0,
            "explicit_copy_function_calls": 0,
            "field_persistence_calls": 0,
            "temporary_fuel_liveness_decode_calls": int(arguments["fuel_liveness_decode"]),
        }
        if mode == "acquire_discard_release":
            del raw
            mark(
                "original_tuple_and_all_handle_aliases_released",
                retained_converted_object=False,
            )
            result["reference_disposal"] = "explicit_del_no_gc"
            result["gc_collected"] = None
            return result, weak_references

        fuel_index = CHANNELS.index("fuel")
        source = raw[fuel_index]
        source_metadata = _bounded_object_metadata(source)
        result["operation_counts"]["fuel_handle_selections"] = 1
        result["fuel_source"] = source_metadata
        mark(
            "fuel_handle_selected", fuel_channel_index=fuel_index,
            source_type=_type_name(source), source_identity=int(id(source)),
            source_data_pointer=source_metadata["data_pointer"],
        )
        mark(
            "fuel_conversion_before", source_type=_type_name(source), source_identity=int(id(source)),
            source_data_pointer=source_metadata["data_pointer"],
        )
        array = np.asarray(source)
        result["operation_counts"]["numpy_asarray_calls"] = 1
        base = getattr(array, "base", None)
        fuel_array = {
            **_bounded_object_metadata(array),
            "owns_data": bool(array.flags.owndata),
            "base_type": _type_name(base) if base is not None else None,
            "base_identity": int(id(base)) if base is not None else None,
            "same_identity_as_source": bool(array is source),
        }
        try:
            fuel_array["shares_memory_with_source"] = bool(np.shares_memory(array, source))
        except Exception:
            fuel_array["shares_memory_with_source"] = None
        result["fuel_array"] = fuel_array
        result["observable_copy_contract"] = {
            "explicit_copy_function_calls": 0,
            "same_identity": fuel_array["same_identity_as_source"],
            "shares_memory": fuel_array["shares_memory_with_source"],
            "source_data_pointer": source_metadata["data_pointer"],
            "converted_data_pointer": fuel_array["data_pointer"],
            "same_data_pointer": bool(
                source_metadata["data_pointer"] is not None
                and fuel_array["data_pointer"] is not None
                and source_metadata["data_pointer"] == fuel_array["data_pointer"]
            ),
            "exact_internal_copy_count_known": bool(fuel_array["same_identity_as_source"]),
            "internal_public_readback_copy_count_known": False,
        }
        if fuel_array["same_identity_as_source"]:
            allocation_classification = "same_object_zero_copy_alias"
            new_data_buffer_allocated = False
        elif fuel_array["shares_memory_with_source"] is True:
            allocation_classification = "distinct_python_object_shared_memory_alias"
            new_data_buffer_allocated = False
        elif fuel_array["shares_memory_with_source"] is False:
            allocation_classification = "independent_data_buffer_observed"
            new_data_buffer_allocated = True
        else:
            allocation_classification = "unconfirmed"
            new_data_buffer_allocated = None
        result["observable_copy_contract"].update({
            "allocation_classification": allocation_classification,
            "new_data_buffer_allocated": new_data_buffer_allocated,
        })
        mark(
            "fuel_conversion_after", dtype=str(array.dtype), shape=[int(value) for value in array.shape],
            strides=[int(value) for value in array.strides], element_count=int(array.size),
            buffer_bytes=int(array.nbytes), c_contiguous=bool(array.flags.c_contiguous),
            f_contiguous=bool(array.flags.f_contiguous),
            owns_data=bool(array.flags.owndata), same_identity_as_source=bool(array is source),
            shares_memory_with_source=fuel_array["shares_memory_with_source"],
            source_data_pointer=source_metadata["data_pointer"],
            converted_data_pointer=fuel_array["data_pointer"],
            same_data_pointer=result["observable_copy_contract"]["same_data_pointer"],
            allocation_classification=allocation_classification,
        )
        del base
        converted_identity = int(id(array))
        converted_is_original = bool(array is source)
        del raw
        del source
        converted_after_source_release = _bounded_object_metadata(array)
        result["converted_after_source_alias_release"] = {
            "valid": True,
            **converted_after_source_release,
        }
        mark(
            "original_tuple_and_all_handle_aliases_released",
            retained_converted_object=True,
            retained_converted_identity=converted_identity,
            retained_converted_is_original_fuel_object=converted_is_original,
            retained_converted_data_pointer=converted_after_source_release["data_pointer"],
            converted_object_valid=True,
        )
        mark(
            "converted_buffer_only_held", converted_identity=converted_identity,
            converted_is_original_fuel_object=converted_is_original,
            converted_data_pointer=converted_after_source_release["data_pointer"],
            buffer_bytes=int(array.nbytes), element_count=int(array.size),
        )
        converted_weak_reference = weakref.ref(array)
        del array
        converted_alive_after_release = converted_weak_reference() is not None
        result["converted_weak_reference_alive_immediately_after_release"] = converted_alive_after_release
        mark(
            "converted_buffer_released",
            released_identity=converted_identity,
            converted_was_original_fuel_object=converted_is_original,
            converted_weak_reference_alive=converted_alive_after_release,
        )
        result["reference_disposal"] = "ordered_explicit_del_no_gc"
        result["gc_collected"] = None
        return result, weak_references

    array = None
    source = None
    if mode != "acquire_discard":
        fuel_index = CHANNELS.index("fuel")
        source = raw[fuel_index]
        mark("fuel_conversion_before", source_type=_type_name(source))
        array = np.asarray(source)
        base = getattr(array, "base", None)
        result["fuel_array"] = {
            **_bounded_object_metadata(array),
            "owns_data": bool(array.flags.owndata),
            "base_type": _type_name(base) if base is not None else None,
            "base_identity": int(id(base)) if base is not None else None,
            "same_identity_as_source": bool(array is source),
        }
        try:
            result["fuel_array"]["shares_memory_with_source"] = bool(np.shares_memory(array, source))
        except Exception:
            result["fuel_array"]["shares_memory_with_source"] = None
        mark(
            "fuel_conversion_after", dtype=str(array.dtype), shape=[int(value) for value in array.shape],
            strides=[int(value) for value in array.strides], buffer_bytes=int(array.nbytes),
            owns_data=bool(array.flags.owndata),
        )

    if mode in ("fuel_scalar", "fuel_jsonl"):
        mark("numpy_aggregate_before")
        if array.size:
            aggregate = {
                "sum": float(np.sum(array, dtype=np.float64)),
                "mean": float(np.mean(array, dtype=np.float64)),
                "minimum": float(np.min(array)),
                "maximum": float(np.max(array)),
            }
        else:
            aggregate = {"sum": 0.0, "mean": None, "minimum": None, "maximum": None}
        result["fuel_aggregate"] = aggregate
        mark("numpy_aggregate_after")

    if mode == "fuel_spatial":
        mark("spatial_sampling_before")
        temporary_path = output.parent / f"phase6eu_{frame}_fuel.nvdb"
        result["spatial_sample"] = _save_and_sample(
            flow,
            volume,
            array,
            "fuel",
            temporary_path,
            {"representative_collider": {"minimum": [-0.42, -0.20, 0.70], "maximum": [0.42, 0.20, 1.12]}},
        )
        mark("spatial_sampling_after", temporary_file_present=temporary_path.exists())

    disposal = arguments["reference_disposal"]
    if disposal not in ("natural", "del", "gc"):
        raise ValueError(f"unsupported reference disposal mode: {disposal}")
    if disposal in ("del", "gc"):
        if array is not None:
            del array
        if source is not None:
            del source
        del raw
    collected = None
    if disposal == "gc":
        collected = int(gc.collect())
    result["reference_disposal"] = disposal
    result["gc_collected"] = collected
    return result, weak_references


def _p3_spatial_boundary(flow, volume, arguments, frame, output, collectors, operation_state=None):
    """Read and summarize the four Phase 6FO channels with bounded lifetimes.

    The public call returns all channel buffers together.  Each required
    channel is consumed directly, its near-Collider NPZ is finalized, and its
    list slot and local alias are released before the next channel.  No
    ``np.asarray`` call, full-field JSON expansion, private release method, or
    forced garbage collection is used here.
    """
    marker_path = arguments["resource_marker_path"]
    synchronous = arguments["synchronous_memory_markers"]
    operation_state = operation_state or {}
    mark = lambda name, **values: _append_resource_marker(
        marker_path, name, synchronous_memory=synchronous, frame=frame,
        active_blocks=int(flow.get_active_block_count()), **operation_state, **values
    )
    mark("p3_readback_call_before")
    returned = flow.get_latest_nanovdb_readback()
    mark("p3_readback_call_after", returned_channel_count=len(returned))
    handles = returned if isinstance(returned, list) else list(returned)
    if handles is not returned:
        del returned
    if len(handles) != len(CHANNELS):
        raise RuntimeError(f"Phase 6FO expected {len(CHANNELS)} public channels, got {len(handles)}")
    weak_references = []
    for value in handles:
        try:
            weak_references.append(weakref.ref(value))
        except TypeError:
            weak_references.append(None)
    del value
    result = {
        "mode": "p3_spatial_release",
        "returned_type": _type_name(handles),
        "returned_channel_count": len(handles),
        "public_channel_order": list(CHANNELS),
        "requested_channels": list(arguments["readback_channels"]),
        "operation_counts": {
            "public_readback_calls": 1,
            "numpy_asarray_calls": 0,
            "explicit_copy_function_calls": 0,
            "temporary_nanovdb_files": len(arguments["readback_channels"]),
            "near_mesh_npz_writes": len(arguments["readback_channels"]) * len(collectors),
        },
        "channels": {},
        "forced_gc": False,
        "flow_occupancy_mask_claimed": False,
        "public_release_method_used": False,
    }
    thresholds = {"velocity": 0.01, "temperature": 1.01, "smoke": 0.001, "fuel": 0.001}
    rois = _p3_world_rois()
    for channel in arguments["readback_channels"]:
        if channel not in P3_CHANNELS:
            raise RuntimeError(f"Phase 6FO unsupported P3 channel: {channel}")
        channel_index = CHANNELS.index(channel)
        source = handles[channel_index]
        metadata = _bounded_object_metadata(source)
        metadata["channel_index"] = channel_index
        metadata["is_numpy_ndarray"] = isinstance(source, np.ndarray)
        if not metadata["is_numpy_ndarray"]:
            raise RuntimeError(f"Phase 6FO {channel} is not a direct NumPy array")
        if metadata.get("data_pointer") is None:
            raise RuntimeError(f"Phase 6FO {channel} lacks a positive public data pointer")
        before = process_memory_snapshot()
        mark(
            "p3_channel_collection_before", channel=channel, channel_index=channel_index,
            source_identity=int(id(source)), source_data_pointer=metadata["data_pointer"],
            source_nbytes=metadata.get("nbytes"),
        )
        temporary_path = output.parent / f"p3_f{int(frame):04d}_{channel}.nvdb"
        details = _save_and_sample(
            flow, volume, source, channel, temporary_path, rois,
            spatial_collector=collectors, spatial_velocity_only=False,
            frame=frame, profile_threshold=thresholds[channel],
        )
        after = process_memory_snapshot()
        before_private = before.get("private_bytes") if before.get("available") else None
        after_private = after.get("private_bytes") if after.get("available") else None
        result["channels"][channel] = {
            "source": metadata,
            "read_only_direct_array": True,
            "numpy_asarray_called": False,
            "material_copy_requested": False,
            "memory_before": before,
            "memory_after": after,
            "private_bytes_delta": (
                None if before_private is None or after_private is None
                else int(after_private - before_private)
            ),
            "temporary_nanovdb_present_after_collection": temporary_path.exists(),
            "field": details,
        }
        handles[channel_index] = None
        released_identity = int(id(source))
        del source, details
        mark(
            "p3_channel_collection_after", channel=channel,
            released_identity=released_identity,
            temporary_nanovdb_present=temporary_path.exists(),
            private_bytes_delta=result["channels"][channel]["private_bytes_delta"],
        )
    for index in range(len(handles)):
        handles[index] = None
    del handles
    alive = sum(reference is not None and reference() is not None for reference in weak_references)
    result["weak_reference_supported_count"] = sum(reference is not None for reference in weak_references)
    result["weak_reference_alive_after_scope_count"] = int(alive)
    result["reference_disposal"] = "ordered_list_slot_clear_then_del_no_gc"
    mark("p3_all_channel_aliases_released", weak_reference_alive_count=int(alive))
    return result, weak_references


async def _run():
    arguments = _settings()
    output = arguments["output"]
    mark = lambda name, **values: _append_resource_marker(
        arguments["resource_marker_path"], name,
        synchronous_memory=arguments["synchronous_memory_markers"], **values
    )
    report = {
        "schema": f"campfire.{arguments['report_phase']}.point-collision-run.v1", "phase": arguments["report_phase"],
        "status": "running", "lifecycle_marker": "process_entry",
        "lifecycle_history": [], "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in arguments.items()},
        "samples": [], "captures": [],
        "flow_liveness_history": [],
        "completion_contract": {
            "results_saved": False, "timeline_stopped": False,
            "stage_closed": False, "renderer_drained": False,
            "shutdown_requested": False,
        },
    }
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    flow = None
    volume = None
    collectors = []
    collectors_by_index = {}
    allocation_state = None
    capture_provider_alias = None
    capture_manifest_path = None
    emitter = None
    stage = None
    viewport = None
    lifecycle_ownership = {}
    lifecycle_weak_references = {}
    exit_code = 1

    def ownership_snapshot():
        populated = {name: value is not None for name, value in lifecycle_ownership.items()}
        weak_alive = {
            name: reference() is not None
            for name, reference in lifecycle_weak_references.items()
            if reference is not None
        }
        return {
            "ownership_container_count": sum(populated.values()),
            "ownership_container_slots": populated,
            "ownership_weak_reference_supported_count": len(weak_alive),
            "ownership_weak_reference_alive_count": sum(weak_alive.values()),
            "ownership_weak_reference_alive": weak_alive,
        }

    def retain_owned_references(state):
        lifecycle_ownership.clear()
        lifecycle_weak_references.clear()
        owned = {
            "stage": stage,
            "viewport": viewport,
            "capture_provider_alias": capture_provider_alias,
            "flow_interface": flow,
            "volume_provider": volume,
            "emitter_prim": emitter,
            "collectors": collectors,
            "collectors_by_index": collectors_by_index,
        }
        for name, value in owned.items():
            lifecycle_ownership[name] = value
            try:
                lifecycle_weak_references[name] = weakref.ref(value) if value is not None else None
            except TypeError:
                lifecycle_weak_references[name] = None
            mark(
                "owned_reference_retained", reference_name=name,
                reference_present=value is not None,
                reference_identity=int(id(value)) if value is not None else None,
                reference_type=_type_name(value) if value is not None else None,
                weak_reference_supported=lifecycle_weak_references[name] is not None,
            )
        report["lifecycle_reference_ownership"] = {
            "retained": {
                name: {
                    "present": value is not None,
                    "identity": int(id(value)) if value is not None else None,
                    "type": _type_name(value) if value is not None else None,
                }
                for name, value in owned.items()
            },
            "release_order": arguments["lifecycle_reference_release_order"],
        }
        mark("ownership_container_complete", **state(), **ownership_snapshot())

    def release_owned_references(state):
        nonlocal flow, volume, emitter, capture_provider_alias, stage, viewport
        report["lifecycle_marker"] = "capture_related_objects_release_started"
        mark("capture_related_objects_release_started", **state())
        capture_provider_alias = None
        lifecycle_ownership["capture_provider_alias"] = None
        report["lifecycle_marker"] = "capture_related_objects_release_complete"
        mark("capture_related_objects_release_complete", **state())

        report["lifecycle_marker"] = "flow_references_release_started"
        mark("flow_references_release_started", **state())
        if flow is not None:
            _flowusd.release_flowusd_interface(flow)
            flow = None
        emitter = None
        lifecycle_ownership["flow_interface"] = None
        lifecycle_ownership["emitter_prim"] = None
        report["lifecycle_marker"] = "flow_references_release_complete"
        mark("flow_references_release_complete", **state())

        report["lifecycle_marker"] = "provider_readback_references_release_started"
        mark("provider_readback_references_release_started", **state())
        volume = None
        collectors.clear()
        collectors_by_index.clear()
        lifecycle_ownership["volume_provider"] = None
        lifecycle_ownership["collectors"] = None
        lifecycle_ownership["collectors_by_index"] = None
        report["lifecycle_marker"] = "provider_readback_references_release_complete"
        mark("provider_readback_references_release_complete", **state())

        report["lifecycle_marker"] = "stage_viewport_references_release_started"
        mark("stage_viewport_references_release_started", **state())
        stage = None
        viewport = None
        lifecycle_ownership["stage"] = None
        lifecycle_ownership["viewport"] = None
        report["lifecycle_marker"] = "stage_viewport_references_release_complete"
        mark("stage_viewport_references_release_complete", **state())

        snapshot = ownership_snapshot()
        report["lifecycle_reference_ownership"]["released"] = snapshot
        report["lifecycle_reference_ownership"]["python_owned_slots_clear"] = (
            snapshot["ownership_container_count"] == 0
            and flow is None and volume is None and emitter is None
            and capture_provider_alias is None and stage is None and viewport is None
            and not collectors and not collectors_by_index
        )
        mark(
            "ownership_container_released",
            python_owned_slots_clear=report["lifecycle_reference_ownership"]["python_owned_slots_clear"],
            **state(), **snapshot,
        )

    try:
        if arguments["python_memory_telemetry"] and not tracemalloc.is_tracing():
            tracemalloc.start(10)
        unknown_channels = sorted(set(arguments["readback_channels"]) - set(CHANNELS))
        if unknown_channels:
            raise ValueError(f"unsupported readback channels: {unknown_channels}")
        valid_readback_modes = {
            "legacy", "none", "acquire_discard", "acquire_discard_release",
            "fuel_convert", "fuel_convert_release", "fuel_scalar", "fuel_jsonl", "fuel_spatial",
            "p3_spatial_release",
        }
        if arguments["readback_mode"] not in valid_readback_modes:
            raise ValueError(f"unsupported readback mode: {arguments['readback_mode']}")
        if arguments["startup_liveness_gate"] and not (arguments["startup_probe"] and arguments["flow_liveness_audit"]):
            raise ValueError("startup liveness gate requires startup probe and Flow liveness audit")
        if (arguments["startup_liveness_gate"] and arguments["readback_mode"] != "none"
                and any(frame < 120 for frame in arguments["readback_frames"])):
            raise ValueError("startup liveness gate forbids readback before frame 120")
        if not set(arguments["readback_frames"]).issubset(set(arguments["sample_frames"])):
            raise ValueError("readback frames must be a subset of sample frames")
        mark("process_entry")
        if arguments["startup_probe"]:
            mark(
                "startup_extension_ready", label=arguments["startup_probe_label"],
                kit_update_number=int(app.get_update_number()),
            )
        stage_path, point_summary, plan = _build_stage(arguments)
        report["point_payload"] = point_summary
        report["stage_sha256"] = _sha256(stage_path)
        report["lifecycle_marker"] = "offline_stage_complete"
        _write(output, report)
        mark(
            "offline_stage_complete", kit_update_number=int(app.get_update_number()),
            stage_sha256=report["stage_sha256"], payload_sha256=point_summary["payload_sha256"],
        )
        if arguments["startup_probe"]:
            mark("usd_context_connection_started", kit_update_number=int(app.get_update_number()))
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Phase 6EP stage connection failed")
        report["lifecycle_marker"] = "usd_context_connection_complete"
        mark("usd_context_connection_complete", kit_update_number=int(app.get_update_number()))
        emitter = stage.GetPrimAtPath("/World/Flow/EmitterPoint")
        if arguments["startup_probe"]:
            report["startup_live_point_emitter_contract"] = _live_point_emitter_contract(stage, emitter)
            mark(
                "startup_live_point_emitter_contract_complete",
                kit_update_number=int(app.get_update_number()),
                **{key: value for key, value in report["startup_live_point_emitter_contract"].items()
                   if key in ("emitter_path", "emitter_python_identity", "points_prim_path", "enabled", "revision",
                              "total_point_count", "active_point_count", "source_sums")},
            )
        report["public_point_support_attribute_audit"] = {
            "attributes": _stats_attributes(emitter),
            "exact_support_radius_available": False,
            "conservative_support_radius_m": arguments["support_radius_m"],
        }
        viewport = None
        for _ in range(240):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("no active viewport")
        viewport.camera_path = CAMERA_PATH
        viewport.fill_frame = False
        viewport.resolution = CAPTURE_RESOLUTION
        if arguments["startup_probe"]:
            mark("renderer_readiness_started", kit_update_number=int(app.get_update_number()))
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if arguments["startup_probe"]:
            mark(
                "renderer_readiness_complete", kit_update_number=int(app.get_update_number()),
                viewport_identity=int(id(viewport)),
            )
        acquire_position = arguments["startup_flow_acquire_position"]
        if acquire_position not in ("before_updates", "after_updates"):
            raise ValueError(f"unsupported startup Flow acquire position: {acquire_position}")

        def acquire_flow_interfaces(position):
            if arguments["startup_probe"]:
                mark(
                    "flow_interface_acquire_started", kit_update_number=int(app.get_update_number()),
                    acquire_position=position,
                )
            acquired_flow = _flowusd.acquire_flowusd_interface()
            acquired_volume = omni.volume.get_volume_interface()
            if arguments["startup_probe"]:
                mark(
                    "flow_interface_acquire_complete", kit_update_number=int(app.get_update_number()),
                    acquire_position=position, flow_identity=int(id(acquired_flow)),
                    volume_identity=int(id(acquired_volume)),
                )
            return acquired_flow, acquired_volume

        if acquire_position == "before_updates":
            flow, volume = acquire_flow_interfaces(acquire_position)
        timeline.stop()
        if arguments["startup_probe"]:
            mark(
                "timeline_reset_started", kit_update_number=int(app.get_update_number()),
                timeline_playing=bool(timeline.is_playing()), timeline_time=float(timeline.get_current_time()),
            )
        timeline.set_current_time(0.0)
        if arguments["startup_probe"]:
            mark(
                "timeline_reset_complete", kit_update_number=int(app.get_update_number()),
                timeline_playing=bool(timeline.is_playing()), timeline_time=float(timeline.get_current_time()),
            )
        pre_update_count = arguments["startup_pre_timeline_update_count"]
        if arguments["startup_probe"]:
            mark(
                "pre_timeline_updates_started", kit_update_number=int(app.get_update_number()),
                update_count=pre_update_count,
            )
        for _ in range(pre_update_count):
            await app.next_update_async()
        if arguments["startup_probe"]:
            mark(
                "pre_timeline_updates_complete", kit_update_number=int(app.get_update_number()),
                update_count=pre_update_count,
            )
        if acquire_position == "after_updates":
            flow, volume = acquire_flow_interfaces(acquire_position)
        public_members = sorted(name for name in dir(flow) if not name.startswith("_"))
        if arguments["spatial_collectors_enabled"]:
            selected_colliders = arguments["spatial_collider_indices"]
            if selected_colliders is None:
                selected_colliders = tuple(range(len(plan["geometries"])))
            for index in selected_colliders:
                _pose, points, counts, indices, _geometry = plan["geometries"][index]
                collector = SpatialNeighborhoodCollector(
                    output.parent / "spatial" / f"collider_{index}",
                    f"{arguments['scenario']}_collider_{index}", points, counts, indices,
                    np.eye(4), public_members,
                    forced_gc=(arguments["readback_mode"] != "p3_spatial_release"),
                )
                collectors.append(collector)
                collectors_by_index[index] = collector
        if arguments["report_phase"] in ("phase6fp", "phase6fq", "phase6fr", "phase6fs"):
            allocation_state = _phase6fp_allocation_state(
                arguments["allocation_calibration_level"], output, plan, point_summary, public_members, collectors
            )
            report["allocation_calibration"] = {
                key: value for key, value in allocation_state.items()
                if key not in ("owned_python_objects", "weak_references")
            }
            mark(
                "allocation_calibration_prepared",
                level=arguments["allocation_calibration_level"],
                owned_object_count=allocation_state["owned_object_count"],
                weak_reference_count=allocation_state["weak_reference_count"],
                live_weak_reference_count=allocation_state["live_weak_reference_count"],
                logical_buffer_bytes=allocation_state["logical_buffer_bytes"],
                step_count=len(allocation_state["steps"]),
            )
        capture_preparation_mode = arguments["capture_preparation_mode"]
        if capture_preparation_mode not in ("none", "manifest", "provider_alias"):
            raise ValueError(f"unsupported capture preparation mode: {capture_preparation_mode}")
        capture_preparation = {
            "mode": capture_preparation_mode,
            "capture_calls": 0,
            "pixel_buffer_bytes": 0,
            "video_generation_calls": 0,
            "manifest_written": False,
            "provider_alias_created": False,
            "provider_alias_identity": None,
        }
        if capture_preparation_mode in ("manifest", "provider_alias"):
            capture_manifest_path = output.parent / "capture_preparation_manifest.json"
            _write(capture_manifest_path, {
                "schema": "campfire.phase6fq.capture-preparation-manifest.v1",
                "capture_enabled": False,
                "capture_calls": 0,
                "pixel_buffer_bytes": 0,
                "video_generation_calls": 0,
                "resolution": list(CAPTURE_RESOLUTION),
            })
            capture_preparation["manifest_written"] = True
            capture_preparation["manifest_path"] = str(capture_manifest_path)
            capture_preparation["manifest_bytes"] = capture_manifest_path.stat().st_size
        if capture_preparation_mode == "provider_alias":
            # This is deliberately only an additional owned reference to the
            # already-public active viewport.  It does not call capture or
            # allocate a pixel buffer.
            capture_provider_alias = viewport
            capture_preparation["provider_alias_created"] = True
            capture_preparation["provider_alias_identity"] = int(id(capture_provider_alias))
        report["capture_lifecycle_preparation"] = capture_preparation
        mark(
            "capture_related_objects_prepared",
            mode=capture_preparation_mode,
            manifest_written=capture_preparation["manifest_written"],
            provider_alias_created=capture_preparation["provider_alias_created"],
            provider_alias_identity=capture_preparation["provider_alias_identity"],
            capture_calls=0,
            pixel_buffer_bytes=0,
            video_generation_calls=0,
        )
        extra_update_count = arguments["startup_extra_update_before_play_count"]
        if arguments["startup_probe"]:
            mark(
                "extra_updates_before_play_started", kit_update_number=int(app.get_update_number()),
                update_count=extra_update_count,
            )
        for _ in range(extra_update_count):
            await app.next_update_async()
        if arguments["startup_probe"]:
            mark(
                "extra_updates_before_play_complete", kit_update_number=int(app.get_update_number()),
                update_count=extra_update_count,
            )
            mark(
                "timeline_play_request_before", kit_update_number=int(app.get_update_number()),
                flow_identity=int(id(flow)), acquire_position=acquire_position,
                pre_update_count=pre_update_count, extra_update_count=extra_update_count,
            )
        timeline.play()
        report["lifecycle_marker"] = "timeline_playing"
        _write(output, report)
        mark("timeline_playing", kit_update_number=int(app.get_update_number()))
        capture_frames = set()
        if arguments["capture"]:
            capture_frames = set(range(arguments["capture_start"], arguments["capture_end"] + 1))
        sample_frames = tuple(arguments["sample_frames"])
        final_frame = max(sample_frames[-1], max(capture_frames, default=0))
        pending_readback_frame = None
        last_field_element_count = None
        last_field_logical_bytes = None
        last_field_measurement_frame = None
        stability_started = False
        stability_samples = []
        initial_stage_identity = str(stage.GetRootLayer().identifier)
        initial_flow_identity = int(id(flow))
        liveness_positions = plan["positions"][plan["active"]]
        startup_contract = report.get("startup_live_point_emitter_contract")
        startup_history = []
        startup_liveness_confirmed = not arguments["startup_liveness_gate"]
        for frame in range(1, final_frame + 1):
            await app.next_update_async()
            if arguments["flow_liveness_audit"]:
                current_active = int(flow.get_active_block_count())
                liveness_sample = {
                    "frame": int(frame),
                    "perf_counter_ns": int(time.perf_counter_ns()),
                    "kit_update_number": int(app.get_update_number()),
                    "timeline_playing": bool(timeline.is_playing()),
                    "timeline_time": float(timeline.get_current_time()),
                    "active_blocks": current_active,
                    "stage_identity": str(context.get_stage().GetRootLayer().identifier) if context.get_stage() else None,
                    "flow_identity": int(id(flow)),
                }
                report["flow_liveness_history"].append(liveness_sample)
                if arguments["startup_probe"]:
                    current_stage = context.get_stage()
                    current_emitter = emitter if current_stage else None
                    sample = {
                        **liveness_sample,
                        "point_revision": int(current_emitter.GetAttribute("campfire:residentRevision").Get()),
                        "total_point_count": int(startup_contract["total_point_count"]),
                        "active_point_count": int(startup_contract["active_point_count"]),
                        "source_sums": startup_contract["source_sums"],
                        "stage_sha256": report["stage_sha256"],
                        "payload_sha256": point_summary["payload_sha256"],
                        "payload_array_contracts": startup_contract["arrays"],
                        "stage_python_identity": int(id(current_stage)),
                        "emitter_path": str(current_emitter.GetPath()),
                        "emitter_python_identity": int(id(current_emitter)),
                        "points_prim_python_identity": int(startup_contract["points_prim_python_identity"]),
                        "emitter_enabled": bool(current_emitter.GetAttribute("enabled").Get()),
                        "renderer_ready": True,
                        "viewport_identity": int(id(viewport)),
                        "flow_interface_ready": flow is not None,
                    }
                    startup_history.append(sample)
                    mark("startup_frame_sample", **sample)
                    if arguments["startup_liveness_gate"] and frame in (60, 120):
                        thresholds = {
                            "classification_frame": 60,
                            "final_frame": frame,
                            "representative_active_blocks": 128,
                            "small_field_minimum_blocks": 20,
                            "small_field_maximum_blocks": 32,
                            "expected_point_revision": 1,
                            "expected_total_point_count": 1440,
                            "expected_active_point_count": 1344,
                            "minimum_fuel_sum": arguments["startup_expected_fuel_sum"] - arguments["startup_source_sum_tolerance"],
                            "minimum_temperature_sum": arguments["startup_expected_temperature_sum"] - arguments["startup_source_sum_tolerance"],
                            "minimum_smoke_sum": arguments["startup_expected_smoke_sum"] - arguments["startup_source_sum_tolerance"],
                        }
                        classification = classify_startup(startup_history, startup_contract, thresholds)
                        identity_source = _startup_identity_and_source_gate(startup_history, startup_contract, arguments)
                        evidence = {
                            **classification,
                            "identity_and_exact_source": identity_source,
                            "gate_frame": int(frame),
                            "readback_permitted": bool(
                                classification.get("classification") == "representative_ingestion"
                                and identity_source["pass"]
                            ),
                        }
                        report["startup_liveness_gate"] = evidence
                        if evidence["readback_permitted"]:
                            startup_liveness_confirmed = True
                            mark("startup_liveness_confirmed", **evidence)
                        elif frame == 60 and classification.get("classification") not in ("no_source", "stale_telemetry", "lifecycle_failure") and identity_source["pass"]:
                            mark("startup_liveness_pending", **evidence)
                        else:
                            mark("startup_liveness_rejected", **evidence)
                            raise RuntimeError(f"startup liveness rejected before readback: {classification.get('classification')}")
            if frame in arguments["settling_end_frames"]:
                settling_iteration = arguments["settling_end_frames"].index(frame) + 1
                mark(
                    "settling_end", frame=frame, settling_iteration=int(settling_iteration),
                    active_blocks=int(flow.get_active_block_count()),
                    timeline_time=float(timeline.get_current_time()),
                    kit_update_index=int(app.get_update_number()),
                    field_element_count=last_field_element_count,
                    field_logical_bytes=last_field_logical_bytes,
                    field_measurement_frame=last_field_measurement_frame,
                    field_measurement_source=(
                        "previous_public_readback" if last_field_measurement_frame is not None
                        else "unavailable_without_public_readback"
                    ),
                )
            if (
                arguments["stability_observation_extra_seconds"] > 0.0
                and frame == arguments["stability_observation_start_frame"]
            ):
                if not timeline.is_playing():
                    raise RuntimeError("timeline stopped before the stability observation window")
                stability_started = True
                mark(
                    "stability_observation_started", frame=frame,
                    active_blocks=int(flow.get_active_block_count()),
                    **_lifecycle_state(timeline, context, flow, volume, emitter, collectors),
                )
            if pending_readback_frame is not None:
                mark("next_frame_started", frame=frame, previous_readback_frame=pending_readback_frame)
                pending_readback_frame = None
            if frame in capture_frames:
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
                path = output.parent / "frames" / f"frame_{frame:04d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                report["captures"].append({"frame": frame, **(await _capture(viewport, path))})
            if frame not in sample_frames:
                continue
            if arguments["readback_mode"] != "legacy" and frame not in arguments["operation_frames"]:
                report["samples"].append({
                    "frame": frame, "active_blocks": int(flow.get_active_block_count()),
                    "channels": {}, "operation": False, "sentinel": True,
                })
                mark("sample_persisted", frame=frame, readback=False, operation=False, sentinel=True)
                continue
            operation_state = {
                "timeline_time": float(timeline.get_current_time()),
                "kit_update_index": int(app.get_update_number()),
            }
            mark(
                "pre_operation", frame=frame, active_blocks=int(flow.get_active_block_count()),
                field_element_count=last_field_element_count,
                field_logical_bytes=last_field_logical_bytes,
                field_measurement_frame=last_field_measurement_frame,
                **operation_state,
            )
            mark("sample_started", frame=frame, active_blocks=int(flow.get_active_block_count()), **operation_state)
            if int(point_summary["active_point_count"]) == 0:
                report["samples"].append({
                    "frame": frame,
                    "active_blocks": int(flow.get_active_block_count()),
                    "channels": {
                        channel: {"available": False, "reason": "no active Point source after conservative support filtering"}
                        for channel in CHANNELS
                    },
                })
                _write(output, report)
                mark("sample_persisted", frame=frame)
                continue
            if arguments["readback_mode"] != "legacy":
                sample = {"frame": frame, "active_blocks": int(flow.get_active_block_count()), "channels": {}}
                if arguments["readback_mode"] != "none" and frame in arguments["readback_frames"]:
                    if arguments["startup_liveness_gate"] and not startup_liveness_confirmed:
                        raise RuntimeError("readback blocked because startup liveness was not confirmed")
                    if arguments["readback_mode"] == "p3_spatial_release":
                        boundary, weak_references = _p3_spatial_boundary(
                            flow, volume, arguments, frame, output, collectors,
                            operation_state=operation_state,
                        )
                    else:
                        boundary, weak_references = _readback_boundary(
                            flow, volume, arguments, frame, output, liveness_positions=liveness_positions,
                            operation_state=operation_state,
                        )
                    fuel_metadata = (
                        boundary.get("fuel_source")
                        or (boundary.get("channels", {}).get("fuel", {}).get("source"))
                        or boundary.get("channel_objects", [None] * len(CHANNELS))[CHANNELS.index("fuel")]
                    )
                    if fuel_metadata:
                        last_field_element_count = fuel_metadata.get("element_count", fuel_metadata.get("size"))
                        last_field_logical_bytes = fuel_metadata.get("nbytes")
                        last_field_measurement_frame = int(frame)
                    alive_after_scope = sum(reference is not None and reference() is not None for reference in weak_references)
                    boundary["weak_reference_supported_count"] = sum(reference is not None for reference in weak_references)
                    boundary["weak_reference_alive_after_scope_count"] = alive_after_scope
                    sample["readback_boundary"] = boundary
                    mark(
                        "python_references_released", frame=frame,
                        disposal=arguments["reference_disposal"], weak_reference_alive_count=alive_after_scope,
                        **operation_state,
                    )
                    if arguments["readback_mode"] == "fuel_jsonl":
                        bounded = {
                            "schema": "campfire.phase6eu.fuel-aggregate.v1", "frame": frame,
                            "active_blocks": sample["active_blocks"],
                            "fuel_aggregate": boundary.get("fuel_aggregate"),
                        }
                        mark("jsonl_write_before", frame=frame)
                        _append_bounded_jsonl(arguments["bounded_jsonl_path"], bounded)
                        mark(
                            "jsonl_write_after", frame=frame,
                            jsonl_bytes=arguments["bounded_jsonl_path"].stat().st_size,
                        )
                    pending_readback_frame = frame
                report["samples"].append(sample)
                mark(
                    "sample_metadata_complete", frame=frame,
                    readback=bool(sample.get("readback_boundary")), active_blocks=sample["active_blocks"],
                    **operation_state,
                )
                mark(
                    "operation_completed", frame=frame,
                    readback=bool(sample.get("readback_boundary")), active_blocks=sample["active_blocks"],
                    field_element_count=last_field_element_count,
                    field_logical_bytes=last_field_logical_bytes,
                    field_measurement_frame=last_field_measurement_frame,
                    **operation_state,
                )
                mark(
                    "release_completed", frame=frame,
                    readback=bool(sample.get("readback_boundary")),
                    weak_reference_alive_count=(
                        sample.get("readback_boundary", {}).get("weak_reference_alive_after_scope_count", 0)
                    ),
                    **operation_state,
                )
                mark("settling_started", frame=frame, active_blocks=sample["active_blocks"], **operation_state)
                continue
            if not arguments["readback_channels"]:
                report["samples"].append({"frame": frame, "active_blocks": int(flow.get_active_block_count()), "channels": {}})
                _write(output, report)
                mark("sample_persisted", frame=frame, readback=False)
                continue
            mark("readback_started", frame=frame)
            raw = flow.get_latest_nanovdb_readback()
            mark("readback_complete", frame=frame, returned_channel_count=len(raw))
            sample = {"frame": frame, "active_blocks": int(flow.get_active_block_count()), "channels": {}}
            for channel in arguments["readback_channels"]:
                channel_index = CHANNELS.index(channel)
                mark("channel_started", frame=frame, channel=channel)
                array = np.asarray(raw[channel_index])
                if array.size == 0:
                    sample["channels"][channel] = {"available": False}
                    mark("channel_complete", frame=frame, channel=channel, available=False)
                    continue
                nvdb_path = output.parent / f"sample_{frame}_{channel}.nvdb"
                bounds = {
                    "scene": {"minimum": [-1.1, -1.1, 0.2], "maximum": [1.1, 1.1, 2.1]},
                    "upper": {"minimum": [-0.5, -0.5, 0.9], "maximum": [0.5, 0.5, 1.8]},
                }
                if arguments["report_phase"] in ("phase6er", "phase6es"):
                    bounds.update({
                        "emitter_side": {"minimum": [-0.36, -0.16, 0.50], "maximum": [0.36, 0.16, 0.65]},
                        "opposite_side": {"minimum": [-0.36, -0.16, 0.895], "maximum": [0.36, 0.16, 1.05]},
                        "far_above": {"minimum": [-0.50, -0.30, 1.10], "maximum": [0.50, 0.30, 1.55]},
                        "exterior_flow": {"minimum": [0.50, -0.25, 0.40], "maximum": [0.90, 0.25, 1.55]},
                    })
                spatial_collectors = collectors
                if channel != "velocity" and arguments["spatial_scalar_collider_indices"] is not None:
                    spatial_collectors = [collectors_by_index[index] for index in arguments["spatial_scalar_collider_indices"] if index in collectors_by_index]
                details = _save_and_sample(
                    flow, volume, array, channel, nvdb_path, bounds,
                    spatial_collector=(spatial_collectors if arguments["spatial_all_channels"] or channel == "velocity" else None),
                    spatial_velocity_only=not arguments["spatial_all_channels"], frame=frame,
                    profile_threshold=(
                        {"velocity": 0.01, "fuel": 0.001, "temperature": 0.1, "burn": 0.001, "smoke": 0.001}[channel]
                        if arguments["report_phase"] in ("phase6eq", "phase6er", "phase6es") else None
                    ),
                )
                sample["channels"][channel] = {"available": True, "word_count": int(array.size), "buffer_dtype": str(array.dtype), "buffer_bytes": int(array.nbytes), **details}
                mark("channel_complete", frame=frame, channel=channel, available=True, buffer_bytes=int(array.nbytes))
            report["samples"].append(sample)
            mark("sample_persist_started", frame=frame)
            _write(output, report)
            mark("sample_persisted", frame=frame, raw_json_bytes=output.stat().st_size)
        mark(
            "final_sample_complete", frame=final_frame,
            **_lifecycle_state(timeline, context, flow, volume, emitter, collectors),
        )
        if arguments["stability_observation_extra_seconds"] > 0.0:
            if not stability_started:
                raise RuntimeError("stability observation start frame was not reached")
            extra_seconds = arguments["stability_observation_extra_seconds"]
            active_interval = arguments["stability_active_block_sample_seconds"]
            extra_start = time.monotonic()
            next_active_sample = 0.0
            extra_updates = 0
            while True:
                elapsed = time.monotonic() - extra_start
                if elapsed >= extra_seconds:
                    break
                await app.next_update_async()
                extra_updates += 1
                if not timeline.is_playing():
                    raise RuntimeError("timeline stopped during the stability observation window")
                elapsed = time.monotonic() - extra_start
                if elapsed >= next_active_sample:
                    sample = {
                        "elapsed_seconds": float(elapsed),
                        "update_index": int(extra_updates),
                        "active_blocks": int(flow.get_active_block_count()),
                        "timeline_time": float(timeline.get_current_time()),
                    }
                    stability_samples.append(sample)
                    mark("stability_observation_sample", **sample)
                    next_active_sample += active_interval
            actual_seconds = time.monotonic() - extra_start
            report["stability_observation"] = {
                "start_frame": arguments["stability_observation_start_frame"],
                "extra_seconds_requested": extra_seconds,
                "extra_seconds_actual": float(actual_seconds),
                "active_block_sample_seconds": active_interval,
                "extra_update_count": int(extra_updates),
                "samples": stability_samples,
                "timeline_playing_at_end": bool(timeline.is_playing()),
            }
            mark(
                "stability_observation_ended", frame=final_frame,
                extra_seconds_actual=float(actual_seconds), extra_update_count=int(extra_updates),
                active_blocks=int(flow.get_active_block_count()),
                **_lifecycle_state(timeline, context, flow, volume, emitter, collectors),
            )
        report["spatial_manifest_collider_indices"] = list(collectors_by_index)
        report["spatial_manifests"] = [collectors_by_index[index].finalize() for index in collectors_by_index]
        report["active_blocks_final"] = int(flow.get_active_block_count())
        if allocation_state is not None:
            report["allocation_calibration"]["live_weak_reference_count_before_shutdown"] = sum(
                reference() is not None for reference in allocation_state["weak_references"]
            )
        report["source_sums"] = {
            "fuel": float(sum(emitter.GetAttribute("pointFuels").Get())),
            "temperature": float(sum(emitter.GetAttribute("pointTemperatures").Get())),
            "smoke": float(sum(emitter.GetAttribute("pointSmokes").Get())),
        }
        report["revision"] = int(emitter.GetAttribute("campfire:residentRevision").Get())
        if arguments["startup_probe"]:
            active_values = [item["active_blocks"] for item in startup_history]
            report["startup_probe"] = {
                "label": arguments["startup_probe_label"],
                "history": startup_history,
                "first_nonzero_frame": next((item["frame"] for item in startup_history if item["active_blocks"] > 0), None),
                "first_24_frame": next((item["frame"] for item in startup_history if item["active_blocks"] == 24), None),
                "first_above_24_frame": next((item["frame"] for item in startup_history if item["active_blocks"] > 24), None),
                "first_representative_frame": next((item["frame"] for item in startup_history if item["active_blocks"] >= 128), None),
                "minimum_active_blocks": min(active_values) if active_values else None,
                "maximum_active_blocks": max(active_values) if active_values else None,
            }
        report["flow_liveness_audit"] = {
            "enabled": bool(arguments["flow_liveness_audit"]),
            "initial_stage_identity": initial_stage_identity,
            "final_stage_identity": str(context.get_stage().GetRootLayer().identifier) if context.get_stage() else None,
            "initial_flow_identity": initial_flow_identity,
            "final_flow_identity": int(id(flow)),
            "history_sample_count": len(report["flow_liveness_history"]),
            "first_nonzero_frame": next(
                (item["frame"] for item in report["flow_liveness_history"] if item["active_blocks"] > 0), None
            ),
            "first_24_frame": next(
                (item["frame"] for item in report["flow_liveness_history"] if item["active_blocks"] == 24), None
            ),
            "timeline_advanced": bool(
                report["flow_liveness_history"]
                and len({item["timeline_time"] for item in report["flow_liveness_history"]}) > 1
            ),
            "telemetry_fresh": bool(
                report["flow_liveness_history"]
                and all(
                    right["perf_counter_ns"] > left["perf_counter_ns"] and right["frame"] > left["frame"]
                    for left, right in zip(report["flow_liveness_history"], report["flow_liveness_history"][1:])
                )
            ),
            "stage_identity_unchanged": all(
                item["stage_identity"] == initial_stage_identity for item in report["flow_liveness_history"]
            ),
            "flow_identity_unchanged": all(
                item["flow_identity"] == initial_flow_identity for item in report["flow_liveness_history"]
            ),
        }
        report["status"] = "ok"
        report["completion_contract"]["results_saved"] = True
        report["lifecycle_marker"] = "measurement_complete"
        _write(output, report)
        mark("measurement_complete", **_lifecycle_state(timeline, context, flow, volume, emitter, collectors))
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        try:
            if arguments["lifecycle_calibration"]:
                state = lambda: _lifecycle_state(timeline, context, flow, volume, emitter, collectors)
                report["lifecycle_marker"] = "timeline_stop_request_before"
                mark("timeline_stop_request_before", **state())
                timeline.stop()
                report["lifecycle_marker"] = "timeline_stop_request_after"
                mark("timeline_stop_request_after", **state())
                for _ in range(12):
                    await app.next_update_async()
                    if not timeline.is_playing():
                        break
                if timeline.is_playing():
                    raise RuntimeError("timeline did not stop within 12 Kit updates")
                report["lifecycle_marker"] = "timeline_stop_confirmed"
                mark("timeline_stop_confirmed", **state())
                report["completion_contract"]["timeline_stopped"] = True

                drain_updates = arguments["renderer_drain_updates"]
                report["lifecycle_marker"] = "renderer_drain_started"
                mark("renderer_drain_started", update_count=drain_updates, **state())
                for update_index in range(1, drain_updates + 1):
                    mark("renderer_update_started", update_index=update_index, **state())
                    await app.next_update_async()
                    mark("renderer_update_complete", update_index=update_index, **state())
                report["lifecycle_marker"] = "renderer_drain_complete"
                mark("renderer_drain_complete", **state())
                report["completion_contract"]["renderer_drained"] = True

                release_order = arguments["lifecycle_reference_release_order"]
                if release_order not in ("before_stage_close", "after_stage_close"):
                    raise ValueError(f"unsupported lifecycle reference release order: {release_order}")
                mark("reference_release_order_selected", release_order=release_order, **state())
                retain_owned_references(state)
                if release_order == "before_stage_close":
                    release_owned_references(state)

                report["lifecycle_marker"] = "stage_close_request_before"
                mark("stage_close_request_before", **state())
                close_timeout = arguments["stage_close_timeout_seconds"]
                try:
                    if close_timeout > 0.0:
                        await asyncio.wait_for(context.close_stage_async(), timeout=close_timeout)
                    else:
                        await context.close_stage_async()
                except asyncio.TimeoutError:
                    report["lifecycle_marker"] = "stage_close_timeout"
                    mark("stage_close_timeout", timeout_seconds=close_timeout, **state())
                    raise RuntimeError(f"close_stage_async exceeded {close_timeout:.3f} seconds")
                report["lifecycle_marker"] = "stage_close_request_after"
                mark("stage_close_request_after", **state())
                report["lifecycle_marker"] = "stage_close_complete"
                mark("stage_close_complete", **state(), **ownership_snapshot())
                report["completion_contract"]["stage_closed"] = True
                if context.get_stage() is not None:
                    raise RuntimeError("USD context still exposes a stage after close_stage_async")
                report["lifecycle_marker"] = "usd_context_disconnected"
                mark("usd_context_disconnected", **state())
                for update_index in range(1, 5):
                    mark("post_close_renderer_update_started", update_index=update_index, **state())
                    await app.next_update_async()
                    mark("post_close_renderer_update_complete", update_index=update_index, **state())
                if release_order == "after_stage_close":
                    # The release-after-close ablation retains every owned Flow,
                    # provider, collector, and viewport alias until USD detach and
                    # the bounded post-close renderer drain have completed.
                    mark("references_retained_through_post_close", **state())
                    release_owned_references(state)
            else:
                report["lifecycle_marker"] = "timeline_stopping"
                mark("timeline_stopping")
                timeline.stop()
                for _ in range(12):
                    await app.next_update_async()
                report["lifecycle_marker"] = "timeline_stopped"
                mark("timeline_stopped")
                report["completion_contract"]["timeline_stopped"] = True
                await context.close_stage_async()
                for _ in range(12):
                    await app.next_update_async()
                report["lifecycle_marker"] = "renderer_drain_complete"
                mark("renderer_drain_complete")
                report["completion_contract"]["stage_closed"] = True
                report["completion_contract"]["renderer_drained"] = True
                if flow is not None:
                    _flowusd.release_flowusd_interface(flow)
                    flow = None
            if arguments["lifecycle_calibration"]:
                report["lifecycle_marker"] = "app_close_requested"
                mark("app_close_requested", **_lifecycle_state(timeline, context, flow, volume, emitter, collectors))
            report["lifecycle_marker"] = "shutdown_complete"
            mark("shutdown_complete", **_lifecycle_state(timeline, context, flow, volume, emitter, collectors))
            report["completion_contract"]["shutdown_requested"] = True
            report["lifecycle_history"].append({"marker": "shutdown_complete", "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        except Exception as error:
            report["shutdown_error"] = f"{type(error).__name__}: {error}"
            report["status"] = "error"
            exit_code = 1
        _write(output, report)
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        app.post_uncancellable_quit(exit_code)


if __name__ == "__main__":
    asyncio.ensure_future(_run())
