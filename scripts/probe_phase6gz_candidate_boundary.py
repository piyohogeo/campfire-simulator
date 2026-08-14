"""Phase 6GZ: one-process prefixes around the first temperature channel pipeline."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import sys
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module
from phase6gz_boundary_contract import candidate_level, validate_temporary_path

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
SAMPLE_PATH = (SCRIPT_DIR / "probe_phase6dt_flow_collision_reference.py").resolve()
MAX_JSON_BYTES = 256 * 1024
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()
MODE = settings.get_as_string("/phase6go/isolationMode") or "R0"
LEVEL = candidate_level(MODE)


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6GZ bounded operation report exceeded 256 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


base, base_audit = load_exact_module(
    BASE_PATH, BASE_PATH, module_name="campfire_phase6gz_phase6gn_base", required_entrypoints=())
samples, sample_audit = load_exact_module(
    SAMPLE_PATH, SAMPLE_PATH, module_name="campfire_phase6gz_sampling",
    required_entrypoints=("_sample_grid", "_profile_grid")
)
shared = base.shared
phase6gl = base.phase6gl
discovery = phase6gl.discovery
policy = phase6gl.policy
schema_contract = phase6gl.schema_contract
candidate = phase6gl.candidate

report = {
    "schema": "campfire.phase6gz.candidate-boundary-operation.v1",
    "status": "running",
    "operation_result": "running",
    "mode": MODE,
    "level": LEVEL,
    "public_readback_calls": 0,
    "calls": {"array_metadata": 0, "buffer_to_volume": 0, "volume_metadata": 0, "save": 0,
              "typed_read": 0, "sampling": 0, "collector": 0},
    "checkpoints": [],
    "temporary_files": [],
}


def checkpoint(name: str, **values) -> None:
    report["last_operation_marker"] = name
    report["checkpoints"].append({"name": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **values})
    _atomic_json(REPORT_PATH, report)


def _grid_fields(row: dict) -> dict:
    volume = row.get("volume")
    if not isinstance(volume, dict) or not volume.get("grids"):
        return {"grid_count": 0, "grid_short_name": None, "grid_class": None, "value_type": None,
                "index_bounding_box": None, "world_bounding_box": None}
    grid = volume["grids"][0]
    return {"grid_count": int(volume["grid_count"]), "grid_short_name": grid.get("short_name"),
            "grid_class": grid.get("grid_class"), "value_type": str(grid.get("grid_type")),
            "index_bounding_box": grid.get("index_bounding_box"),
            "world_bounding_box": grid.get("world_bounding_box")}


def _poll_file(path: Path, seconds: float = 5.0) -> int:
    deadline = time.monotonic() + seconds
    while (not path.is_file() or path.stat().st_size == 0) and time.monotonic() < deadline:
        time.sleep(0.01)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"temporary NanoVDB was not durable: {path.name}")
    return int(path.stat().st_size)


def _instrumented_schema_volume(flow, volume_provider, value, path: Path, remaining: int, marker, index: int):
    marker("phase6gz_schema_buffer_to_volume_before", handle_index=index)
    report["calls"]["buffer_to_volume"] += 1
    grid_data = flow.buffer_to_volume(value)
    marker("phase6gz_schema_buffer_to_volume_after", handle_index=index, python_type=shared._type_name(grid_data))
    marker("phase6gz_schema_volume_metadata_before", handle_index=index)
    report["calls"]["volume_metadata"] += 1
    count = int(volume_provider.get_num_grids(grid_data))
    if count < 1 or count > discovery.MAX_GRID_COUNT:
        raise RuntimeError(f"schema grid count outside bounds: {count}")
    grids = []
    for grid_index in range(count):
        grid_type = str(volume_provider.get_grid_type(grid_data, grid_index))
        grids.append({
            "index": grid_index, "short_name": discovery._json_value(volume_provider.get_short_grid_name(grid_data, grid_index)),
            "grid_class": discovery._json_value(volume_provider.get_grid_class(grid_data, grid_index)), "grid_type": grid_type,
            "index_bounding_box": discovery._json_value(volume_provider.get_index_bounding_box(grid_data, grid_index)),
            "world_bounding_box": discovery._json_value(volume_provider.get_world_bounding_box(grid_data, grid_index)),
        })
    marker("phase6gz_schema_volume_metadata_after", handle_index=index, grid_count=count)
    parameters = shared.omni.volume.SaveVolumeParameters()
    parameters.flags = shared.omni.volume.kNanoVDBCodecNone
    marker("phase6gz_schema_save_before", handle_index=index, temporary_name=path.name)
    report["calls"]["save"] += 1
    if not volume_provider.save_volume(grid_data, str(path), parameters):
        raise RuntimeError("schema metadata save failed")
    marker("phase6gz_schema_save_after", handle_index=index)
    size = _poll_file(path, 10.0)
    if size > discovery.PER_HANDLE_FILE_LIMIT or size > remaining:
        raise RuntimeError(f"schema metadata file exceeded limit: {size}")
    marker("phase6gz_schema_file_durable", handle_index=index, file_bytes=size)
    typed = discovery._typed_nanovdb_metadata(path, grids[0]["grid_type"])
    path.unlink(missing_ok=True)
    return {"grid_data_python_type": shared._type_name(grid_data), "grid_count": count, "grids": grids,
            "nano_grid": typed, "temporary_file_bytes": size, "temporary_file_retained": False}, size


def _bounded_temperature_volume_metadata(volume_provider, grid_data, marker) -> dict:
    marker("phase6gz_temperature_volume_metadata_before")
    report["calls"]["volume_metadata"] += 1
    count = int(volume_provider.get_num_grids(grid_data))
    if count < 1 or count > discovery.MAX_GRID_COUNT:
        raise RuntimeError(f"temperature grid count outside bounds: {count}")
    grid_type = str(volume_provider.get_grid_type(grid_data, 0))
    result = {
        "grid_count": count,
        "index0": {
            "grid_type": grid_type,
            "short_name": discovery._json_value(volume_provider.get_short_grid_name(grid_data, 0)),
            "grid_class": discovery._json_value(volume_provider.get_grid_class(grid_data, 0)),
            "index_bounding_box": discovery._json_value(volume_provider.get_index_bounding_box(grid_data, 0)),
            "world_bounding_box": discovery._json_value(volume_provider.get_world_bounding_box(grid_data, 0)),
        },
    }
    marker("phase6gz_temperature_volume_metadata_after", grid_count=count, grid_type=grid_type)
    return result


def _phase6gz_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    operation_state = operation_state or {}

    def marker(name: str, **values) -> None:
        shared._append_resource_marker(
            arguments["resource_marker_path"], name,
            synchronous_memory=arguments["synchronous_memory_markers"], frame=int(frame),
            active_blocks=int(flow.get_active_block_count()), phase="phase6gz", mode=MODE,
            **operation_state, **values,
        )
        checkpoint(name, frame=int(frame), **values)

    metadata_root = output.parent / f"channel-schema-metadata-f{int(frame):04d}"
    metadata_root.mkdir(parents=True, exist_ok=True)
    handles = None
    references = []
    rows = []
    temperature_grid_data = None
    typed_handle = None
    typed_grid = None
    temperature_path = output.parent / f"p3_f{int(frame):04d}_temperature.nvdb"
    validate = validate_temporary_path(output.parent, temperature_path)
    if not validate["pass"]:
        raise RuntimeError(f"temporary path contract failed: {validate['reasons']}")
    try:
        marker("phase6gz_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        marker("phase6gz_readback_after", returned_handle_count=len(handles))
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected public list of 7 handles, got {type(handles)!r}/{len(handles)}")
        marker("phase6gz_list_count_check_after", returned_handle_count=7, returned_type=shared._type_name(handles))

        total_bytes = 0
        for index in range(7):
            source = handles[index]
            references.append(weakref.ref(source))
            marker("phase6gz_handle_array_metadata_before", handle_index=index)
            report["calls"]["array_metadata"] += 1
            array = discovery._array_metadata(source)
            marker("phase6gz_handle_array_metadata_after", handle_index=index,
                   python_type=array.get("python_type"), logical_bytes=array.get("logical_bytes"))
            row = {"index": index, "label": f"handle[{index}]", "python_type": array.get("python_type"),
                   "native_type": array.get("native_type"), "is_numpy_array": array.get("is_numpy_array"),
                   "dtype": array.get("dtype"), "shape": array.get("shape"), "strides": array.get("strides"),
                   "element_count": int(source.size), "logical_bytes": int(source.nbytes),
                   "data_pointer": array.get("data_pointer"), "object_identity": int(id(source)),
                   "alias_contract": {"source_identity": int(id(source)), "alias_identity": int(id(source)),
                                      "same_python_object": True, "shares_memory": bool(np.shares_memory(source, source)),
                                      "shares_memory_required": bool(source.size > 0), "numpy_asarray_called": False,
                                      "material_copy_created": False}}
            if int(source.size) > 0:
                path = metadata_root / f"handle_{index}.nvdb"
                volume_metadata, file_bytes = _instrumented_schema_volume(
                    flow, volume_provider, source, path, discovery.TOTAL_FILE_LIMIT - total_bytes, marker, index)
                total_bytes += file_bytes
                row["volume"] = volume_metadata
            else:
                row["volume"] = {"grid_count": 0, "grids": [], "temporary_file_bytes": 0,
                                 "temporary_file_retained": False, "empty_handle_not_converted": True}
            row.update(_grid_fields(row))
            digest = {key: value for key, value in row.items() if key not in ("object_identity", "data_pointer", "alias_contract")}
            row["metadata_sha256"] = hashlib.sha256(json.dumps(digest, sort_keys=True, separators=(",", ":"),
                                                               allow_nan=False).encode("utf-8")).hexdigest().upper()
            rows.append(row)

        marker("phase6gz_schema_validation_before")
        api = discovery._api_metadata(flow)
        observation = {"candidate_schema_id": candidate["schema_id"],
            "candidate_schema_sha256": phase6gl._sha256(phase6gl.CANDIDATE_PATH),
            "versions": {"flow": api["flow_extension"]["version"], "kit": api["kit_build"],
                         "volume": api["volume_extension"]["version"]}, "api": api["api_name"],
            "export_enable_state": copy.deepcopy(schema_contract["condition"]["export_enable_state"]),
            "public_readback_calls": 1, "returned_handle_count": 7, "handles": rows, "unknown_handles": []}
        validation = policy.validate_raw_schema(observation, schema_contract)
        if not validation["pass"]:
            raise RuntimeError(f"raw schema validation failed: {validation['reasons']}")
        marker("phase6gz_schema_validation_after", schema_pass=True)
        for row, wanted in zip(rows, schema_contract["schema_gate"]["handles"]):
            row["channel"] = wanted["channel"]

        # Preserve the Candidate B channel order. Velocity completes before temperature begins.
        velocity_index = list(candidate["exact_order"]).index("velocity")
        velocity_path = output.parent / f"p3_f{int(frame):04d}_velocity.nvdb"
        marker("phase6gz_velocity_pipeline_before", channel="velocity")
        report["calls"]["buffer_to_volume"] += 1
        report["calls"]["save"] += 1
        report["calls"]["typed_read"] += 1
        report["calls"]["sampling"] += 1
        report["calls"]["collector"] += 1
        shared._save_and_sample(flow, volume_provider, handles[velocity_index], "velocity", velocity_path,
                                shared._p3_world_rois(), spatial_collector=collectors,
                                spatial_velocity_only=False, frame=frame, profile_threshold=0.01)
        marker("phase6gz_velocity_pipeline_after", channel="velocity", temporary_present=velocity_path.exists())

        temperature_index = list(candidate["exact_order"]).index("temperature")
        source = handles[temperature_index]
        marker("phase6gz_temperature_entry", handle_index=temperature_index, logical_bytes=int(source.nbytes))
        if LEVEL >= 1:
            marker("phase6gz_temperature_buffer_to_volume_before", handle_index=temperature_index)
            report["calls"]["buffer_to_volume"] += 1
            temperature_grid_data = flow.buffer_to_volume(source)
            marker("phase6gz_temperature_buffer_to_volume_after", python_type=shared._type_name(temperature_grid_data))
        if LEVEL >= 2:
            report["temperature_volume_metadata"] = _bounded_temperature_volume_metadata(
                volume_provider, temperature_grid_data, marker)
        if LEVEL >= 3:
            parameters = shared.omni.volume.SaveVolumeParameters()
            parameters.flags = shared.omni.volume.kNanoVDBCodecNone
            marker("phase6gz_temperature_save_before", temporary_name=temperature_path.name)
            report["calls"]["save"] += 1
            if not volume_provider.save_volume(temperature_grid_data, str(temperature_path), parameters):
                raise RuntimeError("temperature save returned false")
            marker("phase6gz_temperature_save_after")
            size = _poll_file(temperature_path, 5.0)
            report["temperature_file_bytes"] = size
            report["temporary_files"].append({"name": temperature_path.name, "bytes": size})
            marker("phase6gz_temperature_file_durable", file_bytes=size)
        if LEVEL >= 4:
            marker("phase6gz_temperature_typed_read_before")
            report["calls"]["typed_read"] += 1
            typed_handle = shared.nanovdb.io.readGrid(str(temperature_path))
            typed_grid = typed_handle.floatGrid()
            marker("phase6gz_temperature_typed_read_after", python_type=shared._type_name(typed_grid))
        if LEVEL >= 5:
            marker("phase6gz_temperature_sampling_before")
            report["calls"]["sampling"] += 1
            rois = shared._p3_world_rois()
            sample_result = {name: samples._sample_grid(typed_grid, roi, False) for name, roi in rois.items()}
            profile_result = samples._profile_grid(typed_grid, rois["scene"], False, 1.01)
            report["temperature_sampling"] = {"roi_count": len(sample_result),
                                               "available_count": sum(bool(row.get("available")) for row in sample_result.values()),
                                               "profile_significant_voxel_count": profile_result.get("significant_voxel_count")}
            marker("phase6gz_temperature_sampling_after", roi_count=len(sample_result))
        if LEVEL >= 6:
            marker("phase6gz_temperature_collector_before", collector_count=len(collectors))
            report["calls"]["collector"] += 1
            neighborhoods = [collector.capture(typed_grid, "temperature", frame, False, shared.nanovdb.math.Vec3d)
                             for collector in collectors]
            report["temperature_collector"] = {"collector_count": len(neighborhoods)}
            marker("phase6gz_temperature_collector_after", collector_count=len(neighborhoods))

        marker("phase6gz_release_before")
        temperature_path.unlink(missing_ok=True)
        typed_grid = None
        typed_handle = None
        temperature_grid_data = None
        source = None
        for index in range(len(handles)):
            handles[index] = None
        handles.clear()
        handles = None
        weak_alive = sum(reference() is not None for reference in references)
        report["weak_reference_alive_after_release_count"] = weak_alive
        marker("phase6gz_release_after", weak_reference_alive_count=weak_alive)
        if weak_alive:
            raise RuntimeError(f"weak reference residual after release: {weak_alive}")
        report["status"] = "pass"
        report["operation_result"] = "pass"
        checkpoint("phase6gz_operation_complete", level=LEVEL)
        return {"mode": f"phase6gz_{MODE}", "returned_channel_count": 7,
                "field_body_json_npz_or_openvdb_written": False,
                "weak_reference_alive_after_scope_count": 0}, references
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "operation_failure"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        checkpoint("phase6gz_operation_failure")
        raise
    finally:
        if temperature_path.is_file():
            temperature_path.unlink(missing_ok=True)


shared._p3_spatial_boundary = _phase6gz_boundary
_atomic_json(AUDIT_PATH, {"schema": "campfire.phase6gz.kit-import-audit.v1", "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(), "wrapper": str(Path(__file__).resolve()),
    "mode": MODE, "level": LEVEL, "base_import": base_audit, "sample_import": sample_audit,
    "patch_target": "shared._p3_spatial_boundary", "patched": shared._p3_spatial_boundary is _phase6gz_boundary})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
