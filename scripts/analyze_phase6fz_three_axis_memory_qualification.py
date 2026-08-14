"""Analyze Phase 6FZ memory validity, lifecycle, and diagnostic cleanup separately."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_phase6fx_memory_ceiling_qualification as phase6fx
import analyze_phase6ft_memory_ceiling_qualification as legacy
from phase6fz_three_axis_policy import MEMORY_VALID, classify_attempt, evaluate_population


def _json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _jsonl(path: Path) -> list[dict]:
    return legacy._jsonl(path)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest().upper()


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _ordered(names: list[str], required: list[str]) -> bool:
    cursor = -1
    for name in required:
        try:
            cursor = names.index(name, cursor + 1)
        except ValueError:
            return False
    return True


def _base_report(root: Path, contract: dict) -> dict:
    compatibility = copy.deepcopy(contract)
    compatibility["phase"] = "phase6fx"
    compatibility["schema"] = "campfire.phase6fx.memory-ceiling-qualification-contract.v1"
    compatibility["population"]["required_representative_processes"] = int(
        contract["population"]["required_basic_processes"]
    )
    compatibility.setdefault("startup", {})["startup_replacement_budget"] = 0
    with tempfile.TemporaryDirectory(prefix="phase6fz-base-") as directory:
        path = Path(directory) / "compatibility.json"
        path.write_text(json.dumps(compatibility), encoding="utf-8")
        return phase6fx.build(root, path)


def _artifact_gate(attempt_root: Path, markers: list[dict]) -> tuple[dict, dict | None, dict | None, dict | None]:
    memory_root = attempt_root / "case" / "memory-measurement"
    commit = _json(memory_root / "memory_measurement_commit.json")
    committer = _json(memory_root / "committer_summary.json")
    raw_snapshot = _json(memory_root / "measurement_raw_snapshot.json")
    metadata_snapshot = _json(memory_root / "attempt_metadata_snapshot.json")
    commit_markers = _jsonl(memory_root / "measurement_commit_markers.jsonl")
    marker = next((row for row in commit_markers if row.get("marker") == "memory_measurement_artifact_committed"), None)
    close = next((row for row in markers if row.get("marker") == "stage_close_request_before"), None)
    commit_time = _parse_time((marker or {}).get("timestamp_utc") or (commit or {}).get("committed_at_utc"))
    close_time = _parse_time((close or {}).get("timestamp_utc"))

    hashes_match = bool(commit and marker)
    checked_files = []
    for name, details in (commit or {}).get("files", {}).items():
        path = Path(str((details or {}).get("path") or ""))
        expected = str((details or {}).get("sha256") or "").upper()
        observed = _sha256(path)
        match = bool(expected and observed == expected)
        hashes_match = hashes_match and match
        checked_files.append({"name": name, "path": str(path), "expected": expected, "observed": observed, "match": match})
    summary_hash = _sha256(memory_root / "memory_measurement_commit.json")
    marker_summary_hash = str((marker or {}).get("summary_sha256") or "").upper()
    hashes_match = hashes_match and bool(summary_hash and summary_hash == marker_summary_hash)

    committed_before = bool(
        commit
        and commit.get("status") == "committed_before_stage_close"
        and not commit.get("stage_close_observed_during_commit")
        and (close_time is None or (commit_time is not None and commit_time < close_time))
    )
    telemetry = (commit or {}).get("telemetry") or {}
    telemetry_complete = bool(
        int(telemetry.get("resource_sample_count") or 0) > 0
        and telemetry.get("kit_observed") is True
        and telemetry.get("runner_observed") is True
        and telemetry.get("diagnostic_observed") is True
        and telemetry.get("tree_private_present") is True
        and telemetry.get("available_physical_present") is True
        and telemetry.get("commit_headroom_present") is True
    )
    actual_metadata = _json(attempt_root / "attempt_metadata.json") or {}
    metadata_match = bool(
        metadata_snapshot
        and metadata_snapshot.get("attempt_id") == actual_metadata.get("attempt_id")
        and metadata_snapshot.get("condition") == actual_metadata.get("condition")
        and metadata_snapshot.get("slot_id") == actual_metadata.get("slot_id")
        and metadata_snapshot.get("replacement_for") == actual_metadata.get("replacement_for")
    )
    evidence = {
        "committed": bool(commit and committer and committer.get("status") == "ok" and marker),
        "committed_before_stage_close": committed_before,
        "hashes_match": hashes_match,
        "metadata_match": metadata_match,
        "telemetry_complete": telemetry_complete,
        "final_sample_before_stage_close": committed_before,
        "commit": commit,
        "committer": committer,
        "commit_marker": marker,
        "commit_time_utc": commit_time.isoformat() if commit_time else None,
        "stage_close_request_time_utc": close_time.isoformat() if close_time else None,
        "files_checked": checked_files,
        "summary_hash_match": bool(summary_hash and summary_hash == marker_summary_hash),
    }
    return evidence, raw_snapshot, metadata_snapshot, commit


def _diagnostic_gate(attempt_root: Path, base: dict, lifecycle_status: str, identity_counts: dict) -> dict:
    diagnostic_path = attempt_root / "case" / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json"
    diagnostic = base.get("diagnostic") or {}
    if lifecycle_status == "normal":
        return {
            "classification": "not_required",
            "artifact_committed": True,
            "child_absent": True,
            "detach_safe": True,
            "attach_state_known": True,
            "exact_cleanup_complete": True,
            "started": False,
        }
    started = diagnostic_path.is_file() and diagnostic.get("started") is True
    attach = diagnostic.get("attach_observed")
    detach = diagnostic.get("detach_observed")
    stack_pass = diagnostic.get("all_thread_stack_pass") or {}
    module_pass = diagnostic.get("module_pass") or {}
    detach_pass = diagnostic.get("detach_recovery_pass") or {}
    child_passes = [value for value in (stack_pass, module_pass, detach_pass) if isinstance(value, dict) and value]
    child_absent = bool(child_passes) and all(value.get("process_absent") is True for value in child_passes)
    attach_known = isinstance(attach, bool)
    detach_safe = detach is True or attach is False
    if attach is False:
        classification = "diagnostic_attach_unavailable"
    elif stack_pass.get("timed_out"):
        classification = "diagnostic_partial_stack_timeout"
    elif module_pass.get("timed_out"):
        classification = "diagnostic_partial_module_timeout"
    elif diagnostic.get("all_thread_stack_observed") and diagnostic.get("modules_observed") and detach_safe:
        classification = "diagnostic_complete"
    elif detach_safe:
        classification = "diagnostic_partial_stack_timeout"
    else:
        classification = "diagnostic_detach_failure"
    return {
        "classification": classification,
        "artifact_committed": started,
        "child_absent": child_absent,
        "detach_safe": detach_safe,
        "attach_state_known": attach_known,
        "exact_cleanup_complete": identity_counts.get("final_attempt_owned_residual", 0) == 0,
        "started": started,
        "attach_observed": attach,
        "detach_observed": detach,
        "all_thread_stack_observed": diagnostic.get("all_thread_stack_observed"),
        "modules_observed": diagnostic.get("modules_observed"),
        "known_ngx_signature": diagnostic.get("known_ngx_signature") is True,
        "passes": {"stack": stack_pass, "module": module_pass, "detach": detach_pass},
        "diagnostic_path": str(diagnostic_path),
    }


def _attempt_evidence(attempt_root: Path, base: dict, condition: dict, contract: dict) -> tuple[dict, dict]:
    markers = _jsonl(attempt_root / "case" / "resource_markers.jsonl")
    names = [str(row.get("marker")) for row in markers]
    artifact, raw, metadata, commit = _artifact_gate(attempt_root, markers)
    raw = raw or {}
    metadata = metadata or {}
    samples = raw.get("samples") or []
    observed_frames = {int(row.get("frame")) for row in samples if row.get("frame") is not None}
    payload = raw.get("point_payload") or {}
    startup = raw.get("startup_liveness_gate") or {}
    source = raw.get("source_sums") or {}
    required_source = contract["physical_fixture"]["expected_source_sums"]
    tolerance = float(contract["physical_fixture"]["source_sum_absolute_tolerance"])
    source_match = all(
        abs(float(source.get(name, float("inf"))) - float(required_source[name])) <= tolerance
        for name in ("fuel", "temperature", "smoke")
    )
    snapshot_trace = None
    snapshot_resource = attempt_root / "case" / "memory-measurement" / "measurement_resource_snapshot.jsonl"
    if snapshot_resource.is_file() and raw:
        snapshot_trace = legacy._trace_summary(snapshot_resource, raw, contract)
    snapshot_trace = snapshot_trace or {}
    full_trace = base.get("resource_trace") or {}
    max_kit = max(int(snapshot_trace.get("kit_private_peak_bytes") or 0), int(full_trace.get("kit_private_peak_bytes") or 0))
    max_tree = max(int(snapshot_trace.get("tree_private_peak_bytes") or 0), int(full_trace.get("tree_private_peak_bytes") or 0))
    max_runner = max(int(snapshot_trace.get("runner_private_peak_bytes") or 0), int(full_trace.get("runner_private_peak_bytes") or 0))
    max_diagnostic = max(int(snapshot_trace.get("diagnostic_private_peak_bytes") or 0), int(full_trace.get("diagnostic_private_peak_bytes") or 0))
    physical_values = [value for value in (
        snapshot_trace.get("available_physical_minimum_bytes"), full_trace.get("available_physical_minimum_bytes")
    ) if value is not None]
    commit_values = [value for value in (
        snapshot_trace.get("commit_headroom_minimum_bytes"), full_trace.get("commit_headroom_minimum_bytes")
    ) if value is not None]

    identity = base.get("identity_cleanup") or {}
    counts = identity.get("counts") or {}
    lifecycle_status = (
        "normal" if "stage_close_complete" in names and "shutdown_complete" in names and base.get("process_exit_code") == 0
        else "stage_close_timeout" if "stage_close_timeout" in names
        else "other_failure"
    )
    diagnostic = _diagnostic_gate(attempt_root, base, lifecycle_status, counts)
    runner_evidence = _json(attempt_root / "case" / "runner_evidence.json") or {}
    import_audit = runner_evidence.get("kit_import_audit") or {}
    dump_count = len(runner_evidence.get("dump_inventory") or [])
    fatal_count = len(runner_evidence.get("fatal_lines") or [])
    upload_count = len(runner_evidence.get("automatic_upload_attempt_lines") or [])
    timeout_after_request = _ordered(names, ["stage_close_request_before", "stage_close_timeout"])
    measurement_before_timeout = _ordered(names, ["measurement_complete", "stage_close_request_before", "stage_close_timeout"])

    normalized = {
        "operation": {
            "condition_operation_complete": raw.get("status") == "ok" and (raw.get("completion_contract") or {}).get("results_saved") is True,
            "fixed_frame_reached": set(condition["sample_frames"]).issubset(observed_frames),
            "startup_identity_match": startup.get("classification") == "representative_ingestion" and startup.get("readback_permitted") is True,
            "payload_identity_match": (
                str(payload.get("payload_sha256") or "").upper() == contract["physical_fixture"]["payload_sha256"]
                and int(payload.get("active_count", payload.get("active_point_count", -1))) == int(contract["physical_fixture"]["active_points"])
                and int(payload.get("total_count", payload.get("total_point_count", payload.get("original_point_count", -1)))) == int(contract["physical_fixture"]["total_points"])
                and int(raw.get("revision", -1)) == int(contract["physical_fixture"]["revision"])
            ),
            "source_identity_match": source_match,
            "active_block_evidence_present": all(row.get("active_blocks") is not None for row in samples) and bool(samples),
            "condition_identity_match": metadata.get("condition") == condition["id"],
            "resource_observation_complete": int(snapshot_trace.get("kit_sample_count") or 0) >= int(contract["recording"]["minimum_preclose_resource_samples"]),
            "operation_markers_complete": _ordered(names, ["final_sample_complete", "measurement_complete"]),
            "kit_import_contract_match": (
                import_audit.get("status") == "pass"
                and Path(str((import_audit.get("import") or {}).get("resolved_file") or "")).resolve()
                == (SCRIPT_DIR / "probe_phase6fo_supply_comparison.py").resolve()
                and set((import_audit.get("import") or {}).get("required_entrypoints") or ())
                == {"_run", "_append_resource_marker"}
            ),
        },
        "artifact": {name: artifact.get(name) is True for name in (
            "committed", "committed_before_stage_close", "hashes_match", "metadata_match",
            "telemetry_complete", "final_sample_before_stage_close"
        )},
        "resource": {
            "kit_within_limit": max_kit < int(contract["safety"]["kit_absolute_stop_bytes"]),
            "tree_within_limit": max_tree < int(contract["safety"]["unique_tree_absolute_stop_bytes"]),
            "runner_within_limit": max_runner <= int(contract["safety"]["runner_private_limit_bytes"]),
            "diagnostic_within_limit": max_diagnostic <= int(contract["safety"]["diagnostic_private_limit_bytes"]),
            "physical_floor_met": bool(physical_values) and min(physical_values) >= int(contract["safety"]["physical_memory_floor_bytes"]),
            "commit_floor_met": bool(commit_values) and min(commit_values) >= int(contract["safety"]["commit_headroom_floor_bytes"]),
            "no_persistent_unexplained_accumulation": not bool((snapshot_trace.get("final_window") or {}).get("persistent_unexplained_accumulation")),
        },
        "lifecycle": {
            "status": lifecycle_status,
            "stage_close_complete": "stage_close_complete" in names,
            "extension_shutdown_complete": "extension_on_shutdown_end" in (base.get("extension_shutdown_markers") or []),
            "normal_os_exit": base.get("process_exit_code") == 0 and "os_process_exit_observed" in _jsonl_names(attempt_root / "case" / "runner_lifecycle_markers.jsonl"),
            "timeout_after_stage_close_request": timeout_after_request,
            "measurement_completed_before_timeout": measurement_before_timeout,
        },
        "diagnostic": diagnostic,
        "cleanup": {
            "phase6fu_complete": identity.get("qualified") is True,
            "cleanup_suppression_released": counts.get("cleanup_suppression_released", 0) >= 1,
            "final_helpers_absent": counts.get("final_attempt_owned_residual", 0) == 0 and counts.get("unresolved_unknown", 0) == 0,
        },
        "identity": {
            "phase6fw_qualified": identity.get("qualified") is True,
            "attempt_owned_residual_zero": counts.get("final_attempt_owned_residual", 0) == 0,
            "unresolved_unknown_zero": counts.get("unresolved_unknown", 0) == 0,
            "mismatch_stop_zero": counts.get("attempted_termination_of_mismatch", 0) == 0,
            "dual_source_absence": counts.get("dual_source_absence", 0) >= 1,
        },
        "safety": {
            "fatal_zero": fatal_count == 0,
            "dump_zero": dump_count == 0,
            "upload_zero": upload_count == 0,
            "device_lost_zero": not any("device lost" in str(value).lower() for value in runner_evidence.get("fatal_lines") or []),
            "tdr_zero": not any("tdr" in str(value).lower() for value in runner_evidence.get("fatal_lines") or []),
        },
    }
    details = {
        "artifact_commit": artifact,
        "snapshot_resource_trace": snapshot_trace,
        "full_resource_trace": full_trace,
        "formal_resource": {
            "kit_private_peak_bytes": max_kit,
            "tree_private_peak_bytes": max_tree,
            "runner_private_peak_bytes": max_runner,
            "diagnostic_private_peak_bytes": max_diagnostic,
            "available_physical_minimum_bytes": min(physical_values) if physical_values else None,
            "commit_headroom_minimum_bytes": min(commit_values) if commit_values else None,
        },
        "markers": names,
        "raw_snapshot": raw,
        "metadata_snapshot": metadata,
        "condition_contract": condition,
        "identity_cleanup": identity,
        "diagnostic": diagnostic,
        "safety_counts": {"fatal": fatal_count, "dump": dump_count, "upload": upload_count},
        "stage_close_seconds": base.get("stage_close_seconds"),
        "stage_close_timeout_seconds": base.get("stage_close_timeout_seconds"),
    }
    return normalized, details


def _jsonl_names(path: Path) -> list[str]:
    return [str(row.get("marker") or row.get("name")) for row in _jsonl(path)]


def _median(values: list[int]) -> float | int | None:
    return statistics.median(values) if values else None


def build(root: Path, contract_path: Path) -> dict:
    contract = _json(contract_path)
    if not contract or contract.get("phase") != "phase6fz":
        raise ValueError("invalid Phase 6FZ contract")
    base = _base_report(root, contract)
    by_condition = {row["id"]: row for row in contract["conditions"]}
    attempts = []
    base_by_id = {row["attempt_id"]: row for row in base.get("attempts") or []}
    for attempt_root in sorted((root / "attempts").glob("attempt*")):
        if not attempt_root.is_dir():
            continue
        metadata = _json(attempt_root / "attempt_metadata.json") or {}
        attempt_id = str(metadata.get("attempt_id") or attempt_root.name)
        base_attempt = base_by_id.get(attempt_id) or {}
        condition = by_condition.get(str(metadata.get("condition")))
        if condition is None:
            attempts.append({
                "attempt_id": attempt_id,
                "condition": metadata.get("condition"),
                "slot_kind": metadata.get("slot_kind", "basic"),
                "replacement_for": metadata.get("replacement_for"),
                "classification": "memory_invalid_operation_failure",
                "memory_valid": False,
                "lifecycle_status": "unknown",
                "diagnostic_classification": "diagnostic_unavailable",
                "failures": ["operation:unknown_condition"],
            })
            continue
        normalized, details = _attempt_evidence(attempt_root, base_attempt, condition, contract)
        decision = classify_attempt(normalized)
        row = {
            "attempt_id": attempt_id,
            "slot_id": metadata.get("slot_id"),
            "slot_kind": metadata.get("slot_kind", "basic"),
            "sequence": metadata.get("sequence"),
            "position": metadata.get("position"),
            "condition": metadata.get("condition"),
            "replacement_for": metadata.get("replacement_for"),
            "classification": decision["classification"],
            "memory_valid": decision["memory_valid"],
            "lifecycle_status": decision["lifecycle_status"],
            "diagnostic_classification": decision["diagnostic_classification"],
            "failures": decision["failures"],
            "normalized_evidence": normalized,
            **details,
        }
        attempts.append(row)

    population = evaluate_population(attempts, contract)
    memory_valid = [row for row in attempts if row["classification"] in MEMORY_VALID]
    kit_peaks = [int(row["formal_resource"]["kit_private_peak_bytes"]) for row in memory_valid]
    tree_peaks = [int(row["formal_resource"]["tree_private_peak_bytes"]) for row in memory_valid]
    max_kit = max(kit_peaks) if kit_peaks else None
    max_tree = max(tree_peaks) if tree_peaks else None
    legacy = int(contract["safety"]["legacy_kit_evaluation_threshold_bytes"])
    legacy_crossings = sum(value >= legacy for value in kit_peaks)
    legacy_margin = legacy - max_kit if max_kit is not None else None
    legacy_retire = bool(
        legacy_crossings >= int(contract["decision"]["legacy_retire_crossings"])
        or (legacy_margin is not None and legacy_margin < int(contract["decision"]["legacy_retire_margin_bytes"]))
    )
    memory_resource_qualified = bool(
        population["required_memory_population_complete"]
        and not population["population_stopping_failure"]
        and max_kit is not None
        and max_kit <= int(contract["safety"]["candidate_peak_maximum_bytes"])
        and int(contract["safety"]["kit_absolute_stop_bytes"]) - max_kit >= int(contract["safety"]["minimum_candidate_headroom_bytes"])
        and max_tree is not None
        and max_tree < int(contract["safety"]["unique_tree_absolute_stop_bytes"])
        and all(not row["snapshot_resource_trace"]["final_window"]["persistent_unexplained_accumulation"] for row in memory_valid)
    )
    timeout_rows = [row for row in attempts if row["classification"] == "memory_valid_lifecycle_timeout"]
    phase6fo_ready = bool(
        memory_resource_qualified
        and len(timeout_rows) <= int(contract["decision"]["maximum_timeouts_for_monitored_restart"])
        and all(value <= 1 for value in population["timeout_by_condition"].values())
        and not population["pending_replacement_origins"]
        and len(attempts) <= int(contract["population"]["maximum_total_launches"])
    )
    conditions = {}
    for condition_id in by_condition:
        rows = [row for row in memory_valid if row["condition"] == condition_id]
        peaks = [int(row["formal_resource"]["kit_private_peak_bytes"]) for row in rows]
        conditions[condition_id] = {
            "memory_valid_samples": len(rows),
            "normal_os_exit": sum(row["classification"] == "memory_valid_lifecycle_normal" for row in rows),
            "stage_close_timeout": sum(row["classification"] == "memory_valid_lifecycle_timeout" for row in rows),
            "kit_peak_bytes": peaks,
            "kit_peak_minimum_bytes": min(peaks) if peaks else None,
            "kit_peak_median_bytes": _median(peaks),
            "kit_peak_maximum_bytes": max(peaks) if peaks else None,
            "kit_peak_range_bytes": max(peaks) - min(peaks) if peaks else None,
            "tree_peak_bytes": [int(row["formal_resource"]["tree_private_peak_bytes"]) for row in rows],
        }
    diagnostic_counts = {}
    for row in attempts:
        key = row["diagnostic_classification"]
        diagnostic_counts[key] = diagnostic_counts.get(key, 0) + 1
    identity_totals = {}
    for row in attempts:
        for key, value in (row.get("identity_cleanup") or {}).get("counts", {}).items():
            if isinstance(value, int):
                identity_totals[key] = identity_totals.get(key, 0) + value
    return {
        "schema": "campfire.phase6fz.three-axis-memory-qualification-report.v1",
        "phase": "phase6fz",
        "contract_sha256": (root / "frozen_contract.sha256").read_text(encoding="utf-8").split()[0],
        "frozen_history": {
            "phase6ft_reclassified": False,
            "phase6fv_reclassified": False,
            "phase6fx_reclassified": False,
            "past_artifact_reused": False,
        },
        "phase6fo_started": False,
        "attempts": attempts,
        "population": population,
        "counts": {
            "memory_valid": len(memory_valid),
            "memory_invalid": len(attempts) - len(memory_valid),
            "normal_os_exit": sum(row["classification"] == "memory_valid_lifecycle_normal" for row in attempts),
            "stage_close_timeout": len(timeout_rows),
            "exact_cleanup_success": sum((row.get("normalized_evidence") or {}).get("cleanup", {}).get("phase6fu_complete") is True for row in attempts),
            "protected_pid_reuse": identity_totals.get("protected_pid_reuse_non_residual", 0),
            "attempt_owned_residual": identity_totals.get("final_attempt_owned_residual", 0),
            "unresolved_unknown": identity_totals.get("unresolved_unknown", 0),
        },
        "diagnostic_counts": diagnostic_counts,
        "replacement_map": population["replacement_map"],
        "conditions": conditions,
        "distribution": {
            "includes_lifecycle_timeout_samples": True,
            "kit_peak_bytes": kit_peaks,
            "kit_peak_minimum_bytes": min(kit_peaks) if kit_peaks else None,
            "kit_peak_median_bytes": _median(kit_peaks),
            "kit_peak_maximum_bytes": max_kit,
            "kit_peak_range_bytes": max(kit_peaks) - min(kit_peaks) if kit_peaks else None,
            "tree_peak_bytes": tree_peaks,
            "stage_close_seconds": [
                row["stage_close_seconds"] if row["classification"] == "memory_valid_lifecycle_normal"
                else {"right_censored_at_seconds": row["stage_close_timeout_seconds"]}
                for row in memory_valid
            ],
        },
        "legacy_14_gib": {
            "threshold_bytes": legacy,
            "memory_valid_crossings": legacy_crossings,
            "minimum_margin_bytes": legacy_margin,
            "retired_as_anomaly_ceiling": legacy_retire,
        },
        "candidate_16_gib": {
            "limit_bytes": int(contract["safety"]["kit_absolute_stop_bytes"]),
            "memory_valid_maximum_peak_bytes": max_kit,
            "headroom_bytes": int(contract["safety"]["kit_absolute_stop_bytes"]) - max_kit if max_kit is not None else None,
            "qualified": memory_resource_qualified,
        },
        "candidate_17_gib_tree": {
            "limit_bytes": int(contract["safety"]["unique_tree_absolute_stop_bytes"]),
            "memory_valid_maximum_peak_bytes": max_tree,
            "headroom_bytes": int(contract["safety"]["unique_tree_absolute_stop_bytes"]) - max_tree if max_tree is not None else None,
            "qualified": memory_resource_qualified,
        },
        "persistent_unexplained_accumulation_detected": any(
            row["snapshot_resource_trace"]["final_window"]["persistent_unexplained_accumulation"]
            for row in memory_valid
        ),
        "memory_ceiling_qualified": memory_resource_qualified,
        "lifecycle_issue_resolved": False,
        "phase6fo_monitored_restart_ready": phase6fo_ready,
        "identity_policy_totals": identity_totals,
        "production_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root.resolve(), args.contract.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
