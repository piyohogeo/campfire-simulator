"""Pure Phase 6HA lifecycle-only replacement classification."""

from __future__ import annotations


REQUIRED_OPERATION_MARKERS = frozenset({
    "phase6ha_readback_after",
    "phase6ha_schema_validation_after",
    "phase6ha_velocity_pipeline_after",
    "phase6ha_temperature_entry",
    "phase6ha_temperature_conversion_before",
    "phase6ha_temperature_conversion_after",
    "phase6ha_volume_release_before",
    "phase6ha_volume_release_after",
    "phase6ha_handles_release_before",
    "phase6ha_handles_release_after",
    "phase6ha_operation_complete",
})

REQUIRED_LIFECYCLE_MARKERS = frozenset({"stage_close_complete", "shutdown_complete"})


def classify_attempt(evidence: dict) -> dict:
    """Classify one accepted launch without inferring absent evidence."""

    markers = frozenset(evidence.get("markers") or ())
    reasons: list[str] = []
    if evidence.get("operation_result") != "pass":
        reasons.append("operation_not_complete")
    if int(evidence.get("temperature_conversion_calls", -1)) != 1:
        reasons.append("temperature_conversion_count_not_one")
    if int(evidence.get("forbidden_content_access_calls", -1)) != 0:
        reasons.append("forbidden_content_access_detected")
    missing_operation = sorted(REQUIRED_OPERATION_MARKERS - markers)
    if missing_operation:
        reasons.append("operation_marker_missing:" + ",".join(missing_operation))
    missing_lifecycle = sorted(REQUIRED_LIFECYCLE_MARKERS - markers)
    if missing_lifecycle:
        reasons.append("lifecycle_marker_missing:" + ",".join(missing_lifecycle))
    if not evidence.get("resource_pass", False):
        reasons.append("resource_failure")
    if not evidence.get("temporary_cleanup_pass", False):
        reasons.append("temporary_cleanup_failure")
    if not evidence.get("process_cleanup_pass", False):
        reasons.append("process_cleanup_failure")
    if int(evidence.get("residual_process_count", -1)) != 0:
        reasons.append("residual_process_nonzero")
    if evidence.get("python_exception", False):
        reasons.append("python_exception")
    if evidence.get("native_exception", False):
        reasons.append("native_exception")
    if evidence.get("cleanup_failure", False):
        reasons.append("cleanup_failure")

    natural_exit = bool(evidence.get("natural_os_exit", False))
    exit_code = evidence.get("process_exit_code")
    if not reasons and natural_exit and exit_code == 0:
        return {"classification": "qualified_normal_exit", "replacement_allowed": False, "reasons": []}

    only_post_shutdown_exit_missing = (
        not reasons
        and not natural_exit
        and exit_code is None
        and evidence.get("raw_classification") == "os_exit_timeout"
        and evidence.get("last_lifecycle_marker") == "shutdown_complete"
    )
    if only_post_shutdown_exit_missing:
        return {
            "classification": "replaceable_post_shutdown_os_exit_failure",
            "replacement_allowed": True,
            "reasons": ["only_natural_os_exit_after_shutdown_complete_missing"],
        }
    if not reasons:
        reasons.append("termination_not_exact_post_shutdown_os_exit_failure")
    return {"classification": "nonreplaceable_failure", "replacement_allowed": False, "reasons": reasons}


def population_decision(attempts: list[dict], replacement_budget: int = 1) -> dict:
    if not attempts:
        return {"action": "launch_original", "qualified": False}
    latest = attempts[-1]
    if latest["classification"] == "qualified_normal_exit":
        return {"action": "stop_qualified", "qualified": True,
                "qualified_attempt_index": len(attempts) - 1}
    if len(attempts) == 1 and latest["replacement_allowed"] and replacement_budget == 1:
        return {"action": "launch_single_replacement", "qualified": False}
    return {"action": "stop_safe", "qualified": False}
