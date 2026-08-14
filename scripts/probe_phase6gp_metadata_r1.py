"""Phase 6GP: one public readback and bounded Python metadata only."""

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

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
MAX_JSON_BYTES = 128 * 1024
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6GP bounded JSON exceeded 128 KiB")
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
    module_name="campfire_phase6gp_phase6gn_base",
    required_entrypoints=(),
)
shared = base.shared
report = {
    "schema": "campfire.phase6gp.metadata-r1-operation.v1",
    "status": "running",
    "operation_result": "running",
    "public_readback_calls": 0,
    "numpy_asarray_calls": 0,
    "volume_conversion_calls": 0,
    "field_body_files_written": 0,
    "sampling_calls": 0,
    "collector_calls": 0,
    "flux_calls": 0,
    "checkpoints": [],
    "slots": [],
    "last_completed_slot": None,
}


def checkpoint(name: str, **values) -> None:
    row = {"name": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **values}
    report["checkpoints"].append(row)
    report["last_operation_marker"] = name
    _atomic_json(REPORT_PATH, report)


def _mark(arguments, frame, flow, name, **values) -> None:
    shared._append_resource_marker(
        arguments["resource_marker_path"],
        name,
        synchronous_memory=arguments["synchronous_memory_markers"],
        frame=int(frame),
        active_blocks=int(flow.get_active_block_count()),
        phase="phase6gp",
        isolation_mode="R1_metadata_only",
        **values,
    )
    checkpoint(name, frame=int(frame), active_blocks=int(flow.get_active_block_count()), **values)


def _metadata_boundary(flow, volume, arguments, frame, output, collectors, operation_state=None):
    del volume, output, collectors, operation_state
    mark = lambda name, **values: _mark(arguments, frame, flow, name, **values)
    handles = None
    references = []
    try:
        mark("phase6gp_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        mark("phase6gp_readback_after")
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected builtins.list with 7 slots, got {type_name(handles)}/{len(handles)}")
        report["returned"] = {
            "python_type": type_name(handles),
            "count": len(handles),
            "slot_types": [type_name(value) for value in handles],
        }
        mark("phase6gp_handle_count_type_after", handle_count=7, returned_type=type_name(handles))

        for slot in range(7):
            mark("phase6gp_slot_metadata_before", slot=slot)
            value = handles[slot]
            metadata = bounded_slot_metadata(slot, value)
            report["slots"].append(metadata)
            report["last_completed_slot"] = slot
            try:
                references.append(weakref.ref(value))
            except TypeError:
                references.append(None)
            value = None
            mark(
                "phase6gp_slot_metadata_after",
                slot=slot,
                python_type=metadata["python_type"],
                ndim=metadata["ndim"],
                shape=metadata["shape"],
                dtype=metadata["dtype"],
                size=metadata["size"],
                nbytes=metadata["nbytes"],
                empty=metadata["empty"],
            )
        mark("phase6gp_metadata_all_after", completed_slot_count=len(report["slots"]))

        mark("phase6gp_reference_release_before")
        for slot in range(7):
            handles[slot] = None
        handles.clear()
        handles = None
        weak_alive = sum(reference is not None and reference() is not None for reference in references)
        report["weak_reference_alive_after_release_count"] = int(weak_alive)
        report["operation_result"] = "pass" if weak_alive == 0 else "failure"
        report["status"] = "pass" if weak_alive == 0 else "fail"
        mark("phase6gp_reference_release_after", weak_reference_alive_count=int(weak_alive))
        if weak_alive:
            raise RuntimeError(f"weak-reference residual after release: {weak_alive}")
        return {
            "mode": "phase6gp_metadata_r1",
            "returned_channel_count": 7,
            "weak_reference_alive_after_scope_count": 0,
            "field_body_json_npz_or_openvdb_written": False,
        }, references
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "failure"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        checkpoint("phase6gp_operation_failure", last_completed_slot=report["last_completed_slot"])
        raise


shared._p3_spatial_boundary = _metadata_boundary
_atomic_json(AUDIT_PATH, {
    "schema": "campfire.phase6gp.kit-import-audit.v1",
    "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_file": str(Path(__file__).resolve()),
    "base_wrapper": str(BASE_PATH),
    "base_import": import_audit,
    "patch_target": "shared._p3_spatial_boundary",
    "patched": shared._p3_spatial_boundary is _metadata_boundary,
})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
