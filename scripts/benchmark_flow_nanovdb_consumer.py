"""Qualify a complete-stage NanoVDB emitter on the fixed Flow build.

The default-off spike builds the entire USD stage before attaching it to the
Kit USD context.  This deliberately avoids the live emitter redefinition that
the Point-emitter spike found unsafe.  Production code and canonical scenes are
not changed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.timeline
import omni.usd
import omni.volume
from omni.flowusd import _flowusd
from pxr import Sdf, Usd, UsdVol, Vt

from campfire.app.flow_scene import FLOW_EMITTER_PATH, FLOW_VERSION, populate_flow_scene


SURFACE_POINTS_PER_LOG = 360
GRID_SHAPE = (24, 12, 4)


def _summary(values, warmup=0):
    measured = list(values[warmup:])
    ordered = sorted(measured)
    return {
        "sample_count": len(measured),
        "warmup_samples_excluded": warmup,
        "mean_ms": statistics.fmean(measured),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(measured),
    }


def _set(prim, name, value):
    attribute = prim.GetAttribute(name)
    if not attribute:
        raise RuntimeError(f"Flow schema attribute unavailable: {prim.GetPath()}.{name}")
    if not attribute.Set(value):
        raise RuntimeError(f"Flow attribute Set failed: {prim.GetPath()}.{name}")
    return attribute


def _surface_points():
    axial_cells, circumferential_cells, radial_cells = GRID_SHAPE
    length_m = 0.72
    radius_m = 0.105
    dz = length_m / axial_cells
    dr = radius_m / radial_cells
    points = []
    for axial in range(axial_cells):
        x = -0.5 * length_m + (axial + 0.5) * dz
        for circumferential in range(circumferential_cells):
            angle = 2.0 * math.pi * (circumferential + 0.5) / circumferential_cells
            for radial in range(radial_cells):
                if radial != radial_cells - 1 and axial not in (0, axial_cells - 1):
                    continue
                radius = (radial + 0.5) * dr
                points.append(
                    (
                        x,
                        radius * math.cos(angle),
                        0.48 + radius * math.sin(angle),
                    )
                )
    if len(points) != SURFACE_POINTS_PER_LOG:
        raise RuntimeError(f"Unexpected surface point count: {len(points)}")
    return np.asarray(points, dtype=np.float32)


def _readback_summary(flow_interface):
    names = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
    raw = flow_interface.get_latest_nanovdb_readback()
    result = {}
    for index, name in enumerate(names):
        value = raw[index] if index < len(raw) else []
        array = np.asarray(value)
        result[name] = {
            "word_count": int(array.size),
            "byte_count": int(array.nbytes),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest() if array.size else None,
        }
    return result


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6bt/output")).resolve()
    frames = settings.get_as_int("/phase6bt/frames") or 120
    warmup = settings.get_as_int("/phase6bt/warmup") or 30
    encoding = settings.get_as_string("/phase6bt/encoding") or "float4"
    if encoding not in ("float4", "rgba8"):
        raise ValueError(f"Unsupported NanoVDB encoding: {encoding}")
    container = settings.get_as_string("/phase6bt/container") or "direct"
    if container not in ("direct", "flow-point-cloud"):
        raise ValueError(f"Unsupported NanoVDB container: {container}")
    source = settings.get_as_string("/phase6bt/source") or "direct-array"
    if source not in ("direct-array", "volume-asset", "asset-attribute"):
        raise ValueError(f"Unsupported NanoVDB source: {source}")
    if source in ("volume-asset", "asset-attribute") and encoding != "rgba8":
        raise ValueError("The asset qualifications use the packed RGBA8 buffer")
    output.parent.mkdir(parents=True, exist_ok=True)
    scene_path = output.with_suffix(".scene.usda")
    volume_path = output.with_suffix(".source.nvdb")
    scene_path.unlink(missing_ok=True)
    volume_path.unlink(missing_ok=True)
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    flow_interface = None
    persistent_context_initialized = False
    report = {
        "schema_version": 1,
        "phase": "phase6bt",
        "status": "running",
        "default_off": True,
        "production_code_changed": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    try:
        for _ in range(5):
            await app.next_update_async()
        points = _surface_points()
        colors = np.empty((len(points), 3), dtype=np.float32)
        colors[:, 0] = np.float32(2.0)
        colors[:, 1] = np.float32(0.8)
        colors[:, 2] = np.float32(0.2)
        identity = np.eye(4, dtype=np.float64).reshape(-1)
        flow_interface = _flowusd.acquire_flowusd_interface()
        flow_interface.init_persistent_voxelize_context()
        persistent_context_initialized = True
        producer_started = time.perf_counter_ns()
        buffers = flow_interface.voxelize_points_and_sync_v2(
            points, colors, identity, identity, 0.025, 256
        )
        producer_ms = (time.perf_counter_ns() - producer_started) / 1_000_000.0
        if len(buffers) != 5:
            raise RuntimeError(f"Expected five NanoVDB buffers, received {len(buffers)}")

        conversion_started = time.perf_counter_ns()
        selected_buffers = buffers[:4] if encoding == "float4" else buffers[4:5]
        usd_arrays = (
            tuple(
                Vt.UIntArray.FromNumpy(np.asarray(buffer, dtype=np.uint32))
                for buffer in selected_buffers
            )
            if source == "direct-array"
            else ()
        )
        conversion_ms = (time.perf_counter_ns() - conversion_started) / 1_000_000.0

        volume_save_ms = None
        if source in ("volume-asset", "asset-attribute"):
            grid_data = flow_interface.buffer_to_volume(buffers[4])
            save_parameters = omni.volume.SaveVolumeParameters()
            save_parameters.flags = omni.volume.kNanoVDBCodecBlosc
            volume_save_started = time.perf_counter_ns()
            if not omni.volume.get_volume_interface().save_volume(
                grid_data, str(volume_path), save_parameters
            ):
                raise RuntimeError("omni.volume failed to save the NanoVDB source")
            volume_save_ms = (
                time.perf_counter_ns() - volume_save_started
            ) / 1_000_000.0

        offline_stage = Usd.Stage.CreateNew(str(scene_path))
        populate_flow_scene(offline_stage)
        offline_stage.RemovePrim(FLOW_EMITTER_PATH)
        emitter_path = FLOW_EMITTER_PATH
        if container == "flow-point-cloud":
            point_cloud_path = FLOW_EMITTER_PATH
            point_cloud = offline_stage.DefinePrim(point_cloud_path, "FlowPointCloud")
            for name, value in (
                ("enabled", True),
                ("autoCellSize", False),
                ("cellSize", 0.025),
                ("levelCount", 1),
                ("updateWhilePaused", True),
            ):
                _set(point_cloud, name, value)
            emitter_path = point_cloud_path.AppendChild("NanoVdbEmitter")
        emitter = offline_stage.DefinePrim(emitter_path, "FlowEmitterNanoVdb")
        for name, value in (
            ("layer", 0),
            ("enabled", True),
            ("levelCount", 1),
            ("allocationScale", 1.0),
            ("allocateActiveLeaves", True),
            ("colorIsSrgb", False),
            ("temperatureScale", 1.0),
            ("fuelScale", 1.0),
            ("burnScale", 1.0),
            ("smokeScale", 0.05),
            ("coupleRateTemperature", 10.0),
            ("coupleRateFuel", 2.0),
            ("coupleRateBurn", 2.0),
            ("coupleRateSmoke", 1.0),
            ("minSmoke", 0.0001),
            ("enableStreaming", False),
            ("streamOnce", False),
        ):
            _set(emitter, name, value)
        revision = emitter.CreateAttribute(
            "campfire:residentRevision", Sdf.ValueTypeNames.Int64
        )
        if source == "volume-asset":
            volume_prim_path = Sdf.Path("/World/NanoVdbSource")
            field_path = volume_prim_path.AppendChild("rgba")
            volume = UsdVol.Volume.Define(offline_stage, volume_prim_path)
            field = UsdVol.OpenVDBAsset.Define(offline_stage, field_path)
            field.CreateFilePathAttr().Set(Sdf.AssetPath(volume_path.as_posix()))
            field.CreateFieldNameAttr().Set("Flow")
            volume.CreateFieldRelationship("rgba", field_path)
            emitter.GetRelationship("volumePrim").SetTargets([volume_prim_path])
        elif source == "asset-attribute":
            _set(
                emitter,
                "nanoVdbRgba8s:assetPath",
                Sdf.AssetPath(volume_path.as_posix()),
            )
            _set(emitter, "nanoVdbRgba8s:gridName", "Flow")
        set_started = time.perf_counter_ns()
        with Sdf.ChangeBlock():
            if source in ("volume-asset", "asset-attribute"):
                pass
            elif encoding == "float4":
                _set(emitter, "nanoVdbTemperatures", usd_arrays[0])
                _set(emitter, "nanoVdbFuels", usd_arrays[1])
                _set(emitter, "nanoVdbBurns", usd_arrays[2])
                _set(emitter, "nanoVdbSmokes", usd_arrays[3])
            else:
                _set(emitter, "nanoVdbRgba8s", usd_arrays[0])
            if not revision.Set(1):
                raise RuntimeError("NanoVDB consumer revision Set failed")
        offline_set_ms = (time.perf_counter_ns() - set_started) / 1_000_000.0
        save_started = time.perf_counter_ns()
        offline_stage.GetRootLayer().Save()
        save_ms = (time.perf_counter_ns() - save_started) / 1_000_000.0
        offline_stage = None

        open_started = time.perf_counter_ns()
        await context.open_stage_async(str(scene_path))
        open_ms = (time.perf_counter_ns() - open_started) / 1_000_000.0
        stage = context.get_stage()
        attached_emitter = stage.GetPrimAtPath(emitter_path)
        if not attached_emitter or attached_emitter.GetTypeName() != "FlowEmitterNanoVdb":
            raise RuntimeError("Complete-stage NanoVDB emitter did not survive stage attach")

        update_times = []
        active_blocks = []
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.play()
        for _ in range(warmup + frames):
            started = time.perf_counter_ns()
            await app.next_update_async()
            update_times.append((time.perf_counter_ns() - started) / 1_000_000.0)
            active_blocks.append(int(flow_interface.get_active_block_count()))
        timeline.pause()
        readback = _readback_summary(flow_interface)
        report.update(
            {
                "status": "ok",
                "configuration": {
                    "flow_version": FLOW_VERSION,
                    "point_count": len(points),
                    "cell_size_m": 0.025,
                    "max_blocks": 256,
                    "emitter_count": 1,
                    "encoding": encoding,
                    "container": container,
                    "source": source,
                    "nano_vdb_word_array_attribute_count": len(usd_arrays),
                    "source_binding_attribute_count": (
                        2 if source == "asset-attribute" else 0
                    ),
                    "source_relationship_count": (
                        1 if source == "volume-asset" else 0
                    ),
                    "measured_frames": frames,
                    "warmup_frames": warmup,
                    "complete_stage_before_attach": True,
                },
                "producer": {
                    "voxelize_and_sync_ms": producer_ms,
                    "buffer_count": len(buffers),
                    "float_channel_bytes": [int(np.asarray(v).nbytes) for v in buffers[:4]],
                    "packed_rgba_bytes": int(np.asarray(buffers[4]).nbytes),
                    "packed_rgba_authored_or_referenced": encoding == "rgba8",
                },
                "usd": {
                    "numpy_to_vt_uint_arrays_ms": conversion_ms,
                    "offline_payload_set_and_revision_ms": offline_set_ms,
                    "offline_usda_save_ms": save_ms,
                    "nvdb_asset_save_ms": volume_save_ms,
                    "nvdb_asset_file_bytes": (
                        volume_path.stat().st_size if volume_path.is_file() else None
                    ),
                    "stage_open_and_attach_ms": open_ms,
                    "scene_file_bytes": scene_path.stat().st_size,
                    "runtime_attribute_updates": 0,
                    "runtime_objects_changed_publications": 0,
                },
                "flow": {
                    "active_blocks_peak": max(active_blocks),
                    "active_blocks_final": active_blocks[-1],
                    "active_blocks_mean_measured": statistics.fmean(active_blocks[warmup:]),
                    "kit_flow_render_update": _summary(update_times, warmup),
                    "nanovdb_readback": readback,
                    "consumer_qualified": max(active_blocks) > 0,
                },
                "revision": {
                    "published": 1,
                    "attached_consumer": int(
                        attached_emitter.GetAttribute("campfire:residentRevision").Get()
                    ),
                },
                "mapping_evidence": {
                    "buffer_0": "red float grid -> temperature",
                    "buffer_1": "green float grid -> fuel",
                    "buffer_2": "blue float grid -> burn",
                    "buffer_3": "color-independent alpha occupancy float grid -> smoke",
                    "buffer_4": (
                        "packed RGBA8 grid; authored by this trial"
                        if encoding == "rgba8"
                        else "packed RGBA8 grid; not authored by this four-float-channel trial"
                    ),
                },
                "limitations": {
                    "dynamic_publish_measured": False,
                    "flow_ingestion_time_separate_ms": None,
                    "emitter_rasterization_time_separate_ms": None,
                    "solver_render_separate_time_ms": None,
                    "reason": (
                        "This first consumer qualification uses one immutable complete stage; "
                        "the fixed public interface exposes no separate ingestion timer."
                    ),
                },
            }
        )
        output.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        carb.log_info(
            f"[phase6bt] blocks={max(active_blocks)} report={output}"
        )
        app.post_uncancellable_quit(0 if max(active_blocks) > 0 else 2)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        carb.log_error(f"[phase6bt] failed: {type(error).__name__}: {error}")
        app.post_uncancellable_quit(1)
    finally:
        if flow_interface is not None:
            if persistent_context_initialized:
                flow_interface.release_persistent_voxelize_context()
            _flowusd.release_flowusd_interface(flow_interface)


asyncio.ensure_future(_run())
