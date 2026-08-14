"""Phase 6GO bounded post-readback native-operation isolation wrapper."""

from __future__ import annotations

import asyncio
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

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
CANDIDATE_PATH = (SCRIPT_DIR / "phase6gh_public_channel_schema_candidate.json").resolve()
MAX_JSON_BYTES = 1024 * 1024
MAX_TEMP_NVDB_BYTES = 256 * 1024 * 1024
ORDER = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence", "rgba")
settings = carb.settings.get_settings()
MODE = settings.get_as_string("/phase6go/isolationMode") or "R0"
CHANNEL = settings.get_as_string("/phase6go/isolationChannel") or "temperature"
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6GO bounded JSON exceeded 1 MiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


try:
    base, import_audit = load_exact_module(
        BASE_PATH, BASE_PATH, module_name="campfire_phase6go_phase6gn_base", required_entrypoints=(),
    )
    shared = base.shared
    if MODE not in {"R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7"}:
        raise ImportError(f"unsupported isolation mode: {MODE}")
    if CHANNEL not in ORDER[:-1]:
        raise ImportError(f"unsupported isolation channel: {CHANNEL}")
except BaseException as exc:
    _atomic_json(AUDIT_PATH, {
        "schema": "campfire.phase6go.kit-import-audit.v1", "status": "fail",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "error_type": type(exc).__name__,
        "error": str(exc), "wrapper_file": str(Path(__file__).resolve()), "process_id": os.getpid(),
    })
    raise


candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
expected_handles = {row["channel"]: row for row in candidate["handles"]}
report = {
    "schema": "campfire.phase6go.post-readback-isolation.v1", "status": "running",
    "mode": MODE, "channel": CHANNEL, "channels": [CHANNEL] if MODE != "R7" else ["temperature", "velocity"],
    "public_readback_calls": 0, "numpy_asarray_calls": 0, "full_field_material_copies": 0,
    "forced_gc": False, "checkpoints": [], "handles": [], "temporary_files_retained": 0,
}


def checkpoint(name: str, **values) -> None:
    row = {"name": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **values}
    report["checkpoints"].append(row)
    report["last_checkpoint"] = name
    _atomic_json(REPORT_PATH, report)


def _mark(arguments, frame, flow, name, **values):
    shared._append_resource_marker(
        arguments["resource_marker_path"], name,
        synchronous_memory=arguments["synchronous_memory_markers"], frame=int(frame),
        active_blocks=int(flow.get_active_block_count()), isolation_mode=MODE,
        isolation_channel=CHANNEL, **values,
    )
    checkpoint(name, frame=int(frame), active_blocks=int(flow.get_active_block_count()), **values)


def _volume_public_metadata(volume, grid_data) -> dict:
    count = int(volume.get_num_grids(grid_data))
    if count < 1 or count > 4:
        raise RuntimeError(f"grid count outside 1..4: {count}")
    rows = []
    for index in range(count):
        rows.append({
            "index": index, "short_name": str(volume.get_short_grid_name(grid_data, index)),
            "grid_class": str(volume.get_grid_class(grid_data, index)),
            "value_type": str(volume.get_grid_type(grid_data, index)),
            "index_bounding_box": str(volume.get_index_bounding_box(grid_data, index)),
            "world_bounding_box": str(volume.get_world_bounding_box(grid_data, index)),
        })
    return {"grid_data_type": shared._type_name(grid_data), "grid_data_identity": int(id(grid_data)),
            "grid_count": count, "grids": rows}


def _save_temp(volume, grid_data, path: Path) -> dict:
    path.unlink(missing_ok=True)
    parameters = shared.omni.volume.SaveVolumeParameters()
    parameters.flags = shared.omni.volume.kNanoVDBCodecNone
    if not volume.save_volume(grid_data, str(path), parameters):
        raise RuntimeError("temporary NVDB save returned false")
    deadline = time.monotonic() + 10.0
    while (not path.is_file() or path.stat().st_size == 0) and time.monotonic() < deadline:
        time.sleep(0.01)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("temporary NVDB was not durable within 10 seconds")
    size = int(path.stat().st_size)
    if size > MAX_TEMP_NVDB_BYTES:
        raise RuntimeError(f"temporary NVDB exceeded {MAX_TEMP_NVDB_BYTES} bytes")
    digest_state = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest_state.update(block)
    digest = digest_state.hexdigest().upper()
    return {"bytes": size, "sha256": digest}


