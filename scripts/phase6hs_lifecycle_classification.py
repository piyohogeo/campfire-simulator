"""Phase 6HS operation/lifecycle composition with one shared consumer."""

from __future__ import annotations

import copy

from phase6hr_lifecycle_classification import (
    attach_evaluation as attach_phase6hr_evaluation,
    consume_guard_report as consume_phase6hr_guard,
)


GUARD_SCHEMA = "campfire.phase6hs.resource-guard.v1"


def attach_evaluation(raw_guard: dict, lifecycle_evidence: dict, policy: dict, operation_validation: dict) -> dict:
    report = attach_phase6hr_evaluation(raw_guard, lifecycle_evidence, policy)
    report["schema"] = GUARD_SCHEMA
    report["canonical_operation_validation"] = copy.deepcopy(operation_validation)
    if operation_validation.get("accepted") is not True:
        report["status"] = "failed"
        report["stop_reason"] = "canonical_operation_report_failure"
    return report


def consume_guard_report(report: dict, policy: dict, *, expected_attempt_id: str, operation_validation: dict) -> dict:
    failure = {"accepted":False,"reason":"guard_parent_operation_validation_mismatch","classification":"cleanup_failure","allowed_helper_set":[],"killed_pid_set":[]}
    if report.get("schema") != GUARD_SCHEMA:
        return {**failure, "reason":"guard_schema_mismatch"}
    persisted = report.get("canonical_operation_validation")
    if not isinstance(persisted, dict):
        return {**failure, "reason":"canonical_operation_validation_missing"}
    if persisted != operation_validation:
        return failure
    if operation_validation.get("accepted") is not True:
        return {**failure, "reason":operation_validation.get("reason", "canonical_operation_report_failure")}
    compatible = copy.deepcopy(report)
    compatible["schema"] = "campfire.phase6hr.resource-guard.v1"
    return consume_phase6hr_guard(compatible, policy, expected_attempt_id=expected_attempt_id)
