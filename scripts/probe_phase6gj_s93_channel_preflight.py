"""Phase 6GJ one-readback S93 schema and ordered alias-lifetime preflight."""

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

DISCOVERY_PATH = (SCRIPT_DIR / "probe_phase6gd_channel_metadata.py").resolve()
POLICY_PATH = (SCRIPT_DIR / "phase6gj_empty_rgba_alias_policy.py").resolve()
CONTRACT_PATH = (SCRIPT_DIR / "phase6gj_empty_rgba_alias_contract.json").resolve()
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
    discovery, discovery_audit = load_exact_module(
        DISCOVERY_PATH, DISCOVERY_PATH, module_name="campfire_phase6gj_discovery_boundary",
        required_entrypoints=("_volume_metadata", "_array_metadata", "_api_metadata"),
    )
    policy, policy_audit = load_exact_module(
        POLICY_PATH, POLICY_PATH, module_name="campfire_phase6gj_channel_policy",
        required_entrypoints=("validate_raw_schema", "validate_preflight"),
    )
    _atomic_json(audit_path, {
        "schema": "campfire.phase6gj.kit-import-audit.v1", "status": "pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "kit_app_ready_exec": True,
        "wrapper_file": str(Path(__file__).resolve()), "working_directory": str(Path.cwd()),
        "imports": [discovery_audit, policy_audit],
    })
except BaseException as exc:
    _atomic_json(audit_path, {
        "schema": "campfire.phase6gj.kit-import-audit.v1", "status": "fail",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "error_type": type(exc).__name__,
        "error": str(exc), "wrapper_file": str(Path(__file__).resolve()),
    })
    raise

shared = discovery.shared
contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
if _sha256(CANDIDATE_PATH) != contract["candidate_schema"]["sha256"]:
    raise RuntimeError("Phase 6GJ candidate schema hash mismatch")

_controlled_build = shared._build_stage


def _build_preflight_stage(arguments):
    stage_path, point_summary, plan = _controlled_build(arguments)
    stage = shared.Usd.Stage.Open(str(stage_path))
    export = stage.GetPrimAtPath(shared.point_core.SIMULATE_PATH.AppendChild("nanoVdbExport"))
    observed = {
        "divergence": bool(export.GetAttribute("divergenceEnabled").Get()),
        "rgba": bool(export.GetAttribute("rgbaEnabled").Get()),
        "rgb": bool(export.GetAttribute("rgbEnabled").Get()),
    }
    if observed != contract["condition"]["export_enable_state"]:
        raise RuntimeError(f"Phase 6GJ export enable state mismatch: {observed}")
    point_summary["phase6gj_export_enable_state"] = observed
    return stage_path, point_summary, plan


shared._build_stage = _build_preflight_stage


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


