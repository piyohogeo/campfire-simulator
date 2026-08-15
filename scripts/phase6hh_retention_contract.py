"""Canonical evidence and read-only audit for Phase 6HH result lifetime."""

from __future__ import annotations

import json
from pathlib import Path

import phase6hf_operation_schema as hf

SCHEMA = "campfire.phase6hh.operation-report.v1"
AUDIT_SCHEMA = "campfire.phase6hh.read-only-audit.v1"
COMPLETE_MARKER = "phase6hh_operation_complete"
FAILURE_MARKER = "phase6hh_operation_failure"
CONDITIONS = (
    {"name": "l0_sampling_none", "mode": "L0", "roi_count": 0, "retention": "none"},
    {"name": "l1_scene_immediate_clear", "mode": "L1", "roi_count": 1, "retention": "immediate_clear"},
    {"name": "l2_scene_retain_to_report", "mode": "L2", "roi_count": 1, "retention": "retain"},
)
ROW_BY_NAME = {row["name"]: row for row in CONDITIONS}


def new_runtime_report(*, condition: str, attempt_id: str) -> dict:
    if condition not in ROW_BY_NAME or attempt_id != condition:
        raise ValueError("condition/attempt mismatch")
    row = ROW_BY_NAME[condition]
    report = hf.new_runtime_report(condition="r0_velocity_roi_prefix_0", attempt_id="r0_velocity_roi_prefix_0")
    report.update({
        "schema": SCHEMA,
        "phase": "phase6hh",
        "condition": condition,
        "attempt_identity": {"attempt_id": attempt_id, "condition": condition},
        "mode": row["mode"],
        "executed_roi_names": [],
        "retention_mode": row["retention"],
        "sampling_result_evidence": None,
        "sampling_bounded_metadata": None,
        "sampling_local_result_clear_completed": row["roi_count"] == 0,
        "sampling_result_retained_count": 0,
        "sampling_result_retained_to_operation_report": False,
    })
    return report


def expected_counts(condition: str) -> dict[str, int]:
    if condition not in ROW_BY_NAME:
        raise ValueError("unknown condition")
    result = hf.new_counter_values()
    result.update({
        "readback": 1,
        "array_metadata": 7,
        "schema_volume_conversion": 5,
        "schema_metadata": 5,
        "schema_temporary_save": 5,
        "schema_typed_read": 5,
        "velocity_alias_metadata": 1,
        "velocity_second_conversion": 1,
        "velocity_file_save": 1,
        "velocity_file_durability_check": 1,
        "velocity_file_read": 1,
        "velocity_vector_grid_access": 1,
        "velocity_basic_metadata": 1,
        "velocity_roi_sampling": ROW_BY_NAME[condition]["roi_count"],
        "velocity_temporary_file_deletion": 1,
    })
    return result


def complete_operation(report: dict) -> None:
    report["status"] = "pass"
    report["operation_result"] = "pass"
    report["operation_complete"] = True
    hf.append_checkpoint(report, COMPLETE_MARKER)


def write_operation_report(path: Path, report: dict) -> None:
    hf.write_operation_report(path, report)


def validate_operation_files(
    report_path: Path,
    resource_marker_path: Path,
    *,
    expected_condition: str,
    expected_attempt_id: str,
    resource_pass: bool,
    cleanup_pass: bool,
) -> dict:
    raw, reasons = hf._read_report(report_path)
    resource = hf._resource_state(resource_marker_path)
    canonical_complete = False
    if raw is not None:
        calls = raw.get("calls")
        if not isinstance(calls, dict):
            reasons.append("call_counts_missing")
            calls = {}
        for key in hf.COUNTER_KEYS:
            if key not in calls:
                reasons.append(f"forbidden_call_missing:{key}")
            elif type(calls[key]) is not int:
                reasons.append(f"call_count_type_invalid:{key}")
        for key in calls:
            if key not in hf.COUNTER_KEYS:
                reasons.append(f"call_count_unknown:{key}")
        if raw.get("schema") != SCHEMA:
            reasons.append("canonical_schema_mismatch")
        if raw.get("condition") != expected_condition:
            reasons.append("canonical_condition_mismatch")
        identity = raw.get("attempt_identity")
        if not isinstance(identity, dict) or identity.get("attempt_id") != expected_attempt_id:
            reasons.append("attempt_identity_mismatch")
        checkpoints = raw.get("checkpoints")
        names = [row.get("name") for row in checkpoints if isinstance(row, dict)] if isinstance(checkpoints, list) else []
        canonical_complete = (
            raw.get("operation_result") == "pass"
            and raw.get("operation_complete") is True
            and raw.get("last_operation_marker") == COMPLETE_MARKER
            and COMPLETE_MARKER in names
        )
        if not canonical_complete:
            reasons.append("canonical_operation_incomplete")
        if raw.get("references_released") is not True:
            reasons.append("references_not_released")
        if raw.get("weak_reference_alive_after_release_count") != 0:
            reasons.append("weak_reference_residual_nonzero")
        expected = expected_counts(expected_condition)
        for key, wanted in expected.items():
            if key in calls and type(calls[key]) is int and calls[key] != wanted:
                label = "forbidden_call_nonzero" if wanted == 0 else "call_count_value_mismatch"
                reasons.append(f"{label}:{key}")
        row = ROW_BY_NAME[expected_condition]
        wanted_rois = [] if row["roi_count"] == 0 else ["scene"]
        if raw.get("executed_roi_names") != wanted_rois:
            reasons.append("executed_roi_order_mismatch")
        if raw.get("retention_mode") != row["retention"]:
            reasons.append("retention_mode_mismatch")
        if row["roi_count"]:
            evidence = raw.get("sampling_result_evidence")
            if not isinstance(evidence, dict):
                reasons.append("sampling_result_evidence_missing")
            else:
                if evidence.get("python_type") != "builtins.dict":
                    reasons.append("sampling_result_type_mismatch")
                if evidence.get("container_structure") != "mapping_with_scalar_leaves":
                    reasons.append("sampling_result_structure_mismatch")
                if evidence.get("contains_numpy") is not False or evidence.get("contains_native_wrapper") is not False:
                    reasons.append("sampling_result_contains_forbidden_owner")
                if evidence.get("weakref_supported") is not False:
                    reasons.append("sampling_result_weakref_semantics_mismatch")
            if not isinstance(raw.get("sampling_bounded_metadata"), dict):
                reasons.append("sampling_bounded_metadata_missing")
            if raw.get("sampling_local_result_clear_completed") is not True:
                reasons.append("sampling_local_result_not_cleared")
            wanted_count = 1 if row["retention"] == "retain" else 0
            if raw.get("sampling_result_retained_count") != wanted_count:
                reasons.append("sampling_retained_count_mismatch")
            if raw.get("sampling_result_retained_to_operation_report") is not (row["retention"] == "retain"):
                reasons.append("sampling_report_retention_mismatch")
    if resource["complete"] and resource["failure"]:
        reasons.append("resource_operation_markers_conflict")
    elif resource["failure"] and canonical_complete:
        reasons.append("canonical_resource_operation_conflict")
    elif resource["complete"] and not canonical_complete:
        reasons.append("resource_complete_without_canonical_complete")
    if not resource_pass:
        reasons.append("resource_gate_failed")
    if not cleanup_pass:
        reasons.append("cleanup_gate_failed")
    return {
        "pass": not reasons,
        "reasons": reasons,
        "canonical_source": str(report_path),
        "canonical_schema": SCHEMA,
        "counter_schema": list(hf.COUNTER_KEYS),
        "canonical_complete": canonical_complete,
        "resource_marker_role": "telemetry_and_consistency_only",
        "resource_operation_state": resource,
    }


