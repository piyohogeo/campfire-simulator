"""Analyze Phase 6FM using explicit post-release settling-end baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

try:
    from scripts.analyze_phase6fh_lifecycle_qualification import jsonl, load
    from scripts.analyze_phase6fl_three_iteration import (
        LABELS, _attempt as phase6fl_attempt, _epoch, _first, _gpu_samples,
        _nearest_gpu, _outer_interval, _outer_samples, evaluate_paired_accumulation,
        evaluate_staircase,
    )
except ModuleNotFoundError:
    from analyze_phase6fh_lifecycle_qualification import jsonl, load
    from analyze_phase6fl_three_iteration import (
        LABELS, _attempt as phase6fl_attempt, _epoch, _first, _gpu_samples,
        _nearest_gpu, _outer_interval, _outer_samples, evaluate_paired_accumulation,
        evaluate_staircase,
    )


def _private(record: dict | None) -> int | None:
    value = ((record or {}).get("process_memory") or {}).get("private_bytes")
    return value if type(value) is int else None


def _working_set(record: dict | None) -> int | None:
    value = ((record or {}).get("process_memory") or {}).get("working_set_bytes")
    return value if type(value) is int else None


def _nearest_outer(samples: list[dict], timestamp: float) -> dict | None:
    return min(samples, key=lambda item: abs(float(item.get("timestamp_utc_epoch") or 0.0) - timestamp)) if samples else None


def _nearest_gpu_record(samples: list[dict], timestamp: float, gpu_index: int = 0) -> dict | None:
    candidates = [item for item in samples if item.get("gpu_index") == gpu_index]
    return min(candidates, key=lambda item: abs(item["timestamp_utc_epoch"] - timestamp)) if candidates else None


def _delta(right, left):
    return right - left if type(right) is int and type(left) is int else None


def _explicit_iteration(case_dir: Path, outer_path: Path, gpu_path: Path, frame: int, end_frame: int, index: int, contract: dict) -> dict:
    markers = jsonl(case_dir / "resource_markers.jsonl")
    outer = _outer_samples(outer_path)
    gpu = _gpu_samples(gpu_path)
    pre = _first(markers, "pre_operation", frame)
    completed = _first(markers, "operation_completed", frame)
    released = _first(markers, "release_completed", frame)
    settling_started = _first(markers, "settling_started", frame)
    settled = _first(markers, "settling_end", end_frame)
    readback_before = _first(markers, "readback_call_before", frame)
    readback_after = _first(markers, "readback_call_after", frame)
    asarray_before = _first(markers, "fuel_conversion_before", frame)
    asarray_after = _first(markers, "fuel_conversion_after", frame)
    failures = []
    for name, value in (
        ("pre_operation", pre), ("operation_completed", completed),
        ("release_completed", released), ("settling_started", settling_started),
        ("settling_end", settled),
    ):
        if value is None:
            failures.append(f"explicit_{name}_marker_missing")
    start_epoch = _epoch(settling_started or {})
    end_epoch = _epoch(settled or {})
    interval = _outer_interval(outer, start_epoch, end_epoch) if start_epoch and end_epoch else []
    duration = end_epoch - start_epoch if start_epoch and end_epoch else None
    minimum = contract["settling"]
    if duration is None or duration < minimum["minimum_wall_seconds"]:
        failures.append("explicit_settling_wall_time")
    if len(interval) < minimum["minimum_outer_resource_samples"]:
        failures.append("explicit_settling_resource_samples")
    renderer_updates = end_frame - frame
    if renderer_updates < minimum["minimum_renderer_updates"]:
        failures.append("explicit_settling_renderer_updates")
    if settled and settled.get("settling_iteration") != index:
        failures.append("settling_iteration_identity")
    if released and released.get("weak_reference_alive_count") not in (None, 0):
        failures.append("release_weak_reference_residual")
    pre_outer = _nearest_outer(outer, _epoch(pre or {})) if pre else None
    settled_outer = _nearest_outer(outer, _epoch(settled or {})) if settled else None
    readback_gpu_before = _nearest_gpu_record(gpu, _epoch(readback_before or {})) if readback_before else None
    readback_gpu_after = _nearest_gpu_record(gpu, _epoch(readback_after or {})) if readback_after else None
    asarray_gpu_before = _nearest_gpu_record(gpu, _epoch(asarray_before or {})) if asarray_before else None
    asarray_gpu_after = _nearest_gpu_record(gpu, _epoch(asarray_after or {})) if asarray_after else None
    return {
        "iteration": index,
        "operation_frame": frame,
        "settling_end_frame": end_frame,
        "pre_operation": {
            "private_bytes": _private(pre),
            "working_set_bytes": _working_set(pre),
            "unique_tree_private_bytes": (pre_outer or {}).get("tree_private_bytes"),
            "gpu_dedicated_memory_mib": _nearest_gpu(gpu, _epoch(pre or {})) if pre else None,
            "active_blocks": (pre or {}).get("active_blocks"),
            "field_element_count": (pre or {}).get("field_element_count"),
            "field_logical_bytes": (pre or {}).get("field_logical_bytes"),
            "timeline_time": (pre or {}).get("timeline_time"),
            "kit_update_index": (pre or {}).get("kit_update_index"),
        },
        "settling_end": {
            "private_bytes": _private(settled),
            "working_set_bytes": _working_set(settled),
            "unique_tree_private_bytes": (settled_outer or {}).get("tree_private_bytes"),
            "gpu_dedicated_memory_mib": _nearest_gpu(gpu, _epoch(settled or {})) if settled else None,
            "active_blocks": (settled or {}).get("active_blocks"),
            "field_element_count": (settled or {}).get("field_element_count"),
            "field_logical_bytes": (settled or {}).get("field_logical_bytes"),
            "field_measurement_frame": (settled or {}).get("field_measurement_frame"),
            "field_measurement_source": (settled or {}).get("field_measurement_source"),
            "timeline_time": (settled or {}).get("timeline_time"),
            "kit_update_index": (settled or {}).get("kit_update_index"),
        },
        "settling_wall_seconds": duration,
        "resource_sample_count": len(interval),
        "renderer_update_count": renderer_updates,
        "weak_reference_residual": (released or {}).get("weak_reference_alive_count"),
        "readback_adjacent": {
            "cpu_private_delta_bytes": _delta(_private(readback_after), _private(readback_before)),
            "gpu_dedicated_delta_mib": (
                readback_gpu_after["dedicated_memory_mib"] - readback_gpu_before["dedicated_memory_mib"]
                if readback_gpu_before and readback_gpu_after else None
            ),
            "gpu_same_telemetry_sample": bool(
                readback_gpu_before and readback_gpu_after
                and readback_gpu_before["timestamp_utc_epoch"] == readback_gpu_after["timestamp_utc_epoch"]
            ),
        },
        "numpy_asarray_adjacent": {
            "cpu_private_delta_bytes": _delta(_private(asarray_after), _private(asarray_before)),
            "gpu_dedicated_delta_mib": (
                asarray_gpu_after["dedicated_memory_mib"] - asarray_gpu_before["dedicated_memory_mib"]
                if asarray_gpu_before and asarray_gpu_after else None
            ),
            "gpu_same_telemetry_sample": bool(
                asarray_gpu_before and asarray_gpu_after
                and asarray_gpu_before["timestamp_utc_epoch"] == asarray_gpu_after["timestamp_utc_epoch"]
            ),
        },
        "failures": sorted(set(failures)),
        "gate_pass": not failures,
    }


def _field_adjusted_pair(control: list[int | None], candidate: list[int | None], field: list[int | None], threshold: int) -> dict:
    paired = evaluate_paired_accumulation(control, candidate, threshold)
    complete = paired["complete"] and len(field) == 3 and all(type(value) is int for value in field)
    if not complete:
        return {**paired, "field_context_complete": False, "field_adjusted_gate_pass": False, "failures": sorted(set(paired["failures"] + ["field_context_required"]))}
    field_steps = [field[1] - field[0], field[2] - field[1]]
    adjusted = [paired["candidate_minus_control_steps_bytes"][i] - max(0, field_steps[i]) for i in range(2)]
    adjusted_total = paired["candidate_minus_control_total_bytes"] - max(0, field[2] - field[0])
    staircase = (
        paired["candidate"]["step_2_minus_1_bytes"] > 0
        and paired["candidate"]["step_3_minus_2_bytes"] > 0
        and adjusted[0] > threshold and adjusted[1] > threshold
        and adjusted_total > 2 * threshold
    )
    failures = ["settled_field_adjusted_two_step_staircase"] if staircase else []
    return {
        **paired,
        "field_context_complete": True,
        "field_steps_bytes": field_steps,
        "field_adjusted_candidate_minus_control_steps_bytes": adjusted,
        "field_adjusted_candidate_minus_control_total_bytes": adjusted_total,
        "field_adjusted_staircase": staircase,
        "field_adjusted_gate_pass": not staircase,
        "failures": failures,
    }


def _distribution(values) -> dict:
    finite = [float(value) for value in values if isinstance(value, (int, float))]
    return {"values": finite, "minimum": min(finite) if finite else None, "median": statistics.median(finite) if finite else None, "maximum": max(finite) if finite else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--base-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load(args.contract)
    base = load(args.base_contract)
    attempts = []
    for attempt_root in sorted(args.root.glob("attempt[0-9][0-9]")):
        metadata = load(attempt_root / "attempt_metadata.json")
        if not metadata:
            continue
        item = phase6fl_attempt(attempt_root, metadata, contract, base)
        label = LABELS[item["condition"]][0]
        explicit = [
            _explicit_iteration(
                attempt_root / label,
                attempt_root / "runner-logs" / f"{label}.resource.jsonl",
                attempt_root / "runner-logs" / f"{label}.gpu.csv",
                frame, contract["settling_end_frames"][index - 1], index, contract,
            )
            for index, frame in enumerate(contract["operation_frames"], 1)
        ] if item["representative_startup"] and not item["absolute_safety_failures"] and not item["native_lifecycle_failures"] else []
        explicit_failures = [f"iteration{entry['iteration']}:{failure}" for entry in explicit for failure in entry["failures"]]
        if explicit_failures and item["classification"] == "representative_pass":
            item["classification"] = "operation_failure"
            item["operation_failures"] = sorted(set(item["operation_failures"] + explicit_failures))
        item["explicit_iterations"] = explicit
        item["formal_pre_operation_telemetry_only"] = True
        item["formal_settling_end_values_bytes"] = [entry["settling_end"]["private_bytes"] for entry in explicit]
        item["formal_settling_end_accumulation"] = evaluate_staircase(item["formal_settling_end_values_bytes"], contract["accumulation_gate"]["material_step_bytes"])
        attempts.append(item)

    representative = [item for item in attempts if item["classification"] == "representative_pass"]
    nonreplaceable = [item for item in attempts if item["classification"] in {"operation_failure", "native_lifecycle_failure", "absolute_safety_failure"}]
    prereq = [item for item in attempts if item["classification"] == "startup_prerequisite_failure"]
    counts = {name: sum(item["condition"] == name for item in representative) for name in LABELS}
    sequence_results = []
    failure_sequences = {"R1_readback": [], "R2_fuel_alias": []}
    threshold = contract["accumulation_gate"]["material_step_bytes"]
    for sequence in range(1, 4):
        cases = {item["condition"]: item for item in representative if item["sequence"] == sequence}
        if len(cases) != 3:
            continue
        comparisons = {}
        r0_values = cases["R0_control"]["formal_settling_end_values_bytes"]
        for condition in ("R1_readback", "R2_fuel_alias"):
            candidate = cases[condition]
            fields = [entry["settling_end"]["field_logical_bytes"] for entry in candidate["explicit_iterations"]]
            comparison = _field_adjusted_pair(r0_values, candidate["formal_settling_end_values_bytes"], fields, threshold)
            comparisons[condition] = comparison
            if comparison.get("field_adjusted_staircase"):
                failure_sequences[condition].append(sequence)
        sequence_results.append({
            "sequence": sequence,
            "comparisons": comparisons,
            "active_blocks": {name: [entry["settling_end"]["active_blocks"] for entry in case["explicit_iterations"]] for name, case in cases.items()},
            "field_logical_bytes": {name: [entry["settling_end"]["field_logical_bytes"] for entry in case["explicit_iterations"]] for name, case in cases.items()},
        })
    replicated_failures = [
        {"condition": condition, "sequences": sequences, "failure": "replicated_settled_field_adjusted_staircase"}
        for condition, sequences in failure_sequences.items() if len(sequences) >= contract["accumulation_gate"]["minimum_reproducing_sequences"]
    ]
    first_nonreplaceable = next((i for i, item in enumerate(attempts) if item in nonreplaceable), None)
    post_stop = attempts[first_nonreplaceable + 1:] if first_nonreplaceable is not None else []
    qualified = (
        len(representative) == 9 and all(value == 3 for value in counts.values())
        and not nonreplaceable and not post_stop and not replicated_failures
    )
    explicit_iterations = [entry for item in representative for entry in item["explicit_iterations"]]
    report = {
        "schema": "campfire.phase6fm.settled-three-iteration-report.v1",
        "phase": "phase6fm",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": contract["history_frozen"],
        "total_launches": len(attempts),
        "representative_processes": len(representative),
        "startup_prerequisite_failures": len(prereq),
        "condition_counts": counts,
        "attempts": attempts,
        "sequence_results": sequence_results,
        "replicated_settled_failures": replicated_failures,
        "first_replicated_settled_failure": replicated_failures[0] if replicated_failures else None,
        "formal_gate_uses_pre_operation": False,
        "formal_gate_uses_explicit_settling_end": True,
        "operation_summary": {
            "settling_wall_seconds": _distribution(entry["settling_wall_seconds"] for entry in explicit_iterations),
            "resource_sample_count": _distribution(entry["resource_sample_count"] for entry in explicit_iterations),
        },
        "lifecycle_summary": {
            "stage_close_seconds": _distribution(item["stage_close_seconds"] for item in representative),
            "cdb_invocation_count": sum(int(item["cdb_invoked"]) for item in attempts),
        },
        "resource_summary": {
            "kit_peak_bytes": max((((item["resource"]["peaks"] or {}).get("kit")) for item in attempts if isinstance((item["resource"]["peaks"] or {}).get("kit"), (int, float))), default=None),
            "tree_peak_bytes": max((((item["resource"]["peaks"] or {}).get("tree")) for item in attempts if isinstance((item["resource"]["peaks"] or {}).get("tree"), (int, float))), default=None),
        },
        "nonreplaceable_failures": nonreplaceable,
        "attempts_after_required_stop": [item["attempt_id"] for item in post_stop],
        "qualified": qualified,
        "three_readbacks_qualified": qualified,
        "three_fuel_alias_lifetimes_qualified": qualified,
        "more_than_three_iterations_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
