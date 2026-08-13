"""Publish bounded Phase 6FG safe-stop evidence without raw logs or fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = load(args.root / "paired_readback_report.json")
    state = load(args.root / "incremental_state.json")
    cases = []
    for name, case in report["cases"].items():
        wave = case["waveform_telemetry"]
        metrics = wave["metrics"]
        boundary = case.get("boundary") or {}
        cases.append({
            "name": name,
            "formal_gate_pass": case["condition_gate_pass"],
            "formal_failures": case["condition_gate_failures"],
            "kit_peak_bytes": case["absolute_evidence"]["kit_peak_bytes"],
            "kit_ceiling_margin_bytes": 15032385536 - int(case["absolute_evidence"]["kit_peak_bytes"]),
            "tree_peak_bytes": case["absolute_evidence"]["tree_peak_bytes"],
            "stage_close_seconds": case.get("stage_close_seconds"),
            "active_block_mean": metrics["active_blocks"]["mean"],
            "waveform_warning_only": True,
            "waveform_warning_checks": wave["warning_checks"],
            "whole_window_slope_bytes_per_second": metrics["overall_private_slope_bytes_per_second"],
            "terminal_residual_bytes": metrics["terminal_residual_bytes"],
            "readback_immediate_bytes": (case.get("memory_deltas_bytes") or {}).get("readback_immediate"),
            "numpy_asarray_immediate_bytes": (case.get("memory_deltas_bytes") or {}).get("fuel_conversion_immediate"),
            "next_frame_residual_bytes": (case.get("memory_deltas_bytes") or {}).get("next_frame_residual"),
            "settling_end_residual_bytes": (case.get("memory_deltas_bytes") or {}).get("observation_end_residual"),
            "source_alias_release_bytes": (case.get("memory_deltas_bytes") or {}).get("original_alias_release"),
            "converted_alias_release_bytes": (case.get("memory_deltas_bytes") or {}).get("converted_buffer_release"),
            "fuel_logical_bytes": (boundary.get("fuel_array") or {}).get("nbytes"),
            "allocation_classification": (boundary.get("observable_copy_contract") or {}).get("allocation_classification"),
            "weak_reference_residual": boundary.get("weak_reference_alive_after_scope_count"),
            "cache_state": case["versioned_telemetry_context"]["cache_state_classification"],
            "kit_log_sha256": case["versioned_telemetry_context"]["kit_log_sha256"],
        })
    failed_dir = args.root / "sequence02" / "R0_none"
    evidence = load(failed_dir / "runner_evidence.json")
    guard = load(args.root / "sequence02" / "runner-logs" / "R0_none.guard.json")
    diagnostic = (evidence.get("shutdown_monitor") or {}).get("diagnostic") or {}
    debugger = diagnostic.get("debugger") or {}
    fingerprint = diagnostic.get("stack_fingerprint") or {}
    cdb_log = failed_dir / "sensitive-shutdown-diagnostics" / "cdb-thread-stacks.log"
    result = {
        "schema": "campfire.phase6fg.paired-readback-safe-stop-summary.v1",
        "phase": "phase6fg",
        "contract_sha256": report["contract_sha256"],
        "history_frozen": report["history_frozen"],
        "decision_model": {
            "waveform_metrics_formal_gate": False,
            "absolute_and_lifecycle_hard_gate": True,
            "adjacent_operation_markers_primary": True,
        },
        "status": state["status"],
        "completed_passing_conditions": state["completed_conditions"],
        "analyzed_condition_count_including_failed_active": report["completed_conditions"],
        "active_failed_condition": state["active_condition"],
        "stop_reason": state["stop_reason"],
        "cases": cases,
        "absolute_population_peaks": {
            "kit_bytes": max(item["kit_peak_bytes"] for item in cases),
            "tree_bytes": max(item["tree_peak_bytes"] for item in cases),
            "minimum_kit_ceiling_margin_bytes": min(item["kit_ceiling_margin_bytes"] for item in cases),
            "minimum_available_physical_bytes": min(case["absolute_evidence"]["minimum_available_physical_bytes"] for case in report["cases"].values()),
            "minimum_commit_headroom_bytes": min(case["absolute_evidence"]["minimum_commit_headroom_bytes"] for case in report["cases"].values()),
        },
        "failed_lifecycle": {
            "last_marker": (evidence.get("shutdown_monitor") or {}).get("last_lifecycle_marker"),
            "classification": (evidence.get("shutdown_monitor") or {}).get("lifecycle_candidate"),
            "stage_close_timeout_seconds": 180,
            "known_ngx_signature_matched": (evidence.get("shutdown_monitor") or {}).get("known_signature_matched"),
            "cdb_attach_observed": debugger.get("attach_observed"),
            "cdb_all_thread_stack_started": debugger.get("all_thread_stack_observed"),
            "cdb_modules_observed": debugger.get("loaded_modules_observed"),
            "cdb_timed_out": debugger.get("timed_out"),
            "cdb_detach_observed": debugger.get("detach_observed"),
            "cdb_process_absent": debugger.get("process_absent"),
            "fingerprint_name": fingerprint.get("name"),
            "fingerprint_matched": fingerprint.get("matched"),
            "stack_boundary": "omni_usd UsdManager::destroyContext / extension-plugin shutdown; owner unknown",
            "cdb_log_sha256": hashlib.sha256(cdb_log.read_bytes()).hexdigest().upper() if cdb_log.exists() else None,
            "full_dump_created": debugger.get("full_dump_created"),
            "cleanup_killed_pids": guard["observed_process_cleanup"]["killed_pids"],
            "cleanup_remaining": guard["observed_process_cleanup"]["remaining"],
            "cleanup_all_absent": guard["observed_process_cleanup"]["all_observed_absent"],
        },
        "qualification": {
            "paired_population_complete": False,
            "one_readback_qualified": False,
            "one_fuel_alias_qualified": False,
            "repeated_readback_qualified": False,
            "next_phase_allowed": False,
        },
        "production_changed": False,
        "raw_artifact_committed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
