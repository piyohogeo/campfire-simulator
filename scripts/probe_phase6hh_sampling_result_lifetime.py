"""Phase 6HH one-variable velocity sampling-result lifetime probe."""

from __future__ import annotations

import asyncio
import sys
import weakref
from datetime import datetime, timezone
from pathlib import Path

import carb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module
import phase6hf_operation_schema as hf_schema
from phase6hh_retention_contract import (
    COMPLETE_MARKER,
    CONDITIONS,
    FAILURE_MARKER,
    ROW_BY_NAME,
    SCHEMA,
    complete_operation,
    new_runtime_report,
    write_operation_report,
)

HB_PATH = (SCRIPT_DIR / "probe_phase6hb_candidate_lifecycle.py").resolve()
settings = carb.settings.get_settings()
CONDITION = settings.get_as_string("/phase6ep/startupProbeLabel") or ""
if CONDITION not in ROW_BY_NAME:
    raise ImportError(f"unsupported Phase 6HH condition: {CONDITION!r}")
ROW = ROW_BY_NAME[CONDITION]

hb, hb_audit = load_exact_module(
    HB_PATH, HB_PATH, module_name="campfire_phase6hh_phase6hb_base", required_entrypoints=()
)
hb.report = new_runtime_report(condition=CONDITION, attempt_id=CONDITION)


def checkpoint(name: str, **values) -> None:
    hf_schema.append_checkpoint(hb.report, name, **values)
    write_operation_report(hb.REPORT_PATH, hb.report)


original_append_resource_marker = hb.shared._append_resource_marker


def append_resource_marker(path, name, *args, **kwargs):
    translated = name.replace("phase6hb_", "phase6hh_", 1) if name.startswith("phase6hb_") else name
    if kwargs.get("phase") == "phase6hb":
        kwargs["phase"] = "phase6hh"
    return original_append_resource_marker(path, translated, *args, **kwargs)


