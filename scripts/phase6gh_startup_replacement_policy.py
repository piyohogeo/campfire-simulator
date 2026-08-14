"""Phase 6GH fail-closed startup-only replacement policy and fixtures."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

ACCEPTED = "accepted_normal_sample"
STARTUP = "startup_prerequisite_failure"
OPERATION = "operation_failure"
RESOURCE = "resource_failure"
LIFECYCLE = "lifecycle_failure"
CLEANUP = "cleanup_failure"


def _normal(runner: dict, guard: dict) -> bool:
    outcome = runner.get("outcome") or {}
    shutdown = runner.get("shutdown_monitor") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    return all((
        outcome.get("functional_status") == "pass",
        outcome.get("lifecycle_status") == "normal_exit",
        outcome.get("normal_exit_sample_accepted") is True,
        outcome.get("os_process_normal_exit") is True,
        runner.get("process_exit_code") == 0,
        guard.get("status") == "ok",
        guard.get("exit_code") == 0,
        cleanup.get("all_observed_absent") is True,
        shutdown.get("residual_process") is False,
    ))


def classify_attempt(raw: dict, runner: dict, guard: dict, metadata: dict | None) -> dict:
    startup = raw.get("startup_liveness_gate") or {}
    identity = startup.get("identity_and_exact_source") or {}
    shutdown = runner.get("shutdown_monitor") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    safety = []
    if guard.get("stop_reason"):
        safety.append(f"resource_guard:{guard['stop_reason']}")
    if runner.get("fatal_lines"):
        safety.append("fatal")
    if runner.get("dump_inventory"):
        safety.append("dump")
    if runner.get("automatic_upload_attempt_lines"):
        safety.append("automatic_upload")
    if shutdown.get("windows_exception_present") is True:
        safety.append("windows_exception")

    if safety:
        classification, reasons = RESOURCE, safety
    elif cleanup.get("all_observed_absent") is not True or shutdown.get("residual_process") is True:
        classification, reasons = CLEANUP, ["exact_cleanup_or_residual"]
    elif metadata is not None and _normal(runner, guard):
        metadata_ok = all((
            raw.get("status") == "ok",
            raw.get("lifecycle_marker") == "shutdown_complete",
            startup.get("classification") == "representative_ingestion",
            startup.get("readback_permitted") is True,
            identity.get("pass") is True,
            metadata.get("returned_handle_count") == 7,
        ))
        classification = ACCEPTED if metadata_ok else OPERATION
        reasons = [] if metadata_ok else ["accepted_sample_integrity"]
    else:
        exact_24 = all((
            raw.get("status") == "error",
            startup.get("classification") == "small_field_ingestion",
            startup.get("sample_count") == 120,
            startup.get("gate_frame") == 120,
            startup.get("minimum_active_blocks") == 24,
            startup.get("maximum_active_blocks") == 24,
            startup.get("first_24_frame") == 1,
            startup.get("first_above_24_frame") is None,
            startup.get("first_representative_frame") is None,
            startup.get("source_ok") is True,
            startup.get("telemetry_fresh") is True,
            identity.get("pass") is True,
            startup.get("readback_permitted") is False,
            metadata is None,
            runner.get("process_exit_code") == 1,
            runner.get("lifecycle_marker") == "shutdown_complete",
            shutdown.get("lifecycle_candidate") == "normal_exit",
            shutdown.get("exited_within_shutdown_grace") is True,
            shutdown.get("pid_absent_after_termination") is True,
            shutdown.get("terminated_by_outer_runner") is False,
            shutdown.get("residual_process") is False,
            guard.get("stop_reason") is None,
            cleanup.get("all_observed_absent") is True,
        ))
        if exact_24:
            classification, reasons = STARTUP, ["all_120_startup_samples_equal_24;readback_absent"]
        elif (raw.get("completion_contract") or {}).get("stage_closed") is not True or shutdown.get("pid_absent_after_termination") is not True:
            classification, reasons = LIFECYCLE, ["stage_close_or_process_exit_incomplete"]
        else:
            classification, reasons = OPERATION, ["startup_not_exactly_replaceable_or_artifact_integrity"]

    return {
        "schema": "campfire.phase6gh.startup-replacement-classification.v1",
        "classification": classification,
        "replacement_eligible": classification == STARTUP,
        "readback_observed": metadata is not None,
        "reasons": reasons,
        "startup": {key: startup.get(key) for key in (
            "classification", "sample_count", "gate_frame", "minimum_active_blocks",
            "maximum_active_blocks", "first_24_frame", "first_above_24_frame",
            "first_representative_frame", "source_ok", "telemetry_fresh", "readback_permitted",
        )},
    }


def advance_population(state: dict, classification: str) -> dict:
    result = copy.deepcopy(state)
    conditions = result["conditions"]
    condition = conditions[result["condition_index"]] if result["condition_index"] < len(conditions) else None
    result["total_launches"] += 1
    if classification == ACCEPTED:
        result["accepted"].append(condition)
        result["condition_index"] += 1
        result["action"] = "complete" if result["condition_index"] == len(conditions) else "next_condition"
    elif classification == STARTUP:
        if result["replacements_used"] < result["replacement_budget"]:
            result["replacements_used"] += 1
            result["action"] = "replace_same_condition"
        else:
            result["action"] = "safe_stop_replacement_budget_exhausted"
    else:
        result["action"] = "safe_stop_nonreplaceable"
    return result


def _base_documents() -> tuple[dict, dict, dict, dict]:
    raw = {
        "status": "ok", "lifecycle_marker": "shutdown_complete", "completion_contract": {"stage_closed": True},
        "startup_liveness_gate": {
            "classification": "representative_ingestion", "sample_count": 60, "gate_frame": 60,
            "minimum_active_blocks": 24, "maximum_active_blocks": 128, "first_24_frame": 1,
            "first_above_24_frame": 2, "first_representative_frame": 60, "source_ok": True,
            "telemetry_fresh": True, "readback_permitted": True,
            "identity_and_exact_source": {"pass": True},
        },
    }
    runner = {
        "process_exit_code": 0, "lifecycle_marker": "shutdown_complete",
        "outcome": {"functional_status": "pass", "lifecycle_status": "normal_exit", "normal_exit_sample_accepted": True, "os_process_normal_exit": True},
        "shutdown_monitor": {"lifecycle_candidate": "normal_exit", "exited_within_shutdown_grace": True,
            "pid_absent_after_termination": True, "terminated_by_outer_runner": False, "residual_process": False,
            "windows_exception_present": False},
        "fatal_lines": [], "dump_inventory": [], "automatic_upload_attempt_lines": [],
    }
    guard = {"status": "ok", "exit_code": 0, "stop_reason": None, "observed_process_cleanup": {"all_observed_absent": True}}
    return raw, runner, guard, {"returned_handle_count": 7}


def fixtures() -> dict:
    raw, runner, guard, metadata = _base_documents()
    cases = []

    def add(name, expected, mutate=None, keep_metadata=True):
        r, e, g, m = copy.deepcopy(raw), copy.deepcopy(runner), copy.deepcopy(guard), copy.deepcopy(metadata)
        if mutate:
            mutate(r, e, g, m)
        observed = classify_attempt(r, e, g, m if keep_metadata else None)["classification"]
        cases.append({"name": name, "expected": expected, "observed": observed, "pass": observed == expected})

    def small(r, e, g, _m):
        r["startup_liveness_gate"].update(classification="small_field_ingestion", sample_count=120, gate_frame=120,
            minimum_active_blocks=24, maximum_active_blocks=24, first_24_frame=1, first_above_24_frame=None,
            first_representative_frame=None, readback_permitted=False)
        r["status"] = "error"
        e["process_exit_code"] = 1
        e["outcome"] = {"functional_status": "fail", "lifecycle_status": "unknown_shutdown_failure", "normal_exit_sample_accepted": False, "os_process_normal_exit": False}
        g.update(status="failed", exit_code=1)

    add("accepted_normal_metadata", ACCEPTED)
    add("exact_24_no_readback_replaceable", STARTUP, small, False)
    add("exact_24_with_readback_rejected", OPERATION, small, True)
    add("source_identity_mismatch", OPERATION, lambda r, e, g, m: r["startup_liveness_gate"]["identity_and_exact_source"].__setitem__("pass", False), False)
    add("stale_timeline", OPERATION, lambda r, e, g, m: r["startup_liveness_gate"].update(telemetry_fresh=False), False)
    add("resource_limit", RESOURCE, lambda r, e, g, m: g.update(stop_reason="kit_private_limit"), False)
    add("fatal", RESOURCE, lambda r, e, g, m: e.update(fatal_lines=["fatal"]), False)
    add("cleanup_failure", CLEANUP, lambda r, e, g, m: g["observed_process_cleanup"].update(all_observed_absent=False), False)
    add("stage_close_incomplete", LIFECYCLE, lambda r, e, g, m: r["completion_contract"].update(stage_closed=False), False)

    state = {"conditions": ["C0", "C1", "C2"], "condition_index": 0, "accepted": [], "replacement_budget": 2, "replacements_used": 0, "total_launches": 0}
    for classification in (STARTUP, ACCEPTED, ACCEPTED, STARTUP, ACCEPTED):
        state = advance_population(state, classification)
    population = [{"name": "two_replacements_complete", "expected": "complete", "observed": state["action"],
                   "pass": state["action"] == "complete" and state["replacements_used"] == 2 and state["total_launches"] == 5}]
    exhausted = {"conditions": ["C0", "C1", "C2"], "condition_index": 0, "accepted": [], "replacement_budget": 2, "replacements_used": 0, "total_launches": 0}
    for _ in range(3):
        exhausted = advance_population(exhausted, STARTUP)
    population.append({"name": "third_startup_failure_stops", "expected": "safe_stop_replacement_budget_exhausted",
                       "observed": exhausted["action"], "pass": exhausted["action"] == "safe_stop_replacement_budget_exhausted"})
    nonreplaceable = advance_population({"conditions": ["C0", "C1", "C2"], "condition_index": 0, "accepted": [],
        "replacement_budget": 2, "replacements_used": 0, "total_launches": 0}, OPERATION)
    population.append({"name": "operation_failure_stops", "expected": "safe_stop_nonreplaceable",
                       "observed": nonreplaceable["action"], "pass": nonreplaceable["action"] == "safe_stop_nonreplaceable"})
    all_cases = cases + population
    return {"schema": "campfire.phase6gh.startup-replacement-fixtures.v1", "classification_cases": cases,
            "population_cases": population, "passed": sum(c["pass"] for c in all_cases), "total": len(all_cases),
            "status": "pass" if all(c["pass"] for c in all_cases) else "fail"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--guard", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.fixtures:
        result = fixtures()
    else:
        if not all((args.raw, args.runner, args.guard)):
            parser.error("--raw, --runner and --guard are required")
        result = classify_attempt(_load(args.raw), _load(args.runner), _load(args.guard),
                                  _load(args.metadata) if args.metadata and args.metadata.is_file() else None)
    _write(args.output, result)
    return 0 if not args.fixtures or result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
