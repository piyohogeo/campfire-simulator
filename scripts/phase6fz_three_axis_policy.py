"""Pure Phase 6FZ three-axis classification and replacement policy.

The runtime analyzer normalizes filesystem evidence into the small structures
accepted here.  Keeping policy pure makes the fail-closed branches testable
without Kit, CDB, or a large artifact.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable


MEMORY_VALID = {
    "memory_valid_lifecycle_normal",
    "memory_valid_lifecycle_timeout",
}
MEMORY_INVALID = {
    "memory_invalid_operation_failure",
    "memory_invalid_resource_failure",
    "memory_invalid_diagnostic_cleanup_failure",
    "memory_invalid_identity_failure",
    "memory_invalid_lifecycle_failure",
}
SAFE_DEGRADED_DIAGNOSTICS = {
    "diagnostic_complete",
    "diagnostic_partial_stack_timeout",
    "diagnostic_partial_module_timeout",
    "diagnostic_attach_unavailable",
}


def _failed(mapping: dict, names: Iterable[str]) -> list[str]:
    return [name for name in names if mapping.get(name) is not True]


def classify_attempt(evidence: dict) -> dict:
    """Return a fail-closed memory/lifecycle/diagnostic classification."""

    operation = evidence.get("operation") or {}
    artifact = evidence.get("artifact") or {}
    resource = evidence.get("resource") or {}
    lifecycle = evidence.get("lifecycle") or {}
    diagnostic = evidence.get("diagnostic") or {}
    cleanup = evidence.get("cleanup") or {}
    identity = evidence.get("identity") or {}
    safety = evidence.get("safety") or {}

    operation_required = (
        "condition_operation_complete",
        "fixed_frame_reached",
        "startup_identity_match",
        "payload_identity_match",
        "source_identity_match",
        "active_block_evidence_present",
        "condition_identity_match",
        "resource_observation_complete",
        "operation_markers_complete",
        "kit_import_contract_match",
    )
    artifact_required = (
        "committed",
        "committed_before_stage_close",
        "hashes_match",
        "metadata_match",
        "telemetry_complete",
        "final_sample_before_stage_close",
    )
    operation_failures = [
        *(f"operation:{name}" for name in _failed(operation, operation_required)),
        *(f"artifact:{name}" for name in _failed(artifact, artifact_required)),
    ]
    if operation_failures:
        return _decision(
            "memory_invalid_operation_failure", operation_failures, lifecycle, diagnostic
        )

    resource_required = (
        "kit_within_limit",
        "tree_within_limit",
        "runner_within_limit",
        "diagnostic_within_limit",
        "physical_floor_met",
        "commit_floor_met",
        "no_persistent_unexplained_accumulation",
    )
    resource_failures = [f"resource:{name}" for name in _failed(resource, resource_required)]
    if resource_failures:
        return _decision(
            "memory_invalid_resource_failure", resource_failures, lifecycle, diagnostic
        )

    safety_failures = [
        f"safety:{name}"
        for name in ("fatal_zero", "dump_zero", "upload_zero", "device_lost_zero", "tdr_zero")
        if safety.get(name) is not True
    ]
    diagnostic_required = (
        "artifact_committed",
        "child_absent",
        "detach_safe",
        "attach_state_known",
        "exact_cleanup_complete",
    )
    diagnostic_failures = [
        *(f"diagnostic:{name}" for name in _failed(diagnostic, diagnostic_required)),
        *(f"cleanup:{name}" for name in _failed(cleanup, (
            "phase6fu_complete", "cleanup_suppression_released", "final_helpers_absent"
        ))),
        *safety_failures,
    ]
    diagnostic_classification = str(diagnostic.get("classification") or "diagnostic_unavailable")
    if lifecycle.get("status") == "stage_close_timeout":
        if diagnostic_classification not in SAFE_DEGRADED_DIAGNOSTICS:
            diagnostic_failures.append(f"diagnostic:unsafe_classification:{diagnostic_classification}")
    elif lifecycle.get("status") == "normal":
        # A normal lifecycle legitimately has no CDB invocation.  Its bounded
        # diagnostic contract is represented as not_required with all safety
        # predicates already true.
        if diagnostic_classification not in {"not_required", "diagnostic_complete"}:
            diagnostic_failures.append(f"diagnostic:unexpected:{diagnostic_classification}")
    if diagnostic_failures:
        return _decision(
            "memory_invalid_diagnostic_cleanup_failure", diagnostic_failures, lifecycle, diagnostic
        )

    identity_required = (
        "phase6fw_qualified",
        "attempt_owned_residual_zero",
        "unresolved_unknown_zero",
        "mismatch_stop_zero",
        "dual_source_absence",
    )
    identity_failures = [f"identity:{name}" for name in _failed(identity, identity_required)]
    if identity_failures:
        return _decision(
            "memory_invalid_identity_failure", identity_failures, lifecycle, diagnostic
        )

    status = lifecycle.get("status")
    if status == "normal":
        lifecycle_failures = _failed(
            lifecycle,
            ("stage_close_complete", "extension_shutdown_complete", "normal_os_exit"),
        )
        if not lifecycle_failures:
            return _decision("memory_valid_lifecycle_normal", [], lifecycle, diagnostic)
        return _decision(
            "memory_invalid_lifecycle_failure",
            [f"lifecycle:{name}" for name in lifecycle_failures],
            lifecycle,
            diagnostic,
        )
    if status == "stage_close_timeout":
        timeout_failures = _failed(
            lifecycle,
            ("timeout_after_stage_close_request", "measurement_completed_before_timeout"),
        )
        if not timeout_failures:
            return _decision("memory_valid_lifecycle_timeout", [], lifecycle, diagnostic)
        return _decision(
            "memory_invalid_lifecycle_failure",
            [f"lifecycle:{name}" for name in timeout_failures],
            lifecycle,
            diagnostic,
        )
    return _decision(
        "memory_invalid_lifecycle_failure",
        [f"lifecycle:unsupported_status:{status or 'missing'}"],
        lifecycle,
        diagnostic,
    )


def _decision(classification: str, failures: list[str], lifecycle: dict, diagnostic: dict) -> dict:
    return {
        "schema": "campfire.phase6fz.three-axis-attempt-decision.v1",
        "classification": classification,
        "memory_valid": classification in MEMORY_VALID,
        "lifecycle_status": lifecycle.get("status") or "unknown",
        "diagnostic_classification": diagnostic.get("classification") or "diagnostic_unavailable",
        "failures": list(dict.fromkeys(failures)),
    }

def evaluate_population(attempts: list[dict], contract: dict) -> dict:
    """Validate replacement history and compute launch/qualification gates."""

    max_launches = int(contract["population"]["maximum_total_launches"])
    max_replacements = int(contract["population"]["maximum_timeout_replacements"])
    required_per_condition = int(contract["population"]["minimum_memory_valid_per_condition"])
    required_total = int(contract["population"]["minimum_memory_valid_total"])
    required_basic = int(contract["population"]["required_basic_processes"])

    ids = [str(row.get("attempt_id")) for row in attempts]
    failures: list[str] = []
    if len(ids) != len(set(ids)):
        failures.append("attempt_overwritten_or_duplicate")
    if len(attempts) > max_launches:
        failures.append("launch_limit_exceeded")

    by_id = {str(row.get("attempt_id")): row for row in attempts}
    basic = [row for row in attempts if row.get("slot_kind", "basic") == "basic"]
    replacements = [row for row in attempts if row.get("slot_kind") == "replacement"]
    if len(replacements) > max_replacements:
        failures.append("replacement_limit_exceeded")

    timeout_by_condition: Counter[str] = Counter()
    for row in attempts:
        if row.get("classification") == "memory_valid_lifecycle_timeout":
            timeout_by_condition[str(row.get("condition"))] += 1
    if any(value > 1 for value in timeout_by_condition.values()):
        failures.append("same_condition_second_timeout")

    replacement_map = []
    for row in replacements:
        original_id = str(row.get("replacement_for") or "")
        original = by_id.get(original_id)
        valid = bool(
            original
            and original.get("classification") == "memory_valid_lifecycle_timeout"
            and original.get("condition") == row.get("condition")
        )
        if not valid:
            failures.append("invalid_replacement_origin")
        replacement_map.append(
            {
                "replacement_attempt": row.get("attempt_id"),
                "replacement_for": original_id or None,
                "condition": row.get("condition"),
                "original_preserved": original_id in by_id,
                "valid": valid,
            }
        )

    invalid = [row for row in attempts if row.get("classification") in MEMORY_INVALID]
    if invalid:
        failures.append("memory_invalid_attempt_present")

    memory_valid = [row for row in attempts if row.get("classification") in MEMORY_VALID]
    counts = Counter(str(row.get("condition")) for row in memory_valid)
    conditions = [str(row["id"]) for row in contract["conditions"]]
    condition_minimums_met = all(counts[name] >= required_per_condition for name in conditions)
    basic_complete = len(basic) == required_basic
    required_memory_population = bool(
        basic_complete and len(memory_valid) >= required_total and condition_minimums_met
    )

    pending_replacements = []
    replacement_origins = {str(row.get("replacement_for")) for row in replacements}
    for row in attempts:
        if (
            row.get("classification") == "memory_valid_lifecycle_timeout"
            and str(row.get("attempt_id")) not in replacement_origins
        ):
            pending_replacements.append(str(row.get("attempt_id")))
    if len(replacements) + len(pending_replacements) > max_replacements:
        failures.append("replacement_plan_exceeds_limit")

    return {
        "schema": "campfire.phase6fz.population-policy-decision.v1",
        "launched": len(attempts),
        "basic_launched": len(basic),
        "replacement_launched": len(replacements),
        "memory_valid": len(memory_valid),
        "memory_invalid": len(invalid),
        "normal_os_exit": sum(row.get("classification") == "memory_valid_lifecycle_normal" for row in attempts),
        "stage_close_timeout": sum(row.get("classification") == "memory_valid_lifecycle_timeout" for row in attempts),
        "memory_valid_by_condition": dict(counts),
        "timeout_by_condition": dict(timeout_by_condition),
        "basic_complete": basic_complete,
        "condition_minimums_met": condition_minimums_met,
        "required_memory_population_complete": required_memory_population,
        "pending_replacement_origins": pending_replacements,
        "replacement_map": replacement_map,
        "population_stopping_failure": bool(failures),
        "failures": list(dict.fromkeys(failures)),
    }