def velocity_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    operation_state = operation_state or {}

    def marker(name: str, **values) -> None:
        canonical = name if name.startswith("phase6hh_") else f"phase6hh_{name}"
        append_resource_marker(
            arguments["resource_marker_path"],
            canonical,
            synchronous_memory=arguments["synchronous_memory_markers"],
            frame=int(frame),
            active_blocks=int(flow.get_active_block_count()),
            phase="phase6hh",
            retention_mode=ROW["retention"],
            **operation_state,
            **values,
        )
        checkpoint(canonical, frame=int(frame), **values)

    handles = None
    references = []
    velocity_alias = None
    source = None
    volume_row = None
    grid = None
    velocity_result = None
    metadata_root = output.parent / f"phase6hh-schema-f{int(frame):04d}"
    metadata_root.mkdir(parents=True, exist_ok=True)
    velocity_path = output.parent / f"p3_f{int(frame):04d}_velocity.nvdb"
    try:
        marker("readback_before")
        handles = flow.get_latest_nanovdb_readback()
        hf_schema.increment_counter(hb.report, "readback")
        marker("readback_after", returned_handle_count=len(handles))
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected public list of 7 handles, got {type(handles)!r}/{len(handles)}")
        marker("list_count_check_after", returned_handle_count=7, returned_type=hb.shared._type_name(handles))
        references = [weakref.ref(value) for value in handles]

        schema_rows = []
        for index, source in enumerate(handles):
            marker("array_metadata_before", handle_index=index)
            hf_schema.increment_counter(hb.report, "array_metadata")
            row = hb.discovery._array_metadata(source)
            schema_rows.append({
                "index": index,
                "python_type": row.get("python_type"),
                "dtype": row.get("dtype"),
                "shape": row.get("shape"),
                "element_count": int(source.size),
                "logical_bytes": int(source.nbytes),
            })
            marker("array_metadata_after", handle_index=index, python_type=row.get("python_type"), logical_bytes=int(source.nbytes))
        hb.report["bounded_array_metadata"] = schema_rows

        total_bytes = 0
        expected_channels = list(hb.candidate["exact_order"])
        prefix_rows = []

        def schema_marker(name: str, **values) -> None:
            marker(name.replace("phase6gz_", "", 1), **values)

        for index in range(1, 6):
            path = metadata_root / f"handle_{index}.nvdb"
            for counter in ("schema_volume_conversion", "schema_metadata", "schema_temporary_save", "schema_typed_read"):
                hf_schema.increment_counter(hb.report, counter)
            volume_row, file_bytes = hb.gz._instrumented_schema_volume(
                flow, volume_provider, handles[index], path,
                hb.discovery.TOTAL_FILE_LIMIT - total_bytes, schema_marker, index,
            )
            total_bytes += file_bytes
            grid = volume_row["grids"][0]
            wanted = hb.gz.schema_contract["schema_gate"]["handles"][index]
            actual = {
                "channel": expected_channels[index],
                "short_name": grid.get("short_name"),
                "grid_class": grid.get("grid_class"),
                "grid_type": str(grid.get("grid_type")),
                "file_bytes": file_bytes,
            }
            if actual["channel"] != wanted["channel"]:
                raise RuntimeError(f"non-temperature schema channel mismatch at slot {index}")
            prefix_rows.append(actual)
        hb.report["non_temperature_schema_prefix"] = prefix_rows

        velocity_index = expected_channels.index("velocity")
        velocity_alias = handles[velocity_index]
        hf_schema.increment_counter(hb.report, "velocity_alias_metadata")
        alias_metadata = hb.shared._bounded_object_metadata(velocity_alias)
        hb.report["velocity_alias"] = {
            "handle_index": velocity_index,
            "python_type": alias_metadata.get("type"),
            "shape": alias_metadata.get("shape"),
            "dtype": alias_metadata.get("dtype"),
            "element_count": alias_metadata.get("size"),
            "logical_bytes": alias_metadata.get("nbytes"),
        }
        marker("velocity_alias_metadata_complete", **hb.report["velocity_alias"])

        counter_after_events = {
            "velocity_second_conversion_after": "velocity_second_conversion",
            "velocity_file_save_after": "velocity_file_save",
            "velocity_file_durability_check_after": "velocity_file_durability_check",
            "velocity_file_read_after": "velocity_file_read",
            "velocity_vector_grid_access_after": "velocity_vector_grid_access",
            "velocity_basic_metadata_after": "velocity_basic_metadata",
            "velocity_roi_sampling_after": "velocity_roi_sampling",
            "velocity_temporary_file_deletion_after": "velocity_temporary_file_deletion",
        }

        def step_observer(name: str, **values) -> None:
            counter = counter_after_events.get(name)
            if counter is not None:
                hf_schema.increment_counter(hb.report, counter)
            if name == "velocity_roi_sampling_after":
                hb.report["executed_roi_names"].append(values["roi"])
                hb.report["sampling_bounded_metadata"] = {
                    key: values.get(key)
                    for key in ("available", "voxel_count", "nonzero_voxel_count", "mean", "sum", "p95", "maximum")
                }
            elif name == "velocity_roi_result_store_before":
                hb.report["sampling_result_evidence"] = {
                    key: values.get(key)
                    for key in (
                        "python_type", "container_structure", "keys", "value_types",
                        "contains_numpy", "contains_native_wrapper", "weakref_supported",
                        "sample_result_identity",
                    )
                }
            elif name == "velocity_roi_result_store_after":
                hb.report["sampling_result_retained_count"] = int(values["retained_count_after"])
                hb.report["sampling_same_object_retained"] = bool(values["same_object_retained"])
                hb.report["sampling_retained_identity"] = values.get("retained_identity")
            elif name == "velocity_roi_local_result_clear":
                hb.report["sampling_local_result_clear_completed"] = values.get("local_result_is_none") is True
            marker(name, **values)

        roi_count = int(ROW["roi_count"])
        retention = None if roi_count == 0 else str(ROW["retention"])
        marker("velocity_pipeline_before", roi_count=roi_count, roi_names=[] if not roi_count else ["scene"])
        velocity_result = hb.shared._save_and_sample(
            flow,
            volume_provider,
            velocity_alias,
            "velocity",
            velocity_path,
            hb.shared._p3_world_rois(),
            spatial_collector=None,
            spatial_velocity_only=False,
            frame=frame,
            profile_threshold=0.01,
            diagnostic_stop_after="basic_metadata" if roi_count == 0 else "roi_sampling",
            diagnostic_step_observer=step_observer,
            diagnostic_roi_limit=None if roi_count == 0 else 1,
            diagnostic_roi_result_retention=retention,
        )
        marker("velocity_helper_returned", roi_count=roi_count, returned_roi_count=len(velocity_result.get("rois", {})))

        if roi_count == 0:
            hb.report["velocity_result"] = velocity_result
        else:
            bounded_copy = dict(hb.report["sampling_bounded_metadata"])
            report_copy = {
                "active_voxel_count": velocity_result["active_voxel_count"],
                "voxel_size": list(velocity_result["voxel_size"]),
                "rois": {"scene": bounded_copy},
            }
            if ROW["retention"] == "retain":
                if velocity_result.get("rois", {}).get("scene") is None:
                    raise RuntimeError("retained result is absent from velocity_result")
                if id(velocity_result["rois"]["scene"]) != hb.report["sampling_retained_identity"]:
                    raise RuntimeError("retained sampling-result identity mismatch")
                hb.report["velocity_result"] = velocity_result
                hb.report["sampling_result_retained_to_operation_report"] = True
            else:
                if velocity_result.get("rois"):
                    raise RuntimeError("immediate-clear result unexpectedly remained in helper result")
                hb.report["velocity_result"] = report_copy
                hb.report["sampling_result_retained_to_operation_report"] = False
        marker(
            "velocity_pipeline_after",
            roi_count=roi_count,
            executed_roi_names=list(hb.report["executed_roi_names"]),
            temporary_present=velocity_path.exists(),
            retained_count=int(hb.report["sampling_result_retained_count"]),
        )

        marker("release_before", local_result_count=roi_count)
        velocity_result = None
        marker("local_velocity_result_clear", local_velocity_result_is_none=velocity_result is None)
        velocity_alias = None
        source = None
        volume_row = None
        grid = None
        marker("alias_grid_volume_release_complete")
        for index in range(len(handles)):
            handles[index] = None
        handles.clear()
        handles = None
        weak_alive = sum(reference() is not None for reference in references)
        hb.report["weak_reference_alive_after_release_count"] = weak_alive
        hb.report["references_released"] = weak_alive == 0
        marker("handle_release_after", weak_reference_alive_count=weak_alive)
        if weak_alive:
            raise RuntimeError(f"weak-reference residual after release: {weak_alive}")
        for key in (
            "velocity_save", "velocity_sampling", "velocity_collector", "velocity_profile",
            "temperature_conversion", "temperature_metadata", "temperature_save",
            "temperature_typed_read", "temperature_sampling", "temperature_collector",
        ):
            if hb.report["calls"][key] != 0:
                raise RuntimeError(f"prohibited profile/collector/temperature counter is nonzero: {key}")
        marker("operation_report_write_before")
        complete_operation(hb.report)
        write_operation_report(hb.REPORT_PATH, hb.report)
        return {
            "mode": f"phase6hh_{ROW['mode']}",
            "returned_channel_count": 7,
            "field_body_json_npz_or_openvdb_written": False,
            "weak_reference_alive_after_scope_count": 0,
        }, references
    except BaseException as exc:
        hb.report["status"] = "fail"
        hb.report["operation_result"] = "operation_failure"
        hb.report["operation_complete"] = False
        hb.report["error_type"] = type(exc).__name__
        hb.report["error"] = str(exc)[:2048]
        checkpoint(FAILURE_MARKER)
        raise
    finally:
        for path in metadata_root.glob("*.nvdb"):
            path.unlink(missing_ok=True)
        velocity_path.unlink(missing_ok=True)


hb.shared._append_resource_marker = append_resource_marker
hb.shared._p3_spatial_boundary = velocity_boundary
write_operation_report(hb.REPORT_PATH, hb.report)
hb._atomic_json(hb.AUDIT_PATH, {
    "schema": "campfire.phase6hh.kit-import-audit.v1",
    "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper": str(Path(__file__).resolve()),
    "base_wrapper": str(HB_PATH),
    "base_import": hb_audit,
    "condition": CONDITION,
    "mode": ROW["mode"],
    "canonical_operation_schema": SCHEMA,
    "retention_mode": ROW["retention"],
    "roi_count": ROW["roi_count"],
    "collectors_used": False,
    "profile_calls": 0,
    "temperature_native_operations": 0,
})

if __name__ == "__main__":
    asyncio.ensure_future(hb.shared._run())