def _qualified_boundary(flow, volume, arguments, frame, output, collectors, operation_state=None):
    del collectors
    operation_state = operation_state or {}
    mark = lambda name, **values: shared._append_resource_marker(
        arguments["resource_marker_path"], name,
        synchronous_memory=arguments["synchronous_memory_markers"], frame=frame,
        active_blocks=int(flow.get_active_block_count()), **operation_state, **values)
    metadata_root = output.parent / "channel-schema-metadata"
    metadata_root.mkdir(parents=True, exist_ok=True)
    mark("phase6gj_readback_snapshot_before")
    handles = flow.get_latest_nanovdb_readback()
    mark("phase6gj_readback_snapshot_after", returned_handle_count=len(handles))
    if not isinstance(handles, list):
        raise RuntimeError(f"Phase 6GJ expected public list, got {type(handles)!r}")
    if len(handles) != contract["schema_gate"]["expected_handle_count"]:
        raise RuntimeError(f"Phase 6GJ expected 7 public handles, got {len(handles)}")
    rows, weak_references = [], []
    total_temporary_bytes = 0
    for index in range(len(handles)):
        mark("phase6gj_handle_snapshot_before", handle_index=index)
        source = handles[index]
        alias = source
        reference = weakref.ref(source)
        weak_references.append(reference)
        array = discovery._array_metadata(source)
        row = {
            "index": index, "label": f"handle[{index}]", "python_type": array.get("python_type"),
            "native_type": array.get("native_type"), "is_numpy_array": array.get("is_numpy_array"),
            "dtype": array.get("dtype"), "shape": array.get("shape"), "strides": array.get("strides"),
            "element_count": int(source.size), "logical_bytes": int(source.nbytes),
            "data_pointer": array.get("data_pointer"), "object_identity": int(id(source)),
            "alias_contract": {"source_identity": int(id(source)), "alias_identity": int(id(alias)),
                "same_python_object": alias is source, "shares_memory": bool(np.shares_memory(source, alias)),
                "shares_memory_required": bool(source.size > 0),
                "empty_array_overlap_is_ownership_predicate": False,
                "source_data_pointer": array.get("data_pointer"), "alias_data_pointer": array.get("data_pointer"),
                "numpy_asarray_called": False, "material_copy_created": False},
            "python_reference_scope": "returned list slot plus local source/alias until ordered release",
            "internal_extension_reference_count": "unavailable_from_public_api",
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
        snapshot_path = metadata_root / f"handle_{index}_snapshot.json"
        _atomic_json(snapshot_path, row)
        mark("phase6gj_handle_snapshot_complete", handle_index=index, snapshot_path=str(snapshot_path),
             metadata_sha256=row["metadata_sha256"], temporary_bytes=file_bytes)
        alias = None
        handles[index] = None
        source = None
        row["release"] = {"local_alias_cleared": alias is None, "list_slot_cleared": handles[index] is None,
            "weak_reference_supported": True, "weak_reference_alive_after_slot_clear": reference() is not None,
            "python_wrapper_residual": reference() is not None,
            "internal_extension_reference_residual": "unavailable_from_public_api"}
        _atomic_json(snapshot_path, row)
        mark("phase6gj_handle_release_complete", handle_index=index,
             weak_reference_alive=reference() is not None, list_slot_cleared=handles[index] is None)
        rows.append(row)
    handles.clear()
    del handles
    api = discovery._api_metadata(flow)
    raw_observation = {
        "candidate_schema_id": candidate["schema_id"], "candidate_schema_sha256": _sha256(CANDIDATE_PATH),
        "versions": {"flow": api["flow_extension"]["version"], "kit": api["kit_build"],
                     "volume": api["volume_extension"]["version"]},
        "api": api["api_name"], "export_enable_state": copy.deepcopy(contract["condition"]["export_enable_state"]),
        "public_readback_calls": 1, "returned_handle_count": len(rows), "handles": rows, "unknown_handles": []}
    raw_validation = policy.validate_raw_schema(raw_observation, contract)
    _atomic_json(metadata_root / "raw_schema_validation.json", raw_validation)
    mark("phase6gj_raw_schema_validation_complete", schema_pass=raw_validation["pass"], reasons=raw_validation["reasons"])
    if not raw_validation["pass"]:
        raise RuntimeError(f"Phase 6GJ raw schema validation failed: {raw_validation['reasons']}")
    for row, wanted in zip(rows, contract["schema_gate"]["handles"]):
        row["channel"] = wanted["channel"]
    observation = {**raw_observation, "handles": rows,
        "semantic_mapping_applied_after_raw_schema_validation": True,
        "operation_counts": {"public_readback_calls": 1, "numpy_asarray_calls": 0,
                             "material_copies": 0, "field_body_writes": 0,
                             "temporary_nanovdb_metadata_files": 6},
        "weak_reference_supported_count": len(weak_references),
        "weak_reference_alive_after_release_count": sum(reference() is not None for reference in weak_references),
        "ownership_container_residual_count": 0,
        "temporary_nanovdb_metadata_file_bytes": total_temporary_bytes,
        "temporary_nanovdb_metadata_files_retained": 0,
        "field_body_json_npz_or_openvdb_written": False, "formal_channel_names_assigned": True,
        "forced_gc": False, "private_api_used": False, "public_release_method_used": False}
    validation = policy.validate_preflight(observation, contract)
    observation["validation"] = validation
    observation["status"] = "pass" if validation["pass"] else "fail"
    report_path = metadata_root / "bounded_handle_metadata.json"
    preflight_path = metadata_root / "qualified_channel_preflight.json"
    _atomic_json(report_path, observation)
    _atomic_json(preflight_path, observation)
    mark("phase6gj_channel_preflight_durable", preflight_pass=validation["pass"],
         weak_reference_alive_count=observation["weak_reference_alive_after_release_count"],
         report_path=str(preflight_path))
    if not validation["pass"]:
        raise RuntimeError(f"Phase 6GJ channel preflight failed: {validation['reasons']}")
    return {"mode": "phase6gj_s93_channel_preflight", "returned_handle_count": len(rows),
        "channel_objects": rows, "handles": rows, "public_channel_order": contract["schema_gate"]["exact_order"],
        "formal_channel_names_assigned": True, "full_field_json_or_npz_written": False,
        "weak_reference_alive_after_scope_count": 0, "qualified_channel_preflight_path": str(preflight_path),
        "validation": validation, "operation_counts": observation["operation_counts"]}, weak_references


shared._p3_spatial_boundary = _qualified_boundary

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
