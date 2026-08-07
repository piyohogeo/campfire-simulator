"""Measure the fixed Flow build's bundled point-to-NanoVDB boundary.

This default-off Kit spike calls the same ``voxelize_points_and_sync_v2``
binding exercised by omni.flowusd's bundled test.  It does not alter the
campfire production extension, scene schema, or defaults.
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
import psutil
from omni.flowusd import _flowusd


SURFACE_POINTS_PER_LOG = 360
CELLS_PER_LOG = 1152
GRID_SHAPE = (24, 12, 4)


def _arguments():
    settings = carb.settings.get_settings()
    arguments = {
        "log_count": settings.get_as_int("/phase6bq/logCount"),
        "frames": settings.get_as_int("/phase6bq/frames"),
        "warmup": settings.get_as_int("/phase6bq/warmup"),
        "cell_size": settings.get_as_float("/phase6bq/cellSize"),
        "max_blocks": settings.get_as_int("/phase6bq/maxBlocks"),
        "output": Path(settings.get_as_string("/phase6bq/output")),
    }
    if arguments["log_count"] not in (1, 5, 10, 20):
        raise ValueError("log count must be 1, 5, 10, or 20")
    if arguments["frames"] < 20 or arguments["warmup"] < 1:
        raise ValueError("Use at least 20 measured frames and one warmup frame")
    if arguments["cell_size"] <= 0.0 or arguments["max_blocks"] < 1:
        raise ValueError("cell size and max blocks must be positive")
    if not str(arguments["output"]):
        raise ValueError("output path is required")
    return arguments


def _summary(values, warmup):
    measured = list(values[warmup:])
    ordered = sorted(measured)
    return {
        "sample_count": len(measured),
        "warmup_samples_excluded": warmup,
        "mean_ms": statistics.fmean(measured),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(measured),
    }


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
    return points


def _point_source(log_count):
    points = []
    for log_index in range(log_count):
        points.extend(_surface_points_for_log(log_index))
    return np.asarray(points, dtype=np.float32)


def _buffer_summary(buffers):
    result = []
    for index, value in enumerate(buffers):
        array = np.asarray(value)
        payload = array.tobytes()
        result.append(
            {
                "channel_index": index,
                "element_count": int(array.size),
                "byte_count": int(array.nbytes),
                "sha256": hashlib.sha256(payload).hexdigest() if payload else None,
            }
        )
    return result


async def _run(arguments):
    output_path = arguments["output"].resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    app = omni.kit.app.get_app()
    flow_interface = None
    persistent_context_initialized = False
    try:
        for _ in range(5):
            await app.next_update_async()
        source_started = time.perf_counter_ns()
        source_points = _point_source(arguments["log_count"])
        position_source_ms = (time.perf_counter_ns() - source_started) / 1_000_000.0
        point_count = len(source_points)
        identity = np.asarray((
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ), dtype=np.float64)
        flow_interface = _flowusd.acquire_flowusd_interface()
        flow_interface.init_persistent_voxelize_context()
        persistent_context_initialized = True
        source_times_ms = []
        contiguous_copy_times_ms = []
        voxelize_sync_times_ms = []
        output_bytes = []
        process = psutil.Process()
        rss_baseline = int(process.memory_info().rss)
        rss_peak = rss_baseline
        buffers = None
        total_frames = arguments["warmup"] + arguments["frames"]
        for frame in range(total_frames):
            generation_started = time.perf_counter_ns()
            phase = np.float32((frame % 20) * 0.0005)
            colors = np.empty((point_count, 3), dtype=np.float32)
            colors[:, 0] = np.float32(2.0) + phase
            colors[:, 1] = np.float32(0.8) + phase
            colors[:, 2] = np.float32(0.2) + phase
            source_times_ms.append(
                (time.perf_counter_ns() - generation_started) / 1_000_000.0
            )
            copy_started = time.perf_counter_ns()
            points_argument = np.ascontiguousarray(source_points, dtype=np.float32)
            colors_argument = np.ascontiguousarray(colors, dtype=np.float32)
            contiguous_copy_times_ms.append(
                (time.perf_counter_ns() - copy_started) / 1_000_000.0
            )
            voxelize_started = time.perf_counter_ns()
            buffers = flow_interface.voxelize_points_and_sync_v2(
                points_argument,
                colors_argument,
                identity,
                identity,
                arguments["cell_size"],
                arguments["max_blocks"],
            )
            voxelize_sync_times_ms.append(
                (time.perf_counter_ns() - voxelize_started) / 1_000_000.0
            )
            output_bytes.append(sum(int(np.asarray(value).nbytes) for value in buffers))
            rss_peak = max(rss_peak, int(process.memory_info().rss))

        final_buffers = _buffer_summary(buffers)
        report = {
            "schema_version": 1,
            "phase": "phase6bq",
            "status": "ok",
            "default_off": True,
            "production_code_changed": False,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "configuration": {
                "log_count": arguments["log_count"],
                "cells_per_log": CELLS_PER_LOG,
                "surface_points_per_log": SURFACE_POINTS_PER_LOG,
                "point_count": point_count,
                "measured_frames": arguments["frames"],
                "warmup_frames": arguments["warmup"],
                "cell_size_m": arguments["cell_size"],
                "max_blocks": arguments["max_blocks"],
                "input_bytes_per_frame": point_count * 2 * 3 * 4,
                "usd_attribute_update_count_per_frame": 0,
                "objects_changed_count": 0,
            },
            "boundary": {
                "name": "omni.flowusd IFlowUsd.voxelize_points_and_sync_v2",
                "persistent_context_reused": True,
                "availability_evidence": (
                    "Called by the fixed extension's bundled test_commands.py and "
                    "FlowVoxelizePointsAndSync command"
                ),
                "scope": (
                    "The binding call combines Python/C++ argument conversion, GPU "
                    "point voxelization, NanoVDB generation, transfer, and sync. The "
                    "fixed public interface exposes no timers below this boundary."
                ),
            },
            "timing": {
                "position_source_generation_once_ms": position_source_ms,
                "color_source_generation": _summary(
                    source_times_ms, arguments["warmup"]
                ),
                "numpy_contiguous_preparation": _summary(
                    contiguous_copy_times_ms, arguments["warmup"]
                ),
                "python_cpp_gpu_voxelize_nanovdb_sync": _summary(
                    voxelize_sync_times_ms, arguments["warmup"]
                ),
            },
            "output": {
                "buffer_count": len(buffers),
                "bytes_mean_measured": statistics.fmean(
                    output_bytes[arguments["warmup"]:]
                ),
                "bytes_maximum": max(output_bytes[arguments["warmup"]:]),
                "final_buffers": final_buffers,
            },
            "memory": {
                "process_rss_baseline_bytes": rss_baseline,
                "process_rss_peak_bytes": rss_peak,
                "process_rss_peak_delta_bytes": rss_peak - rss_baseline,
                "gpu_memory_bytes": None,
                "gpu_memory_reason": (
                    "No per-call public Flow GPU allocation query is exposed"
                ),
            },
            "limitations": {
                "usd_publish_time_ms": None,
                "flow_emitter_ingestion_time_ms": None,
                "flow_solver_render_time_ms": None,
                "consumer_revision": None,
                "reason": (
                    "This spike isolates the native point-to-NanoVDB producer; it "
                    "does not connect the buffers to a FlowEmitterNanoVdb consumer."
                ),
            },
        }
        output_path.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        carb.log_info(
            f"[phase6bq] points={point_count} "
            f"p95={report['timing']['python_cpp_gpu_voxelize_nanovdb_sync']['p95_ms']:.4f} ms "
            f"report={output_path}"
        )
        app.post_uncancellable_quit(0)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        output_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "phase": "phase6bq",
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        carb.log_error(f"[phase6bq] failed: {type(error).__name__}: {error}")
        app.post_uncancellable_quit(1)
    finally:
        if flow_interface is not None:
            if persistent_context_initialized:
                flow_interface.release_persistent_voxelize_context()
            _flowusd.release_flowusd_interface(flow_interface)


asyncio.ensure_future(_run(_arguments()))