def _selected_schema(channel: str, metadata: dict) -> dict:
    wanted = expected_handles[channel]
    grids = metadata["grids"]
    failures = []
    if len(grids) != 1:
        failures.append("grid_count")
    elif str(grids[0]["short_name"]) != "Flow":
        failures.append("grid_short_name")
    elif str(grids[0]["grid_class"]) != str(wanted["grid_class"]):
        failures.append("grid_class")
    elif str(grids[0]["value_type"]) != str(wanted["value_type"]):
        failures.append("value_type")
    return {"pass": not failures, "failures": failures, "expected": wanted, "observed": grids}


def _bounded_flux_from_npz(paths: list[Path]) -> dict:
    from phase6es_directional_transport import face_transport
    groups = {}
    for path in paths:
        with np.load(path, allow_pickle=False) as payload:
            channel = str(payload["channel"][0])
            if channel in ("temperature", "velocity"):
                groups.setdefault(str(path.parent), {})[channel] = {
                    "local": payload["local_xyz"],
                    "values": payload["velocity_xyz"] if channel == "velocity" else payload["scalar_value"],
                    "voxel": payload["voxel_size_xyz"],
                }
    results = []
    for root, by_channel in sorted(groups.items()):
        if set(by_channel) != {"temperature", "velocity"}:
            raise RuntimeError(f"R7 missing bounded channel pair: {root}")
        left, right = by_channel["temperature"], by_channel["velocity"]
        if left["local"].shape != right["local"].shape or not np.array_equal(left["local"], right["local"]):
            raise RuntimeError(f"R7 near-Mesh coordinate mismatch: {root}")
        results.append({"collector_root": root,
            "faces": face_transport(left["local"], right["values"], left["values"], left["voxel"], 0.05)})
    if not results:
        raise RuntimeError("R7 found no bounded collector pairs")
    return {"formula": "max(dot(velocity,outward_normal),0)*scalar*voxel_face_area", "collectors": results}


