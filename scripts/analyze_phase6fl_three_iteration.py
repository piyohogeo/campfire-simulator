"""Analyze Phase 6FL's bounded three-iteration readback pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from scripts.analyze_phase6fh_lifecycle_qualification import jsonl, load
    from scripts.phase6fk_pointer_evidence import pointer_evidence_from_boundary
except ModuleNotFoundError:
    from analyze_phase6fh_lifecycle_qualification import jsonl, load
    from phase6fk_pointer_evidence import pointer_evidence_from_boundary


LABELS = {
    "R0_control": ("R0_control", "none"),
    "R1_readback": ("R1_readback", "acquire_discard_release"),
    "R2_fuel_alias": ("R2_fuel_alias", "fuel_convert_release"),
}


def _epoch(record: dict) -> float:
    value = record.get("timestamp_utc")
    if not value:
        return 0.0
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _private(record: dict | None) -> int | None:
    value = ((record or {}).get("process_memory") or {}).get("private_bytes")
    return value if type(value) is int else None


def _delta(after: int | None, before: int | None) -> int | None:
    return after - before if type(after) is int and type(before) is int else None


def _first(records: list[dict], marker: str, frame: int | None = None) -> dict | None:
    for record in records:
        if record.get("marker") == marker and (frame is None or record.get("frame") == frame):
            return record
    return None


def _outer_samples(path: Path) -> list[dict]:
    return jsonl(path)


def _outer_interval(samples: list[dict], start: float, end: float) -> list[dict]:
    return [sample for sample in samples if start <= float(sample.get("timestamp_utc_epoch") or 0.0) <= end]


def _kit_from_outer(sample: dict) -> dict | None:
    candidates = [item for item in sample.get("processes", []) if item.get("role") == "kit"]
    return candidates[0] if candidates else None


def _gpu_samples(path: Path) -> list[dict]:
    result = []
    if not path.exists():
        return result
    jst = timezone(timedelta(hours=9))
    with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 5:
                continue
            try:
                timestamp = datetime.strptime(row[0].strip(), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=jst).timestamp()
                index = int(row[1].strip())
                memory_mib = float(row[4].strip())
            except (ValueError, TypeError):
                continue
            result.append({"timestamp_utc_epoch": timestamp, "gpu_index": index, "dedicated_memory_mib": memory_mib})
    return result


def _nearest_gpu(samples: list[dict], timestamp: float, gpu_index: int = 0) -> float | None:
    candidates = [item for item in samples if item["gpu_index"] == gpu_index]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(item["timestamp_utc_epoch"] - timestamp))["dedicated_memory_mib"]


def evaluate_staircase(values: list[int | None], threshold: int) -> dict:
    valid = len(values) == 3 and all(type(value) is int for value in values)
    if not valid:
        return {"complete": False, "gate_pass": False, "failures": ["three_baselines_required"]}
    steps = [values[1] - values[0], values[2] - values[1]]
    total = values[2] - values[0]
    staircase = steps[0] > threshold and steps[1] > threshold and total > 2 * threshold
    return {
        "complete": True,
        "values_bytes": values,
        "step_2_minus_1_bytes": steps[0],
        "step_3_minus_2_bytes": steps[1],
        "step_3_minus_1_bytes": total,
        "material_threshold_bytes": threshold,
        "staircase_accumulation": staircase,
        "gate_pass": not staircase,
        "failures": ["material_two_step_staircase"] if staircase else [],
    }


def evaluate_paired_accumulation(control: list[int | None], candidate: list[int | None], threshold: int) -> dict:
    control_result = evaluate_staircase(control, threshold)
    candidate_result = evaluate_staircase(candidate, threshold)
    if not control_result["complete"] or not candidate_result["complete"]:
        return {"complete": False, "gate_pass": False, "failures": ["paired_three_baselines_required"]}
    control_steps = [control[1] - control[0], control[2] - control[1]]
    candidate_steps = [candidate[1] - candidate[0], candidate[2] - candidate[1]]
    excess = [candidate_steps[index] - control_steps[index] for index in range(2)]
    control_total = control[2] - control[0]
    candidate_total = candidate[2] - candidate[0]
    excess_total = candidate_total - control_total
    accumulation = excess[0] > threshold and excess[1] > threshold and excess_total > 2 * threshold
    return {
        "complete": True,
        "control": control_result,
        "candidate": candidate_result,
        "control_steps_bytes": control_steps,
        "candidate_steps_bytes": candidate_steps,
        "candidate_minus_control_steps_bytes": excess,
        "candidate_minus_control_total_bytes": excess_total,
        "material_threshold_bytes": threshold,
        "operation_specific_staircase_accumulation": accumulation,
        "gate_pass": not accumulation,
        "failures": ["paired_material_two_step_staircase"] if accumulation else [],
    }


def _iteration(
    index: int,
    frame: int,
    settling_end_frame: int,
    condition: str,
    markers: list[dict],
    boundary: dict | None,
    outer: list[dict],
    gpu: list[dict],
    contract: dict,
) -> dict:
    mode = LABELS[condition][1]
    pre_name = "sample_started" if mode == "none" else "readback_call_before"
    post_name = "sample_metadata_complete" if mode == "none" else "readback_call_after"
    pre = _first(markers, pre_name, frame)
    post = _first(markers, post_name, frame)
    next_renderer = _first(markers, "startup_frame_sample", frame + 1)
    settling_end = _first(markers, "sample_started", settling_end_frame)
    settling_end_kind = "next_iteration_pre_operation" if settling_end_frame in contract["operation_frames"] else "finite_settling_sentinel"
    interval = _outer_interval(outer, _epoch(post or {}), _epoch(settling_end or {})) if post and settling_end else []
    kit_interval = [item for sample in interval if (item := _kit_from_outer(sample)) is not None]
    duration = _epoch(settling_end or {}) - _epoch(post or {}) if post and settling_end else None
    frame_span = settling_end_frame - frame
    failures = []
    if pre is None or post is None or next_renderer is None or settling_end is None:
        failures.append("required_iteration_marker_missing")
    settling = contract["settling"]
    if duration is None or duration < settling["minimum_wall_seconds"]:
        failures.append("settling_wall_time")
    if len(interval) < settling["minimum_outer_resource_samples"]:
        failures.append("settling_resource_samples")
    if type(frame_span) is not int or frame_span < settling["minimum_renderer_updates"]:
        failures.append("settling_renderer_updates")

    expected_calls = contract["conditions"][condition]
    operation_counts = (boundary or {}).get("operation_counts") or {}
    if mode == "none":
        operation_counts = {
            "public_readback_calls": 0,
            "numpy_asarray_calls": 0,
            "field_persistence_calls": 0,
        }
        if (post or {}).get("readback") is not False:
            failures.append("r0_control_marker_missing")
    for name in ("public_readback_calls", "numpy_asarray_calls"):
        if operation_counts.get(name) != expected_calls[name]:
            failures.append(f"{name}_count")
    if operation_counts.get("field_persistence_calls", 0) != 0:
        failures.append("field_persistence")
    weak = (boundary or {}).get("weak_reference_alive_after_scope_count")
    if mode != "none" and weak != 0:
        failures.append("channel_weak_reference_residual")

    pointer = None
    if condition == "R2_fuel_alias":
        pointer = pointer_evidence_from_boundary(boundary or {})
        failures.extend(f"pointer:{item}" for item in pointer["failures"])
        max_delta = contract["pointer_contract"]["maximum_absolute_numpy_asarray_private_delta_bytes"]
        before = _first(markers, "fuel_conversion_before", frame)
        after = _first(markers, "fuel_conversion_after", frame)
        if before is None or after is None:
            failures.append("numpy_asarray_markers")
        elif abs(_delta(_private(after), _private(before)) or 0) > max_delta:
            failures.append("numpy_asarray_adjacent_private_delta")

    marker_names = {
        "pre": pre_name,
        "post": post_name,
        "next_renderer": "startup_frame_sample",
        "settling_end": (settling_end or {}).get("marker"),
    }
    pre_private = _private(pre)
    post_private = _private(post)
    next_private = _private(next_renderer)
    settled_private = _private(settling_end)
    source_release = _first(markers, "original_tuple_and_all_handle_aliases_released", frame)
    converted_release = _first(markers, "converted_buffer_released", frame)
    fuel_before = _first(markers, "fuel_conversion_before", frame)
    fuel_after = _first(markers, "fuel_conversion_after", frame)
    gpu_pre = _nearest_gpu(gpu, _epoch(pre or {})) if pre else None
    gpu_post = _nearest_gpu(gpu, _epoch(post or {})) if post else None
    gpu_settled = _nearest_gpu(gpu, _epoch(settling_end or {})) if settling_end else None
    return {
        "iteration": index,
        "frame": frame,
        "mode": mode,
        "marker_names": marker_names,
        "settling_end_kind": settling_end_kind,
        "settling_wall_seconds": duration,
        "settling_renderer_updates": frame_span,
        "settling_outer_resource_samples": len(interval),
        "settling_kit_resource_samples": len(kit_interval),
        "pre_operation_private_bytes": pre_private,
        "post_operation_private_bytes": post_private,
        "next_renderer_private_bytes": next_private,
        "settling_end_private_bytes": settled_private,
        "operation_immediate_delta_bytes": _delta(post_private, pre_private),
        "next_renderer_residual_bytes": _delta(next_private, pre_private),
        "settling_end_residual_bytes": _delta(settled_private, pre_private),
        "source_release_delta_bytes": _delta(_private(source_release), post_private),
        "converted_release_delta_bytes": _delta(_private(converted_release), _private(source_release)),
        "numpy_asarray_delta_bytes": _delta(_private(fuel_after), _private(fuel_before)),
        "gpu_dedicated_memory_mib": {
            "pre_operation": gpu_pre,
            "post_operation": gpu_post,
            "settling_end": gpu_settled,
            "immediate_delta": (gpu_post - gpu_pre) if gpu_post is not None and gpu_pre is not None else None,
            "settling_residual": (gpu_settled - gpu_pre) if gpu_settled is not None and gpu_pre is not None else None,
        },
        "active_blocks": {
            "pre_operation": (pre or {}).get("active_blocks"),
            "post_operation": (post or {}).get("active_blocks"),
            "next_renderer": (next_renderer or {}).get("active_blocks"),
            "settling_end": (settling_end or {}).get("active_blocks"),
        },
        "operation_counts": operation_counts,
        "boundary": boundary,
        "pointer_evidence": pointer,
        "failures": sorted(set(failures)),
        "gate_pass": not failures,
    }


def _attempt(attempt_root: Path, metadata: dict, contract: dict, base: dict) -> dict:
    condition = metadata["condition"]
    label = LABELS[condition][0]
    case_dir = attempt_root / label
    raw = load(case_dir / "raw.json") or {}
    evidence = load(case_dir / "runner_evidence.json") or {}
    guard = load(attempt_root / "runner-logs" / f"{label}.guard.json") or {}
    markers = jsonl(case_dir / "resource_markers.jsonl")
    extension = jsonl(case_dir / "extension_lifecycle_markers.jsonl")
    outer = _outer_samples(attempt_root / "runner-logs" / f"{label}.resource.jsonl")
    gpu = _gpu_samples(attempt_root / "runner-logs" / f"{label}.gpu.csv")
    startup = raw.get("startup_liveness_gate") or {}
    payload = (raw.get("point_payload") or {}).get("payload_sha256")
    representative = bool(
        startup.get("classification") == "representative_ingestion"
        and startup.get("source_ok") is True
        and startup.get("telemetry_fresh") is True
        and (startup.get("identity_and_exact_source") or {}).get("pass") is True
        and payload == base["expected_stage"]["payload_sha256"]
    )
    monitor = evidence.get("shutdown_monitor") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    absolute = []
    if guard.get("status") != "ok" and not raw:
        absolute.append("diagnostic_process_failed_before_raw_evidence")
    if guard.get("stop_reason"):
        absolute.append(f"resource_guard:{guard.get('stop_reason')}")
    if evidence.get("fatal_lines"):
        absolute.append("fatal")
    if evidence.get("dump_inventory"):
        absolute.append("dump")
    if evidence.get("automatic_upload_attempt_lines"):
        absolute.append("automatic_upload")
    if evidence.get("device_lost_lines"):
        absolute.append("device_lost")
    if evidence.get("tdr_lines"):
        absolute.append("tdr")
    if monitor.get("windows_exception_present") is True:
        absolute.append("windows_exception")
    if cleanup.get("remaining") or cleanup.get("all_observed_absent") is not True:
        absolute.append("cleanup_failure")

    names = [item.get("marker") for item in markers]
    extension_names = [item.get("name") or item.get("marker") for item in extension]
    completion = raw.get("completion_contract") or {}
    native = []
    if "stage_close_request_before" in names and (
        "stage_close_timeout" in names or "stage_close_request_after" not in names or completion.get("stage_closed") is not True
    ):
        native.append("stage_close_failure")
    if "stage_close_request_after" in names and not {
        "extension_on_shutdown_begin", "extension_on_shutdown_end"
    }.issubset(set(extension_names)):
        native.append("extension_shutdown_incomplete")
    if monitor.get("residual_process") is True:
        native.append("shutdown_residual")
    if representative and (monitor.get("lifecycle_candidate") != "normal_exit" or monitor.get("exit_code") != 0):
        native.append("representative_normal_os_exit_missing")

    operation_started = any(name in names for name in ("readback_call_before", "sample_started"))
    prerequisite = []
    if not representative:
        prerequisite.append(str(startup.get("classification") or "startup_evidence_missing"))
    if payload != base["expected_stage"]["payload_sha256"]:
        prerequisite.append("payload_hash")
    if not representative and any(name == "readback_call_before" for name in names):
        prerequisite.append("readback_started_before_prerequisite_stop")

    iterations = []
    operation = []
    if representative and not absolute and not native:
        boundaries = [sample.get("readback_boundary") for sample in raw.get("samples", []) if sample.get("readback_boundary")]
        frames = contract["operation_frames"]
        expected_boundary_count = 0 if condition == "R0_control" else 3
        if len(boundaries) != expected_boundary_count:
            operation.append("readback_boundary_count")
        for index, frame in enumerate(frames, 1):
            boundary = None if condition == "R0_control" else (boundaries[index - 1] if index <= len(boundaries) else None)
            item = _iteration(
                index, frame, contract["settling_end_frames"][index - 1],
                condition, markers, boundary, outer, gpu, contract,
            )
            iterations.append(item)
            operation.extend(f"iteration{index}:{failure}" for failure in item["failures"])
        threshold = contract["accumulation_gate"]["material_step_bytes"]
        pre_gate = evaluate_staircase([item["pre_operation_private_bytes"] for item in iterations], threshold)
        settled_gate = evaluate_staircase([item["settling_end_private_bytes"] for item in iterations], threshold)
    else:
        pre_gate = evaluate_staircase([], contract["accumulation_gate"]["material_step_bytes"])
        settled_gate = evaluate_staircase([], contract["accumulation_gate"]["material_step_bytes"])

    if absolute:
        classification = "absolute_safety_failure"
    elif native:
        classification = "native_lifecycle_failure"
    elif prerequisite:
        classification = "startup_prerequisite_failure" if not any(name == "readback_call_before" for name in names) else "operation_failure"
    elif operation:
        classification = "operation_failure"
    else:
        classification = "representative_pass"

    stage_before = _first(markers, "stage_close_request_before")
    stage_after = _first(markers, "stage_close_request_after")
    return {
        "attempt_id": metadata["attempt_id"],
        "attempt_sequence": metadata["attempt_sequence"],
        "slot_id": metadata["slot_id"],
        "sequence": metadata["sequence"],
        "position": metadata["position"],
        "condition": condition,
        "classification": classification,
        "representative_startup": representative,
        "operation_started": operation_started,
        "startup_prerequisite_failures": prerequisite,
        "operation_failures": sorted(set(operation)),
        "native_lifecycle_failures": native,
        "absolute_safety_failures": absolute,
        "startup": startup,
        "iterations": iterations,
        "pre_operation_accumulation": pre_gate,
        "settling_end_accumulation": settled_gate,
        "stage_close_seconds": (_epoch(stage_after) - _epoch(stage_before)) if stage_before and stage_after else None,
        "resource": {
            "guard_status": guard.get("status"),
            "peaks": guard.get("peaks"),
            "machine_minima": guard.get("machine_minima"),
            "outer_sample_count": len(outer),
        },
        "cdb_invoked": bool(evidence.get("cdb_diagnostic")),
    }


def _distribution(values) -> dict:
    finite = [float(value) for value in values if isinstance(value, (int, float))]
    return {
        "values": finite,
        "minimum": min(finite) if finite else None,
        "median": statistics.median(finite) if finite else None,
        "mean": statistics.mean(finite) if finite else None,
        "maximum": max(finite) if finite else None,
    }


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
    for path in sorted(args.root.glob("attempt[0-9][0-9]")):
        metadata = load(path / "attempt_metadata.json")
        if metadata:
            attempts.append(_attempt(path, metadata, contract, base))
    representative = [item for item in attempts if item["classification"] == "representative_pass"]
    counts = {name: sum(item["condition"] == name for item in representative) for name in LABELS}
    nonreplaceable = [item for item in attempts if item["classification"] in {
        "operation_failure", "native_lifecycle_failure", "absolute_safety_failure"
    }]
    prereq = [item for item in attempts if item["classification"] == "startup_prerequisite_failure"]
    first_stop = next((index for index, item in enumerate(attempts) if item in nonreplaceable), None)
    post_stop = attempts[first_stop + 1:] if first_stop is not None else []
    paired = []
    paired_failures = []
    threshold = contract["accumulation_gate"]["material_step_bytes"]
    for sequence in range(1, 4):
        cases = {item["condition"]: item for item in representative if item["sequence"] == sequence}
        if len(cases) != 3:
            continue
        r0 = cases["R0_control"]
        comparisons = {}
        sequence_failures = []
        for name in ("R1_readback", "R2_fuel_alias"):
            candidate = cases[name]
            pre_gate = evaluate_paired_accumulation(
                r0["pre_operation_accumulation"]["values_bytes"],
                candidate["pre_operation_accumulation"]["values_bytes"], threshold,
            )
            settled_gate = evaluate_paired_accumulation(
                r0["settling_end_accumulation"]["values_bytes"],
                candidate["settling_end_accumulation"]["values_bytes"], threshold,
            )
            comparisons[name] = {"pre_operation": pre_gate, "settling_end": settled_gate}
            sequence_failures.extend(f"{name}:pre:{failure}" for failure in pre_gate["failures"])
            sequence_failures.extend(f"{name}:settled:{failure}" for failure in settled_gate["failures"])
        pair = {
            "sequence": sequence,
            "active_block_pre_operation": {
                name: [iteration["active_blocks"]["pre_operation"] for iteration in case["iterations"]]
                for name, case in cases.items()
            },
            "settled_total_change_bytes": {
                name: case["settling_end_accumulation"].get("step_3_minus_1_bytes")
                for name, case in cases.items()
            },
            "process_peak_differences_are_operation_cost_evidence": False,
            "r0_is_context_for_allocator_and_flow_variance": True,
            "operation_specific_accumulation": comparisons,
            "failures": sequence_failures,
            "gate_pass": not sequence_failures,
        }
        paired.append(pair)
        if sequence_failures:
            paired_failures.append(pair)
    qualified = bool(
        len(representative) == 9
        and all(value == 3 for value in counts.values())
        and not nonreplaceable
        and not post_stop
        and not paired_failures
    )
    all_iterations = [iteration for item in representative for iteration in item["iterations"]]
    r1r2 = [item for item in representative if item["condition"] != "R0_control"]
    r2 = [item for item in representative if item["condition"] == "R2_fuel_alias"]
    pointers = [iteration["pointer_evidence"] for item in r2 for iteration in item["iterations"]]
    report = {
        "schema": "campfire.phase6fl.three-iteration-report.v1",
        "phase": "phase6fl",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": contract["history_frozen"],
        "total_launches": len(attempts),
        "representative_processes": len(representative),
        "startup_prerequisite_failures": len(prereq),
        "condition_counts": counts,
        "attempts": attempts,
        "paired_context": paired,
        "paired_nonreplaceable_failures": paired_failures,
        "first_complete_pair_failure": paired_failures[0] if paired_failures else None,
        "operation_summary": {
            "readback_immediate_bytes": _distribution(
                iteration["operation_immediate_delta_bytes"] for item in r1r2 for iteration in item["iterations"]
            ),
            "numpy_asarray_immediate_bytes": _distribution(
                iteration["numpy_asarray_delta_bytes"] for item in r2 for iteration in item["iterations"]
            ),
            "settling_end_residual_bytes": _distribution(iteration["settling_end_residual_bytes"] for iteration in all_iterations),
            "settling_wall_seconds": _distribution(iteration["settling_wall_seconds"] for iteration in all_iterations),
            "settling_outer_resource_samples": _distribution(iteration["settling_outer_resource_samples"] for iteration in all_iterations),
            "r2_pointer_evidence_count": len(pointers),
            "r2_pointer_evidence_complete": len(pointers) == 9 and all(item and item["complete"] for item in pointers),
        },
        "resource_summary": {
            "kit_peak_bytes": max(
                (value for item in attempts if isinstance(
                    (value := ((item["resource"]["peaks"] or {}).get("kit"))), (int, float)
                )), default=None
            ),
            "tree_peak_bytes": max(
                (value for item in attempts if isinstance(
                    (value := ((item["resource"]["peaks"] or {}).get("tree"))), (int, float)
                )), default=None
            ),
            "minimum_available_physical_bytes": min(
                (value for item in attempts if isinstance(
                    (value := ((item["resource"]["machine_minima"] or {}).get("available_physical_bytes"))), (int, float)
                )), default=None
            ),
            "minimum_commit_headroom_bytes": min(
                (value for item in attempts if isinstance(
                    (value := ((item["resource"]["machine_minima"] or {}).get("estimated_commit_headroom_bytes"))), (int, float)
                )), default=None
            ),
        },
        "lifecycle_summary": {
            "stage_close_seconds": _distribution(item["stage_close_seconds"] for item in representative),
            "cdb_invocation_count": sum(int(item["cdb_invoked"]) for item in attempts),
        },
        "waveform_slopes_formal_gate": False,
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
