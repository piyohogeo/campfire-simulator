"""Aggregate the predeclared Phase 6EZ single fuel-conversion boundary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

try:
    from .analyze_phase6ey_dynamic_stationarity import _case as phase6ey_case, _lifecycle_pass
    from .analyze_phase6ew_r0_lifecycle import _json, _jsonl
except ImportError:
    from analyze_phase6ey_dynamic_stationarity import _case as phase6ey_case, _lifecycle_pass
    from analyze_phase6ew_r0_lifecycle import _json, _jsonl


MIB = 1024 * 1024


def _epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _gpu_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        for values in csv.reader(stream):
            if len(values) < 5:
                continue
            try:
                stamp = datetime.strptime(values[0].strip(), "%Y/%m/%d %H:%M:%S.%f").timestamp()
                rows.append({
                    "epoch": stamp,
                    "gpu_index": int(values[1]),
                    "gpu_name": values[2].strip(),
                    "pci_bus_id": values[3].strip(),
                    "dedicated_memory_mib": float(values[4]),
                })
            except (ValueError, TypeError):
                continue
    return [row for row in rows if row["gpu_index"] == 0]


def _nearest(rows: list[dict], timestamp: float, key: str) -> dict | None:
    if not rows:
        return None
    row = min(rows, key=lambda item: abs(float(item[key]) - timestamp))
    return row


def _marker_resources(markers: list[dict], trace: list[dict], gpu: list[dict]) -> list[dict]:
    output = []
    for index, marker in enumerate(markers):
        stamp = _epoch(marker["timestamp_utc"])
        resource = _nearest(trace, stamp, "timestamp_utc_epoch")
        gpu_row = _nearest(gpu, stamp, "epoch")
        kit = None
        if resource:
            kit = next((item for item in resource.get("processes", []) if item.get("role") == "kit"), None)
        memory = marker.get("process_memory") or {}
        output.append({
            "sequence": index,
            "marker": marker.get("marker"),
            "timestamp_utc": marker.get("timestamp_utc"),
            "epoch": stamp,
            "frame": marker.get("frame"),
            "active_blocks": marker.get("active_blocks"),
            "kit_private_bytes_sync": memory.get("private_bytes"),
            "kit_working_set_bytes_sync": memory.get("working_set_bytes"),
            "tree_private_bytes_nearest": None if resource is None else resource.get("tree_private_bytes"),
            "outer_kit_private_bytes_nearest": None if kit is None else kit.get("private_bytes"),
            "outer_resource_alignment_seconds": None if resource is None else abs(float(resource["timestamp_utc_epoch"]) - stamp),
            "gpu_dedicated_memory_mib_nearest": None if gpu_row is None else gpu_row["dedicated_memory_mib"],
            "gpu_alignment_seconds": None if gpu_row is None else abs(float(gpu_row["epoch"]) - stamp),
        })
    return output


def _by_name(rows: list[dict]) -> dict[str, dict]:
    result = {}
    for row in rows:
        result[row["marker"]] = row
    return result


def _delta(by_name: dict[str, dict], before: str, after: str, field: str) -> int | float | None:
    left = by_name.get(before, {}).get(field)
    right = by_name.get(after, {}).get(field)
    if left is None or right is None:
        return None
    return right - left


def _ordered(markers: list[dict | str], required: list[str]) -> bool:
    positions = {}
    for index, marker in enumerate(markers):
        name = marker if isinstance(marker, str) else marker.get("marker")
        positions.setdefault(name, index)
    return all(name in positions for name in required) and [positions[name] for name in required] == sorted(
        positions[name] for name in required
    )


def _readback_boundary(raw: dict) -> dict:
    for sample in raw.get("samples", []):
        boundary = sample.get("readback_boundary")
        if boundary:
            return boundary
    return {}


def _case(root: Path, label: str, prefix: str, contract: dict) -> dict:
    result = phase6ey_case(root, label, prefix, contract)
    case_dir = root / label
    log_dir = root / "runner-logs"
    markers = _jsonl(case_dir / "resource_markers.jsonl")
    trace = _jsonl(log_dir / f"{prefix}.resource.jsonl")
    gpu = _gpu_rows(log_dir / f"{prefix}.gpu.csv")
    raw = _json(case_dir / "raw.json") or {}
    boundary = _readback_boundary(raw)
    resources = _marker_resources(markers, trace, gpu)
    names = _by_name(resources)
    before = "readback_call_before"
    result.update({
        "boundary": boundary,
        "boundary_resources": resources,
        "boundary_marker_order": [row.get("marker") for row in markers],
        "lifecycle_pass": _lifecycle_pass(result),
        "memory_deltas_bytes": {
            "readback_immediate": _delta(names, before, "readback_call_after", "kit_private_bytes_sync"),
            "fuel_conversion_immediate": _delta(names, "fuel_conversion_before", "fuel_conversion_after", "kit_private_bytes_sync"),
            "original_alias_release": _delta(names, "fuel_conversion_after", "original_tuple_and_all_handle_aliases_released", "kit_private_bytes_sync"),
            "converted_buffer_release": _delta(names, "converted_buffer_only_held", "converted_buffer_released", "kit_private_bytes_sync"),
            "next_frame_residual": _delta(names, before, "next_frame_started", "kit_private_bytes_sync"),
            "observation_end_residual": _delta(names, before, "stability_observation_ended", "kit_private_bytes_sync"),
            "stage_close_before_residual": _delta(names, before, "stage_close_request_before", "kit_private_bytes_sync"),
        },
        "gpu_deltas_mib": {
            "readback_immediate": _delta(names, before, "readback_call_after", "gpu_dedicated_memory_mib_nearest"),
            "fuel_conversion_immediate": _delta(names, "fuel_conversion_before", "fuel_conversion_after", "gpu_dedicated_memory_mib_nearest"),
            "next_frame_residual": _delta(names, before, "next_frame_started", "gpu_dedicated_memory_mib_nearest"),
            "observation_end_residual": _delta(names, before, "stability_observation_ended", "gpu_dedicated_memory_mib_nearest"),
        },
        "minimum_kit_ceiling_margin_bytes": int(contract["safety"]["kit_private_limit_bytes"]) - int(result["kit_peak_private_bytes"]),
    })
    return result


def _condition_gate(case: dict, contract: dict, condition: str) -> tuple[bool, list[str]]:
    failures = []
    boundary = case.get("boundary") or {}
    counts = boundary.get("operation_counts") or {}
    gates = contract["gates"]
    if not case.get("lifecycle_pass"):
        failures.append("lifecycle")
    if not case.get("dynamic_stationarity_pass"):
        failures.append("dynamic_stationarity")
    if counts.get("public_readback_calls") != gates["required_public_readback_calls_per_condition"]:
        failures.append("public_readback_call_count")
    if counts.get("field_persistence_calls") != gates["required_field_persistence_calls"]:
        failures.append("field_persistence_call_count")
    required = ["readback_call_before", "readback_call_after", "original_tuple_and_all_handle_aliases_released", "python_references_released", "next_frame_started"]
    if condition == "C1_fuel_convert":
        required = [name for name in contract["ordered_c1_markers"] if name != "os_process_exit_observed"]
        if counts.get("numpy_asarray_calls") != gates["required_c1_numpy_asarray_calls"]:
            failures.append("numpy_asarray_call_count")
        fuel = boundary.get("fuel_array") or {}
        logical = fuel.get("nbytes")
        if logical is None or logical <= 0 or logical > gates["maximum_fuel_logical_bytes"]:
            failures.append("fuel_logical_bytes")
        if (boundary.get("observable_copy_contract") or {}).get("explicit_copy_function_calls") != 0:
            failures.append("explicit_copy_function_call")
    if not _ordered(case["boundary_marker_order"], required):
        failures.append("marker_order")
    if case["minimum_kit_ceiling_margin_bytes"] < 0:
        failures.append("kit_resource_ceiling")
    if condition == "C0_acquire_discard":
        immediate = case["memory_deltas_bytes"].get("readback_immediate")
        reference = contract["phase6ey_history"]["reference_only_immediate_acquire_delta_bytes"]
        if immediate is None or immediate < gates["c0_minimum_immediate_acquire_delta_bytes"]:
            failures.append("c0_immediate_delta")
        elif abs(immediate - reference) > gates["c0_phase6ey_reference_maximum_absolute_delta_difference_bytes"]:
            failures.append("c0_phase6ey_reference_difference")
    return not failures, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    for label, prefix in (("C0_acquire_discard", "C0_acquire_discard"), ("C1_fuel_convert", "C1_fuel_convert")):
        if (args.root / label).exists():
            case = _case(args.root, label, prefix, contract)
            passed, failures = _condition_gate(case, contract, label)
            case["condition_gate_pass"] = passed
            case["condition_gate_failures"] = failures
            cases[label] = case
    c0 = cases.get("C0_acquire_discard")
    c1 = cases.get("C1_fuel_convert")
    comparison = None
    if c0 and c1:
        fuel = c1.get("boundary", {}).get("fuel_array") or {}
        logical = fuel.get("nbytes")
        conversion = c1["memory_deltas_bytes"].get("fuel_conversion_immediate")
        comparison = {
            "fuel_logical_bytes": logical,
            "conversion_cpu_increment_bytes": conversion,
            "conversion_cpu_increment_to_logical_ratio": None if not logical or conversion is None else conversion / logical,
            "conversion_gpu_increment_mib": c1["gpu_deltas_mib"].get("fuel_conversion_immediate"),
            "c1_minus_c0_peak_private_bytes": c1["kit_peak_private_bytes"] - c0["kit_peak_private_bytes"],
            "c1_minus_c0_terminal_private_bytes": c1["aligned_time_series"][-1]["kit_private_bytes"] - c0["aligned_time_series"][-1]["kit_private_bytes"],
            "c1_minus_c0_active_block_mean": c1["dynamic_stationarity"]["metrics"]["active_blocks"]["mean"] - c0["dynamic_stationarity"]["metrics"]["active_blocks"]["mean"],
        }
    report = {
        "schema": "campfire.phase6ez.single-fuel-conversion-report.v1",
        "phase": "phase6ez",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "phase6ey_history_frozen": True,
        "cases": cases,
        "c0_gate_pass": bool(c0 and c0["condition_gate_pass"]),
        "c1_started": c1 is not None,
        "c1_gate_pass": bool(c1 and c1["condition_gate_pass"]),
        "comparison": comparison,
        "qualified_boundary": bool(c0 and c1 and c0["condition_gate_pass"] and c1["condition_gate_pass"]),
        "repeated_conversion_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
