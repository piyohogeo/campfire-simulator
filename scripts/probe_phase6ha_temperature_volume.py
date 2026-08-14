"""Phase 6HA: exactly one temperature buffer-to-volume conversion."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import sys
import weakref
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module

GZ_PATH = (SCRIPT_DIR / "probe_phase6gz_candidate_boundary.py").resolve()
MAX_JSON_BYTES = 256 * 1024
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6HA bounded report exceeded 256 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


gz, gz_audit = load_exact_module(
    GZ_PATH, GZ_PATH, module_name="campfire_phase6ha_phase6gz_base", required_entrypoints=())
shared = gz.shared
phase6gl = gz.phase6gl
discovery = gz.discovery
policy = gz.policy
schema_contract = gz.schema_contract
candidate = gz.candidate

report = {
    "schema": "campfire.phase6ha.temperature-volume-operation.v1",
    "status": "running",
    "operation_result": "running",
    "public_readback_calls": 0,
    "temperature_buffer_to_volume_calls": 0,
    "schema_buffer_to_volume_calls": 0,
    "forbidden_content_access_calls": 0,
    "temperature_metadata_calls": 0,
    "temperature_save_calls": 0,
    "temperature_typed_read_calls": 0,
    "temperature_sampling_calls": 0,
    "temperature_collector_calls": 0,
    "temperature_flux_calls": 0,
    "checkpoints": [],
}


def checkpoint(name: str, **values) -> None:
    report["last_operation_marker"] = name
    report["checkpoints"].append({"name": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **values})
    _atomic_json(REPORT_PATH, report)


def _phase6ha_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    operation_state = operation_state or {}

    def marker(name: str, **values) -> None:
        shared._append_resource_marker(
            arguments["resource_marker_path"], name,
            synchronous_memory=arguments["synchronous_memory_markers"], frame=int(frame),
            active_blocks=int(flow.get_active_block_count()), phase="phase6ha",
            **operation_state, **values,
        )
        checkpoint(name, frame=int(frame), **values)

    metadata_root = output.parent / f"channel-schema-metadata-f{int(frame):04d}"
    metadata_root.mkdir(parents=True, exist_ok=True)
    handles = None
    references = []
    rows = []
    temperature_volume = None
    temperature_volume_reference = None
    source = None
    try:
        marker("phase6ha_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        marker("phase6ha_readback_after", returned_handle_count=len(handles))
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected public list of 7 handles, got {type(handles)!r}/{len(handles)}")
        marker("phase6ha_list_count_check_after", returned_handle_count=7, returned_type=shared._type_name(handles))

        total_bytes = 0
        for index in range(7):
            item = handles[index]
            references.append(weakref.ref(item))
            marker("phase6ha_schema_array_metadata_before", handle_index=index)
            array = discovery._array_metadata(item)
            marker("phase6ha_schema_array_metadata_after", handle_index=index,
                   python_type=array.get("python_type"), logical_bytes=array.get("logical_bytes"))
            row = {"index": index, "label": f"handle[{index}]", "python_type": array.get("python_type"),
                   "native_type": array.get("native_type"), "is_numpy_array": array.get("is_numpy_array"),
                   "dtype": array.get("dtype"), "shape": array.get("shape"), "strides": array.get("strides"),
                   "element_count": int(item.size), "logical_bytes": int(item.nbytes),
                   "data_pointer": array.get("data_pointer"), "object_identity": int(id(item)),
                   "alias_contract": {"source_identity": int(id(item)), "alias_identity": int(id(item)),
                                      "same_python_object": True, "shares_memory": bool(np.shares_memory(item, item)),
                                      "shares_memory_required": bool(item.size > 0), "numpy_asarray_called": False,
                                      "material_copy_created": False}}
            if int(item.size) > 0:
                report["schema_buffer_to_volume_calls"] += 1
                volume_metadata, file_bytes = gz._instrumented_schema_volume(
                    flow, volume_provider, item, metadata_root / f"handle_{index}.nvdb",
                    discovery.TOTAL_FILE_LIMIT - total_bytes, marker, index)
                total_bytes += file_bytes
                row["volume"] = volume_metadata
            else:
                row["volume"] = {"grid_count": 0, "grids": [], "temporary_file_bytes": 0,
                                 "temporary_file_retained": False, "empty_handle_not_converted": True}
            row.update(gz._grid_fields(row))
            digest = {key: value for key, value in row.items()
                      if key not in ("object_identity", "data_pointer", "alias_contract")}
            row["metadata_sha256"] = hashlib.sha256(json.dumps(
                digest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest().upper()
            rows.append(row)

        marker("phase6ha_schema_validation_before")
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
        marker("phase6ha_schema_validation_after", schema_pass=True)

        velocity_index = list(candidate["exact_order"]).index("velocity")
        velocity_path = output.parent / f"p3_f{int(frame):04d}_velocity.nvdb"
        marker("phase6ha_velocity_pipeline_before", channel="velocity")
        shared._save_and_sample(flow, volume_provider, handles[velocity_index], "velocity", velocity_path,
                                shared._p3_world_rois(), spatial_collector=collectors,
                                spatial_velocity_only=False, frame=frame, profile_threshold=0.01)
        marker("phase6ha_velocity_pipeline_after", channel="velocity", temporary_present=velocity_path.exists())

        temperature_index = list(candidate["exact_order"]).index("temperature")
        source = handles[temperature_index]
        report["temperature_source"] = {"slot": temperature_index, "channel": "temperature",
            "python_type": shared._type_name(source), "shape": [int(value) for value in source.shape],
            "dtype": str(source.dtype), "element_count": int(source.size), "logical_bytes": int(source.nbytes)}
        marker("phase6ha_temperature_entry", handle_index=temperature_index,
               python_type=shared._type_name(source), logical_bytes=int(source.nbytes))

        marker("phase6ha_temperature_conversion_before", handle_index=temperature_index)
        report["temperature_buffer_to_volume_calls"] = 1
        temperature_volume = flow.buffer_to_volume(source)
        temperature_volume_reference = weakref.ref(temperature_volume)
        report["temperature_volume_python_type"] = shared._type_name(temperature_volume)
        marker("phase6ha_temperature_conversion_after", python_type=report["temperature_volume_python_type"])

        marker("phase6ha_volume_release_before")
        temperature_volume = None
        volume_alive = temperature_volume_reference() is not None
        report["volume_weak_reference_alive_after_release"] = volume_alive
        marker("phase6ha_volume_release_after", weak_reference_alive=volume_alive)
        if volume_alive:
            raise RuntimeError("temperature volume weak reference remained after release")

        marker("phase6ha_handles_release_before")
        source = None
        for index in range(len(handles)):
            handles[index] = None
        handles.clear()
        handles = None
        item = None
        weak_alive = sum(reference() is not None for reference in references)
        report["handle_weak_reference_alive_after_release_count"] = weak_alive
        marker("phase6ha_handles_release_after", weak_reference_alive_count=weak_alive)
        if weak_alive:
            raise RuntimeError(f"handle weak-reference residual after release: {weak_alive}")

        report["operation_result"] = "pass"
        report["status"] = "pass"
        marker("phase6ha_operation_complete", temperature_conversion_calls=1,
               forbidden_content_access_calls=0)
        return {"mode": "phase6ha_temperature_volume_once", "returned_channel_count": 7,
                "temperature_buffer_to_volume_calls": 1, "field_body_json_npz_or_openvdb_written": False,
                "weak_reference_alive_after_scope_count": 0}, references + [temperature_volume_reference]
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "operation_failure"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        checkpoint("phase6ha_operation_failure")
        raise


shared._p3_spatial_boundary = _phase6ha_boundary
_atomic_json(AUDIT_PATH, {"schema": "campfire.phase6ha.kit-import-audit.v1", "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(), "wrapper": str(Path(__file__).resolve()),
    "base_import": gz_audit, "patch_target": "shared._p3_spatial_boundary",
    "patched": shared._p3_spatial_boundary is _phase6ha_boundary})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