def build_read_only_audit(repo: Path) -> dict:
    report_path = repo / "artifacts/phase6hf-velocity-roi-lifecycle-20260815/runs/launch02_r1_velocity_roi_prefix_1/case/post_readback_isolation.json"
    summary_path = repo / "artifacts/phase6hf-velocity-roi-lifecycle-20260815/phase6hf_summary.json"
    source_path = repo / "scripts/probe_phase6dt_flow_collision_reference.py"
    wrapper_path = repo / "scripts/probe_phase6hf_velocity_roi_lifecycle.py"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    sample = report["velocity_result"]["rois"]["scene"]
    scalar_types = {key: f"{type(value).__module__}.{type(value).__qualname__}" for key, value in sample.items()}
    source = source_path.read_text(encoding="utf-8")
    wrapper = wrapper_path.read_text(encoding="utf-8")
    invariants = {
        "sample_grid_returns_dict_literal": "def _sample_grid(grid, roi: dict, vector: bool) -> dict:" in source and "return {\n        \"available\": True" in source,
        "phase6hf_stores_original_in_rois": 'result["rois"][name] = sample_result' in source,
        "phase6hf_stores_velocity_result_in_report": 'hb.report["velocity_result"] = velocity_result' in wrapper,
        "phase6hf_clears_local_result_before_handles": wrapper.index("velocity_result = None") < wrapper.index("for index in range(len(handles))"),
    }
    if not all(invariants.values()):
        raise RuntimeError(f"Phase 6HF read-only audit invariant failed: {invariants}")
    failure = summary["first_failed_condition"]
    return {
        "schema": AUDIT_SCHEMA,
        "status": "pass",
        "phase6hf_commit": "c27267f",
        "phase6hf_artifacts_reclassified": False,
        "phase6hf_artifacts_reused_as_measurement": False,
        "sources": {"operation_report": str(report_path), "summary": str(summary_path), "shared_helper": str(source_path), "wrapper": str(wrapper_path)},
        "sample_result": {
            "python_type": "builtins.dict",
            "container_structure": "mapping_with_scalar_leaves",
            "keys": sorted(sample),
            "scalar_types": scalar_types,
            "contains_numpy": False,
            "contains_native_wrapper": False,
            "contains_grid_volume_or_handle": False,
            "weakref_supported": False,
            "bounded_values_required_by_report": sample,
        },
        "phase6hf_lifetime": {
            "stored_path": 'velocity_result -> result["rois"]["scene"]',
            "same_result_assigned_to_operation_report": True,
            "local_result_cleared_before_handle_slots": True,
            "operation_report_retains_result_through_operation_complete": True,
            "release_order": ["local velocity_result", "velocity alias", "source", "schema volume row", "grid alias", "handle list slots", "handle list"],
            "weak_residual_scope": "readback handle arrays only; builtins.dict is not weak-referenceable",
        },
        "phase6hf_r1_axes": {
            "sampling_complete": failure["functional_axis"]["sampling_call_count"] == 1,
            "temporary_cleanup_pass": failure["temporary_cleanup"]["pass"],
            "references_released": failure["functional_axis"]["references_released"],
            "weak_residual_zero": failure["functional_axis"]["weak_residual_zero"],
            "stage_close_complete": failure["lifecycle_axis"]["stage_close_complete"],
            "shutdown_complete": failure["lifecycle_axis"]["shutdown_complete"],
            "natural_os_exit": failure["lifecycle_axis"]["natural_os_exit"],
            "cleanup_pass": failure["safety_axis"]["cleanup_pass"],
            "residual_process_count": failure["residual_process_count"],
        },
        "source_invariants": invariants,
    }
