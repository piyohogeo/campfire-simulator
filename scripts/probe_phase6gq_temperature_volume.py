"""Phase 6GQ: convert only qualified slot 0 (temperature) once."""

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
from phase6gq_temperature_volume_contract import validate_temperature_slot

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
SCHEMA_PATH = (SCRIPT_DIR / "phase6gh_public_channel_schema_candidate.json").resolve()
MAX_JSON_BYTES = 128 * 1024
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6GQ bounded JSON exceeded 128 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


base, import_audit = load_exact_module(
    BASE_PATH,
    BASE_PATH,
    module_name="campfire_phase6gq_phase6gn_base",
    required_entrypoints=(),
)
shared = base.shared
qualified_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
mapping = validate_temperature_slot(qualified_schema)
if not mapping["pass"]:
    raise ImportError("qualified public-channel schema no longer maps slot 0 to nonempty temperature")

report = {
    "schema": "campfire.phase6gq.temperature-volume-operation.v1",
    "status": "running",
    "operation_result": "running",
    "mapping": mapping,
    "public_readback_calls": 0,
    "volume_conversion_calls": 0,
    "conversion_returned": False,
    "numpy_asarray_calls": 0,
    "volume_metadata_calls": 0,
    "field_body_files_written": 0,
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
        phase="phase6gq", isolation_mode="temperature_volume_once", **values,
    )
    checkpoint(name, frame=int(frame), active_blocks=int(flow.get_active_block_count()), **values)


def _temperature_volume_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    del volume_provider, output, collectors, operation_state
    mark = lambda name, **values: _mark(arguments, frame, flow, name, **values)
    handles = None
    source = None
    converted = None
    references = []
    try:
        mark("phase6gq_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        mark("phase6gq_readback_after")
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected builtins.list with 7 slots, got {type_name(handles)}/{len(handles)}")
        report["returned"] = {
            "python_type": type_name(handles),
            "count": len(handles),
            "slot_types": [type_name(value) for value in handles],
        }
        mark("phase6gq_handle_count_type_after", handle_count=7, returned_type=type_name(handles))

        source = handles[0]
        source_metadata = bounded_slot_metadata(0, source)
        report["source"] = {"channel": "temperature", **source_metadata}
        try:
            source_reference = weakref.ref(source)
        except TypeError:
            source_reference = None
        references.append(source_reference)
        mark("phase6gq_slot0_selected_after", channel="temperature", **source_metadata)

        mark("phase6gq_nonselected_release_before")
        for slot in range(1, 7):
            handles[slot] = None
        mark("phase6gq_nonselected_release_after", released_slots=[1, 2, 3, 4, 5, 6])

        mark("phase6gq_volume_conversion_before", slot=0, channel="temperature")
        report["volume_conversion_calls"] = 1
        converted = flow.buffer_to_volume(source)
        report["conversion_returned"] = True
        mark("phase6gq_volume_conversion_after", slot=0, channel="temperature")
        report["volume_return_type"] = type_name(converted)
        try:
            converted_reference = weakref.ref(converted)
        except TypeError:
            converted_reference = None
        references.append(converted_reference)
        mark("phase6gq_volume_return_type_after", python_type=report["volume_return_type"])

        mark("phase6gq_volume_release_before")
        converted = None
        volume_alive = converted_reference() is not None if converted_reference is not None else None
        report["volume_weak_reference_alive_after_release"] = volume_alive
        mark("phase6gq_volume_release_after", weak_reference_alive=volume_alive)

        mark("phase6gq_slot0_release_before")
        handles[0] = None
        source = None
        handles.clear()
        handles = None
        source_alive = source_reference() is not None if source_reference is not None else None
        weak_alive = sum(reference is not None and reference() is not None for reference in references)
        report["source_weak_reference_alive_after_release"] = source_alive
        report["weak_reference_alive_after_release_count"] = int(weak_alive)
        report["operation_result"] = "pass" if weak_alive == 0 else "failure"
        report["status"] = "pass" if weak_alive == 0 else "fail"
        mark("phase6gq_slot0_release_after", source_weak_reference_alive=source_alive,
             weak_reference_alive_count=int(weak_alive))
        if weak_alive:
            raise RuntimeError(f"weak-reference residual after release: {weak_alive}")
        return {
            "mode": "phase6gq_temperature_volume_once",
            "returned_channel_count": 7,
            "volume_conversion_calls": 1,
            "weak_reference_alive_after_scope_count": 0,
            "field_body_json_npz_or_openvdb_written": False,
        }, references
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "conversion_boundary_failure"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        checkpoint("phase6gq_operation_failure", conversion_returned=report["conversion_returned"])
        raise


shared._p3_spatial_boundary = _temperature_volume_boundary
_atomic_json(AUDIT_PATH, {
    "schema": "campfire.phase6gq.kit-import-audit.v1", "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_file": str(Path(__file__).resolve()), "base_wrapper": str(BASE_PATH),
    "base_import": import_audit, "qualified_schema_path": str(SCHEMA_PATH),
    "mapping": mapping, "patch_target": "shared._p3_spatial_boundary",
    "patched": shared._p3_spatial_boundary is _temperature_volume_boundary,
})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
