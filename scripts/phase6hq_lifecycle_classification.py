"""Canonical Phase 6HQ lifecycle producer/evaluator/consumer.

The guard owns the canonical evidence.  The parent may only validate the
persisted evidence with this same evaluator; it cannot reinterpret a failed
guard from cleanup aftermath alone.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Iterable


SCHEMA = "campfire.phase6hq.lifecycle-evidence.v1"
EVALUATION_SCHEMA = "campfire.phase6hq.lifecycle-evaluation.v1"
ACCEPTED = {"natural_clean_exit", "cleanup_assisted_exit"}


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.abspath(value))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _marker_names(rows: Iterable[dict]) -> list[str]:
    names = []
    for row in rows:
        name = row.get("marker", row.get("name"))
        if isinstance(name, str):
            names.append(name)
    return names


def _telemetry_path(path: str, policy: dict) -> tuple[bool, str | None]:
    candidate = Path(path)
    parts = [part.lower() for part in candidate.parts]
    basename = candidate.name.lower()
    if basename != policy["telemetry_basename"].lower():
        return False, None
    suffix = [part.lower() for part in Path(policy["telemetry_path_suffix"]).parts]
    if len(parts) < len(suffix) or parts[-len(suffix):] != suffix:
        return False, None
    extension = candidate.parent.parent.name
    if not extension.lower().startswith(policy["telemetry_extension_prefix"].lower()):
        return False, None
    allowed = _path_key(policy["telemetry_extension_store_root"])
    try:
        common = os.path.commonpath((_path_key(path), allowed))
    except ValueError:
        return False, None
    return common == allowed, extension


def _identity_key(identity: dict) -> tuple[int, float, str]:
    return (
        int(identity["pid"]),
        float(identity["create_time_utc_epoch"]),
        _path_key(str(identity["path"])),
    )


def _final_absent_for_identity(cleanup: dict, identity: dict) -> bool:
    key = _identity_key(identity)
    matches = [
        item for item in cleanup.get("final") or []
        if isinstance(item, dict)
        and isinstance(item.get("identity"), dict)
        and _identity_key(item["identity"]) == key
    ]
    if len(matches) != 1 or matches[0].get("state") != "confirmed_exited":
        return False
    queries = matches[0].get("queries") or []
    sources = {item.get("source"): item.get("state") for item in queries if isinstance(item, dict)}
    return sources == {"psutil": "confirmed_exited", "win32": "confirmed_exited"}


def _matching_trace_rows(trace_rows: list[dict], identity: dict) -> list[dict]:
    key = _identity_key(identity)
    matches = []
    for sample in trace_rows:
        for row in sample.get("processes") or []:
            try:
                row_key = (int(row["pid"]), float(row["create_time_utc_epoch"]), _path_key(str(row["path"])))
            except (KeyError, TypeError, ValueError):
                continue
            if row_key == key:
                matches.append({"timestamp_utc_epoch": sample.get("timestamp_utc_epoch"), **row})
    return matches


def _parent_chain(trace_rows: list[dict], identity: dict, root_pid: int) -> tuple[bool, list[dict], float | None, float | None]:
    helper_rows = _matching_trace_rows(trace_rows, identity)
    if not helper_rows:
        return False, [], None, None
    kit_pids = {
        int(row["pid"])
        for sample in trace_rows
        for row in sample.get("processes") or []
        if row.get("role") == "kit" and _is_int(row.get("pid")) and int(row.get("parent_pid", -1)) == root_pid
    }
    parent_pids = {int(row.get("parent_pid", -1)) for row in helper_rows}
    if len(parent_pids) != 1 or not parent_pids.issubset(kit_pids):
        return False, [], None, None
    kit_pid = next(iter(parent_pids))
    timestamps = [float(row["timestamp_utc_epoch"]) for row in helper_rows if isinstance(row.get("timestamp_utc_epoch"), (int, float))]
    chain = [
        {"pid": int(identity["pid"]), "basename": Path(str(identity["path"])).name, "parent_pid": kit_pid},
        {"pid": kit_pid, "role": "kit", "parent_pid": root_pid},
        {"pid": root_pid, "role": "runner", "parent_pid": None},
    ]
    return True, chain, min(timestamps) if timestamps else None, max(timestamps) if timestamps else None


def build_evidence(
    raw_guard: dict,
    operation_report: dict,
    runner_report: dict,
    marker_rows: list[dict],
    trace_rows: list[dict],
    *,
    attempt_id: str,
    mode: str,
    policy: dict,
) -> dict:
    cleanup = copy.deepcopy(raw_guard.get("observed_process_cleanup") or {})
    peaks = raw_guard.get("peaks") or {}
    minima = raw_guard.get("machine_minima") or {}
    safety = policy["safety"]
    resource_pass = all((
        _is_int(peaks.get("runner")) and peaks["runner"] <= safety["runner_private_limit_bytes"],
        _is_int(peaks.get("kit")) and peaks["kit"] <= safety["kit_private_limit_bytes"],
        _is_int(peaks.get("diagnostic")) and peaks["diagnostic"] <= safety["diagnostic_private_limit_bytes"],
        _is_int(peaks.get("tree")) and peaks["tree"] <= safety["unique_tree_private_limit_bytes"],
        _is_int(minima.get("available_physical_bytes")) and minima["available_physical_bytes"] >= safety["available_physical_floor_bytes"],
        _is_int(minima.get("estimated_commit_headroom_bytes")) and minima["estimated_commit_headroom_bytes"] >= safety["commit_headroom_floor_bytes"],
    ))
    markers = _marker_names(marker_rows)
    live = [
        item["identity"] for item in cleanup.get("before") or []
        if isinstance(item, dict) and item.get("state") == "alive_identity_match" and isinstance(item.get("identity"), dict)
    ]
    killed = [item for item in cleanup.get("killed") or [] if isinstance(item, dict)]
    root_pid = int((raw_guard.get("root") or {}).get("pid", -1))
    helper_details = []
    for identity in live:
        path_ok, extension = _telemetry_path(str(identity.get("path", "")), policy)
        chain_ok, chain, first, last = _parent_chain(trace_rows, identity, root_pid)
        helper_details.append({
            "pid": identity.get("pid"),
            "create_time_utc_epoch": identity.get("create_time_utc_epoch"),
            "canonical_path": os.path.abspath(str(identity.get("path", ""))),
            "basename": Path(str(identity.get("path", ""))).name,
            "extension_identity": extension,
            "attempt_id": identity.get("root_attempt_id"),
            "parent_chain": chain,
            "parent_chain_verified": chain_ok,
            "first_observed_utc_epoch": first,
            "last_observed_utc_epoch": last,
            "path_verified": path_ok,
            "termination_requested_at_utc_epoch": identity.get("termination_requested_at_utc_epoch"),
            "termination_result": "absent_psutil_and_win32" if _final_absent_for_identity(cleanup, identity) else "not_verified_absent",
            "before_identity_queries": next((item.get("queries") for item in cleanup.get("before") or [] if item.get("identity") == identity), None),
            "after_identity_queries": next((item.get("queries") for item in cleanup.get("final") or [] if item.get("identity") == identity), None),
        })
    fatal_lines = runner_report.get("fatal_lines") or []
    dumps = runner_report.get("dump_inventory") or []
    uploads = runner_report.get("automatic_upload_attempt_lines") or []
    monitor = runner_report.get("shutdown_monitor") or {}
    return {
        "schema": SCHEMA,
        "attempt_id": attempt_id,
        "mode": mode,
        "operation_complete": operation_report.get("operation_complete") is True and "operation_complete" in markers,
        "shutdown_complete": operation_report.get("shutdown_complete") is True and "shutdown_complete" in markers,
        "kit_exit_code": runner_report.get("process_exit_code"),
        "guarded_runner_exit_code": raw_guard.get("exit_code"),
        "artifact_gate_pass": operation_report.get("status") == "qualified" and runner_report.get("status") == "qualified",
        "resource_gate_pass": resource_pass,
        "identity_gate_pass": cleanup.get("schema") == "campfire.phase6fu.exact-cleanup-summary.v1",
        "fatal_or_native_exception": bool(fatal_lines) or monitor.get("windows_exception_present") is True,
        "dump_count": len(dumps),
        "automatic_upload_count": len(uploads),
        "device_loss_or_tdr": any("device lost" in str(line).lower() or "tdr" in str(line).lower() for line in fatal_lines),
        "cleanup": cleanup,
        "live_identities_before_cleanup": live,
        "killed_identities": killed,
        "killed_pids": cleanup.get("killed_pids"),
        "helper_details": helper_details,
        "cleanup_intervention_reason": "attempt_owned_telemetry_transmitter_outlived_kit" if live else None,
        "marker_names": markers,
        "raw_guard_status_before_canonical_evaluation": raw_guard.get("status"),
        "raw_guard_stop_reason_before_canonical_evaluation": raw_guard.get("stop_reason"),
    }


def evaluate(evidence: dict, policy: dict) -> dict:
    reasons: list[str] = []
    required_true = (
        "operation_complete", "shutdown_complete", "artifact_gate_pass",
        "resource_gate_pass", "identity_gate_pass",
    )
    for key in required_true:
        if evidence.get(key) is not True:
            reasons.append(key + "_failed")
    if evidence.get("kit_exit_code") != 0 or evidence.get("guarded_runner_exit_code") != 0:
        reasons.append("exit_code_nonzero")
    if evidence.get("fatal_or_native_exception") or evidence.get("dump_count") != 0 or evidence.get("automatic_upload_count") != 0 or evidence.get("device_loss_or_tdr"):
        reasons.append("fatal_dump_upload_or_device_failure")
    cleanup = evidence.get("cleanup") or {}
    killed_pids = evidence.get("killed_pids")
    live = evidence.get("live_identities_before_cleanup")
    killed = evidence.get("killed_identities")
    if not isinstance(killed_pids, list) or not isinstance(live, list) or not isinstance(killed, list):
        reasons.append("cleanup_evidence_type_invalid")
        live, killed, killed_pids = [], [], []
    if cleanup.get("all_matching_absent") is not True or cleanup.get("all_observed_absent") is not True:
        reasons.append("cleanup_residual")
    if cleanup.get("matching_remaining") or cleanup.get("final_unknown") or cleanup.get("query_unknown"):
        reasons.append("cleanup_unknown_or_matching_residual")
    if cleanup.get("protected_identity_mismatch"):
        reasons.append("pid_reuse_or_identity_mismatch")
    suppression = cleanup.get("cleanup_suppression") or {}
    if suppression.get("released") is not True or suppression.get("timed_out") is not False:
        reasons.append("cleanup_suppression_incomplete")

    classification = "cleanup_failure"
    helper = None
    if not reasons and len(live) == 0 and len(killed) == 0 and killed_pids == []:
        classification = "natural_clean_exit"
    elif not reasons and len(live) == 1 and len(killed) == 1 and len(killed_pids) == 1:
        live_key = _identity_key(live[0])
        killed_key = _identity_key(killed[0])
        details = evidence.get("helper_details") or []
        if live_key != killed_key or int(killed_pids[0]) != live_key[0]:
            reasons.append("killed_identity_mismatch")
        elif len(details) != 1:
            reasons.append("helper_detail_missing_or_duplicate")
        else:
            helper = details[0]
            if helper.get("path_verified") is not True:
                reasons.append("telemetry_path_invalid")
            if helper.get("parent_chain_verified") is not True:
                reasons.append("parent_chain_invalid")
            if helper.get("attempt_id") != evidence.get("attempt_id"):
                reasons.append("attempt_ownership_invalid")
            if helper.get("termination_requested_at_utc_epoch") is None:
                reasons.append("termination_time_missing")
            if helper.get("termination_result") != "absent_psutil_and_win32":
                reasons.append("termination_absence_not_verified")
            if not reasons:
                classification = "cleanup_assisted_exit"
    elif not reasons:
        reasons.append("only_zero_or_one_telemetry_residual_allowed")

    accepted = classification in ACCEPTED and not reasons
    return {
        "schema": EVALUATION_SCHEMA,
        "classification": classification if accepted else "cleanup_failure",
        "accepted_for_phase6hq_boundary": accepted,
        "natural_exit": classification == "natural_clean_exit" and accepted,
        "cleanup_intervention": classification == "cleanup_assisted_exit" and accepted,
        "reasons": reasons,
        "helper": helper if classification == "cleanup_assisted_exit" and accepted else None,
    }


def attach_evaluation(raw_guard: dict, evidence: dict, policy: dict) -> dict:
    report = copy.deepcopy(raw_guard)
    evaluation = evaluate(evidence, policy)
    report["schema"] = "campfire.phase6hq.resource-guard.v1"
    report["legacy_status_before_canonical_evaluation"] = raw_guard.get("status")
    report["legacy_stop_reason_before_canonical_evaluation"] = raw_guard.get("stop_reason")
    report["canonical_lifecycle_evidence"] = evidence
    report["canonical_lifecycle_evaluation"] = evaluation
    report["canonical_lifecycle_classification"] = evaluation["classification"]
    report["status"] = "ok" if evaluation["accepted_for_phase6hq_boundary"] else "failed"
    report["stop_reason"] = None if evaluation["classification"] == "natural_clean_exit" else evaluation["classification"]
    return report


def consume_guard_report(report: dict, policy: dict, *, expected_attempt_id: str) -> dict:
    if report.get("schema") != "campfire.phase6hq.resource-guard.v1":
        return {"accepted": False, "reason": "guard_schema_mismatch", "classification": "cleanup_failure"}
    evidence = report.get("canonical_lifecycle_evidence")
    persisted = report.get("canonical_lifecycle_evaluation")
    if not isinstance(evidence, dict) or not isinstance(persisted, dict):
        return {"accepted": False, "reason": "canonical_evidence_missing", "classification": "cleanup_failure"}
    if evidence.get("attempt_id") != expected_attempt_id:
        return {"accepted": False, "reason": "attempt_identity_mismatch", "classification": "cleanup_failure"}
    recomputed = evaluate(evidence, policy)
    if recomputed != persisted:
        return {"accepted": False, "reason": "guard_parent_evaluation_mismatch", "classification": "cleanup_failure"}
    if report.get("canonical_lifecycle_classification") != recomputed["classification"]:
        return {"accepted": False, "reason": "guard_classification_contradiction", "classification": "cleanup_failure"}
    expected_status = "ok" if recomputed["accepted_for_phase6hq_boundary"] else "failed"
    if report.get("status") != expected_status:
        return {"accepted": False, "reason": "guard_status_contradiction", "classification": "cleanup_failure"}
    return {
        "accepted": recomputed["accepted_for_phase6hq_boundary"],
        "reason": "pass" if recomputed["accepted_for_phase6hq_boundary"] else "canonical_cleanup_failure",
        "classification": recomputed["classification"],
        "evaluation": recomputed,
    }


def read_jsonl(path: Path, maximum_bytes: int = 64 * 1024 * 1024) -> list[dict]:
    if not path.is_file() or path.stat().st_size > maximum_bytes:
        raise RuntimeError("bounded_jsonl_unavailable:" + str(path))
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows
