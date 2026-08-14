"""Phase 6GT: save one temperature GridData to one temporary NanoVDB file."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import weakref
from datetime import datetime, timezone
from pathlib import Path

import carb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module
from phase6gp_metadata_r1_contract import bounded_slot_metadata, type_name
from phase6gs_harness_contract import ACCESSORS, bounded_public_value, canonical_source_marker_payload, validate_qualified_temperature_slot
from phase6gt_temporary_nvdb_contract import (
    MAXIMUM_FILE_BYTES,
    POLL_INTERVAL_SECONDS,
    POLL_TIMEOUT_SECONDS,
    delete_exact_temporary,
    exact_temporary_path,
    poll_nonempty_file,
    require_absent,
    require_save_return,
)

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
SCHEMA_PATH = (SCRIPT_DIR / "phase6gh_public_channel_schema_candidate.json").resolve()
QUALIFICATION_PATH = (SCRIPT_DIR.parent / "docs/devlog/assets/phase6/phase6gk_public_channel_preflight_qualified.json").resolve()
MAX_JSON_BYTES = 128 * 1024
MAX_GRID_COUNT = 4
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()
TEMPORARY_PATH = exact_temporary_path(REPORT_PATH.parent)


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6GT bounded JSON exceeded 128 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


base, import_audit = load_exact_module(BASE_PATH, BASE_PATH, module_name="campfire_phase6gt_phase6gn_base", required_entrypoints=())
shared = base.shared
candidate = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
mapping = validate_qualified_temperature_slot(candidate, qualification)
if not mapping["pass"]:
    raise ImportError("qualified public-channel schema no longer maps slot 0 to nonempty temperature")

report = {
    "schema": "campfire.phase6gt.temporary-nvdb-operation.v1",
    "status": "running",
    "operation_result": "running",
    "mapping": mapping,
    "public_readback_calls": 0,
    "volume_conversion_calls": 0,
    "accessor_calls": {name: 0 for name in ACCESSORS},
    "bounded_metadata_complete": False,
    "save_volume_calls": 0,
    "save_volume_return": None,
    "file_content_read_calls": 0,
    "file_hash_calls": 0,
    "nanovdb_reload_calls": 0,
    "numpy_asarray_calls": 0,
    "sampling_calls": 0,
    "collector_calls": 0,
    "flux_calls": 0,
    "temporary_file": {
        "path": str(TEMPORARY_PATH),
        "maximum_file_bytes": MAXIMUM_FILE_BYTES,
        "exists_before_save": None,
        "file_exists": None,
        "file_size_bytes": None,
        "within_limit": None,
        "poll_elapsed_seconds": None,
        "deleted": None,
        "file_exists_after_delete": None,
    },
    "checkpoints": [],
}


def checkpoint(name: str, **payload) -> None:
    row = {"name": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **payload}
    report["checkpoints"].append(row)
    report["last_operation_marker"] = name
    _atomic_json(REPORT_PATH, report)


def _phase6gt_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    del output, collectors, operation_state

    def marker(name: str, **payload) -> None:
        active_blocks = int(flow.get_active_block_count())
        shared._append_resource_marker(
            arguments["resource_marker_path"], name,
            synchronous_memory=arguments["synchronous_memory_markers"],
            frame=int(frame), active_blocks=active_blocks,
            phase="phase6gt", isolation_mode="temperature_temporary_nvdb_once",
            **payload,
        )
        checkpoint(name, frame=int(frame), active_blocks=active_blocks, **payload)

    handles = None
    source = None
    converted = None
    source_reference = None
    converted_reference = None
    current_accessor = None
    try:
        marker("phase6gt_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        marker("phase6gt_readback_after")
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected builtins.list with 7 slots, got {type_name(handles)}/{len(handles)}")

        source = handles[0]
        source_metadata = {"channel": "temperature", **bounded_slot_metadata(0, source)}
        source_payload = canonical_source_marker_payload(source_metadata, expected_slot=0, canonical_channel="temperature")
        report["source"] = source_payload
        source_reference = weakref.ref(source)
        marker("phase6gt_slot0_selected_after", **source_payload)
        for slot in range(1, 7):
            handles[slot] = None

        marker("phase6gt_volume_conversion_before", slot=0, channel="temperature")
        report["volume_conversion_calls"] = 1
        converted = flow.buffer_to_volume(source)
        converted_reference = weakref.ref(converted)
        report["volume_python_type"] = type_name(converted)
        marker("phase6gt_volume_conversion_after", python_type=report["volume_python_type"])

        bounded_metadata = {"grid_count": None, "index0": {}}
        current_accessor = "get_num_grids"
        marker("phase6gt_get_num_grids_before")
        report["accessor_calls"][current_accessor] += 1
        value = int(volume_provider.get_num_grids(converted))
        bounded_metadata["grid_count"] = value
        report["bounded_metadata"] = bounded_metadata
        report["last_successful_accessor"] = current_accessor
        marker("phase6gt_get_num_grids_after", result=value)
        if value < 1 or value > MAX_GRID_COUNT:
            raise RuntimeError(f"public volume grid count {value} is outside 1..{MAX_GRID_COUNT}")

        current_accessor = "get_grid_type"
        marker("phase6gt_get_grid_type_before", grid_index=0)
        report["accessor_calls"][current_accessor] += 1
        value = bounded_public_value(volume_provider.get_grid_type(converted, 0))
        bounded_metadata["index0"]["grid_type"] = value
        report["last_successful_accessor"] = current_accessor
        marker("phase6gt_get_grid_type_after", grid_index=0, result=value)

        current_accessor = "get_short_grid_name"
        marker("phase6gt_get_short_grid_name_before", grid_index=0)
        report["accessor_calls"][current_accessor] += 1
        value = bounded_public_value(volume_provider.get_short_grid_name(converted, 0))
        bounded_metadata["index0"]["short_grid_name"] = value
        report["last_successful_accessor"] = current_accessor
        marker("phase6gt_get_short_grid_name_after", grid_index=0, result=value)

        current_accessor = "get_grid_class"
        marker("phase6gt_get_grid_class_before", grid_index=0)
        report["accessor_calls"][current_accessor] += 1
        value = bounded_public_value(volume_provider.get_grid_class(converted, 0))
        bounded_metadata["index0"]["grid_class"] = value
        report["last_successful_accessor"] = current_accessor
        marker("phase6gt_get_grid_class_after", grid_index=0, result=value)

        current_accessor = "get_index_bounding_box"
        marker("phase6gt_get_index_bounding_box_before", grid_index=0)
        report["accessor_calls"][current_accessor] += 1
        value = bounded_public_value(volume_provider.get_index_bounding_box(converted, 0))
        bounded_metadata["index0"]["index_bounding_box"] = value
        report["last_successful_accessor"] = current_accessor
        marker("phase6gt_get_index_bounding_box_after", grid_index=0, result=value)

        current_accessor = "get_world_bounding_box"
        marker("phase6gt_get_world_bounding_box_before", grid_index=0)
        report["accessor_calls"][current_accessor] += 1
        value = bounded_public_value(volume_provider.get_world_bounding_box(converted, 0))
        bounded_metadata["index0"]["world_bounding_box"] = value
        report["last_successful_accessor"] = current_accessor
        marker("phase6gt_get_world_bounding_box_after", grid_index=0, result=value)
        report["bounded_metadata_complete"] = True
        marker("phase6gt_bounded_metadata_complete", accessor_count=len(ACCESSORS))

        require_absent(TEMPORARY_PATH)
        report["temporary_file"]["exists_before_save"] = False
        marker("phase6gt_temporary_path_confirmed", path=str(TEMPORARY_PATH), exists=False)

        parameters = shared.omni.volume.SaveVolumeParameters()
        parameters.flags = shared.omni.volume.kNanoVDBCodecNone
        marker("phase6gt_save_parameters_constructed", codec="kNanoVDBCodecNone")

        marker("phase6gt_save_volume_before")
        report["save_volume_calls"] = 1
        save_return = volume_provider.save_volume(converted, str(TEMPORARY_PATH), parameters)
        report["save_volume_return"] = require_save_return(save_return)
        marker("phase6gt_save_volume_after", save_return=report["save_volume_return"])

        marker("phase6gt_file_poll_started", timeout_seconds=POLL_TIMEOUT_SECONDS)
        poll = poll_nonempty_file(
            TEMPORARY_PATH,
            timeout_seconds=POLL_TIMEOUT_SECONDS,
            interval_seconds=POLL_INTERVAL_SECONDS,
            maximum_file_bytes=MAXIMUM_FILE_BYTES,
        )
        report["temporary_file"].update(poll)
        marker("phase6gt_nonempty_file_confirmed", file_exists=True, poll_elapsed_seconds=poll["elapsed_seconds"])
        marker(
            "phase6gt_file_size_recorded",
            file_size_bytes=poll["file_size_bytes"],
            maximum_file_bytes=MAXIMUM_FILE_BYTES,
            within_limit=True,
        )

        marker("phase6gt_temporary_file_delete_before", path=str(TEMPORARY_PATH))
        deletion = delete_exact_temporary(TEMPORARY_PATH, REPORT_PATH.parent)
        report["temporary_file"].update(deletion)
        marker(
            "phase6gt_temporary_file_delete_after",
            deleted=deletion["deleted"],
            file_exists_after_delete=deletion["file_exists_after_delete"],
        )

        marker("phase6gt_volume_release_before")
        converted = None
        volume_alive = converted_reference() is not None
        report["volume_weak_reference_alive_after_release"] = volume_alive
        marker("phase6gt_volume_release_after", weak_reference_alive=volume_alive)

        marker("phase6gt_source_release_before")
        handles[0] = None
        source = None
        handles.clear()
        handles = None
        source_alive = source_reference() is not None
        weak_alive = int(volume_alive) + int(source_alive)
        report["source_weak_reference_alive_after_release"] = source_alive
        report["weak_reference_alive_after_release_count"] = weak_alive
        report["operation_result"] = "pass" if weak_alive == 0 else "failure"
        report["status"] = "pass" if weak_alive == 0 else "fail"
        marker(
            "phase6gt_source_release_after",
            source_weak_reference_alive=source_alive,
            weak_reference_alive_count=weak_alive,
        )
        if weak_alive:
            raise RuntimeError(f"weak-reference residual after release: {weak_alive}")
        return {
            "mode": "phase6gt_temperature_temporary_nvdb_once",
            "returned_channel_count": 7,
            "volume_conversion_calls": 1,
            "volume_metadata_accessor_calls": len(ACCESSORS),
            "save_volume_calls": 1,
            "temporary_file_deleted": True,
            "weak_reference_alive_after_scope_count": 0,
            "field_body_json_npz_or_openvdb_written": True,
            "temporary_field_body_deleted_before_return": True,
        }, [source_reference, converted_reference]
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "temporary_nvdb_save_boundary_failure"
        report["first_failed_accessor"] = current_accessor
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        if TEMPORARY_PATH.exists():
            report["temporary_file"]["file_exists_on_failure"] = True
            report["temporary_file"]["file_size_on_failure_bytes"] = int(TEMPORARY_PATH.stat().st_size)
            checkpoint("phase6gt_partial_file_cleanup_before")
            deletion = delete_exact_temporary(TEMPORARY_PATH, REPORT_PATH.parent)
            report["temporary_file"].update(deletion)
            checkpoint("phase6gt_partial_file_cleanup_after", deleted=deletion["deleted"])
        checkpoint("phase6gt_operation_failure", accessor=current_accessor)
        raise


shared._p3_spatial_boundary = _phase6gt_boundary
_atomic_json(AUDIT_PATH, {
    "schema": "campfire.phase6gt.kit-import-audit.v1",
    "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_file": str(Path(__file__).resolve()),
    "base_wrapper": str(BASE_PATH),
    "base_import": import_audit,
    "mapping": mapping,
    "patch_target": "shared._p3_spatial_boundary",
    "patched": shared._p3_spatial_boundary is _phase6gt_boundary,
    "temporary_path": str(TEMPORARY_PATH),
    "content_read_allowed": False,
    "hash_allowed": False,
    "reload_allowed": False,
})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
