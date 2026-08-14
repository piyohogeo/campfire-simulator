"""Phase 6GD bounded public NanoVDB handle metadata discovery wrapper.

This wrapper deliberately does not assign semantic channel names.  It reuses
the frozen Phase 6GC stage, startup, source, resource-marker, and lifecycle
implementation and replaces only the single-readback boundary with a bounded
metadata inspection of ``handle[0]`` through ``handle[n-1]``.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
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

SHARED_PATH = (SCRIPT_DIR / "probe_phase6gc_shared_supply_comparison.py").resolve()
settings = carb.settings.get_settings()
audit_path = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()

PER_HANDLE_FILE_LIMIT = 256 * 1024 * 1024
TOTAL_FILE_LIMIT = 512 * 1024 * 1024
MAX_GRID_COUNT = 4
MAX_DOC_BYTES = 4096


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


try:
    shared, import_audit = load_exact_module(
        SHARED_PATH,
        SHARED_PATH,
        module_name="campfire_phase6gd_shared_supply_probe",
        required_entrypoints=("_run", "_append_resource_marker", "_type_name"),
    )
    _atomic_json(
        audit_path,
        {
            "schema": "campfire.phase6gd.kit-import-audit.v1",
            "status": "pass",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "wrapper_file": str(Path(__file__).resolve()),
            "working_directory": str(Path.cwd()),
            "kit_app_ready_exec": True,
            "import": import_audit,
        },
    )
except BaseException as exc:
    _atomic_json(
        audit_path,
        {
            "schema": "campfire.phase6gd.kit-import-audit.v1",
            "status": "fail",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "wrapper_file": str(Path(__file__).resolve()),
            "working_directory": str(Path.cwd()),
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    )
    raise


def _unavailable(reason: str = "public API unavailable") -> dict:
    return {"status": "unavailable", "reason": reason}


def _json_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else str(value)
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    for names in (("x", "y", "z"), ("min", "max")):
        if all(hasattr(value, name) for name in names):
            return {name: _json_value(getattr(value, name)) for name in names}
    try:
        return [_json_value(item) for item in value]
    except TypeError:
        return str(value)


def _call_public(target, name: str, *args):
    method = getattr(target, name, None)
    if method is None:
        return _unavailable(f"{name} is not exposed")
    try:
        return _json_value(method(*args))
    except Exception as exc:
        return _unavailable(f"{type(exc).__name__}: {exc}")


def _array_metadata(value) -> dict:
    result = {
        "python_type": shared._type_name(value),
        "native_type": shared._type_name(value),
        "object_identity": int(id(value)),
        "is_numpy_array": isinstance(value, np.ndarray),
    }
    try:
        weakref.ref(value)
        result["weak_reference_supported"] = True
    except TypeError:
        result["weak_reference_supported"] = False
    for name in ("dtype", "shape", "strides", "nbytes"):
        try:
            item = getattr(value, name)
            if name in ("shape", "strides"):
                item = [int(component) for component in item]
            elif name == "nbytes":
                item = int(item)
            else:
                item = str(item)
            result[name] = item
        except Exception as exc:
            result[name] = _unavailable(f"{type(exc).__name__}: {exc}")
    result["logical_bytes"] = result.get("nbytes", _unavailable())
    try:
        flags = value.flags
        result["c_contiguous"] = bool(flags.c_contiguous)
        result["f_contiguous"] = bool(flags.f_contiguous)
        result["writable"] = bool(flags.writeable)
    except Exception as exc:
        unavailable = _unavailable(f"{type(exc).__name__}: {exc}")
        result.update(c_contiguous=unavailable, f_contiguous=unavailable, writable=unavailable)
    try:
        data = value.__array_interface__.get("data")
        result["data_pointer"] = int(data[0]) if data and int(data[0]) > 0 else _unavailable()
    except Exception as exc:
        result["data_pointer"] = _unavailable(f"{type(exc).__name__}: {exc}")
    return result


def _typed_nanovdb_metadata(path: Path, grid_type: str) -> dict:
    handle = shared.nanovdb.io.readGrid(str(path))
    grid = None
    if "Vec3" in grid_type:
        grid = handle.vec3fGrid()
    elif "Float" in grid_type:
        grid = handle.floatGrid()
    if grid is None:
        return {
            "value_type": grid_type,
            "nano_grid": _unavailable("bundled accessor supports only Float and Vec3f in this probe"),
        }
    voxel = grid.voxelSize()
    result = {
        "grid_name": _call_public(grid, "gridName"),
        "grid_class": _call_public(grid, "gridClass"),
        "value_type": grid_type,
        "active_voxel_count": _call_public(grid, "activeVoxelCount"),
        "voxel_size": [shared._nanovdb_component(voxel, axis) for axis in range(3)],
        "index_bounding_box": _call_public(grid, "indexBBox"),
        "world_bounding_box": _call_public(grid, "worldBBox"),
        "background_value": _unavailable("no stable public background accessor confirmed"),
        "metadata_keys": _unavailable("no public arbitrary-metadata key iterator confirmed"),
    }
    return result


def _volume_metadata(flow, volume, value, temporary_path: Path, remaining_total: int) -> tuple[dict, int]:
    grid_data = flow.buffer_to_volume(value)
    count = int(volume.get_num_grids(grid_data))
    if count < 1 or count > MAX_GRID_COUNT:
        raise RuntimeError(f"public volume grid count {count} is outside 1..{MAX_GRID_COUNT}")
    grids = []
    for grid_index in range(count):
        grid_type = str(volume.get_grid_type(grid_data, grid_index))
        grids.append(
            {
                "index": grid_index,
                "short_name": _json_value(volume.get_short_grid_name(grid_data, grid_index)),
                "grid_class": _json_value(volume.get_grid_class(grid_data, grid_index)),
                "grid_type": grid_type,
                "index_bounding_box": _json_value(volume.get_index_bounding_box(grid_data, grid_index)),
                "world_bounding_box": _json_value(volume.get_world_bounding_box(grid_data, grid_index)),
            }
        )
    parameters = shared.omni.volume.SaveVolumeParameters()
    parameters.flags = shared.omni.volume.kNanoVDBCodecNone
    temporary_path.unlink(missing_ok=True)
    if not volume.save_volume(grid_data, str(temporary_path), parameters):
        raise RuntimeError("public omni.volume save failed")
    deadline = time.monotonic() + 10.0
    while (not temporary_path.is_file() or temporary_path.stat().st_size == 0) and time.monotonic() < deadline:
        time.sleep(0.01)
    if not temporary_path.is_file():
        raise RuntimeError("temporary NanoVDB metadata file was not produced")
    file_bytes = int(temporary_path.stat().st_size)
    if file_bytes > PER_HANDLE_FILE_LIMIT or file_bytes > remaining_total:
        raise RuntimeError(f"temporary NanoVDB size {file_bytes} exceeded bounded diagnostic limit")
    try:
        typed = _typed_nanovdb_metadata(temporary_path, grids[0]["grid_type"])
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "grid_data_python_type": shared._type_name(grid_data),
        "grid_count": count,
        "grids": grids,
        "nano_grid": typed,
        "temporary_file_bytes": file_bytes,
        "temporary_file_retained": False,
    }, file_bytes


def _extension_version(app, extension_name: str):
    manager = app.get_extension_manager()
    extension_id = manager.get_enabled_extension_id(extension_name)
    metadata = manager.get_extension_dict(extension_id) if extension_id else None
    return {
        "enabled_id": extension_id or None,
        "version": (metadata or {}).get("package", {}).get("version") or "unavailable",
    }


def _api_metadata(flow) -> dict:
    method = flow.get_latest_nanovdb_readback
    try:
        signature = str(inspect.signature(method))
    except Exception as exc:
        signature = f"unavailable: {type(exc).__name__}: {exc}"
    doc = inspect.getdoc(method) or "unavailable"
    if len(doc.encode("utf-8")) > MAX_DOC_BYTES:
        doc = doc.encode("utf-8")[:MAX_DOC_BYTES].decode("utf-8", errors="replace")
    app = shared.omni.kit.app.get_app()
    return {
        "api_name": "omni.flowusd._flowusd.IFlowUsd.get_latest_nanovdb_readback",
        "python_callable_type": shared._type_name(method),
        "signature": signature,
        "doc": doc,
        "kit_build": str(getattr(app, "get_build_version", lambda: "unavailable")()),
        "flow_extension": _extension_version(app, "omni.flowusd"),
        "volume_extension": _extension_version(app, "omni.volume"),
        "nanovdb_python_version": str(getattr(shared.nanovdb, "__version__", "unavailable")),
    }


def _bounded_schema_boundary(flow, volume, arguments, frame, output, collectors, operation_state=None):
    del collectors
    operation_state = operation_state or {}
    mark = lambda name, **values: shared._append_resource_marker(
        arguments["resource_marker_path"],
        name,
        synchronous_memory=arguments["synchronous_memory_markers"],
        frame=frame,
        active_blocks=int(flow.get_active_block_count()),
        **operation_state,
        **values,
    )
    mark("schema_readback_call_before")
    returned = flow.get_latest_nanovdb_readback()
    mark("schema_readback_call_after", returned_handle_count=len(returned))
    handles = returned if isinstance(returned, list) else list(returned)
    if handles is not returned:
        del returned
    if len(handles) > 16:
        raise RuntimeError(f"returned handle count {len(handles)} exceeded bounded maximum 16")
    weak_references = []
    rows = []
    total_temporary_bytes = 0
    metadata_root = output.parent / "channel-schema-metadata"
    metadata_root.mkdir(parents=True, exist_ok=True)
    for index in range(len(handles)):
        file_bytes = 0
        value = handles[index]
        mark("schema_handle_started", handle_index=index)
        try:
            reference = weakref.ref(value)
        except TypeError:
            reference = None
        weak_references.append(reference)
        row = {"index": index, "label": f"handle[{index}]", **_array_metadata(value)}
        try:
            volume_metadata, file_bytes = _volume_metadata(
                flow,
                volume,
                value,
                metadata_root / f"handle_{index}.nvdb",
                TOTAL_FILE_LIMIT - total_temporary_bytes,
            )
            total_temporary_bytes += file_bytes
            row["volume"] = volume_metadata
        except Exception as exc:
            row["volume"] = _unavailable(f"{type(exc).__name__}: {exc}")
        semantic = row.get("volume", {}).get("nano_grid", {}).get("grid_name") if isinstance(row.get("volume"), dict) else None
        row["public_channel_or_semantic_name"] = semantic if semantic not in (None, "", "Flow") else "unavailable"
        digest_payload = {
            key: value for key, value in row.items() if key not in ("object_identity", "data_pointer")
        }
        row["metadata_sha256"] = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest().upper()
        rows.append(row)
        handles[index] = None
        del value
        mark("schema_handle_released", handle_index=index, temporary_bytes=file_bytes)
    handles.clear()
    del handles
    result = {
        "mode": "bounded_public_channel_schema_discovery",
        "returned_handle_count": len(rows),
        "handle_order": [row["label"] for row in rows],
        "handles": rows,
        "channel_objects": rows,
        "api": _api_metadata(flow),
        "limits": {
            "maximum_handles": 16,
            "maximum_grids_per_handle": MAX_GRID_COUNT,
            "per_handle_temporary_file_bytes": PER_HANDLE_FILE_LIMIT,
            "total_temporary_file_bytes": TOTAL_FILE_LIMIT,
            "maximum_doc_bytes": MAX_DOC_BYTES,
        },
        "total_temporary_file_bytes": total_temporary_bytes,
        "full_field_json_or_npz_written": False,
        "formal_channel_names_assigned": False,
        "unknown_handles_preserved": True,
        "forced_gc": False,
        "private_api_used": False,
        "public_release_method_used": False,
    }
    report_path = metadata_root / "bounded_handle_metadata.json"
    _atomic_json(report_path, result)
    result["bounded_metadata_path"] = str(report_path)
    result["bounded_metadata_file_bytes"] = report_path.stat().st_size
    mark("schema_metadata_complete", handle_count=len(rows), metadata_file_bytes=report_path.stat().st_size)
    return result, weak_references


shared._p3_spatial_boundary = _bounded_schema_boundary

_original_append = shared._append_resource_marker


def _synchronized_append(path, marker, *args, **kwargs):
    _original_append(path, marker, *args, **kwargs)
    if marker != "measurement_complete":
        return
    acknowledgement = Path(settings.get_as_string("/phase6fz/measurementCommitAck")).resolve()
    failure = Path(settings.get_as_string("/phase6fz/measurementCommitFailure")).resolve()
    timeout = float(settings.get_as_float("/phase6fz/measurementCommitTimeoutSeconds") or 60.0)
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if acknowledgement.is_file():
            return
        if failure.is_file():
            raise RuntimeError("Phase 6GD pre-close measurement committer failed")
        time.sleep(0.05)
    raise TimeoutError("Phase 6GD pre-close measurement commit acknowledgement timed out")


shared._append_resource_marker = _synchronized_append

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
