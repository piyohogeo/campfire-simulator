"""Phase 6GR: read only a bounded public metadata set from temperature volume."""

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
from phase6gr_volume_metadata_contract import ACCESSORS, bounded_public_value, validate_qualified_temperature_slot

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
SCHEMA_PATH = (SCRIPT_DIR / "phase6gh_public_channel_schema_candidate.json").resolve()
QUALIFICATION_PATH = (SCRIPT_DIR.parent / "docs/devlog/assets/phase6/phase6gk_public_channel_preflight_qualified.json").resolve()
MAX_JSON_BYTES = 128 * 1024
MAX_GRID_COUNT = 4
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6GR bounded JSON exceeded 128 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


base, import_audit = load_exact_module(BASE_PATH, BASE_PATH, module_name="campfire_phase6gr_phase6gn_base", required_entrypoints=())
shared = base.shared
qualified_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
mapping = validate_qualified_temperature_slot(qualified_schema, qualification)
if not mapping["pass"]:
    raise ImportError("qualified public-channel schema no longer maps slot 0 to nonempty temperature")

report = {
    "schema": "campfire.phase6gr.volume-metadata-operation.v1",
    "status": "running",
    "operation_result": "running",
    "mapping": mapping,
    "public_readback_calls": 0,
    "volume_conversion_calls": 0,
    "accessor_calls": {name: 0 for name in ACCESSORS},
    "bounded_metadata_complete": False,
    "field_body_files_written": 0,
    "numpy_asarray_calls": 0,
    "save_volume_calls": 0,
    "sampling_calls": 0,
    "collector_calls": 0,
    "flux_calls": 0,
    "checkpoints": [],
}


def checkpoint(name: str, **values) -> None:
    row = {"name": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **values}
    report["checkpoints"].append(row)
    report["last_operation_marker"] = name
    _atomic_json(REPORT_PATH, report)


def _mark(arguments, frame, flow, name, **values) -> None:
    shared._append_resource_marker(
        arguments["resource_marker_path"], name,
        synchronous_memory=arguments["synchronous_memory_markers"],
        frame=int(frame), active_blocks=int(flow.get_active_block_count()),
        phase="phase6gr", isolation_mode="temperature_volume_metadata_once", **values,
    )
    checkpoint(name, frame=int(frame), active_blocks=int(flow.get_active_block_count()), **values)


def _phase6gr_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    del output, collectors, operation_state
    mark = lambda name, **values: _mark(arguments, frame, flow, name, **values)
    handles = None
    source = None
    converted = None
    source_reference = None
    converted_reference = None
    current_accessor = None
    try:
        mark("phase6gr_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        mark("phase6gr_readback_after")
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected builtins.list with 7 slots, got {type_name(handles)}/{len(handles)}")

        source = handles[0]
        report["source"] = {"channel": "temperature", **bounded_slot_metadata(0, source)}
        source_reference = weakref.ref(source)
        mark("phase6gr_slot0_selected_after", channel="temperature", **report["source"])
        for slot in range(1, 7):
            handles[slot] = None

        mark("phase6gr_volume_conversion_before", slot=0, channel="temperature")
        report["volume_conversion_calls"] = 1
        converted = flow.buffer_to_volume(source)
        converted_reference = weakref.ref(converted)
        report["volume_python_type"] = type_name(converted)
        mark("phase6gr_volume_conversion_after", python_type=report["volume_python_type"])

        current_accessor = "get_num_grids"
        mark("phase6gr_get_num_grids_before")
        report["accessor_calls"][current_accessor] += 1
        grid_count = int(volume_provider.get_num_grids(converted))
        report["bounded_metadata"] = {"grid_count": grid_count, "index0": {}}
        report["last_successful_accessor"] = current_accessor
        mark("phase6gr_get_num_grids_after", result=grid_count)
        if grid_count < 1 or grid_count > MAX_GRID_COUNT:
            raise RuntimeError(f"public volume grid count {grid_count} is outside 1..{MAX_GRID_COUNT}")

        calls = (
            ("get_grid_type", "grid_type"),
            ("get_short_grid_name", "short_grid_name"),
            ("get_grid_class", "grid_class"),
            ("get_index_bounding_box", "index_bounding_box"),
            ("get_world_bounding_box", "world_bounding_box"),
        )
        for accessor_name, result_name in calls:
            current_accessor = accessor_name
            mark(f"phase6gr_{accessor_name}_before", grid_index=0)
            report["accessor_calls"][accessor_name] += 1
            raw_value = getattr(volume_provider, accessor_name)(converted, 0)
            value = bounded_public_value(raw_value)
            report["bounded_metadata"]["index0"][result_name] = value
            report["last_successful_accessor"] = accessor_name
            mark(f"phase6gr_{accessor_name}_after", grid_index=0, result=value)

        report["bounded_metadata_complete"] = True
        mark("phase6gr_bounded_metadata_artifact_complete", accessor_count=len(ACCESSORS))

        mark("phase6gr_volume_release_before")
        converted = None
        volume_alive = converted_reference() is not None
        report["volume_weak_reference_alive_after_release"] = volume_alive
        mark("phase6gr_volume_release_after", weak_reference_alive=volume_alive)

        mark("phase6gr_source_release_before")
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
        mark("phase6gr_source_release_after", source_weak_reference_alive=source_alive,
             weak_reference_alive_count=weak_alive)
        if weak_alive:
            raise RuntimeError(f"weak-reference residual after release: {weak_alive}")
        return {
            "mode": "phase6gr_temperature_volume_metadata_once",
            "returned_channel_count": 7,
            "volume_conversion_calls": 1,
            "volume_metadata_accessor_calls": len(ACCESSORS),
            "weak_reference_alive_after_scope_count": 0,
            "field_body_json_npz_or_openvdb_written": False,
        }, [source_reference, converted_reference]
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "metadata_accessor_failure"
        report["first_failed_accessor"] = current_accessor
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        checkpoint("phase6gr_operation_failure", accessor=current_accessor)
        raise


shared._p3_spatial_boundary = _phase6gr_boundary
_atomic_json(AUDIT_PATH, {
    "schema": "campfire.phase6gr.kit-import-audit.v1", "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_file": str(Path(__file__).resolve()), "base_wrapper": str(BASE_PATH),
    "base_import": import_audit, "qualified_schema_path": str(SCHEMA_PATH),
    "qualification_path": str(QUALIFICATION_PATH), "mapping": mapping,
    "patch_target": "shared._p3_spatial_boundary",
    "patched": shared._p3_spatial_boundary is _phase6gr_boundary,
    "forbidden_wide_helper_used": False,
})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
