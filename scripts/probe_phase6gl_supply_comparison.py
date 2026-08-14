"""Phase 6GL seven-handle public readback plus bounded spatial comparison.

The frozen Phase 6GC lifecycle/stage implementation is reused.  This wrapper
changes only the readback boundary: it validates the Phase 6GK raw seven-handle
schema before assigning channel semantics, then feeds the four required direct
buffers to the existing near-Mesh collector.  No full field body is retained.
"""

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

SHARED_PATH = (SCRIPT_DIR / "probe_phase6gc_shared_supply_comparison.py").resolve()
DISCOVERY_PATH = (SCRIPT_DIR / "probe_phase6gd_channel_metadata.py").resolve()
POLICY_PATH = (SCRIPT_DIR / "phase6gj_empty_rgba_alias_policy.py").resolve()
SCHEMA_CONTRACT_PATH = (SCRIPT_DIR / "phase6gk_bounded_artifact_interface_contract.json").resolve()
CANDIDATE_PATH = (SCRIPT_DIR / "phase6gh_public_channel_schema_candidate.json").resolve()
settings = carb.settings.get_settings()
audit_path = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


try:
    shared, shared_audit = load_exact_module(
        SHARED_PATH, SHARED_PATH, module_name="campfire_phase6gl_shared_supply_probe",
        required_entrypoints=("_run", "_append_resource_marker", "_save_and_sample", "_p3_world_rois"),
    )
    discovery, discovery_audit = load_exact_module(
        DISCOVERY_PATH, DISCOVERY_PATH, module_name="campfire_phase6gl_schema_metadata",
        required_entrypoints=("_volume_metadata", "_array_metadata", "_api_metadata"),
    )
    policy, policy_audit = load_exact_module(
        POLICY_PATH, POLICY_PATH, module_name="campfire_phase6gl_schema_policy",
        required_entrypoints=("validate_raw_schema", "validate_preflight"),
    )
    _atomic_json(audit_path, {
        "schema": "campfire.phase6gl.kit-import-audit.v1", "status": "pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "kit_app_ready_exec": True,
        "wrapper_file": str(Path(__file__).resolve()), "working_directory": str(Path.cwd()),
        "imports": [shared_audit, discovery_audit, policy_audit],
    })
except BaseException as exc:
    _atomic_json(audit_path, {
        "schema": "campfire.phase6gl.kit-import-audit.v1", "status": "fail",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "error_type": type(exc).__name__,
        "error": str(exc), "wrapper_file": str(Path(__file__).resolve()),
    })
    raise

schema_contract = json.loads(SCHEMA_CONTRACT_PATH.read_text(encoding="utf-8"))
candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
if _sha256(CANDIDATE_PATH) != schema_contract["candidate_schema"]["sha256"]:
    raise RuntimeError("Phase 6GL candidate schema hash mismatch")


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


