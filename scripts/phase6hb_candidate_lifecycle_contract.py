"""Pure Phase 6HB temperature-free lifecycle ladder contract."""

from __future__ import annotations


FEATURES = (
    "bounded_array_metadata",
    "non_temperature_schema_prefix",
    "velocity_sampling",
    "collector_use",
    "temperature_alias",
)

LADDER = (
    {"name": "a_readback_release_control", "mode": "R0", "features": ()},
    {"name": "b_bounded_array_metadata", "mode": "R1", "features": FEATURES[:1]},
    {"name": "c_non_temperature_schema_prefix", "mode": "R2", "features": FEATURES[:2]},
    {"name": "d_velocity_sampling_no_collector", "mode": "R3", "features": FEATURES[:3]},
    {"name": "e_velocity_sampling_with_collector", "mode": "R4", "features": FEATURES[:4]},
    {"name": "f_temperature_alias_only", "mode": "R5", "features": FEATURES[:5]},
)

BASE_MARKERS = {
    "phase6hb_readback_after",
    "phase6hb_release_after",
    "phase6hb_operation_complete",
}


def validate_ladder(rows: list[dict]) -> dict:
    reasons = []
    if [row.get("name") for row in rows] != [row["name"] for row in LADDER]:
        reasons.append("condition_order_mismatch")
    if len({row.get("name") for row in rows}) != len(rows):
        reasons.append("duplicate_condition")
    previous = set()
    for index, row in enumerate(rows):
        current = set(row.get("features") or ())
        if index == 0 and current:
            reasons.append("control_has_added_feature")
        if index > 0 and (not previous.issubset(current) or len(current - previous) != 1):
            reasons.append(f"condition_{index + 1}_not_one_variable_increment")
        previous = current
    if previous != set(FEATURES):
        reasons.append("candidate_common_prefix_not_completed")
    return {"pass": not reasons, "reasons": reasons}


def classify_axes(evidence: dict) -> dict:
    markers = set(evidence.get("markers") or ())
    operation_complete = (
        evidence.get("operation_result") == "pass"
        and BASE_MARKERS.issubset(markers)
        and evidence.get("references_released") is True
        and evidence.get("temperature_volume_calls") == 0
        and evidence.get("temperature_metadata_calls") == 0
        and evidence.get("temperature_save_calls") == 0
        and evidence.get("temperature_sampling_calls") == 0
        and evidence.get("temperature_typed_read_calls") == 0
        and evidence.get("temperature_collector_calls") == 0
    )
    lifecycle = {
        "stage_close_complete": "stage_close_complete" in markers,
        "shutdown_complete": "shutdown_complete" in markers,
        "natural_os_exit": evidence.get("raw_classification") == "normal_exit"
            and evidence.get("process_exit_code") == 0,
    }
    safety = {
        "resource_pass": evidence.get("resource_pass") is True,
        "cleanup_pass": evidence.get("cleanup_pass") is True,
        "residual_zero": evidence.get("residual_process_count") == 0,
    }
    normal = operation_complete and all(lifecycle.values()) and all(safety.values())
    if normal:
        classification = "normal_exit"
    elif not operation_complete:
        classification = "operation_failure"
    elif not lifecycle["stage_close_complete"]:
        classification = "stage_close_failure"
    elif not lifecycle["shutdown_complete"]:
        classification = "shutdown_marker_failure"
    elif not lifecycle["natural_os_exit"]:
        classification = "post_shutdown_os_exit_failure"
    elif not all(safety.values()):
        classification = "safety_failure"
    else:
        classification = "unknown_failure"
    return {
        "classification": classification,
        "operation_complete": operation_complete,
        "lifecycle": lifecycle,
        "safety": safety,
        "continue_ladder": normal,
    }
