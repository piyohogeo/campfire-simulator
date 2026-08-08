"""Validate USD transform frames against stable Resident surface-cell order."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import math
import struct
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
from pxr import Gf, Usd, UsdGeom

import campfire.app
from campfire.app.resident_point_scene import resident_point_layout_for_logs
from campfire.app.wood import LogSpec, create_log


AXIAL_CELLS = 24
CIRCUMFERENTIAL_CELLS = 12
RADIAL_CELLS = 4
CELLS_PER_LOG = AXIAL_CELLS * CIRCUMFERENTIAL_CELLS * RADIAL_CELLS
SURFACE_POINTS_PER_LOG = 360
RADIUS_M = 0.105
LENGTH_M = 0.72
POINT_TOLERANCE_M = 1.0e-6


def _write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _configure_libraries(legacy, frame) -> None:
    dp = ctypes.POINTER(ctypes.c_double)
    fp = ctypes.POINTER(ctypes.c_float)
    up = ctypes.POINTER(ctypes.c_uint32)
    sizep = ctypes.POINTER(ctypes.c_size_t)
    legacy.campfire_native_surface_layout.argtypes = (
        [dp]
        + [ctypes.c_size_t] * 5
        + [ctypes.c_double] * 2
        + [dp, up, fp, ctypes.c_size_t, sizep]
    )
    legacy.campfire_native_surface_layout.restype = ctypes.c_int32
    frame.campfire_surface_layout_frames.argtypes = (
        [dp]
        + [ctypes.c_size_t] * 5
        + [ctypes.c_double] * 2
        + [dp, dp, fp, ctypes.c_size_t, sizep]
    )
    frame.campfire_surface_layout_frames.restype = ctypes.c_int32


def _f32(value: float) -> float:
    return ctypes.c_float(float(value)).value


def _dot(first, second) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _determinant(frame) -> float:
    axis_x, axis_y, axis_z = frame
    return (
        axis_x[0] * (axis_y[1] * axis_z[2] - axis_y[2] * axis_z[1])
        - axis_x[1] * (axis_y[0] * axis_z[2] - axis_y[2] * axis_z[0])
        + axis_x[2] * (axis_y[0] * axis_z[1] - axis_y[1] * axis_z[0])
    )


def _sample_transform(stage: Usd.Stage, log_id: str) -> dict:
    prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
    transform = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
        Usd.TimeCode.Default()
    )
    origin_value = transform.ExtractTranslation()
    axes = []
    norms = []
    for local_axis in (
        Gf.Vec3d(1.0, 0.0, 0.0),
        Gf.Vec3d(0.0, 1.0, 0.0),
        Gf.Vec3d(0.0, 0.0, 1.0),
    ):
        transformed = transform.TransformDir(local_axis)
        norm = float(transformed.GetLength())
        norms.append(norm)
        normalized = transformed / norm
        axes.append(tuple(float(normalized[index]) for index in range(3)))
    origin = tuple(float(origin_value[index]) for index in range(3))
    frame = tuple(axes)
    return {
        "transform": transform,
        "origin": origin,
        "frame": frame,
        "norms": tuple(norms),
        "dot_xy": _dot(frame[0], frame[1]),
        "dot_xz": _dot(frame[0], frame[2]),
        "dot_yz": _dot(frame[1], frame[2]),
        "determinant": _determinant(frame),
        "xform_op_order": [
            str(value)
            for value in prim.GetAttribute("xformOpOrder").Get()
        ],
    }


def _model(log_id: str, temperature_offset: float):
    model = campfire.app.create_cylindrical_wood_model(
        log_id=log_id,
        radius_m=RADIUS_M,
        length_m=LENGTH_M,
        moisture_ratio_dry_basis=0.12,
        initial_temperature_k=400.0,
        axial_cells=AXIAL_CELLS,
        circumferential_cells=CIRCUMFERENTIAL_CELLS,
        radial_cells=RADIAL_CELLS,
    )
    for local, cell in enumerate(model.cells):
        cell.temperature_k = temperature_offset + local * 0.01
    if sum(cell.surface_exposure > 0.0 for cell in model.cells) != SURFACE_POINTS_PER_LOG:
        raise RuntimeError("Production wood topology surface count changed")
    return model


def _local_position(local: int) -> Gf.Vec3d:
    radial = local % RADIAL_CELLS
    circumferential = (local // RADIAL_CELLS) % CIRCUMFERENTIAL_CELLS
    axial = local // (RADIAL_CELLS * CIRCUMFERENTIAL_CELLS)
    axial_position = (
        -0.5 * LENGTH_M
        + (axial + 0.5) * LENGTH_M / AXIAL_CELLS
    )
    angle = 2.0 * math.pi * (circumferential + 0.5) / CIRCUMFERENTIAL_CELLS
    radial_position = (radial + 0.5) * RADIUS_M / RADIAL_CELLS
    return Gf.Vec3d(
        axial_position,
        radial_position * math.cos(angle),
        radial_position * math.sin(angle),
    )


def _scenario_arrays(models, samples):
    exposure_values = []
    origins = []
    frames = []
    records = []
    for log_index, (model, sample) in enumerate(zip(models, samples)):
        origins.extend(sample["origin"])
        for axis in sample["frame"]:
            frames.extend(axis)
        fuel = 0.15 + log_index * 0.25
        smoke = 0.05 + log_index * 0.10
        for local, cell in enumerate(model.cells):
            exposure_values.append(float(cell.surface_exposure))
            if cell.surface_exposure <= 0.0:
                continue
            world = sample["transform"].Transform(_local_position(local))
            records.append(
                {
                    "stable_id": f"{model.spec.log_id}:{local}",
                    "log_index": log_index,
                    "local_index": local,
                    "point": tuple(_f32(world[index]) for index in range(3)),
                    "fuel": fuel,
                    "temperature": float(cell.temperature_k),
                    "smoke": smoke,
                }
            )
    return {
        "exposure": (ctypes.c_double * len(exposure_values))(*exposure_values),
        "origins": (ctypes.c_double * len(origins))(*origins),
        "frames": (ctypes.c_double * len(frames))(*frames),
        "records": records,
    }


def _call_frame(library, arrays, log_count: int):
    point_count = log_count * SURFACE_POINTS_PER_LOG
    output = (ctypes.c_float * (point_count * 3))()
    count = ctypes.c_size_t(0)
    code = library.campfire_surface_layout_frames(
        arrays["exposure"],
        log_count,
        CELLS_PER_LOG,
        AXIAL_CELLS,
        CIRCUMFERENTIAL_CELLS,
        RADIAL_CELLS,
        RADIUS_M,
        LENGTH_M,
        arrays["origins"],
        arrays["frames"],
        output,
        point_count,
        ctypes.byref(count),
    )
    positions = [
        tuple(float(output[index * 3 + component]) for component in range(3))
        for index in range(count.value)
    ]
    return code, count.value, positions


def _call_legacy(library, arrays, axes, log_count: int):
    point_count = log_count * SURFACE_POINTS_PER_LOG
    output = (ctypes.c_float * (point_count * 3))()
    count = ctypes.c_size_t(0)
    axis_values = (ctypes.c_uint32 * len(axes))(*axes)
    code = library.campfire_native_surface_layout(
        arrays["exposure"],
        log_count,
        CELLS_PER_LOG,
        AXIAL_CELLS,
        CIRCUMFERENTIAL_CELLS,
        RADIAL_CELLS,
        RADIUS_M,
        LENGTH_M,
        arrays["origins"],
        axis_values,
        output,
        point_count,
        ctypes.byref(count),
    )
    positions = [
        tuple(float(output[index * 3 + component]) for component in range(3))
        for index in range(count.value)
    ]
    return code, count.value, positions


def _maximum_point_error(positions, records) -> float:
    if len(positions) != len(records):
        return math.inf
    return max(
        abs(positions[index][component] - records[index]["point"][component])
        for index in range(len(records))
        for component in range(3)
    )


def _record_digest(records) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record["stable_id"].encode("ascii"))
        digest.update(struct.pack("<3d", record["fuel"], record["temperature"], record["smoke"]))
    return digest.hexdigest()


def _coordinate_channel_map(positions, records, offset, count):
    return {
        tuple(round(component, 6) for component in positions[index]): (
            records[index]["fuel"],
            records[index]["temperature"],
            records[index]["smoke"],
        )
        for index in range(offset, offset + count)
    }


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6dk/output")).resolve()
    legacy_path = Path(settings.get_as_string("/phase6dk/legacyDll")).resolve()
    frame_path = Path(settings.get_as_string("/phase6dk/frameDll")).resolve()
    app = omni.kit.app.get_app()
    report = {
        "schema_version": 1,
        "phase": "phase6dk",
        "status": "running",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await app.next_update_async()
        legacy = ctypes.CDLL(str(legacy_path))
        frame = ctypes.CDLL(str(frame_path))
        _configure_libraries(legacy, frame)

        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/World")
        log_specs = (
            LogSpec("frame_x", (-0.20, -0.26, 0.16), 0.0, RADIUS_M, LENGTH_M),
            LogSpec("frame_y", (0.20, 0.26, 0.16), 90.0, RADIUS_M, LENGTH_M),
            LogSpec("frame_45", (-0.20, -0.12, 0.34), 45.0, RADIUS_M, LENGTH_M),
            LogSpec("frame_3d", (0.20, 0.12, 0.38), 0.0, RADIUS_M, LENGTH_M),
        )
        for spec in log_specs:
            create_log(stage, spec)
        axis = Gf.Vec3f(1.0, 2.0, 3.0).GetNormalized()
        half_angle = math.radians(37.0) * 0.5
        stage.GetPrimAtPath("/World/Logs/frame_3d").GetAttribute(
            "xformOp:orient"
        ).Set(Gf.Quatf(math.cos(half_angle), axis * math.sin(half_angle)))

        samples = {spec.log_id: _sample_transform(stage, spec.log_id) for spec in log_specs}
        models = {
            spec.log_id: _model(spec.log_id, 410.0 + index * 50.0)
            for index, spec in enumerate(log_specs)
        }
        cardinal_ids = ("frame_x", "frame_y")
        arbitrary_ids = ("frame_45", "frame_3d")
        cardinal_layout = resident_point_layout_for_logs(stage, cardinal_ids)
        noncardinal_error = None
        try:
            resident_point_layout_for_logs(stage, arbitrary_ids)
        except ValueError as exc:
            noncardinal_error = str(exc)

        cardinal_arrays = _scenario_arrays(
            [models[log_id] for log_id in cardinal_ids],
            [samples[log_id] for log_id in cardinal_ids],
        )
        arbitrary_arrays = _scenario_arrays(
            [models[log_id] for log_id in arbitrary_ids],
            [samples[log_id] for log_id in arbitrary_ids],
        )
        cardinal_code, cardinal_count, cardinal_positions = _call_frame(
            frame, cardinal_arrays, 2
        )
        arbitrary_code, arbitrary_count, arbitrary_positions = _call_frame(
            frame, arbitrary_arrays, 2
        )
        legacy_code, legacy_count, legacy_positions = _call_legacy(
            legacy, cardinal_arrays, cardinal_layout["axes"], 2
        )
        cardinal_error = _maximum_point_error(
            cardinal_positions, cardinal_arrays["records"]
        )
        arbitrary_error = _maximum_point_error(
            arbitrary_positions, arbitrary_arrays["records"]
        )

        y_offset = SURFACE_POINTS_PER_LOG
        proper_map = _coordinate_channel_map(
            cardinal_positions,
            cardinal_arrays["records"],
            y_offset,
            SURFACE_POINTS_PER_LOG,
        )
        legacy_map = _coordinate_channel_map(
            legacy_positions,
            cardinal_arrays["records"],
            y_offset,
            SURFACE_POINTS_PER_LOG,
        )
        common_coordinates = set(proper_map) & set(legacy_map)
        temperature_mismatches = sum(
            proper_map[key][1] != legacy_map[key][1]
            for key in common_coordinates
        )
        fuel_mismatches = sum(
            proper_map[key][0] != legacy_map[key][0]
            for key in common_coordinates
        )
        smoke_mismatches = sum(
            proper_map[key][2] != legacy_map[key][2]
            for key in common_coordinates
        )

        frame_checks = {
            log_id: {
                "origin": sample["origin"],
                "frame": sample["frame"],
                "axis_norms": sample["norms"],
                "dot_xy": sample["dot_xy"],
                "dot_xz": sample["dot_xz"],
                "dot_yz": sample["dot_yz"],
                "determinant": sample["determinant"],
                "xform_op_order": sample["xform_op_order"],
            }
            for log_id, sample in samples.items()
        }
        rigid_frames_valid = all(
            max(abs(norm - 1.0) for norm in check["axis_norms"]) <= 1.0e-6
            and max(abs(check[name]) for name in ("dot_xy", "dot_xz", "dot_yz")) <= 1.0e-6
            and abs(check["determinant"] - 1.0) <= 4.0e-6
            for check in frame_checks.values()
        )
        cardinal_digest = _record_digest(cardinal_arrays["records"])
        arbitrary_digest = _record_digest(arbitrary_arrays["records"])
        gates = {
            "production_cardinal_resolver_returns_axes_0_1": tuple(cardinal_layout["axes"]) == (0, 1),
            "production_noncardinal_resolver_fails_closed": bool(noncardinal_error),
            "usd_frames_are_right_handed_orthonormal": rigid_frames_valid,
            "cardinal_frame_call_succeeded": cardinal_code == 0 and cardinal_count == 720,
            "arbitrary_frame_call_succeeded": arbitrary_code == 0 and arbitrary_count == 720,
            "cardinal_position_cell_identity_matches": cardinal_error <= POINT_TOLERANCE_M,
            "arbitrary_position_cell_identity_matches": arbitrary_error <= POINT_TOLERANCE_M,
            "stable_channel_identity_digests_present": len(cardinal_digest) == 64 and len(arbitrary_digest) == 64,
            "legacy_y_geometry_set_is_complete": len(common_coordinates) == SURFACE_POINTS_PER_LOG,
            "legacy_y_temperature_misalignment_detected": temperature_mismatches > 0,
            "legacy_y_log_constant_channels_remain_aligned": fuel_mismatches == 0 and smoke_mismatches == 0,
            "legacy_call_succeeded": legacy_code == 0 and legacy_count == 720,
        }
        report.update(
            {
                "status": "ok" if all(gates.values()) else "error",
                "scope": {
                    "usd_stage": "anonymous in-memory",
                    "stage_connected_to_kit_context": False,
                    "production_wood_authoring_used": True,
                    "flow_or_renderer_used": False,
                },
                "measurement": {
                    "scenario_count": 2,
                    "logs_per_scenario": 2,
                    "points_per_scenario": 720,
                    "cells_per_log": CELLS_PER_LOG,
                    "surface_points_per_log": SURFACE_POINTS_PER_LOG,
                },
                "gates": {
                    "passed": sum(bool(value) for value in gates.values()),
                    "total": len(gates),
                    "checks": gates,
                },
                "usd_transform_samples": frame_checks,
                "production_resolver": {
                    "cardinal_axes": cardinal_layout["axes"],
                    "noncardinal_error": noncardinal_error,
                },
                "position_identity": {
                    "cardinal_max_error_m": cardinal_error,
                    "arbitrary_max_error_m": arbitrary_error,
                    "cardinal_record_sha256": cardinal_digest,
                    "arbitrary_record_sha256": arbitrary_digest,
                },
                "legacy_y_channel_boundary": {
                    "common_coordinate_count": len(common_coordinates),
                    "temperature_mismatch_count": temperature_mismatches,
                    "fuel_mismatch_count": fuel_mismatches,
                    "smoke_mismatch_count": smoke_mismatches,
                    "interpretation": "Legacy reflection preserves the point set and log-constant channels but assigns cell-varying temperature values to different coordinates.",
                },
                "decision": {
                    "usd_frame_extraction_qualified": rigid_frames_valid,
                    "frame_position_channel_identity_qualified": cardinal_error <= POINT_TOLERANCE_M and arbitrary_error <= POINT_TOLERANCE_M,
                    "legacy_axis_migration_is_value_preserving": False,
                    "production_integration_qualified": False,
                    "next": "Define an explicit migration policy for existing Y layouts, then prototype immutable frame metadata and selective publication without activating Point.",
                },
            }
        )
    except Exception as exc:  # pragma: no cover - real Kit evidence
        report.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        _write(output, report)
        settings.set("/app/fastShutdown", True)
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run())
