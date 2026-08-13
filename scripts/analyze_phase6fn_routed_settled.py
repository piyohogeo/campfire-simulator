"""Phase 6FN analyzer with routed, independent formal decision layers."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

try:
    from scripts.analyze_phase6fh_lifecycle_qualification import jsonl, load
    from scripts.analyze_phase6fl_three_iteration import (
        LABELS, _epoch, _first, _gpu_samples, _nearest_gpu, _outer_interval,
        _outer_samples, evaluate_staircase,
    )
    from scripts.phase6fk_pointer_evidence import pointer_evidence_from_boundary
except ModuleNotFoundError:
    from analyze_phase6fh_lifecycle_qualification import jsonl, load
    from analyze_phase6fl_three_iteration import (
        LABELS, _epoch, _first, _gpu_samples, _nearest_gpu, _outer_interval,
        _outer_samples, evaluate_staircase,
    )
    from phase6fk_pointer_evidence import pointer_evidence_from_boundary


FORMAL_METADATA_SCHEMA = "campfire.phase6fn.attempt-metadata.v1"
EMBEDDED_RAW_SCHEMA = "campfire.phase6fk.point-collision-run.v1"
OPERATION_MARKERS = {
    "pre_operation", "sample_started", "operation_completed", "release_completed",
    "readback_call_before", "readback_call_after", "fuel_conversion_before",
    "fuel_conversion_after", "original_tuple_and_all_handle_aliases_released",
    "converted_buffer_released",
}


def _private(record):
    value = ((record or {}).get("process_memory") or {}).get("private_bytes")
    return value if type(value) is int else None


def _working(record):
    value = ((record or {}).get("process_memory") or {}).get("working_set_bytes")
    return value if type(value) is int else None


def _delta(after, before):
    return after - before if type(after) is int and type(before) is int else None


def _nearest_outer(samples, timestamp):
    return min(samples, key=lambda item: abs(float(item.get("timestamp_utc_epoch") or 0.0) - timestamp)) if samples else None


def _gpu_record(samples, timestamp, gpu_index=0):
    candidates = [item for item in samples if item.get("gpu_index") == gpu_index]
    return min(candidates, key=lambda item: abs(item["timestamp_utc_epoch"] - timestamp)) if candidates else None


def _layer(name, failures, **evidence):
    return {"layer": name, "gate_pass": not failures, "failures": sorted(set(failures)), "evidence": evidence}


def route_artifact(metadata, raw):
    failures = []
    if metadata.get("schema") != FORMAL_METADATA_SCHEMA or metadata.get("phase") != "phase6fn":
        failures.append("unknown_formal_metadata_schema_or_phase")
    if raw.get("schema") != EMBEDDED_RAW_SCHEMA or raw.get("phase") != "phase6fk":
        failures.append("unknown_embedded_raw_schema_or_phase")
    return _layer(
        "phase_schema_routing", failures,
        formal_metadata_schema=metadata.get("schema"), formal_phase=metadata.get("phase"),
        embedded_raw_schema=raw.get("schema"), embedded_raw_phase=raw.get("phase"),
        legacy_evaluator_used=False, explicit_evaluator_used=True,
        formal_decision_authority="phase6fn_explicit_layers",
        legacy_warning_promoted_to_formal_failure=False,
    )


def startup_layer(raw, base):
    startup = raw.get("startup_liveness_gate") or {}
    payload = (raw.get("point_payload") or {}).get("payload_sha256")
    failures = []
    if startup.get("classification") != "representative_ingestion": failures.append(str(startup.get("classification") or "startup_evidence_missing"))
    if startup.get("source_ok") is not True: failures.append("source_not_ok")
    if startup.get("telemetry_fresh") is not True: failures.append("telemetry_not_fresh")
    if (startup.get("identity_and_exact_source") or {}).get("pass") is not True: failures.append("identity_or_exact_source")
    if payload != base["expected_stage"]["payload_sha256"]: failures.append("payload_hash")
    return _layer("startup_prerequisite", failures, startup=startup, payload_sha256=payload)


def _boundaries(raw):
    return [sample.get("readback_boundary") for sample in raw.get("samples", []) if sample.get("readback_boundary")]


def operation_layer(condition, raw, markers, contract):
    failures = []
    frames = contract["operation_frames"]
    sentinel = contract["settling_end_frames"][-1]
    boundaries = _boundaries(raw)
    expected_boundary_count = 0 if condition == "R0_control" else 3
    if len(boundaries) != expected_boundary_count: failures.append("readback_boundary_count")
    sentinel_markers = [item.get("marker") for item in markers if item.get("frame") == sentinel and item.get("marker") in OPERATION_MARKERS]
    if sentinel_markers: failures.append("fourth_operation_marker_at_sentinel")
    sample_by_frame = {sample.get("frame"): sample for sample in raw.get("samples", [])}
    sentinel_sample = sample_by_frame.get(sentinel) or {}
    if sentinel_sample.get("operation") is not False or sentinel_sample.get("sentinel") is not True:
        failures.append("nonoperation_sentinel_contract")
    iterations = []
    for index, frame in enumerate(frames, 1):
        local = []
        required = ["pre_operation", "operation_completed", "release_completed"]
        found = {name: _first(markers, name, frame) for name in required}
        for name, value in found.items():
            if value is None: local.append(f"{name}_marker_missing")
        epochs = [_epoch(found[name] or {}) for name in required]
        if all(epochs) and epochs != sorted(epochs): local.append("operation_marker_order")
        boundary = None if condition == "R0_control" else (boundaries[index - 1] if index <= len(boundaries) else None)
        expected = contract["conditions"][condition]
        counts = (boundary or {}).get("operation_counts") or ({"public_readback_calls": 0, "numpy_asarray_calls": 0, "field_persistence_calls": 0} if condition == "R0_control" else {})
        for key in ("public_readback_calls", "numpy_asarray_calls"):
            if counts.get(key) != expected[key]: local.append(f"{key}_count")
        if counts.get("field_persistence_calls", 0) != 0: local.append("field_persistence")
        if condition != "R0_control" and _first(markers, "original_tuple_and_all_handle_aliases_released", frame) is None:
            local.append("source_release_marker_missing")
        if condition == "R2_fuel_alias" and _first(markers, "converted_buffer_released", frame) is None:
            local.append("converted_release_marker_missing")
        iterations.append({"iteration": index, "frame": frame, "operation_counts": counts, "failures": local, "gate_pass": not local})
        failures.extend(f"iteration{index}:{failure}" for failure in local)
    return _layer(
        "operation_integrity", failures, condition=condition, expected_operation_frames=frames,
        actual_operation_iterations=iterations, sentinel_frame=sentinel,
        sentinel_operation_markers=sentinel_markers, readback_boundary_count=len(boundaries),
    )


def explicit_settling_layer(markers, outer, gpu, contract):
    failures = []
    iterations = []
    for index, (start_frame, end_frame) in enumerate(zip(contract["operation_frames"], contract["settling_end_frames"]), 1):
        local = []
        started = _first(markers, "settling_started", start_frame)
        ended = _first(markers, "settling_end", end_frame)
        if started is None: local.append("settling_started_missing")
        if ended is None: local.append("settling_end_missing")
        if ended and ended.get("settling_iteration") != index: local.append("settling_iteration_mismatch")
        start_epoch, end_epoch = _epoch(started or {}), _epoch(ended or {})
        elapsed = end_epoch - start_epoch if start_epoch and end_epoch else None
        interval = _outer_interval(outer, start_epoch, end_epoch) if elapsed is not None else []
        updates = _delta((ended or {}).get("kit_update_index"), (started or {}).get("kit_update_index"))
        settling = contract["settling"]
        if elapsed is None or elapsed < settling["minimum_wall_seconds"]: local.append("settling_wall_time")
        if len(interval) < settling["minimum_outer_resource_samples"]: local.append("settling_resource_samples")
        if updates is None or updates < settling["minimum_renderer_updates"]: local.append("settling_renderer_updates")
        nearest = _nearest_outer(outer, end_epoch) if ended else None
        gpu_value = _nearest_gpu(gpu, end_epoch) if ended else None
        iterations.append({
            "iteration": index, "start_frame": start_frame, "end_frame": end_frame,
            "elapsed_seconds": elapsed, "resource_sample_count": len(interval), "renderer_update_count": updates,
            "settling_end": {
                "private_bytes": _private(ended), "working_set_bytes": _working(ended),
                "unique_tree_private_bytes": (nearest or {}).get("tree_private_bytes"),
                "gpu_dedicated_memory_mib": gpu_value, "active_blocks": (ended or {}).get("active_blocks"),
                "field_element_count": (ended or {}).get("field_element_count"),
                "field_logical_bytes": (ended or {}).get("field_logical_bytes"),
                "field_measurement_source": (ended or {}).get("field_measurement_source"),
                "timeline_time": (ended or {}).get("timeline_time"), "kit_update_index": (ended or {}).get("kit_update_index"),
            },
            "failures": local, "gate_pass": not local,
        })
        failures.extend(f"iteration{index}:{failure}" for failure in local)
    return _layer("explicit_settling_integrity", failures, iterations=iterations, formal_marker="settling_end")


def pointer_layer(condition, raw, markers, gpu, contract):
    failures, evidence = [], []
    boundaries = _boundaries(raw)
    if condition == "R0_control":
        return _layer("pointer_alias_integrity", failures, applicable=False, iterations=[])
    for index, frame in enumerate(contract["operation_frames"], 1):
        boundary = boundaries[index - 1] if index <= len(boundaries) else {}
        pointer = pointer_evidence_from_boundary(boundary) if condition == "R2_fuel_alias" else {"complete": True, "failures": []}
        local = list(pointer["failures"])
        if boundary.get("weak_reference_alive_after_scope_count") != 0:
            local.append("channel_weak_reference_residual_not_zero")
        if condition == "R2_fuel_alias" and boundary.get("converted_weak_reference_alive_immediately_after_release") is not False:
            local.append("converted_weak_reference_alive_after_release")
        before, after = _first(markers, "fuel_conversion_before", frame), _first(markers, "fuel_conversion_after", frame)
        cpu_delta = _delta(_private(after), _private(before)) if condition == "R2_fuel_alias" else None
        gpu_delta = None
        if condition == "R2_fuel_alias":
            if before is None or after is None: local.append("numpy_asarray_markers")
            elif abs(cpu_delta or 0) > contract["pointer_contract"]["maximum_absolute_numpy_asarray_private_delta_bytes"]:
                local.append("numpy_asarray_adjacent_private_delta")
            gpu_before = _gpu_record(gpu, _epoch(before or {})) if before else None
            gpu_after = _gpu_record(gpu, _epoch(after or {})) if after else None
            gpu_delta = (gpu_after["dedicated_memory_mib"] - gpu_before["dedicated_memory_mib"]) if gpu_before and gpu_after else None
            if gpu_delta is not None and abs(gpu_delta) > contract["pointer_contract"]["maximum_absolute_numpy_asarray_gpu_delta_mib"]:
                local.append("numpy_asarray_adjacent_gpu_delta")
        evidence.append({"iteration": index, "frame": frame, "pointer": pointer, "cpu_private_delta_bytes": cpu_delta, "gpu_dedicated_delta_mib": gpu_delta, "failures": local, "gate_pass": not local})
        failures.extend(f"iteration{index}:{failure}" for failure in local)
    return _layer("pointer_alias_integrity", failures, applicable=True, pointer_required=condition == "R2_fuel_alias", iterations=evidence)


def safety_lifecycle_cleanup_layers(raw, evidence, guard, markers, extension):
    safety = []
    monitor = evidence.get("shutdown_monitor") or {}
    if guard.get("status") != "ok": safety.append(f"resource_guard:{guard.get('stop_reason') or 'not_ok'}")
    for key, name in (("fatal_lines", "fatal"), ("dump_inventory", "dump"), ("automatic_upload_attempt_lines", "automatic_upload"), ("device_lost_lines", "device_lost"), ("tdr_lines", "tdr")):
        if evidence.get(key): safety.append(name)
    if monitor.get("windows_exception_present") is True: safety.append("windows_exception")
    safety_layer = _layer("absolute_resource_safety", safety, guard_status=guard.get("status"), peaks=guard.get("peaks"), machine_minima=guard.get("machine_minima"))
    names = [item.get("marker") for item in markers]
    ext_names = [item.get("name") or item.get("marker") for item in extension]
    completion = raw.get("completion_contract") or {}
    lifecycle = []
    if "stage_close_request_before" not in names or "stage_close_request_after" not in names or completion.get("stage_closed") is not True: lifecycle.append("stage_close_incomplete")
    if not {"extension_on_shutdown_begin", "extension_on_shutdown_end"}.issubset(set(ext_names)): lifecycle.append("extension_shutdown_incomplete")
    if monitor.get("lifecycle_candidate") != "normal_exit" or monitor.get("exit_code") != 0: lifecycle.append("normal_os_exit_missing")
    before, after = _first(markers, "stage_close_request_before"), _first(markers, "stage_close_request_after")
    lifecycle_layer = _layer("lifecycle", lifecycle, stage_close_seconds=(_epoch(after or {}) - _epoch(before or {})) if before and after else None, cdb_invoked=bool(evidence.get("cdb_diagnostic")), monitor=monitor)
    cleanup = []
    observed = guard.get("observed_process_cleanup") or {}
    if observed.get("remaining") or observed.get("all_observed_absent") is not True: cleanup.append("cleanup_residual")
    cleanup_layer = _layer("cleanup", cleanup, observed=observed)
    return safety_layer, lifecycle_layer, cleanup_layer


def _load_object(path):
    try:
        value = load(path)
    except Exception as exc:
        return {}, f"{type(exc).__name__}:{exc}"
    return (value, None) if isinstance(value, dict) else ({}, "missing_or_not_object")


def analyze_attempt(attempt_root, metadata, contract, base):
    condition = metadata.get("condition")
    label = (contract.get("conditions", {}).get(condition) or {}).get("label", condition or "unknown")
    case_dir = attempt_root / label
    raw, raw_error = _load_object(case_dir / "raw.json")
    evidence, evidence_error = _load_object(case_dir / "runner_evidence.json")
    guard, guard_error = _load_object(attempt_root / "runner-logs" / f"{label}.guard.json")
    parse_errors = [f"raw:{raw_error}" if raw_error else None, f"runner_evidence:{evidence_error}" if evidence_error else None, f"guard:{guard_error}" if guard_error else None]
    try:
        markers = jsonl(case_dir / "resource_markers.jsonl")
        extension = jsonl(case_dir / "extension_lifecycle_markers.jsonl")
        outer = _outer_samples(attempt_root / "runner-logs" / f"{label}.resource.jsonl")
        gpu = _gpu_samples(attempt_root / "runner-logs" / f"{label}.gpu.csv")
    except Exception as exc:
        markers, extension, outer, gpu = [], [], [], []
        parse_errors.append(f"stream:{type(exc).__name__}:{exc}")
    parse_errors = [item for item in parse_errors if item]
    route = route_artifact(metadata, raw)
    if parse_errors:
        route["failures"] = sorted(set(route["failures"] + ["artifact_missing_or_parse_failure"]))
        route["gate_pass"] = False
        route["evidence"]["parse_errors"] = parse_errors
    startup = startup_layer(raw, base) if route["gate_pass"] else _layer("startup_prerequisite", ["routing_failed"])
    operation = operation_layer(condition, raw, markers, contract) if route["gate_pass"] and startup["gate_pass"] else _layer("operation_integrity", ["prerequisite_not_met"])
    settling = explicit_settling_layer(markers, outer, gpu, contract) if route["gate_pass"] and startup["gate_pass"] else _layer("explicit_settling_integrity", ["prerequisite_not_met"])
    pointer = pointer_layer(condition, raw, markers, gpu, contract) if operation["gate_pass"] else _layer("pointer_alias_integrity", ["operation_integrity_failed"])
    safety, lifecycle, cleanup = safety_lifecycle_cleanup_layers(raw, evidence, guard, markers, extension)
    paired_pending = _layer("paired_settled_accumulation", [], status="pending_population", formal_baseline="explicit_settling_end_after_ordered_release")
    layers = {item["layer"]: item for item in (route, startup, operation, settling, pointer, paired_pending, safety, lifecycle, cleanup)}
    prereq_only = not startup["gate_pass"] and route["gate_pass"] and not any(item.get("marker") in OPERATION_MARKERS for item in markers)
    if not route["gate_pass"]: classification = "diagnostic_harness_failure"
    elif not safety["gate_pass"]: classification = "absolute_safety_failure"
    elif not lifecycle["gate_pass"]: classification = "native_lifecycle_failure"
    elif not cleanup["gate_pass"]: classification = "cleanup_failure"
    elif prereq_only: classification = "startup_prerequisite_failure"
    elif not operation["gate_pass"] or not settling["gate_pass"] or not pointer["gate_pass"]: classification = "operation_failure"
    else: classification = "representative_pass"
    pre_values = [_private(_first(markers, "pre_operation", frame)) for frame in contract["operation_frames"]]
    settled_values = [item["settling_end"]["private_bytes"] for item in settling.get("evidence", {}).get("iterations", [])]
    return {
        "attempt_id": metadata.get("attempt_id"), "sequence": metadata.get("sequence"), "position": metadata.get("position"),
        "condition": condition, "classification": classification, "replaceable_startup_prerequisite": classification == "startup_prerequisite_failure",
        "routing": route["evidence"], "layers": layers, "pre_operation_values_bytes": pre_values,
        "settling_end_values_bytes": settled_values, "settling_end_accumulation": evaluate_staircase(settled_values, contract["accumulation_gate"]["material_step_bytes"]),
    }


def field_adjusted_pair(control, candidate, field, threshold):
    if not (len(control) == len(candidate) == len(field) == 3) or not all(type(v) is int for v in control + candidate + field):
        return {"complete": False, "gate_pass": False, "failures": ["paired_field_context_incomplete"]}
    candidate_steps = [candidate[i + 1] - candidate[i] for i in range(2)]
    control_steps = [control[i + 1] - control[i] for i in range(2)]
    field_steps = [max(0, field[i + 1] - field[i]) for i in range(2)]
    adjusted = [candidate_steps[i] - control_steps[i] - field_steps[i] for i in range(2)]
    total = candidate[2] - candidate[0] - (control[2] - control[0]) - max(0, field[2] - field[0])
    candidate_positive = all(step > 0 for step in candidate_steps)
    failed = candidate_positive and all(step > threshold for step in adjusted) and total > 2 * threshold
    return {"complete": True, "candidate_steps_bytes": candidate_steps, "control_steps_bytes": control_steps, "field_positive_steps_bytes": field_steps, "field_adjusted_steps_bytes": adjusted, "field_adjusted_total_bytes": total, "material_threshold_bytes": threshold, "operation_specific_staircase_accumulation": failed, "gate_pass": not failed, "failures": ["field_adjusted_material_two_step_staircase"] if failed else []}


def analyze_root(root, contract, base, contract_sha256=None):
    attempts = []
    for path in sorted(root.glob("attempt[0-9][0-9]")):
        metadata, metadata_error = _load_object(path / "attempt_metadata.json")
        if metadata_error:
            attempts.append({"attempt_id": path.name, "classification": "diagnostic_harness_failure", "layers": {"phase_schema_routing": _layer("phase_schema_routing", ["attempt_metadata_missing_or_parse_failure"], parse_error=metadata_error)} })
        else:
            attempts.append(analyze_attempt(path, metadata, contract, base))
    representative = [a for a in attempts if a["classification"] == "representative_pass"]
    counts = {name: sum(a.get("condition") == name for a in representative) for name in LABELS}
    sequence_results, reproduced = [], {"R1_readback": [], "R2_fuel_alias": []}
    threshold = contract["accumulation_gate"]["material_step_bytes"]
    for sequence in range(1, 4):
        cases = {a["condition"]: a for a in representative if a.get("sequence") == sequence}
        if len(cases) != 3: continue
        comparisons = {}
        r0 = cases["R0_control"]["settling_end_values_bytes"]
        for condition in ("R1_readback", "R2_fuel_alias"):
            candidate = cases[condition]
            field = [i["settling_end"]["field_logical_bytes"] for i in candidate["layers"]["explicit_settling_integrity"]["evidence"]["iterations"]]
            comparison = field_adjusted_pair(r0, candidate["settling_end_values_bytes"], field, threshold)
            comparisons[condition] = comparison
            if comparison.get("operation_specific_staircase_accumulation"): reproduced[condition].append(sequence)
        sequence_results.append({"sequence": sequence, "comparisons": comparisons})
    replicated = [{"condition": c, "sequences": s, "failure": "replicated_settled_field_adjusted_staircase"} for c, s in reproduced.items() if len(s) >= contract["accumulation_gate"]["minimum_reproducing_sequences"]]
    nonreplaceable = [a for a in attempts if a["classification"] not in ("representative_pass", "startup_prerequisite_failure")]
    first_stop_index = next((i for i, a in enumerate(attempts) if a in nonreplaceable), None)
    post_stop = attempts[first_stop_index + 1:] if first_stop_index is not None else []
    qualified = len(representative) == 9 and all(v == 3 for v in counts.values()) and not nonreplaceable and not post_stop and not replicated
    stage_close = [a["layers"]["lifecycle"]["evidence"].get("stage_close_seconds") for a in representative]
    finite_close = [v for v in stage_close if isinstance(v, (int, float))]
    return {
        "schema": "campfire.phase6fn.routed-settled-report.v1", "phase": "phase6fn",
        "contract_sha256": contract_sha256 or hashlib.sha256(json.dumps(contract, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest().upper(),
        "formal_decision_authority": "phase6fn_explicit_layers", "legacy_evaluator_used_for_formal_decision": False,
        "total_launches": len(attempts), "representative_processes": len(representative), "startup_replacements": sum(a["classification"] == "startup_prerequisite_failure" for a in attempts),
        "condition_counts": counts, "attempts": attempts, "sequence_results": sequence_results,
        "decision_layers": {"paired_settled_accumulation": {"gate_pass": not replicated, "failures": replicated, "sequences": sequence_results}},
        "replicated_settled_failures": replicated,
        "nonreplaceable_failures": nonreplaceable, "attempts_after_required_stop": [a.get("attempt_id") for a in post_stop],
        "stage_close_seconds": {"values": finite_close, "minimum": min(finite_close) if finite_close else None, "median": statistics.median(finite_close) if finite_close else None, "maximum": max(finite_close) if finite_close else None},
        "qualified": qualified, "three_readbacks_qualified": qualified, "three_fuel_alias_lifetimes_qualified": qualified,
        "more_than_three_iterations_qualified": False, "production_changed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True); parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--base-contract", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        contract, base = load(args.contract), load(args.base_contract)
        if not contract or not base: raise ValueError("contract_or_base_parse_failure")
        report = analyze_root(args.root, contract, base, hashlib.sha256(args.contract.read_bytes()).hexdigest().upper())
    except Exception as exc:
        report = {"schema": "campfire.phase6fn.routed-settled-report.v1", "phase": "phase6fn", "qualified": False, "analyzer_failure": f"{type(exc).__name__}:{exc}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if report.get("analyzer_failure"): raise SystemExit(2)


if __name__ == "__main__": main()