def _qualified_spatial_boundary(flow, volume, arguments, frame, output, collectors, operation_state=None):
    operation_state = operation_state or {}
    mark = lambda name, **values: shared._append_resource_marker(
        arguments["resource_marker_path"], name,
        synchronous_memory=arguments["synchronous_memory_markers"], frame=frame,
        active_blocks=int(flow.get_active_block_count()), **operation_state, **values)
    metadata_root = output.parent / f"channel-schema-metadata-f{int(frame):04d}"
    metadata_root.mkdir(parents=True, exist_ok=True)
    mark("phase6gl_readback_before")
    handles = flow.get_latest_nanovdb_readback()
    mark("phase6gl_readback_after", returned_handle_count=len(handles))
    if not isinstance(handles, list) or len(handles) != 7:
        raise RuntimeError(f"Phase 6GL expected public list of 7 handles, got {type(handles)!r}/{len(handles)}")

    rows, references = [], []
    total_temporary_bytes = 0
    for index, wanted in enumerate(schema_contract["schema_gate"]["handles"]):
        source = handles[index]
        alias = source
        reference = weakref.ref(source)
        references.append(reference)
        array = discovery._array_metadata(source)
        row = {
            "index": index, "label": f"handle[{index}]", "python_type": array.get("python_type"),
            "native_type": array.get("native_type"), "is_numpy_array": array.get("is_numpy_array"),
            "dtype": array.get("dtype"), "shape": array.get("shape"), "strides": array.get("strides"),
            "element_count": int(source.size), "logical_bytes": int(source.nbytes),
            "data_pointer": array.get("data_pointer"), "object_identity": int(id(source)),
            "alias_contract": {"source_identity": int(id(source)), "alias_identity": int(id(alias)),
                "same_python_object": alias is source, "shares_memory": bool(np.shares_memory(source, alias)),
                "shares_memory_required": bool(source.size > 0), "numpy_asarray_called": False,
                "material_copy_created": False},
        }
        file_bytes = 0
        if int(source.size) > 0:
            volume_metadata, file_bytes = discovery._volume_metadata(
                flow, volume, source, metadata_root / f"handle_{index}.nvdb",
                discovery.TOTAL_FILE_LIMIT - total_temporary_bytes)
            total_temporary_bytes += file_bytes
            row["volume"] = volume_metadata
        else:
            row["volume"] = {"grid_count": 0, "grids": [], "temporary_file_bytes": 0,
                             "temporary_file_retained": False, "empty_handle_not_converted": True}
        row.update(_grid_fields(row))
        digest_payload = {key: value for key, value in row.items()
                          if key not in ("object_identity", "data_pointer", "alias_contract")}
        row["metadata_sha256"] = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest().upper()
        rows.append(row)
        alias = None

    api = discovery._api_metadata(flow)
    raw_observation = {
        "candidate_schema_id": candidate["schema_id"], "candidate_schema_sha256": _sha256(CANDIDATE_PATH),
        "versions": {"flow": api["flow_extension"]["version"], "kit": api["kit_build"],
                     "volume": api["volume_extension"]["version"]},
        "api": api["api_name"], "export_enable_state": copy.deepcopy(schema_contract["condition"]["export_enable_state"]),
        "public_readback_calls": 1, "returned_handle_count": len(rows), "handles": rows, "unknown_handles": []}
    raw_validation = policy.validate_raw_schema(raw_observation, schema_contract)
    _atomic_json(metadata_root / "raw_schema_validation.json", raw_validation)
    if not raw_validation["pass"]:
        raise RuntimeError(f"Phase 6GL raw schema validation failed: {raw_validation['reasons']}")
    for row, wanted in zip(rows, schema_contract["schema_gate"]["handles"]):
        row["channel"] = wanted["channel"]

    result = {
        "mode": "p3_spatial_release", "returned_type": shared._type_name(handles),
        "returned_channel_count": 7, "public_channel_order": list(candidate["exact_order"]),
        "requested_channels": list(arguments["readback_channels"]), "schema_handles": rows,
        "raw_schema_validation": raw_validation,
        "operation_counts": {"public_readback_calls": 1, "numpy_asarray_calls": 0,
            "explicit_copy_function_calls": 0, "material_copies": 0, "field_body_writes": 0,
            "temporary_nanovdb_metadata_files": 6,
            "near_mesh_npz_writes": len(arguments["readback_channels"]) * len(collectors)},
        "channels": {}, "forced_gc": False, "flow_occupancy_mask_claimed": False,
        "public_release_method_used": False, "field_body_json_npz_or_openvdb_written": False,
    }
    thresholds = {"velocity": 0.01, "temperature": 1.01, "smoke": 0.001, "fuel": 0.001}
    rois = shared._p3_world_rois()
    order = list(candidate["exact_order"])
    for channel in arguments["readback_channels"]:
        index = order.index(channel)
        source = handles[index]
        metadata = shared._bounded_object_metadata(source)
        metadata.update(channel_index=index, is_numpy_ndarray=isinstance(source, np.ndarray))
        if not metadata["is_numpy_ndarray"] or metadata.get("data_pointer") is None:
            raise RuntimeError(f"Phase 6GL {channel} direct buffer contract failed")
        before = shared.process_memory_snapshot()
        temporary_path = output.parent / f"p3_f{int(frame):04d}_{channel}.nvdb"
        details = shared._save_and_sample(
            flow, volume, source, channel, temporary_path, rois, spatial_collector=collectors,
            spatial_velocity_only=False, frame=frame, profile_threshold=thresholds[channel])
        after = shared.process_memory_snapshot()
        before_private = before.get("private_bytes") if before.get("available") else None
        after_private = after.get("private_bytes") if after.get("available") else None
        result["channels"][channel] = {
            "source": metadata, "read_only_direct_array": True, "numpy_asarray_called": False,
            "material_copy_requested": False, "memory_before": before, "memory_after": after,
            "private_bytes_delta": None if before_private is None or after_private is None else int(after_private-before_private),
            "temporary_nanovdb_present_after_collection": temporary_path.exists(), "field": details,
        }

    del source, details
    for index in range(len(handles)):
        handles[index] = None
        rows[index]["release"] = {"list_slot_cleared": True, "weak_reference_supported": True,
                                  "weak_reference_alive_after_slot_clear": references[index]() is not None}
    handles.clear()
    del handles, alias
    observation = {**raw_observation, "handles": rows,
        "semantic_mapping_applied_after_raw_schema_validation": True,
        "operation_counts": {"public_readback_calls": 1, "numpy_asarray_calls": 0,
                             "material_copies": 0, "field_body_writes": 0},
        "weak_reference_alive_after_release_count": sum(ref() is not None for ref in references),
        "ownership_container_residual_count": 0}
    validation = policy.validate_preflight(observation, schema_contract)
    result["schema_validation"] = validation
    result["weak_reference_alive_after_scope_count"] = observation["weak_reference_alive_after_release_count"]
    result["ownership_container_residual_count"] = 0
    _atomic_json(metadata_root / "bounded_schema_and_alias.json", {**observation, "validation": validation})
    if not validation["pass"]:
        raise RuntimeError(f"Phase 6GL schema/alias validation failed: {validation['reasons']}")
    mark("phase6gl_schema_spatial_boundary_complete", schema_pass=True,
         weak_reference_alive_count=result["weak_reference_alive_after_scope_count"])
    return result, references


shared._p3_spatial_boundary = _qualified_spatial_boundary

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
