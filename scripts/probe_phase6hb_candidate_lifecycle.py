"""Phase 6HB: temperature-free Candidate lifecycle isolation ladder."""

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
from phase6hb_candidate_lifecycle_contract import LADDER

BASE_PATH = (SCRIPT_DIR / "probe_phase6gn_supply_comparison.py").resolve()
GZ_PATH = (SCRIPT_DIR / "probe_phase6gz_candidate_boundary.py").resolve()
MAX_JSON_BYTES = 256 * 1024
settings = carb.settings.get_settings()
REPORT_PATH = Path(settings.get_as_string("/phase6go/isolationReportPath")).resolve()
AUDIT_PATH = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()
MODE = settings.get_as_string("/phase6go/isolationMode") or "R0"
LEVEL_BY_MODE = {row["mode"]: index for index, row in enumerate(LADDER)}
if MODE not in LEVEL_BY_MODE:
    raise ImportError(f"unsupported Phase 6HB ladder mode: {MODE}")
LEVEL = LEVEL_BY_MODE[MODE]


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise RuntimeError("Phase 6HB bounded report exceeded 256 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


base, base_audit = load_exact_module(
    BASE_PATH, BASE_PATH, module_name="campfire_phase6hb_phase6gn_base", required_entrypoints=()
)
gz, gz_audit = load_exact_module(
    GZ_PATH, GZ_PATH, module_name="campfire_phase6hb_phase6gz_helpers", required_entrypoints=()
)
shared = base.shared
discovery = gz.discovery
candidate = gz.candidate

report = {
    "schema": "campfire.phase6hb.candidate-lifecycle-operation.v1",
    "status": "running",
    "operation_result": "running",
    "mode": MODE,
    "level": LEVEL,
    "features": list(LADDER[LEVEL]["features"]),
    "public_readback_calls": 0,
    "calls": {
        "array_metadata": 0,
        "non_temperature_buffer_to_volume": 0,
        "non_temperature_volume_metadata": 0,
        "non_temperature_save": 0,
        "non_temperature_typed_read": 0,
        "velocity_sampling": 0,
        "velocity_collector": 0,
        "temperature_buffer_to_volume": 0,
        "temperature_metadata": 0,
        "temperature_save": 0,
        "temperature_sampling": 0,
        "temperature_collector": 0,
    },
    "checkpoints": [],
}


def checkpoint(name: str, **values) -> None:
    report["last_operation_marker"] = name
    report["checkpoints"].append({
        "name": name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **values,
    })
    _atomic_json(REPORT_PATH, report)


def _phase6hb_boundary(flow, volume_provider, arguments, frame, output, collectors, operation_state=None):
    operation_state = operation_state or {}

    def marker(name: str, **values) -> None:
        shared._append_resource_marker(
            arguments["resource_marker_path"],
            name,
            synchronous_memory=arguments["synchronous_memory_markers"],
            frame=int(frame),
            active_blocks=int(flow.get_active_block_count()),
            phase="phase6hb",
            isolation_mode=MODE,
            **operation_state,
            **values,
        )
        checkpoint(name, frame=int(frame), **values)

    handles = None
    references = []
    temperature_alias = None
    schema_rows = []
    metadata_root = output.parent / f"phase6hb-schema-f{int(frame):04d}"
    metadata_root.mkdir(parents=True, exist_ok=True)
    velocity_path = output.parent / f"p3_f{int(frame):04d}_velocity.nvdb"
    try:
        marker("phase6hb_readback_before")
        handles = flow.get_latest_nanovdb_readback()
        report["public_readback_calls"] = 1
        marker("phase6hb_readback_after", returned_handle_count=len(handles))
        if not isinstance(handles, list) or len(handles) != 7:
            raise RuntimeError(f"expected public list of 7 handles, got {type(handles)!r}/{len(handles)}")
        marker("phase6hb_list_count_check_after", returned_handle_count=7, returned_type=shared._type_name(handles))
        references = [weakref.ref(value) for value in handles]

        if LEVEL >= 1:
            for index, source in enumerate(handles):
                marker("phase6hb_array_metadata_before", handle_index=index)
                report["calls"]["array_metadata"] += 1
                row = discovery._array_metadata(source)
                schema_rows.append({
                    "index": index,
                    "python_type": row.get("python_type"),
                    "dtype": row.get("dtype"),
                    "shape": row.get("shape"),
                    "element_count": int(source.size),
                    "logical_bytes": int(source.nbytes),
                })
                marker(
                    "phase6hb_array_metadata_after",
                    handle_index=index,
                    python_type=row.get("python_type"),
                    logical_bytes=int(source.nbytes),
                )
            report["bounded_array_metadata"] = schema_rows

        if LEVEL >= 2:
            # Slot 0 temperature and slot 6 empty RGBA are deliberately excluded.
            total_bytes = 0
            expected_channels = list(candidate["exact_order"])
            prefix_rows = []

            def schema_marker(name: str, **values) -> None:
                marker(name.replace("phase6gz_", "phase6hb_"), **values)

            for index in range(1, 6):
                path = metadata_root / f"handle_{index}.nvdb"
                report["calls"]["non_temperature_buffer_to_volume"] += 1
                report["calls"]["non_temperature_volume_metadata"] += 1
                report["calls"]["non_temperature_save"] += 1
                report["calls"]["non_temperature_typed_read"] += 1
                volume_row, file_bytes = gz._instrumented_schema_volume(
                    flow,
                    volume_provider,
                    handles[index],
                    path,
                    discovery.TOTAL_FILE_LIMIT - total_bytes,
                    schema_marker,
                    index,
                )
                total_bytes += file_bytes
                grid = volume_row["grids"][0]
                wanted = gz.schema_contract["schema_gate"]["handles"][index]
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
            report["non_temperature_schema_prefix"] = prefix_rows

        if LEVEL >= 3:
            velocity_index = list(candidate["exact_order"]).index("velocity")
            use_collectors = collectors if LEVEL >= 4 else None
            marker(
                "phase6hb_velocity_pipeline_before",
                collector_enabled=use_collectors is not None,
                collector_count=len(collectors) if use_collectors is not None else 0,
            )
            report["calls"]["velocity_sampling"] = 1
            report["calls"]["velocity_collector"] = len(collectors) if use_collectors is not None else 0
            shared._save_and_sample(
                flow,
                volume_provider,
                handles[velocity_index],
                "velocity",
                velocity_path,
                shared._p3_world_rois(),
                spatial_collector=use_collectors,
                spatial_velocity_only=False,
                frame=frame,
                profile_threshold=0.01,
            )
            marker("phase6hb_velocity_pipeline_after", temporary_present=velocity_path.exists())

        if LEVEL >= 5:
            temperature_alias = handles[0]
            marker(
                "phase6hb_temperature_alias_held",
                handle_index=0,
                python_type=shared._type_name(temperature_alias),
                logical_bytes=int(temperature_alias.nbytes),
            )

        marker("phase6hb_release_before")
        temperature_alias = None
        source = None
        for index in range(len(handles)):
            handles[index] = None
        handles.clear()
        handles = None
        weak_alive = sum(reference() is not None for reference in references)
        report["weak_reference_alive_after_release_count"] = weak_alive
        report["references_released"] = weak_alive == 0
        marker("phase6hb_release_after", weak_reference_alive_count=weak_alive)
        if weak_alive:
            raise RuntimeError(f"weak-reference residual after release: {weak_alive}")
        if any(report["calls"][name] for name in (
            "temperature_buffer_to_volume",
            "temperature_metadata",
            "temperature_save",
            "temperature_sampling",
            "temperature_collector",
        )):
            raise RuntimeError("temperature operation prohibition violated")
        report["status"] = "pass"
        report["operation_result"] = "pass"
        checkpoint("phase6hb_operation_complete", level=LEVEL)
        return {
            "mode": f"phase6hb_{MODE}",
            "returned_channel_count": 7,
            "field_body_json_npz_or_openvdb_written": False,
            "weak_reference_alive_after_scope_count": 0,
        }, references
    except BaseException as exc:
        report["status"] = "fail"
        report["operation_result"] = "operation_failure"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:2048]
        checkpoint("phase6hb_operation_failure")
        raise
    finally:
        for path in metadata_root.glob("*.nvdb"):
            path.unlink(missing_ok=True)
        velocity_path.unlink(missing_ok=True)


shared._p3_spatial_boundary = _phase6hb_boundary
_atomic_json(AUDIT_PATH, {
    "schema": "campfire.phase6hb.kit-import-audit.v1",
    "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper": str(Path(__file__).resolve()),
    "mode": MODE,
    "level": LEVEL,
    "base_import": base_audit,
    "gz_helper_import": gz_audit,
    "patch_target": "shared._p3_spatial_boundary",
    "patched": shared._p3_spatial_boundary is _phase6hb_boundary,
    "temperature_operations_prohibited": True,
})

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
