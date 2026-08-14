"""Pure-Python contract helpers for Phase 6GQ."""

from __future__ import annotations


def validate_temperature_slot(schema: dict) -> dict:
    rows = [row for row in schema.get("handles", []) if row.get("index") == 0]
    passed = (
        len(rows) == 1
        and rows[0].get("channel") == "temperature"
        and rows[0].get("state") == "nonempty"
    )
    return {
        "pass": passed,
        "slot": 0,
        "channel": rows[0].get("channel") if len(rows) == 1 else None,
        "state": rows[0].get("state") if len(rows) == 1 else None,
    }


def classify(conversion_returned: bool, release_complete: bool, lifecycle_normal_exit: bool) -> dict:
    operation_complete = conversion_returned and release_complete
    if operation_complete and lifecycle_normal_exit:
        return {"operation_result": "pass", "lifecycle_result": "normal_exit", "classification": "qualified"}
    if operation_complete:
        return {"operation_result": "partial_operation_evidence", "lifecycle_result": "failure", "classification": "safe_stop"}
    return {"operation_result": "conversion_boundary_failure", "lifecycle_result": "not_qualified", "classification": "safe_stop"}
