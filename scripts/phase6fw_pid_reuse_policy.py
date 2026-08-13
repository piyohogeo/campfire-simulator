"""Fail-closed post-cleanup classification for Phase 6FW PID reuse.

This module deliberately does not alter Phase 6FU's seven-state query or exact
cleanup implementation.  It consumes the completed cleanup evidence and adds a
final policy layer that can distinguish a protected, proven PID reuse from an
attempt-owned residual.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import ntpath
import os
from pathlib import Path
from typing import Any


SCHEMA = "campfire.phase6fw.pid-reuse-policy-decision.v1"
TRUSTED_SOURCES = {"psutil", "win32"}
CREATION_TIME_TOLERANCE_SECONDS = 1.0
REQUIRED_MARKERS = (
    "cleanup_suppression_released",
    "exact_cleanup_started",
    "exact_cleanup_complete",
)
UNKNOWN_STATES = {
    "query_failed_unknown",
    "access_denied_unknown",
    "creation_time_unknown",
    "path_unknown",
}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _strip_namespace_prefix(path: str) -> str:
    lowered = path.lower()
    if lowered.startswith("\\\\?\\unc\\"):
        return "\\\\" + path[8:]
    if lowered.startswith("\\\\?\\"):
        return path[4:]
    if lowered.startswith("\\??\\"):
        return path[4:]
    return path


def _existing_final_path(path: str) -> str | None:
    """Resolve an existing Windows path without inventing aliases."""
    if os.name != "nt" or not os.path.exists(path):
        return None
    resolved = os.path.realpath(path)
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        count = ctypes.windll.kernel32.GetLongPathNameW(path, buffer, len(buffer))
        if 0 < count < len(buffer):
            resolved = buffer.value
    except (AttributeError, OSError):
        pass
    return ntpath.normcase(ntpath.normpath(_strip_namespace_prefix(resolved)))


def normalize_windows_path(value: Any) -> dict[str, Any]:
    """Return conservative Windows path evidence.

    Lexically different paths with the same executable basename are not called
    different unless both existing paths can be resolved.  This prevents an
    8.3 name, namespace prefix, junction, or System32 redirect from creating a
    false PID-reuse decision.
    """
    if not isinstance(value, str) or not value.strip():
        return {"status": "unknown", "reason": "path_missing", "input": value}
    raw = _strip_namespace_prefix(value.strip().replace("/", "\\"))
    if not ntpath.isabs(raw):
        return {"status": "unknown", "reason": "path_not_absolute", "input": value}
    lexical = ntpath.normcase(ntpath.normpath(raw))
    return {
        "status": "ok",
        "input": value,
        "lexical": lexical,
        "basename": ntpath.basename(lexical),
        "resolved_existing": _existing_final_path(raw),
    }


def compare_windows_paths(left: Any, right: Any) -> dict[str, Any]:
    a = normalize_windows_path(left)
    b = normalize_windows_path(right)
    evidence = {"left": a, "right": b}
    if a["status"] != "ok" or b["status"] != "ok":
        return {**evidence, "result": "unknown", "reason": "path_incomplete"}
    if a["lexical"] == b["lexical"]:
        return {**evidence, "result": "same", "reason": "canonical_lexical_match"}
    if a["basename"] != b["basename"]:
        return {**evidence, "result": "different", "reason": "different_executable_basename"}
    if a["resolved_existing"] and b["resolved_existing"]:
        result = "same" if a["resolved_existing"] == b["resolved_existing"] else "different"
        return {**evidence, "result": result, "reason": "existing_paths_resolved"}
    return {**evidence, "result": "unknown", "reason": "possible_unresolved_path_alias"}


def compare_creation_times(left: Any, right: Any) -> dict[str, Any]:
    a = _finite_number(left)
    b = _finite_number(right)
    if a is None or b is None:
        return {
            "result": "unknown",
            "left": left,
            "right": right,
            "unit": "UTC Unix epoch seconds",
            "tolerance_seconds": CREATION_TIME_TOLERANCE_SECONDS,
        }
    delta = abs(a - b)
    return {
        "result": "different" if delta > CREATION_TIME_TOLERANCE_SECONDS else "same",
        "left": a,
        "right": b,
        "absolute_delta_seconds": delta,
        "unit": "UTC Unix epoch seconds",
        "tolerance_seconds": CREATION_TIME_TOLERANCE_SECONDS,
    }


def compare_identities(original: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    pid_same = original.get("pid") == current.get("pid") and isinstance(original.get("pid"), int)
    time = compare_creation_times(original.get("create_time_utc_epoch"), current.get("create_time_utc_epoch"))
    path = compare_windows_paths(original.get("path"), current.get("path"))
    if not pid_same:
        result = "unknown"
        reason = "pid_not_same"
    elif time["result"] == "unknown" or path["result"] == "unknown":
        result = "unknown"
        reason = "identity_component_unknown"
    elif time["result"] == "different" or path["result"] == "different":
        result = "different"
        reason = "creation_time_or_path_differs"
    else:
        result = "same"
        reason = "creation_time_and_path_match"
    return {"result": result, "reason": reason, "pid_same": pid_same, "creation_time": time, "path": path}


def _marker_integrity(markers: list[dict[str, Any]]) -> dict[str, Any]:
    names = [row.get("marker") for row in markers if isinstance(row, dict)]
    positions: list[int] = []
    cursor = 0
    for required in REQUIRED_MARKERS:
        try:
            position = names.index(required, cursor)
        except ValueError:
            return {"complete": False, "ordered": False, "names": names, "missing": required}
        positions.append(position)
        cursor = position + 1
    return {"complete": True, "ordered": positions == sorted(positions), "names": names, "positions": positions}


def _complete_query(query: dict[str, Any]) -> bool:
    return (
        query.get("source") in TRUSTED_SOURCES
        and isinstance(query.get("pid"), int)
        and _finite_number(query.get("create_time_utc_epoch")) is not None
        and normalize_windows_path(query.get("path"))["status"] == "ok"
    )


def _queries_conflict(queries: list[dict[str, Any]]) -> bool:
    complete = [row for row in queries if _complete_query(row)]
    if len(complete) < 2:
        return False
    reference = complete[0]
    for row in complete[1:]:
        if reference["pid"] != row["pid"]:
            return True
        comparison = compare_identities(reference, row)
        if comparison["result"] != "same":
            return True
    return False


def _termination_pids(payload: dict[str, Any], cleanup: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    for row in payload.get("termination_requests") or []:
        identity = row.get("identity") if isinstance(row, dict) else None
        pid = (identity or {}).get("pid") if isinstance(identity, dict) else None
        if isinstance(pid, int):
            result.add(pid)
    for pid in cleanup.get("killed_pids") or []:
        if isinstance(pid, int):
            result.add(pid)
    return result


def _classify_mismatch(
    row: dict[str, Any],
    termination_pids: set[int],
) -> tuple[str, list[str], dict[str, Any]]:
    original = row.get("identity") or {}
    queries = [query for query in (row.get("queries") or []) if isinstance(query, dict)]
    comparisons = [
        {"source": query.get("source"), "state": query.get("state"), "comparison": compare_identities(original, query), "query": query}
        for query in queries
    ]
    complete = [item for item in comparisons if _complete_query(item["query"])]
    failures: list[str] = []
    if not isinstance(original.get("pid"), int):
        failures.append("original_pid_missing")
    if _finite_number(original.get("create_time_utc_epoch")) is None:
        failures.append("original_creation_time_missing")
    if normalize_windows_path(original.get("path"))["status"] != "ok":
        failures.append("original_absolute_path_missing")
    if not complete:
        failures.append("trusted_complete_current_identity_missing")
    if _queries_conflict(queries):
        failures.append("trusted_query_identity_conflict")
    if any(item["comparison"]["result"] == "same" for item in complete):
        failures.append("trusted_query_matches_original")
    if complete and not any(item["comparison"]["result"] == "different" for item in complete):
        failures.append("clear_identity_mismatch_missing")
    if any(item["comparison"]["result"] == "unknown" for item in complete):
        failures.append("complete_query_comparison_unknown")
    pid = original.get("pid")
    if isinstance(pid, int) and pid in termination_pids:
        failures.append("mismatched_current_identity_stop_requested")
    classification = "protected_pid_reuse_non_residual" if not failures else "unresolved_identity_failure"
    evidence = {
        "original_identity": original,
        "queries": queries,
        "comparisons": comparisons,
        "trusted_complete_query_count": len(complete),
        "access_denied_query_count": sum(row.get("state") == "access_denied_unknown" for row in queries),
        "current_identity_stop_requested": isinstance(pid, int) and pid in termination_pids,
        "original_absence_basis": "pid_occupied_by_proven_different_identity" if not failures else None,
    }
    return classification, failures, evidence


def classify(payload: dict[str, Any]) -> dict[str, Any]:
    cleanup = payload.get("cleanup") or {}
    markers = payload.get("cleanup_markers") or []
    final = cleanup.get("final") or []
    marker_integrity = _marker_integrity(markers)
    suppression = cleanup.get("cleanup_suppression") or {}
    termination_pids = _termination_pids(payload, cleanup)
    global_failures: list[str] = []
    if cleanup.get("schema") != "campfire.phase6fu.exact-cleanup-summary.v1":
        global_failures.append("phase6fu_cleanup_schema_missing")
    if cleanup.get("all_matching_absent") is not True:
        global_failures.append("matching_identity_residual")
    if cleanup.get("matching_remaining"):
        global_failures.append("matching_identity_residual")
    if cleanup.get("final_unknown"):
        global_failures.append("unresolved_identity_query")
    if cleanup.get("all_observed_absent") is not True:
        global_failures.append("attempt_absence_not_confirmed")
    if set(cleanup.get("absence_confirmation_sources") or []) != TRUSTED_SOURCES:
        global_failures.append("dual_source_evidence_missing")
    if suppression.get("released") is not True or suppression.get("timed_out") is True:
        global_failures.append("cleanup_suppression_not_released")
    if not marker_integrity.get("complete") or not marker_integrity.get("ordered"):
        global_failures.append("cleanup_marker_integrity")
    rediscovered = payload.get("post_summary_rediscovered") or []
    if rediscovered:
        global_failures.append("attempt_identity_rediscovered_after_summary")

    rows: list[dict[str, Any]] = []
    counts = {
        "attempt_identity_absent": 0,
        "attempt_owned_residual": 0,
        "protected_pid_reuse_non_residual": 0,
        "unresolved_identity_failure": 0,
        "matching_residual": 0,
        "identity_mismatch_protection": 0,
        "attempted_termination_of_mismatch": 0,
    }
    seen: set[tuple[Any, Any, Any]] = set()
    for row in final:
        if not isinstance(row, dict):
            global_failures.append("final_identity_row_invalid")
            continue
        identity = row.get("identity") or {}
        key = (identity.get("pid"), identity.get("create_time_utc_epoch"), identity.get("path"))
        if key in seen:
            continue
        seen.add(key)
        state = row.get("state")
        failures: list[str] = []
        evidence: dict[str, Any] = {"identity": identity, "phase6fu_state": state}
        if state == "confirmed_exited":
            classification = "attempt_identity_absent"
        elif state == "alive_identity_mismatch":
            classification, failures, mismatch = _classify_mismatch(row, termination_pids)
            evidence["pid_reuse"] = mismatch
            counts["identity_mismatch_protection"] += 1
            counts["attempted_termination_of_mismatch"] += int(mismatch["current_identity_stop_requested"])
        elif state == "alive_identity_match":
            classification = "attempt_owned_residual"
            failures.append("attempt_owned_identity_alive")
            counts["matching_residual"] += 1
        elif state in UNKNOWN_STATES:
            classification = "unresolved_identity_failure"
            failures.append("identity_query_unresolved")
        else:
            classification = "unresolved_identity_failure"
            failures.append("unrecognized_phase6fu_state")
        counts[classification] += 1
        rows.append({"classification": classification, "failures": failures, "evidence": evidence})

    for identity in rediscovered:
        if not isinstance(identity, dict):
            continue
        counts["attempt_identity_absent"] = max(0, counts["attempt_identity_absent"] - 1)
        counts["attempt_owned_residual"] += 1
        counts["matching_residual"] += 1
        rows.append(
            {
                "classification": "attempt_owned_residual",
                "failures": ["attempt_identity_rediscovered_after_summary"],
                "evidence": {"identity": identity, "phase6fu_state": "post_summary_rediscovered"},
            }
        )

    if not final:
        global_failures.append("final_identity_evidence_missing")
    all_other_ended = all(
        row["classification"] in {"attempt_identity_absent", "protected_pid_reuse_non_residual"}
        for row in rows
    )
    if not all_other_ended:
        global_failures.append("attempt_identity_not_absent")
    for row in rows:
        global_failures.extend(row["failures"])
    global_failures = list(dict.fromkeys(global_failures))
    final_residual = counts["attempt_owned_residual"]
    final_unknown = counts["unresolved_identity_failure"]
    qualified = not global_failures and final_residual == 0 and final_unknown == 0
    return {
        "schema": SCHEMA,
        "phase": "phase6fw",
        "status": "qualified" if qualified else "fail_closed",
        "qualified": qualified,
        "phase6fu_model_changed": False,
        "phase6fv_reclassified": False,
        "source_artifact": payload.get("source_artifact"),
        "identities": rows,
        "counts": {
            **counts,
            "unresolved_unknown": final_unknown,
            "dual_source_absence": int(set(cleanup.get("absence_confirmation_sources") or []) == TRUSTED_SOURCES),
            "cleanup_suppression_released": int(suppression.get("released") is True and suppression.get("timed_out") is not True),
            "final_attempt_owned_residual": final_residual,
        },
        "marker_integrity": marker_integrity,
        "global_failures": global_failures,
        "all_other_attempt_identities_ended": all_other_ended,
        "termination_request_pids": sorted(termination_pids),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    payload = json.loads(arguments.input.read_text(encoding="utf-8"))
    result = classify(payload)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["qualified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