def _isolation_boundary(flow, volume, arguments, frame, output, collectors, operation_state=None):
    mark = lambda name, **values: _mark(arguments, frame, flow, name, **values)
    mark("phase6go_readback_call_before")
    handles = flow.get_latest_nanovdb_readback()
    report["public_readback_calls"] = 1
    mark("phase6go_readback_call_after")
    mark("phase6go_return_bounded_before")
    if not isinstance(handles, list) or len(handles) != 7:
        raise RuntimeError(f"expected list[7], got {type(handles)!r}/{len(handles)}")
    returned = {"type": shared._type_name(handles), "count": len(handles),
                "element_types": [shared._type_name(value) for value in handles]}
    report["returned"] = returned
    mark("phase6go_return_bounded_after", returned_handle_count=7, returned_type=returned["type"])

    references = []
    if MODE != "R0":
        for index, source in enumerate(handles):
            mark("phase6go_object_metadata_before", handle_index=index)
            metadata = shared._bounded_object_metadata(source)
            metadata.update(index=index, channel=ORDER[index])
            report["handles"].append(metadata)
            mark("phase6go_object_metadata_after", handle_index=index, object_identity=metadata["identity"],
                 data_pointer=metadata.get("data_pointer"), logical_bytes=metadata.get("nbytes"))
            mark("phase6go_identity_pointer_weakref_before", handle_index=index)
            try:
                reference = weakref.ref(source)
                weak_supported = True
            except TypeError:
                reference = None
                weak_supported = False
            references.append(reference)
            metadata["weak_reference_supported"] = weak_supported
            mark("phase6go_identity_pointer_weakref_after", handle_index=index,
                 object_identity=metadata["identity"], data_pointer=metadata.get("data_pointer"),
                 weak_reference_supported=weak_supported)
        source = None
    else:
        for value in handles:
            try:
                references.append(weakref.ref(value))
            except TypeError:
                references.append(None)
        value = None

    selected_channels = [CHANNEL] if MODE != "R7" else ["temperature", "velocity"]
    volume_metadata = {}
    temporary_paths = []
    if MODE in {"R2", "R3", "R4"}:
        source = handles[ORDER.index(CHANNEL)]
        mark("phase6go_buffer_to_volume_before", handle_index=ORDER.index(CHANNEL), source_identity=id(source))
        grid_data = flow.buffer_to_volume(source)
        mark("phase6go_buffer_to_volume_after", handle_index=ORDER.index(CHANNEL), grid_data_identity=id(grid_data))
        mark("phase6go_volume_metadata_before", handle_index=ORDER.index(CHANNEL), grid_data_identity=id(grid_data))
        volume_metadata[CHANNEL] = _volume_public_metadata(volume, grid_data)
        mark("phase6go_volume_metadata_after", handle_index=ORDER.index(CHANNEL),
             grid_count=volume_metadata[CHANNEL]["grid_count"])
        if MODE in {"R3", "R4"}:
            path = output.parent / f"phase6go_{MODE}_{CHANNEL}.nvdb"
            mark("phase6go_temporary_nvdb_save_before", handle_index=ORDER.index(CHANNEL))
            saved = _save_temp(volume, grid_data, path)
            mark("phase6go_temporary_nvdb_save_after", handle_index=ORDER.index(CHANNEL), **saved)
            if MODE == "R4":
                mark("phase6go_raw_schema_validation_before", handle_index=ORDER.index(CHANNEL))
                validation = _selected_schema(CHANNEL, volume_metadata[CHANNEL])
                report["selected_schema_validation"] = validation
                mark("phase6go_raw_schema_validation_after", handle_index=ORDER.index(CHANNEL), schema_pass=validation["pass"])
                if not validation["pass"]:
                    raise RuntimeError(f"selected schema failed: {validation['failures']}")
            path.unlink(missing_ok=True)
            mark("phase6go_temporary_nvdb_release_after", handle_index=ORDER.index(CHANNEL), retained=path.exists())
        report["volume_metadata"] = volume_metadata
        mark("phase6go_volume_release_before", handle_index=ORDER.index(CHANNEL), grid_data_identity=id(grid_data))
        grid_data = None
        source = None
        mark("phase6go_volume_release_after", handle_index=ORDER.index(CHANNEL))

    if MODE in {"R5", "R6", "R7"}:
        rois = shared._p3_world_rois()
        for selected in selected_channels:
            source = handles[ORDER.index(selected)]
            path = output.parent / f"phase6go_{MODE}_{selected}.nvdb"
            if MODE in {"R6", "R7"}:
                mark("phase6go_near_mesh_collector_before", channel=selected,
                     collector_count=len(collectors))
            mark("phase6go_save_and_sample_before", channel=selected, handle_index=ORDER.index(selected))
            details = shared._save_and_sample(
                flow, volume, source, selected, path, rois,
                spatial_collector=(collectors if MODE in {"R6", "R7"} else None),
                spatial_velocity_only=False, frame=frame,
                profile_threshold={"temperature": 1.01, "velocity": 0.01}[selected],
            )
            report.setdefault("sampling", {})[selected] = details
            mark("phase6go_save_and_sample_after", channel=selected, handle_index=ORDER.index(selected),
                 temporary_retained=path.exists())
            if MODE in {"R6", "R7"}:
                mark("phase6go_near_mesh_collector_after", channel=selected,
                     collector_count=len(collectors), collector_file_count=sum(len(item.files) for item in collectors))
            source = None
            details = None
        if MODE == "R7":
            mark("phase6go_directional_flux_before")
            paths = [Path(record["path"]) for collector in collectors for record in collector.files]
            report["directional_flux"] = _bounded_flux_from_npz(paths)
            mark("phase6go_directional_flux_after", collider_artifact_count=len(paths))

    mark("phase6go_release_sequence_before")
    for index in range(len(handles)):
        mark("phase6go_handle_release_before", handle_index=index)
        handles[index] = None
        mark("phase6go_handle_release_after", handle_index=index,
             weak_reference_alive=(references[index]() is not None if references[index] is not None else None))
    handles.clear()
    handles = None
    alive = sum(reference is not None and reference() is not None for reference in references)
    report["weak_reference_alive_after_release_count"] = int(alive)
    report["status"] = "pass" if alive == 0 else "fail"
    mark("phase6go_release_sequence_after", weak_reference_alive_count=int(alive))
    if alive:
        raise RuntimeError(f"weak-reference residual after release: {alive}")
    return {
        "mode": "phase6go_post_readback_isolation", "isolation_mode": MODE,
        "isolation_channel": CHANNEL, "returned_channel_count": 7,
        "weak_reference_alive_after_scope_count": 0,
        "field_body_json_npz_or_openvdb_written": MODE in {"R3", "R4", "R5", "R6", "R7"},
        "temporary_field_body_deleted_before_return": MODE in {"R3", "R4", "R5", "R6", "R7"},
    }, references


shared._p3_spatial_boundary = _isolation_boundary
_atomic_json(AUDIT_PATH, {
    "schema": "campfire.phase6go.kit-import-audit.v1", "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(), "wrapper_file": str(Path(__file__).resolve()),
    "base_wrapper": str(BASE_PATH), "base_import": import_audit, "mode": MODE, "channel": CHANNEL,
    "patch_target": "shared._p3_spatial_boundary", "patched": shared._p3_spatial_boundary is _isolation_boundary,
})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
