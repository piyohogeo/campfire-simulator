"""Canonical Phase 6HR lifecycle evaluator with a strict NGX helper tree."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

from phase6hq_lifecycle_classification import (
    _final_absent_for_identity,
    _identity_key,
    _marker_names,
    _matching_trace_rows,
    _path_key,
    _telemetry_path,
)


EVIDENCE_SCHEMA = "campfire.phase6hr.lifecycle-evidence.v1"
EVALUATION_SCHEMA = "campfire.phase6hr.lifecycle-evaluation.v1"
ACCEPTED = {"natural_clean_exit", "cleanup_assisted_telemetry_exit", "cleanup_assisted_ngx_exit"}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _query_pair(item: dict, expected: str) -> bool:
    queries = item.get("queries") or []
    observed = {row.get("source"): row.get("state") for row in queries if isinstance(row, dict)}
    return observed == {"psutil": expected, "win32": expected}


def _kind(path: str, policy: dict) -> tuple[str, str | None]:
    telemetry, extension = _telemetry_path(path, policy)
    if telemetry:
        return "telemetry", extension
    normalized = os.path.normcase(os.path.abspath(path))
    ngx_pattern = re.compile(policy["ngx_driverstore_path_regex"], re.IGNORECASE)
    if Path(path).name.lower() == "nvngx_update.exe" and ngx_pattern.fullmatch(normalized.replace("/", "\\")):
        package = Path(path).parent.name
        return "ngx_updater", package
    if normalized == _path_key(policy["conhost_exact_path"]):
        return "ngx_conhost", "Microsoft Windows System32"
    return "unknown", None


def _trace_kit(trace_rows: list[dict], root_pid: int) -> tuple[int | None, dict | None]:
    identities = {}
    for sample in trace_rows:
        for row in sample.get("processes") or []:
            if row.get("role") == "kit" and int(row.get("parent_pid", -1)) == root_pid:
                identities[(int(row["pid"]), float(row["create_time_utc_epoch"]), _path_key(str(row["path"])))] = row
    if len(identities) != 1:
        return None, None
    key, row = next(iter(identities.items()))
    return key[0], row


def _helper_detail(identity: dict, cleanup: dict, trace_rows: list[dict], root: dict, policy: dict) -> dict:
    rows = _matching_trace_rows(trace_rows, identity)
    kind, package = _kind(str(identity.get("path", "")), policy)
    timestamps = [float(row["timestamp_utc_epoch"]) for row in rows if isinstance(row.get("timestamp_utc_epoch"), (int, float))]
    before = [item for item in cleanup.get("before") or [] if isinstance(item, dict) and isinstance(item.get("identity"), dict) and _identity_key(item["identity"]) == _identity_key(identity)]
    final = [item for item in cleanup.get("final") or [] if isinstance(item, dict) and isinstance(item.get("identity"), dict) and _identity_key(item["identity"]) == _identity_key(identity)]
    return {
        "kind": kind,
        "pid": identity.get("pid"),
        "create_time_utc_epoch": identity.get("create_time_utc_epoch"),
        "canonical_path": os.path.abspath(str(identity.get("path", ""))),
        "basename": Path(str(identity.get("path", ""))).name,
        "parent_pid": identity.get("parent_pid"),
        "attempt_id": identity.get("root_attempt_id"),
        "driver_or_extension_identity": package,
        "first_observed_utc_epoch": min(timestamps) if timestamps else None,
        "last_observed_utc_epoch": max(timestamps) if timestamps else None,
        "observed_parent_pids": sorted({int(row.get("parent_pid", -1)) for row in rows}),
        "observation_count": len(rows),
        "created_after_attempt_start": isinstance(identity.get("create_time_utc_epoch"), (int, float)) and float(identity["create_time_utc_epoch"]) > float(root.get("create_time_utc_epoch", float("inf"))),
        "termination_precheck": before[0].get("queries") if len(before) == 1 else None,
        "termination_precheck_exact_live": len(before) == 1 and _query_pair(before[0], "alive_identity_match"),
        "termination_requested_at_utc_epoch": identity.get("termination_requested_at_utc_epoch"),
        "termination_result": "absent_psutil_and_win32" if _final_absent_for_identity(cleanup, identity) else "not_verified_absent",
        "post_cleanup_queries": final[0].get("queries") if len(final) == 1 else None,
        # The Phase 6FU/FW identity path exposes executable identity but not a
        # bounded Authenticode API.  Path/package identity remains mandatory;
        # signer evidence is explicitly unavailable rather than inferred.
        "authenticode": {"status": "unavailable", "reason": "bounded_identity_path_has_no_signer_query"},
        "allow_rule": kind,
    }


def build_evidence(raw_guard: dict, operation_report: dict, runner_report: dict, marker_rows: list[dict], trace_rows: list[dict], *, attempt_id: str, mode: str, policy: dict) -> dict:
    cleanup = copy.deepcopy(raw_guard.get("observed_process_cleanup") or {})
    peaks, minima, safety = raw_guard.get("peaks") or {}, raw_guard.get("machine_minima") or {}, policy["safety"]
    resource_pass = all((
        _is_int(peaks.get("runner")) and peaks["runner"] <= safety["runner_private_limit_bytes"],
        _is_int(peaks.get("kit")) and peaks["kit"] <= safety["kit_private_limit_bytes"],
        _is_int(peaks.get("diagnostic")) and peaks["diagnostic"] <= safety["diagnostic_private_limit_bytes"],
        _is_int(peaks.get("tree")) and peaks["tree"] <= safety["unique_tree_private_limit_bytes"],
        _is_int(minima.get("available_physical_bytes")) and minima["available_physical_bytes"] >= safety["available_physical_floor_bytes"],
        _is_int(minima.get("estimated_commit_headroom_bytes")) and minima["estimated_commit_headroom_bytes"] >= safety["commit_headroom_floor_bytes"],
    ))
    markers = _marker_names(marker_rows)
    live = [item["identity"] for item in cleanup.get("before") or [] if isinstance(item, dict) and item.get("state") == "alive_identity_match" and isinstance(item.get("identity"), dict)]
    killed = [item for item in cleanup.get("killed") or [] if isinstance(item, dict)]
    root = raw_guard.get("root") or {}
    root_pid = int(root.get("pid", -1))
    kit_pid, kit_row = _trace_kit(trace_rows, root_pid)
    helpers = [_helper_detail(item, cleanup, trace_rows, root, policy) for item in live]
    fatal = runner_report.get("fatal_lines") or []
    monitor = runner_report.get("shutdown_monitor") or {}
    return {
        "schema": EVIDENCE_SCHEMA,
        "attempt_id": attempt_id,
        "mode": mode,
        "attempt_started_utc_epoch": root.get("create_time_utc_epoch"),
        "runner_pid": root_pid,
        "kit_pid": kit_pid,
        "kit_identity": kit_row,
        "operation_complete": operation_report.get("operation_complete") is True and "operation_complete" in markers,
        "shutdown_complete": operation_report.get("shutdown_complete") is True and "shutdown_complete" in markers,
        "kit_exit_code": runner_report.get("process_exit_code"),
        "guarded_runner_exit_code": raw_guard.get("exit_code"),
        "artifact_gate_pass": operation_report.get("status") == "qualified" and runner_report.get("status") == "qualified",
        "resource_gate_pass": resource_pass,
        "identity_gate_pass": cleanup.get("schema") == "campfire.phase6fu.exact-cleanup-summary.v1",
        "fatal_or_native_exception": bool(fatal) or monitor.get("windows_exception_present") is True,
        "dump_count": len(runner_report.get("dump_inventory") or []),
        "automatic_upload_count": len(runner_report.get("automatic_upload_attempt_lines") or []),
        "device_loss_or_tdr": any("device lost" in str(line).lower() or "tdr" in str(line).lower() for line in fatal),
        "cleanup": cleanup,
        "live_identities_before_cleanup": live,
        "killed_identities": killed,
        "killed_pids": cleanup.get("killed_pids"),
        "helpers": helpers,
        "telemetry_helpers": [item for item in helpers if item["kind"] == "telemetry"],
        "ngx_updaters": [item for item in helpers if item["kind"] == "ngx_updater"],
        "ngx_conhosts": [item for item in helpers if item["kind"] == "ngx_conhost"],
        "unknown_helpers": [item for item in helpers if item["kind"] == "unknown"],
        "marker_names": markers,
        "raw_guard_status_before_canonical_evaluation": raw_guard.get("status"),
        "raw_guard_stop_reason_before_canonical_evaluation": raw_guard.get("stop_reason"),
    }


def _common_reasons(evidence: dict) -> list[str]:
    reasons = []
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        reasons.append("evidence_schema_mismatch")
    for key in ("operation_complete", "shutdown_complete", "artifact_gate_pass", "resource_gate_pass", "identity_gate_pass"):
        if evidence.get(key) is not True:
            reasons.append(key + "_failed")
    if evidence.get("kit_exit_code") != 0 or evidence.get("guarded_runner_exit_code") != 0:
        reasons.append("exit_code_nonzero")
    if evidence.get("fatal_or_native_exception") or evidence.get("dump_count") != 0 or evidence.get("automatic_upload_count") != 0 or evidence.get("device_loss_or_tdr"):
        reasons.append("fatal_dump_upload_or_device_failure")
    cleanup = evidence.get("cleanup") or {}
    if cleanup.get("all_matching_absent") is not True or cleanup.get("all_observed_absent") is not True or cleanup.get("matching_remaining") or cleanup.get("final_unknown") or cleanup.get("query_unknown"):
        reasons.append("cleanup_residual_or_unknown")
    if cleanup.get("protected_identity_mismatch"):
        reasons.append("pid_reuse_or_identity_mismatch")
    suppression = cleanup.get("cleanup_suppression") or {}
    if suppression.get("released") is not True or suppression.get("timed_out") is not False:
        reasons.append("cleanup_suppression_incomplete")
    live, killed, killed_pids = evidence.get("live_identities_before_cleanup"), evidence.get("killed_identities"), evidence.get("killed_pids")
    if not isinstance(live, list) or not isinstance(killed, list) or not isinstance(killed_pids, list):
        reasons.append("cleanup_evidence_type_invalid")
        return reasons
    try:
        if sorted(_identity_key(item) for item in live) != sorted(_identity_key(item) for item in killed):
            reasons.append("killed_identity_set_mismatch")
        if sorted(int(item["pid"]) for item in killed) != sorted(int(pid) for pid in killed_pids):
            reasons.append("killed_pid_set_mismatch")
    except (KeyError, TypeError, ValueError):
        reasons.append("cleanup_identity_invalid")
    return reasons


def evaluate(evidence: dict, policy: dict) -> dict:
    reasons = _common_reasons(evidence)
    helpers = evidence.get("helpers") or []
    telemetry = evidence.get("telemetry_helpers") or []
    updaters = evidence.get("ngx_updaters") or []
    conhosts = evidence.get("ngx_conhosts") or []
    unknown = evidence.get("unknown_helpers") or []
    if len(telemetry) > 1: reasons.append("telemetry_count_exceeded")
    if len(updaters) > 1 or len(conhosts) > 1: reasons.append("ngx_tree_count_exceeded")
    if unknown: reasons.append("unknown_helper_present")
    kit_pid = evidence.get("kit_pid")
    if not _is_int(kit_pid):
        reasons.append("kit_identity_missing_or_duplicate")
    for helper in helpers:
        if helper.get("attempt_id") != evidence.get("attempt_id"): reasons.append("attempt_ownership_invalid")
        if helper.get("created_after_attempt_start") is not True: reasons.append("helper_predates_attempt")
        if helper.get("observation_count", 0) < 1: reasons.append("parent_chain_observation_missing")
        if helper.get("first_observed_utc_epoch") is None or helper.get("last_observed_utc_epoch") is None: reasons.append("observation_time_missing")
        if helper.get("termination_precheck_exact_live") is not True: reasons.append("termination_precheck_invalid")
        if helper.get("termination_requested_at_utc_epoch") is None: reasons.append("termination_time_missing")
        if helper.get("termination_result") != "absent_psutil_and_win32": reasons.append("post_cleanup_absence_invalid")
        if (helper.get("authenticode") or {}).get("status") == "mismatch": reasons.append("authenticode_identity_mismatch")
    if telemetry and (telemetry[0].get("parent_pid") != kit_pid or telemetry[0].get("observed_parent_pids") != [kit_pid]): reasons.append("telemetry_parent_chain_invalid")
    if updaters and (updaters[0].get("parent_pid") != kit_pid or updaters[0].get("observed_parent_pids") != [kit_pid]): reasons.append("ngx_parent_not_kit")
    if bool(updaters) != bool(conhosts): reasons.append("ngx_tree_incomplete")
    if updaters and conhosts and (conhosts[0].get("parent_pid") != updaters[0].get("pid") or conhosts[0].get("observed_parent_pids") != [updaters[0].get("pid")]): reasons.append("conhost_parent_not_ngx")

    classification = "cleanup_failure"
    if not reasons and not helpers:
        classification = "natural_clean_exit"
    elif not reasons and len(telemetry) == 1 and not updaters and not conhosts:
        classification = "cleanup_assisted_telemetry_exit"
    elif not reasons and len(updaters) == 1 and len(conhosts) == 1 and len(telemetry) <= 1:
        classification = "cleanup_assisted_ngx_exit"
    elif not reasons:
        reasons.append("helper_set_not_allowlisted")
    accepted = classification in ACCEPTED and not reasons
    allowed = [{"kind": item["kind"], "pid": item["pid"], "path": item["canonical_path"], "parent_pid": item["parent_pid"]} for item in helpers] if accepted else []
    return {
        "schema": EVALUATION_SCHEMA,
        "classification": classification if accepted else "cleanup_failure",
        "reason": "pass" if accepted else (reasons[0] if reasons else "cleanup_failure"),
        "accepted_for_phase6hr_boundary": accepted,
        "natural_exit": classification == "natural_clean_exit" and accepted,
        "cleanup_intervention": classification in {"cleanup_assisted_telemetry_exit", "cleanup_assisted_ngx_exit"} and accepted,
        "reasons": reasons,
        "allowed_helper_set": allowed,
        "killed_pid_set": sorted(evidence.get("killed_pids") or []),
        "telemetry_helpers": telemetry,
        "ngx_tree": {"updater": updaters[0] if len(updaters) == 1 else None, "conhost": conhosts[0] if len(conhosts) == 1 else None},
    }


def attach_evaluation(raw_guard: dict, evidence: dict, policy: dict) -> dict:
    report = copy.deepcopy(raw_guard)
    evaluation = evaluate(evidence, policy)
    report.update({
        "schema": "campfire.phase6hr.resource-guard.v1",
        "legacy_status_before_canonical_evaluation": raw_guard.get("status"),
        "legacy_stop_reason_before_canonical_evaluation": raw_guard.get("stop_reason"),
        "canonical_lifecycle_evidence": evidence,
        "canonical_lifecycle_evaluation": evaluation,
        "canonical_lifecycle_classification": evaluation["classification"],
        "status": "ok" if evaluation["accepted_for_phase6hr_boundary"] else "failed",
        "stop_reason": None if evaluation["classification"] == "natural_clean_exit" else evaluation["classification"],
    })
    return report


def consume_guard_report(report: dict, policy: dict, *, expected_attempt_id: str) -> dict:
    if report.get("schema") != "campfire.phase6hr.resource-guard.v1":
        return {"accepted": False, "reason": "guard_schema_mismatch", "classification": "cleanup_failure", "allowed_helper_set": [], "killed_pid_set": []}
    evidence, persisted = report.get("canonical_lifecycle_evidence"), report.get("canonical_lifecycle_evaluation")
    if not isinstance(evidence, dict) or not isinstance(persisted, dict):
        return {"accepted": False, "reason": "canonical_evidence_missing", "classification": "cleanup_failure", "allowed_helper_set": [], "killed_pid_set": []}
    if evidence.get("attempt_id") != expected_attempt_id:
        return {"accepted": False, "reason": "attempt_identity_mismatch", "classification": "cleanup_failure", "allowed_helper_set": [], "killed_pid_set": []}
    recomputed = evaluate(evidence, policy)
    contradictions = (
        recomputed != persisted,
        report.get("canonical_lifecycle_classification") != recomputed["classification"],
        report.get("status") != ("ok" if recomputed["accepted_for_phase6hr_boundary"] else "failed"),
    )
    if any(contradictions):
        return {"accepted": False, "reason": "guard_parent_evaluation_mismatch", "classification": "cleanup_failure", "allowed_helper_set": [], "killed_pid_set": []}
    return {
        "accepted": recomputed["accepted_for_phase6hr_boundary"],
        "reason": recomputed["reason"],
        "classification": recomputed["classification"],
        "allowed_helper_set": recomputed["allowed_helper_set"],
        "killed_pid_set": recomputed["killed_pid_set"],
        "evaluation": recomputed,
    }
