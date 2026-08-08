"""Exercise the isolated Phase 6DJ rigid-frame surface layout ABI."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


AXIAL_CELLS = 24
CIRCUMFERENTIAL_CELLS = 12
RADIAL_CELLS = 4
CELLS_PER_LOG = AXIAL_CELLS * CIRCUMFERENTIAL_CELLS * RADIAL_CELLS
SURFACE_POINTS_PER_LOG = 360
RADIUS_M = 0.105
LENGTH_M = 0.72


def _configure_legacy(library):
    dp = ctypes.POINTER(ctypes.c_double)
    fp = ctypes.POINTER(ctypes.c_float)
    up = ctypes.POINTER(ctypes.c_uint32)
    sizep = ctypes.POINTER(ctypes.c_size_t)
    library.campfire_native_surface_layout.argtypes = (
        [dp]
        + [ctypes.c_size_t] * 5
        + [ctypes.c_double] * 2
        + [dp, up, fp, ctypes.c_size_t, sizep]
    )
    library.campfire_native_surface_layout.restype = ctypes.c_int32


def _configure_frame(library):
    dp = ctypes.POINTER(ctypes.c_double)
    fp = ctypes.POINTER(ctypes.c_float)
    sizep = ctypes.POINTER(ctypes.c_size_t)
    library.campfire_surface_frame_spike_abi_version.argtypes = ()
    library.campfire_surface_frame_spike_abi_version.restype = ctypes.c_int32
    library.campfire_surface_frame_spike_tolerance.argtypes = ()
    library.campfire_surface_frame_spike_tolerance.restype = ctypes.c_double
    library.campfire_surface_layout_frames.argtypes = (
        [dp]
        + [ctypes.c_size_t] * 5
        + [ctypes.c_double] * 2
        + [dp, dp, fp, ctypes.c_size_t, sizep]
    )
    library.campfire_surface_layout_frames.restype = ctypes.c_int32


def _surface_exposure(log_count: int) -> np.ndarray:
    values = np.zeros(log_count * CELLS_PER_LOG, dtype=np.float64)
    for log_index in range(log_count):
        for axial in range(AXIAL_CELLS):
            for circumferential in range(CIRCUMFERENTIAL_CELLS):
                for radial in range(RADIAL_CELLS):
                    local = (
                        (axial * CIRCUMFERENTIAL_CELLS + circumferential)
                        * RADIAL_CELLS
                        + radial
                    )
                    if axial in (0, AXIAL_CELLS - 1) or radial == RADIAL_CELLS - 1:
                        values[log_index * CELLS_PER_LOG + local] = 1.0
    expected = log_count * SURFACE_POINTS_PER_LOG
    if int(np.count_nonzero(values)) != expected:
        raise AssertionError("Surface topology did not produce the expected point count")
    return values


def _call_legacy(library, exposure, origins, axes, output=None, capacity=None):
    point_count = exposure.size // CELLS_PER_LOG * SURFACE_POINTS_PER_LOG
    if output is None:
        output = np.empty((point_count, 3), dtype=np.float32)
    if capacity is None:
        capacity = len(output)
    count = ctypes.c_size_t(987654)
    result = library.campfire_native_surface_layout(
        exposure.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        len(origins),
        CELLS_PER_LOG,
        AXIAL_CELLS,
        CIRCUMFERENTIAL_CELLS,
        RADIAL_CELLS,
        RADIUS_M,
        LENGTH_M,
        origins.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        axes.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
        output.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        capacity,
        ctypes.byref(count),
    )
    return result, count.value, output


def _call_frame(library, exposure, origins, frames, output=None, capacity=None):
    point_count = exposure.size // CELLS_PER_LOG * SURFACE_POINTS_PER_LOG
    if output is None:
        output = np.empty((point_count, 3), dtype=np.float32)
    if capacity is None:
        capacity = len(output)
    count = ctypes.c_size_t(987654)
    result = library.campfire_surface_layout_frames(
        exposure.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        len(origins),
        CELLS_PER_LOG,
        AXIAL_CELLS,
        CIRCUMFERENTIAL_CELLS,
        RADIAL_CELLS,
        RADIUS_M,
        LENGTH_M,
        origins.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        frames.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        output.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        capacity,
        ctypes.byref(count),
    )
    return result, count.value, output


def _reference(exposure, origins, frames):
    values = []
    axial_step = LENGTH_M / AXIAL_CELLS
    radial_step = RADIUS_M / RADIAL_CELLS
    for log_index in range(len(origins)):
        for local in range(CELLS_PER_LOG):
            if exposure[log_index * CELLS_PER_LOG + local] <= 0.0:
                continue
            radial = local % RADIAL_CELLS
            circumferential = (local // RADIAL_CELLS) % CIRCUMFERENTIAL_CELLS
            axial = local // (RADIAL_CELLS * CIRCUMFERENTIAL_CELLS)
            axial_position = -0.5 * LENGTH_M + (axial + 0.5) * axial_step
            angle = 2.0 * math.pi * (circumferential + 0.5) / CIRCUMFERENTIAL_CELLS
            radial_position = (radial + 0.5) * radial_step
            local_position = np.asarray(
                [
                    axial_position,
                    radial_position * math.cos(angle),
                    radial_position * math.sin(angle),
                ],
                dtype=np.float64,
            )
            values.append(origins[log_index] + frames[log_index].T @ local_position)
    return np.asarray(values, dtype=np.float32)


def _rotation_xyz(x_degrees, y_degrees, z_degrees):
    x, y, z = (math.radians(value) for value in (x_degrees, y_degrees, z_degrees))
    rx = np.asarray(
        [[1.0, 0.0, 0.0], [0.0, math.cos(x), -math.sin(x)], [0.0, math.sin(x), math.cos(x)]]
    )
    ry = np.asarray(
        [[math.cos(y), 0.0, math.sin(y)], [0.0, 1.0, 0.0], [-math.sin(y), 0.0, math.cos(y)]]
    )
    rz = np.asarray(
        [[math.cos(z), -math.sin(z), 0.0], [math.sin(z), math.cos(z), 0.0], [0.0, 0.0, 1.0]]
    )
    return (rz @ ry @ rx).T


def _sorted_rows(values):
    order = np.lexsort((values[:, 2], values[:, 1], values[:, 0]))
    return values[order]


def _timing(callable_, iterations=300, warmup=30):
    values = []
    for index in range(iterations + warmup):
        started = time.perf_counter_ns()
        result, count, _ = callable_()
        elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
        if result != 0 or count != 2 * SURFACE_POINTS_PER_LOG:
            raise RuntimeError(f"Timed layout call failed: code={result}, count={count}")
        if index >= warmup:
            values.append(elapsed)
    ordered = sorted(values)
    return {
        "samples": len(values),
        "mean_ms": statistics.fmean(values),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dll", required=True, type=Path)
    parser.add_argument("--frame-dll", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--production-source-unchanged", required=True, choices=("true", "false"))
    arguments = parser.parse_args()

    legacy = ctypes.CDLL(str(arguments.legacy_dll.resolve()))
    frame = ctypes.CDLL(str(arguments.frame_dll.resolve()))
    _configure_legacy(legacy)
    _configure_frame(frame)
    if frame.campfire_surface_frame_spike_abi_version() != 1:
        raise RuntimeError("Unexpected Phase 6DI frame spike ABI")

    exposure = _surface_exposure(2)
    origins = np.asarray([[0.0, -0.26, 0.16], [0.0, 0.26, 0.16]], dtype=np.float64)
    axes = np.asarray([0, 1], dtype=np.uint32)
    cardinal_frames = np.asarray(
        [
            np.eye(3, dtype=np.float64),
            [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        ],
        dtype=np.float64,
    )
    legacy_code, legacy_count, legacy_positions = _call_legacy(
        legacy, exposure, origins, axes
    )
    frame_code, frame_count, frame_positions = _call_frame(
        frame, exposure, origins, cardinal_frames
    )
    first = slice(0, SURFACE_POINTS_PER_LOG)
    second = slice(SURFACE_POINTS_PER_LOG, 2 * SURFACE_POINTS_PER_LOG)
    cardinal_x_exact = legacy_positions[first].tobytes() == frame_positions[first].tobytes()
    cardinal_y_same_index_error = float(
        np.max(np.abs(legacy_positions[second] - frame_positions[second]))
    )
    cardinal_y_set_error = float(
        np.max(
            np.abs(
                _sorted_rows(legacy_positions[second])
                - _sorted_rows(frame_positions[second])
            )
        )
    )

    rotation_frames = np.asarray(
        [_rotation_xyz(0.0, 0.0, 45.0), _rotation_xyz(22.0, -18.0, 31.0)],
        dtype=np.float64,
    )
    rotation_code, rotation_count, rotation_positions = _call_frame(
        frame, exposure, origins, rotation_frames
    )
    rotation_reference = _reference(exposure, origins, rotation_frames)
    rotation_45_error = float(
        np.max(np.abs(rotation_positions[first] - rotation_reference[first]))
    )
    rotation_3d_error = float(
        np.max(np.abs(rotation_positions[second] - rotation_reference[second]))
    )

    invalid_results = {}
    invalid_frames = {
        "scale": np.asarray(cardinal_frames),
        "shear": np.asarray(cardinal_frames),
        "reflection": np.asarray(cardinal_frames),
        "non_finite": np.asarray(cardinal_frames),
    }
    invalid_frames["scale"] = invalid_frames["scale"].copy()
    invalid_frames["scale"][0, 0, 0] = 1.01
    invalid_frames["shear"] = invalid_frames["shear"].copy()
    invalid_frames["shear"][0, 1] = (0.1, 1.0, 0.0)
    invalid_frames["reflection"] = invalid_frames["reflection"].copy()
    invalid_frames["reflection"][0, 2] = (0.0, 0.0, -1.0)
    invalid_frames["non_finite"] = invalid_frames["non_finite"].copy()
    invalid_frames["non_finite"][0, 0, 0] = math.nan
    for name, candidate in invalid_frames.items():
        output = np.full((720, 3), -12345.5, dtype=np.float32)
        before = output.tobytes()
        code, count, _ = _call_frame(frame, exposure, origins, candidate, output)
        invalid_results[name] = {
            "return_code": code,
            "count_unchanged": count == 987654,
            "output_unchanged": output.tobytes() == before,
        }

    capacity_output = np.full((720, 3), -12345.5, dtype=np.float32)
    capacity_before = capacity_output.tobytes()
    capacity_code, capacity_count, _ = _call_frame(
        frame,
        exposure,
        origins,
        cardinal_frames,
        capacity_output,
        capacity=719,
    )
    capacity_result = {
        "return_code": capacity_code,
        "count_unchanged": capacity_count == 987654,
        "output_unchanged": capacity_output.tobytes() == capacity_before,
    }

    legacy_timing = _timing(lambda: _call_legacy(legacy, exposure, origins, axes))
    frame_timing = _timing(
        lambda: _call_frame(frame, exposure, origins, cardinal_frames)
    )
    tolerance = 1.0e-6
    gates = {
        "legacy_layout_succeeded": legacy_code == 0 and legacy_count == 720,
        "frame_layout_succeeded": frame_code == 0 and frame_count == 720,
        "cardinal_x_byte_exact": cardinal_x_exact,
        "legacy_y_is_not_same_index_rigid_rotation": cardinal_y_same_index_error > 0.01,
        "legacy_y_point_set_equivalent": cardinal_y_set_error <= tolerance,
        "rotation_45_matches_reference": rotation_code == 0
        and rotation_count == 720
        and rotation_45_error <= tolerance,
        "rotation_3d_matches_reference": rotation_3d_error <= tolerance,
        "invalid_frames_fail_closed": all(
            item["return_code"] == 3
            and item["count_unchanged"]
            and item["output_unchanged"]
            for item in invalid_results.values()
        ),
        "capacity_failure_is_atomic": capacity_code == 2
        and capacity_result["count_unchanged"]
        and capacity_result["output_unchanged"],
        "production_native_source_unchanged": arguments.production_source_unchanged
        == "true",
    }
    report = {
        "schema_version": 1,
        "phase": "phase6dj",
        "status": "ok" if all(gates.values()) else "failed",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "measurement": {
            "log_count": 2,
            "cells_per_log": CELLS_PER_LOG,
            "surface_points_per_log": SURFACE_POINTS_PER_LOG,
            "point_count": 720,
            "frame_tolerance": frame.campfire_surface_frame_spike_tolerance(),
        },
        "runtime": {
            "python": sys.version,
            "python_executable": sys.executable,
            "numpy": np.__version__,
            "kit_runtime_required": False,
        },
        "gates": {
            "passed": sum(bool(value) for value in gates.values()),
            "total": len(gates),
            "checks": gates,
        },
        "equivalence": {
            "cardinal_x_byte_exact": cardinal_x_exact,
            "cardinal_y_same_index_max_error_m": cardinal_y_same_index_error,
            "cardinal_y_sorted_point_set_max_error_m": cardinal_y_set_error,
            "rotation_45_reference_max_error_m": rotation_45_error,
            "rotation_3d_reference_max_error_m": rotation_3d_error,
        },
        "failure_atomicity": {
            "invalid_frames": invalid_results,
            "insufficient_capacity": capacity_result,
        },
        "timing": {
            "legacy_cardinal_720_points": legacy_timing,
            "rigid_frame_720_points": frame_timing,
        },
        "artifacts": {
            "legacy_dll_sha256": hashlib.sha256(arguments.legacy_dll.read_bytes()).hexdigest(),
            "frame_dll_sha256": hashlib.sha256(arguments.frame_dll.read_bytes()).hexdigest(),
        },
        "decision": {
            "frame_kernel_correctness_qualified": all(gates.values()),
            "production_integration_qualified": False,
            "legacy_y_mapping_is_reflection": True,
            "channel_alignment_migration_required": True,
            "next": "Validate per-cell channel alignment against real USD transforms before integrating frame metadata into Resident payloads.",
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["gates"], indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
