"""Analyze the Phase 6FV post-6FU memory-ceiling qualification."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import analyze_phase6ft_memory_ceiling_qualification as legacy


IDENTITY_KEYS = {
    "pid",
    "create_time_utc_epoch",
    "path",
    "parent_pid",
    "observed_at_utc_epoch",
    "role",
    "root_attempt_id",
}


def _identity_cleanup_gate(attempt_root: Path, attempt: dict) -> tuple[list[str], dict]:
    cleanup = attempt.get("cleanup") or {}
    before = cleanup.get("before") or []
    identities = [row.get("identity") or {} for row in before if isinstance(row, dict)]
    marker_rows = legacy._jsonl(attempt_root / "runner-logs" / "cleanup_markers.jsonl")
    marker_names = [str(row.get("marker")) for row in marker_rows]
    sources = set(cleanup.get("absence_confirmation_sources") or [])
    suppression = cleanup.get("cleanup_suppression") or {}
    failures: list[str] = []
    if cleanup.get("schema") != "campfire.phase6fu.exact-cleanup-summary.v1":
        failures.append("phase6fu_cleanup_schema_missing")
    if not identities or any(not IDENTITY_KEYS.issubset(identity) for identity in identities):
        failures.append("exact_identity_fields_incomplete")
    if cleanup.get("all_matching_absent") is not True or cleanup.get("all_observed_absent") is not True:
        failures.append("dual_source_absence_not_confirmed")
    if sources != {"psutil", "win32"}:
        failures.append("absence_confirmation_sources_incomplete")
    if cleanup.get("final_unknown"):
        failures.append("identity_unknown_unresolved")
    if cleanup.get("protected_identity_mismatch"):
        failures.append("identity_mismatch_observed")
    if suppression.get("released") is not True or suppression.get("timed_out") is True:
        failures.append("cleanup_suppression_not_released")
    if "cleanup_suppression_released" not in marker_names or "exact_cleanup_complete" not in marker_names:
        failures.append("cleanup_marker_integrity")
    evidence = {
        "schema": cleanup.get("schema"),
        "observed_identity_count": cleanup.get("observed_identity_count"),
        "identity_fields_complete": bool(identities) and all(IDENTITY_KEYS.issubset(identity) for identity in identities),
        "absence_confirmation_sources": sorted(sources),
        "all_matching_absent": cleanup.get("all_matching_absent"),
        "all_observed_absent": cleanup.get("all_observed_absent"),
        "final_unknown_count": len(cleanup.get("final_unknown") or []),
        "protected_identity_mismatch_count": len(cleanup.get("protected_identity_mismatch") or []),
        "cleanup_suppression": suppression,
        "cleanup_markers": marker_names,
    }
    return failures, evidence


def _condition_groups(contract: dict, passed: list[dict]) -> dict:
    groups = {}
    for condition in contract["conditions"]:
        rows = [row for row in passed if row["condition"] == condition["id"]]
        peaks = [row["resource_trace"]["kit_private_peak_bytes"] for row in rows]
        tree = [row["resource_trace"]["tree_private_peak_bytes"] for row in rows]
        groups[condition["id"]] = {
            "runs": len(rows),
            "kit_peak_bytes": peaks,
            "kit_peak_minimum_bytes": min(peaks) if peaks else None,
            "kit_peak_median_bytes": legacy._median(peaks),
            "kit_peak_maximum_bytes": max(peaks) if peaks else None,
            "kit_peak_range_bytes": (max(peaks) - min(peaks)) if peaks else None,
            "tree_peak_bytes": tree,
            "tree_peak_median_bytes": legacy._median(tree),
            "stage_close_seconds": [row["stage_close_seconds"] for row in rows],
            "active_blocks_terminal": [
                int(row["active_blocks_at_frames"].get(str(condition["terminal_frame"])) or 0)
                for row in rows
            ],
        }
    return groups


def build(root: Path, contract_path: Path) -> dict:
    contract = legacy._json(contract_path)
    if not contract or contract.get("phase") != "phase6fv":
        raise ValueError("invalid Phase 6FV contract")

    compatibility = copy.deepcopy(contract)
    compatibility["phase"] = "phase6ft"
    compatibility["safety"]["kit_provisional_hard_limit_bytes"] = contract["safety"]["kit_absolute_stop_bytes"]
    compatibility["safety"]["unique_tree_provisional_hard_limit_bytes"] = contract["safety"]["unique_tree_absolute_stop_bytes"]
    with tempfile.TemporaryDirectory(prefix="phase6fv-analyzer-") as directory:
        temporary_contract = Path(directory) / "compatibility.json"
        temporary_contract.write_text(json.dumps(compatibility), encoding="utf-8")
        report = legacy.build(root, temporary_contract)

    for attempt in report["attempts"]:
        attempt_root = root / "attempts" / attempt["attempt_id"]
        identity_failures, evidence = _identity_cleanup_gate(attempt_root, attempt)
        attempt["identity_cleanup"] = evidence
        if identity_failures:
            attempt["failures"] = list(dict.fromkeys([*attempt["failures"], *identity_failures]))
            attempt["classification"] = "nonreplaceable_failure"

    planned = int(contract["population"]["required_representative_processes"])
    passed = [row for row in report["attempts"] if row["classification"] == "representative_pass"]
    failed = [row for row in report["attempts"] if row["classification"] == "nonreplaceable_failure"]
    startup = [row for row in report["attempts"] if row["classification"] == "startup_prerequisite_failure"]
    traces = [row["resource_trace"] for row in passed]
    kit_peaks = [row["kit_private_peak_bytes"] for row in traces]
    tree_peaks = [row["tree_private_peak_bytes"] for row in traces]
    runner_peaks = [int(row["runner_private_peak_bytes"] or 0) for row in traces]
    diagnostic_peaks = [int(row["diagnostic_private_peak_bytes"] or 0) for row in traces]
    physical_minima = [row["available_physical_minimum_bytes"] for row in traces]
    commit_minima = [row["commit_headroom_minimum_bytes"] for row in traces]
    max_kit = max(kit_peaks) if kit_peaks else None
    max_tree = max(tree_peaks) if tree_peaks else None
    max_runner = max(runner_peaks) if runner_peaks else None
    max_diagnostic = max(diagnostic_peaks) if diagnostic_peaks else None
    min_physical = min(physical_minima) if physical_minima else None
    min_commit = min(commit_minima) if commit_minima else None
    complete = len(passed) == planned and not failed
    no_persistent = all(not row["final_window"]["persistent_unexplained_accumulation"] for row in traces)
    resource_gate = bool(
        max_kit is not None
        and max_kit <= int(contract["safety"]["candidate_peak_maximum_bytes"])
        and max_tree is not None
        and max_tree < int(contract["safety"]["unique_tree_absolute_stop_bytes"])
        and max_runner <= int(contract["safety"]["runner_private_limit_bytes"])
        and max_diagnostic <= int(contract["safety"]["diagnostic_private_limit_bytes"])
        and min_physical >= int(contract["safety"]["physical_memory_floor_bytes"])
        and min_commit >= int(contract["safety"]["commit_headroom_floor_bytes"])
    )
    candidate = bool(complete and resource_gate and no_persistent)
    legacy_threshold = int(contract["safety"]["legacy_kit_evaluation_threshold_bytes"])
    legacy_crossings = sum(peak >= legacy_threshold for peak in kit_peaks)
    legacy_margin = legacy_threshold - max_kit if max_kit is not None else None
    legacy_too_strict = bool(
        legacy_crossings >= 2
        or (legacy_margin is not None and legacy_margin < int(contract["decision"]["legacy_small_margin_bytes"]))
    )
    closes = [row["stage_close_seconds"] for row in passed]
    terminal_blocks = [
        int(row["active_blocks_at_frames"].get(str(row["condition_contract"]["terminal_frame"])) or 0)
        for row in passed
    ]

    report.update(
        {
            "schema": "campfire.phase6fv.memory-ceiling-qualification-report.v1",
            "phase": "phase6fv",
            "phase6ft_reclassified": False,
            "phase6ft_artifact_reused": False,
            "phase6fu_guard_required": True,
            "phase6fo_restarted": False,
            "production_changed": False,
            "population": {
                "planned": planned,
                "launched": len(report["attempts"]),
                "representative_pass": len(passed),
                "startup_prerequisite_failure": len(startup),
                "nonreplaceable_failure": len(failed),
            },
            "qualification_complete": complete,
            "candidate_16_gib_qualified": candidate,
            "candidate_17_gib_tree_qualified": candidate,
            "phase6fo_restart_ready": candidate,
            "safe_stop": failed[0] if failed else None,
            "conditions": _condition_groups(contract, passed),
            "legacy_14_gib": {
                "threshold_bytes": legacy_threshold,
                "normal_crossings": legacy_crossings,
                "minimum_margin_bytes": legacy_margin,
                "too_strict_as_anomaly_ceiling": legacy_too_strict,
            },
            "candidate_16_gib": {
                "limit_bytes": int(contract["safety"]["kit_absolute_stop_bytes"]),
                "required_fixed_headroom_bytes": int(contract["safety"]["minimum_candidate_headroom_bytes"]),
                "normal_maximum_peak_bytes": max_kit,
                "observed_fixed_headroom_bytes": int(contract["safety"]["kit_absolute_stop_bytes"]) - max_kit if max_kit is not None else None,
            },
            "candidate_17_gib_tree": {
                "limit_bytes": int(contract["safety"]["unique_tree_absolute_stop_bytes"]),
                "normal_maximum_peak_bytes": max_tree,
                "observed_fixed_headroom_bytes": int(contract["safety"]["unique_tree_absolute_stop_bytes"]) - max_tree if max_tree is not None else None,
            },
            "separated_resource_extrema": {
                "runner_private_peak_bytes": max_runner,
                "diagnostic_private_peak_bytes": max_diagnostic,
                "available_physical_minimum_bytes": min_physical,
                "commit_headroom_minimum_bytes": min_commit,
            },
            "distribution": {
                "kit_peak_bytes": kit_peaks,
                "kit_run_range_bytes": (max(kit_peaks) - min(kit_peaks)) if kit_peaks else None,
                "tree_peak_bytes": tree_peaks,
                "stage_close_seconds": closes,
                "stage_close_vs_kit_peak_pearson": legacy._pearson(kit_peaks, closes) if len(kit_peaks) == len(closes) else None,
                "terminal_active_blocks": terminal_blocks,
                "terminal_active_blocks_vs_kit_peak_pearson": legacy._pearson(terminal_blocks, kit_peaks) if len(terminal_blocks) == len(kit_peaks) else None,
            },
            "persistent_unexplained_accumulation_detected": not no_persistent,
            "cdb_invocations": sum(bool((row.get("diagnostic") or {}).get("started")) for row in report["attempts"]),
        }
    )
    return report


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
