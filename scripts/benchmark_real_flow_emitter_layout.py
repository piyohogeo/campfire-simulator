"""Run one default-off real-Kit/Flow emitter transport measurement.

The script is launched with Kit's ``--exec`` option.  It does not alter the
campfire production extension or its defaults.  Publicly observable timing
boundaries are reported exactly; Flow USD ingestion and rasterization are not
invented when the fixed Flow build exposes no separate timer.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.timeline
import omni.usd
import omni.flowusd
import psutil
from omni.flowusd import _flowusd
from pxr import Sdf, Tf, Usd, UsdGeom, Vt

from campfire.app.flow_scene import (
    FLOW_EMITTER_PATH,
    FLOW_VERSION,
    populate_flow_scene,
)


LAYOUTS = ("sphere", "point-single", "point-per-log")
SURFACE_POINTS_PER_LOG = 360
CELLS_PER_LOG = 1152
GRID_SHAPE = (24, 12, 4)


def _parse_arguments():
    settings = carb.settings.get_settings()
    configured_layout = settings.get_as_string("/phase6bp/layout")
    configured_output = settings.get_as_string("/phase6bp/output")
    if configured_layout or configured_output:
        arguments = argparse.Namespace(
            layout=configured_layout,
            log_count=settings.get_as_int("/phase6bp/logCount"),
            frames=settings.get_as_int("/phase6bp/frames"),
            warmup=settings.get_as_int("/phase6bp/warmup"),
            output=Path(configured_output),
        )
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--layout", choices=LAYOUTS, required=True)
        parser.add_argument("--log-count", type=int, default=20)
        parser.add_argument("--frames", type=int, default=120)
        parser.add_argument("--warmup", type=int, default=30)
        parser.add_argument("--output", type=Path, required=True)
        arguments = parser.parse_args(sys.argv[1:])
    if arguments.layout not in LAYOUTS:
        raise ValueError(f"Unsupported layout: {arguments.layout}")
    if arguments.log_count not in (1, 5, 10, 20):
        raise ValueError("log count must be 1, 5, 10, or 20")
    if arguments.frames < 20 or arguments.warmup < 1:
        raise ValueError("Use at least 20 measured frames and one warmup frame")
    return arguments


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


def _surface_points_for_log(log_index):
    axial_cells, circumferential_cells, radial_cells = GRID_SHAPE
    length_m = 0.72
    radius_m = 0.105
    dz = length_m / axial_cells
    dr = radius_m / radial_cells
    row, column = divmod(log_index, 5)
    origin_x = (column - 2.0) * 0.22
    origin_y = (row - 1.5) * 0.22
    origin_z = 0.42 + 0.045 * ((row + column) % 2)
    rotate = (row % 2) == 1
    points = []
    for axial in range(axial_cells):
        axial_position = -0.5 * length_m + (axial + 0.5) * dz
        for circumferential in range(circumferential_cells):
            angle = 2.0 * math.pi * (circumferential + 0.5) / circumferential_cells
            for radial in range(radial_cells):
                if radial != radial_cells - 1 and axial not in (0, axial_cells - 1):
                    continue
                radial_position = (radial + 0.5) * dr
                cross_a = radial_position * math.cos(angle)
                cross_b = radial_position * math.sin(angle)
                if rotate:
                    x = origin_x + cross_a
                    y = origin_y + axial_position
                else:
                    x = origin_x + axial_position
                    y = origin_y + cross_a
                points.append((x, y, origin_z + cross_b))
    if len(points) != SURFACE_POINTS_PER_LOG:
        raise RuntimeError(f"Unexpected surface point count: {len(points)}")
    return np.asarray(points, dtype=np.float32)


def _build_point_sources(log_count):
    per_log = tuple(_surface_points_for_log(index) for index in range(log_count))
    return per_log, np.concatenate(per_log, axis=0)


def _configure_point_cloud_stage(stage):
    root_path = Sdf.Path("/PointCloud/PointCloud/flowPointCloud")
    root = stage.GetPrimAtPath(root_path)
    if not root or root.GetTypeName() != "FlowPointCloud":
        raise RuntimeError("Bundled PointCloud preset root is unavailable")
    simulate = stage.GetPrimAtPath(root_path.AppendChild("flowSimulate"))
    if not simulate or simulate.GetTypeName() != "FlowSimulate":
        raise RuntimeError("Bundled PointCloud simulate prim is unavailable")
    return root_path


def _define_point_emitters(stage, root_path, layout, per_log_points, all_points):
    original_path = root_path.AppendChild("flowEmitterPoint")
    if layout != "point-single":
        raise RuntimeError(
            "Point-per-log is deferred until the non-structural bundled-preset "
            "path is qualified"
        )
    point_sets = (all_points,) if layout == "point-single" else per_log_points
    emitters = []
    for index, points in enumerate(point_sets):
        path = (
            original_path
            if layout == "point-single"
            else root_path.AppendChild(f"flowEmitterPoint{index:02d}")
        )
        prim = stage.GetPrimAtPath(path)
        if not prim or prim.GetTypeName() != "FlowEmitterPoint":
            raise RuntimeError(f"Bundled Point emitter unavailable: {path}")
        source_path = Sdf.Path("/PointCloud/SourcePoints")
        source = UsdGeom.Points.Define(stage, source_path)
        source_positions = Vt.Vec3fArray.FromNumpy(points * np.float32(100.0))
        source.GetPointsAttr().Set(source_positions)
        source.GetWidthsAttr().Set(Vt.FloatArray([1.0] * len(points)))
        source_colors = np.empty((len(points), 3), dtype=np.float32)
        source_colors[:, 0] = np.float32(2.0)
        source_colors[:, 1] = np.float32(0.8)
        source_colors[:, 2] = np.float32(0.2)
        color_attribute = source.GetPrim().CreateAttribute(
            "primvars:displayColor", Sdf.ValueTypeNames.Color3fArray
        )
        color_attribute.SetMetadata("interpolation", "vertex")
        color_attribute.Set(Vt.Vec3fArray.FromNumpy(source_colors))
        relationship = prim.GetRelationship("pointsPrim")
        if not relationship:
            relationship = prim.CreateRelationship("pointsPrim")
        relationship.SetTargets([source_path])
        position_started = time.perf_counter_ns()
        positions = Vt.Vec3fArray.FromNumpy(points)
        position_boundary_ms = (time.perf_counter_ns() - position_started) / 1_000_000.0
        position_set_started = time.perf_counter_ns()
        position_attribute = _set(prim, "pointPositions", positions)
        position_set_ms = (time.perf_counter_ns() - position_set_started) / 1_000_000.0
        emitters.append(
            {
                "prim": prim,
                "point_count": len(points),
                "positions": position_attribute,
                "fuels": prim.GetAttribute("pointFuels"),
                "temperatures": prim.GetAttribute("pointTemperatures"),
                "smokes": prim.GetAttribute("pointSmokes"),
                "revision": prim.CreateAttribute(
                    "campfire:residentRevision", Sdf.ValueTypeNames.Int64
                ),
                "position_boundary_ms": position_boundary_ms,
                "position_set_ms": position_set_ms,
            }
        )
    return tuple(emitters)


def _sphere_handles(stage):
    prim = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    return (
        {
            "prim": prim,
            "point_count": 0,
            "fuel": prim.GetAttribute("fuel"),
            "temperature": prim.GetAttribute("temperature"),
            "smoke": prim.GetAttribute("smoke"),
            "couple_fuel": prim.GetAttribute("coupleRateFuel"),
            "couple_temperature": prim.GetAttribute("coupleRateTemperature"),
            "couple_smoke": prim.GetAttribute("coupleRateSmoke"),
            "revision": prim.CreateAttribute(
                "campfire:residentRevision", Sdf.ValueTypeNames.Int64
            ),
        },
    )


def _point_frame_source(total_points, revision):
    phase = np.float32((revision % 20) * 0.0005)
    fuels = np.full(total_points, np.float32(0.8) + phase, dtype=np.float32)
    temperatures = np.full(
        total_points, np.float32(2.0) + phase, dtype=np.float32
    )
    smokes = np.full(total_points, np.float32(0.05) + phase, dtype=np.float32)
    return fuels, temperatures, smokes


def _convert_point_frame(source, emitters):
    fuels, temperatures, smokes = source
    converted = []
    start = 0
    for emitter in emitters:
        stop = start + emitter["point_count"]
        converted.append(
            {
                "fuels": Vt.FloatArray.FromNumpy(fuels[start:stop]),
                "temperatures": Vt.FloatArray.FromNumpy(temperatures[start:stop]),
                "smokes": Vt.FloatArray.FromNumpy(smokes[start:stop]),
            }
        )
        start = stop
    return tuple(converted)


def _publish_point_frame(emitters, converted, revision):
    for emitter, values in zip(emitters, converted):
        for name in ("fuels", "temperatures", "smokes"):
            if not emitter[name].Set(values[name]):
                raise RuntimeError(f"Point {name} Set failed")
    for emitter in emitters:
        if not emitter["revision"].Set(revision):
            raise RuntimeError("Point revision Set failed")


def _publish_sphere_frame(emitter, revision):
    phase = (revision % 20) * 0.0005
    values = (
        ("fuel", 0.8 + phase),
        ("temperature", 2.0 + phase),
        ("smoke", 0.05 + phase),
        ("couple_fuel", 2.0),
        ("couple_temperature", 10.0),
        ("couple_smoke", 1.0),
    )
    for name, value in values:
        if not emitter[name].Set(value):
            raise RuntimeError(f"Sphere {name} Set failed")
    if not emitter["revision"].Set(revision):
        raise RuntimeError("Sphere revision Set failed")


def _change_block_publish(callback):
    block = Sdf.ChangeBlock()
    block.__enter__()
    set_started = time.perf_counter_ns()
    try:
        callback()
    except BaseException:
        block.__exit__(*sys.exc_info())
        raise
    set_ms = (time.perf_counter_ns() - set_started) / 1_000_000.0
    exit_started = time.perf_counter_ns()
    block.__exit__(None, None, None)
    exit_ms = (time.perf_counter_ns() - exit_started) / 1_000_000.0
    return set_ms, exit_ms


def _readback_summary(flow_interface):
    channel_names = (
        "temperature",
        "fuel",
        "burn",
        "smoke",
        "velocity",
        "divergence",
    )
    started = time.perf_counter_ns()
    raw = flow_interface.get_latest_nanovdb_readback()
    query_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    channels = {}
    for index, name in enumerate(channel_names):
        value = raw[index] if index < len(raw) else []
        count = int(getattr(value, "size", len(value)))
        try:
            payload = value.tobytes()
        except AttributeError:
            try:
                payload = bytes(value)
            except (TypeError, ValueError):
                payload = b""
        channels[name] = {
            "word_count": count,
            "byte_count": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        }
    return {"query_ms": query_ms, "channels": channels}


async def _run(arguments):
    output_path = arguments.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    flow_interface = None
    listener = None
    try:
        for _ in range(5):
            await app.next_update_async()
        total_points = arguments.log_count * SURFACE_POINTS_PER_LOG
        position_source_started = time.perf_counter_ns()
        per_log_points, all_points = _build_point_sources(arguments.log_count)
        position_source_ms = (
            time.perf_counter_ns() - position_source_started
        ) / 1_000_000.0
        if arguments.layout == "sphere":
            await context.new_stage_async()
            stage = context.get_stage()
            populate_flow_scene(stage)
            emitters = _sphere_handles(stage)
            scene_source = "campfire Phase 1 FlowEmitterSphere scene"
        else:
            flow_extension_path = Path(omni.flowusd.__file__).resolve().parents[2]
            point_preset = (
                flow_extension_path / "data" / "presets" / "PointCloud" / "Native.usda"
            )
            if not point_preset.is_file():
                raise RuntimeError(f"Bundled PointCloud preset missing: {point_preset}")
            point_scene = output_path.with_suffix(".scene.usda")
            point_scene.unlink(missing_ok=True)
            offline_stage = Usd.Stage.CreateNew(str(point_scene))
            offline_stage.GetRootLayer().subLayerPaths = [point_preset.as_posix()]
            offline_root_path = _configure_point_cloud_stage(offline_stage)
            _define_point_emitters(
                offline_stage,
                offline_root_path,
                arguments.layout,
                per_log_points,
                all_points,
            )
            offline_stage.GetRootLayer().Save()
            offline_stage = None
            await context.open_stage_async(str(point_scene))
            stage = context.get_stage()
            point_root_path = _configure_point_cloud_stage(stage)
            emitters = _define_point_emitters(
                stage,
                point_root_path,
                arguments.layout,
                per_log_points,
                all_points,
            )
            scene_source = str(point_scene)

        flow_interface = _flowusd.acquire_flowusd_interface()
        public_interface_methods = sorted(
            name for name in dir(flow_interface) if not name.startswith("_")
        )
        notice_count = 0
        publication_notice_count = 0
        notice_callback_times_ms = []
        publication_notice_callback_times_ms = []
        notice_revisions_consistent = True
        active_revision = 0
        emitter_paths = tuple(str(emitter["prim"].GetPath()) for emitter in emitters)

        def observe_notice(notice, _sender):
            nonlocal notice_count, publication_notice_count
            nonlocal notice_revisions_consistent
            started = time.perf_counter_ns()
            changed_paths = tuple(notice.GetChangedInfoOnlyPaths())
            resynced_paths = tuple(notice.GetResyncedPaths())
            relevant = any(
                str(path).startswith(emitter_path)
                for path in changed_paths + resynced_paths
                for emitter_path in emitter_paths
            )
            if relevant:
                revisions = tuple(
                    int(emitter["revision"].Get()) for emitter in emitters
                )
                notice_revisions_consistent = notice_revisions_consistent and (
                    len(set(revisions)) == 1 and revisions[0] == active_revision
                )
                publication_notice_count += 1
            notice_count += 1
            callback_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            notice_callback_times_ms.append(callback_ms)
            if relevant:
                publication_notice_callback_times_ms.append(callback_ms)

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe_notice, stage)
        source_times_ms = []
        boundary_times_ms = []
        set_times_ms = []
        block_exit_times_ms = []
        update_times_ms = []
        active_block_query_times_ms = []
        active_blocks = []
        process = psutil.Process()
        rss_baseline = int(process.memory_info().rss)
        rss_peak = rss_baseline
        total_frames = arguments.warmup + arguments.frames
        final_source = None

        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.play()
        for offset in range(total_frames):
            active_revision = offset + 1
            if arguments.layout == "sphere":
                source_started = time.perf_counter_ns()
                final_source = {
                    "fuel": 0.8 + (active_revision % 20) * 0.0005,
                    "temperature": 2.0 + (active_revision % 20) * 0.0005,
                    "smoke": 0.05 + (active_revision % 20) * 0.0005,
                }
                source_times_ms.append(
                    (time.perf_counter_ns() - source_started) / 1_000_000.0
                )
                boundary_times_ms.append(0.0)
                set_ms, exit_ms = _change_block_publish(
                    lambda: _publish_sphere_frame(emitters[0], active_revision)
                )
            else:
                source_started = time.perf_counter_ns()
                final_source = _point_frame_source(total_points, active_revision)
                source_times_ms.append(
                    (time.perf_counter_ns() - source_started) / 1_000_000.0
                )
                boundary_started = time.perf_counter_ns()
                converted = _convert_point_frame(final_source, emitters)
                boundary_times_ms.append(
                    (time.perf_counter_ns() - boundary_started) / 1_000_000.0
                )
                set_ms, exit_ms = _change_block_publish(
                    lambda: _publish_point_frame(
                        emitters, converted, active_revision
                    )
                )
            set_times_ms.append(set_ms)
            block_exit_times_ms.append(exit_ms)
            update_started = time.perf_counter_ns()
            await app.next_update_async()
            update_times_ms.append(
                (time.perf_counter_ns() - update_started) / 1_000_000.0
            )
            query_started = time.perf_counter_ns()
            active_blocks.append(int(flow_interface.get_active_block_count()))
            active_block_query_times_ms.append(
                (time.perf_counter_ns() - query_started) / 1_000_000.0
            )
            rss_peak = max(rss_peak, int(process.memory_info().rss))

        timeline.pause()
        readback = _readback_summary(flow_interface)
        final_revisions = tuple(
            int(emitter["revision"].Get()) for emitter in emitters
        )
        if arguments.layout == "sphere":
            output_equivalence = {
                "fuel_close": math.isclose(
                    float(emitters[0]["fuel"].Get()), final_source["fuel"], rel_tol=1e-6
                ),
                "temperature_close": math.isclose(
                    float(emitters[0]["temperature"].Get()),
                    final_source["temperature"],
                    rel_tol=1e-6,
                ),
                "smoke_close": math.isclose(
                    float(emitters[0]["smoke"].Get()), final_source["smoke"], rel_tol=1e-6
                ),
            }
            attribute_updates = 7
            logical_bytes = 6 * 4 + 8
        else:
            published_counts = {
                name: sum(len(emitter[name].Get()) for emitter in emitters)
                for name in ("fuels", "temperatures", "smokes")
            }
            published_sums = {
                name: sum(
                    float(value)
                    for emitter in emitters
                    for value in emitter[name].Get()
                )
                for name in ("fuels", "temperatures", "smokes")
            }
            source_names = ("fuels", "temperatures", "smokes")
            output_equivalence = {
                "point_counts": published_counts,
                "point_counts_exact": all(
                    published_counts[name] == total_points for name in source_names
                ),
                "channel_sums_close": all(
                    math.isclose(
                        published_sums[name],
                        float(final_source[index].sum()),
                        rel_tol=1e-6,
                    )
                    for index, name in enumerate(source_names)
                ),
            }
            attribute_updates = len(emitters) * 4
            logical_bytes = total_points * 12 + len(emitters) * 8

        report = {
            "schema_version": 1,
            "phase": "phase6bp",
            "status": "ok",
            "default_off": True,
            "production_code_changed": False,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "configuration": {
                "layout": arguments.layout,
                "flow_version": FLOW_VERSION,
                "log_count": arguments.log_count,
                "cells_per_log": CELLS_PER_LOG,
                "surface_points_per_log": SURFACE_POINTS_PER_LOG,
                "point_count": total_points if arguments.layout != "sphere" else 0,
                "emitter_count": len(emitters),
                "measured_frames": arguments.frames,
                "warmup_frames": arguments.warmup,
                "positions_static_after_seed": arguments.layout != "sphere",
                "scene_source": scene_source,
                "attribute_update_count_per_frame": attribute_updates,
                "logical_transfer_bytes_per_frame": logical_bytes,
            },
            "position_seed": {
                "source_generation_ms": position_source_ms,
                "python_cpp_boundary_ms": sum(
                    emitter.get("position_boundary_ms", 0.0) for emitter in emitters
                ),
                "usd_set_ms": sum(
                    emitter.get("position_set_ms", 0.0) for emitter in emitters
                ),
            },
            "timing": {
                "source_generation": _summary(source_times_ms, arguments.warmup),
                "python_cpp_boundary": _summary(
                    boundary_times_ms, arguments.warmup
                ),
                "usd_attribute_set": _summary(set_times_ms, arguments.warmup),
                "change_block_exit_all_consumers": _summary(
                    block_exit_times_ms, arguments.warmup
                ),
                "objects_changed_probe_callback": _summary(
                    notice_callback_times_ms
                ),
                "publication_notice_probe_callback": _summary(
                    publication_notice_callback_times_ms
                ),
                "kit_flow_render_update": _summary(
                    update_times_ms, arguments.warmup
                ),
                "active_block_query": _summary(
                    active_block_query_times_ms, arguments.warmup
                ),
            },
            "notice": {
                "objects_changed_count": notice_count,
                "objects_changed_per_frame": notice_count / total_frames,
                "publication_objects_changed_count": publication_notice_count,
                "publication_objects_changed_per_frame": (
                    publication_notice_count / total_frames
                ),
                "revision_consistent_for_every_notice": (
                    notice_revisions_consistent
                ),
                "scope": (
                    "ChangeBlock exit includes all synchronous notice consumers; "
                    "the probe callback time isolates only this script's listener."
                ),
            },
            "flow": {
                "point_cloud_preset_core_simulation_enabled": (
                    None if arguments.layout == "sphere" else False
                ),
                "point_cloud_preset_stream_once": (
                    None if arguments.layout == "sphere" else True
                ),
                "active_blocks_final": active_blocks[-1],
                "active_blocks_peak": max(active_blocks),
                "active_blocks_mean_measured": statistics.fmean(
                    active_blocks[arguments.warmup:]
                ),
                "nanovdb_readback": readback,
                "public_interface_methods": public_interface_methods,
                "ingestion_time_ms": None,
                "emitter_rasterization_time_ms": None,
                "solver_render_separate_time_ms": None,
                "unseparated_scope": (
                    "Flow USD ingestion/rasterization may execute during synchronous "
                    "notice delivery and/or the next Kit update; the fixed public "
                    "interface exposes no separate timer."
                ),
            },
            "memory": {
                "process_rss_baseline_bytes": rss_baseline,
                "process_rss_peak_bytes": rss_peak,
                "process_rss_peak_delta_bytes": rss_peak - rss_baseline,
                "gpu_memory_bytes": None,
                "gpu_memory_reason": "No per-emitter public Flow GPU allocation query verified",
            },
            "equivalence": {
                "usd_channels": output_equivalence,
                "consumer_revisions": list(final_revisions),
                "consumer_revision_consistent": (
                    len(set(final_revisions)) == 1
                    and final_revisions[0] == total_frames
                ),
                "flow_field_semantic_equivalence": None,
                "flow_field_reason": (
                    "Raw NanoVDB word hashes are recorded, but semantic voxel values "
                    "are not decoded by this spike."
                ),
            },
        }
        output_path.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        carb.log_info(
            f"[phase6bp] {arguments.layout} logs={arguments.log_count} "
            f"blocks={max(active_blocks)} report={output_path}"
        )
        app.post_uncancellable_quit(0)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        output_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "phase": "phase6bp",
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        carb.log_error(f"[phase6bp] failed: {type(error).__name__}: {error}")
        app.post_uncancellable_quit(1)
    finally:
        if listener is not None:
            listener.Revoke()
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)


arguments = _parse_arguments()
asyncio.ensure_future(_run(arguments))
