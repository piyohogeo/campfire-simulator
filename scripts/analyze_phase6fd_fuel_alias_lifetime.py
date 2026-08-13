"""Aggregate the frozen Phase 6FD one-readback fuel-alias boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .analyze_phase6ez_fuel_conversion import _case as base_case, _condition_gate as base_gate, _ordered
    from .analyze_phase6ew_r0_lifecycle import _json
    from .phase6fc_startup_contract import classify_startup
    from .summarize_phase6fc_startup_reproduction import normalized_stage_sha
except ImportError:
    from analyze_phase6ez_fuel_conversion import _case as base_case, _condition_gate as base_gate, _ordered
    from analyze_phase6ew_r0_lifecycle import _json
    from phase6fc_startup_contract import classify_startup
    from summarize_phase6fc_startup_reproduction import normalized_stage_sha


def _startup_thresholds(contract: dict) -> dict:
    startup = contract["startup"]
    sums = startup["expected_source_sums"]
    tolerance = float(startup["source_sum_absolute_tolerance"])
    return {
        "classification_frame": startup["classification_frame"],
        "final_frame": startup["final_frame"],
        "representative_active_blocks": startup["representative_active_blocks"],
        "small_field_minimum_blocks": startup["small_field_minimum_blocks"],
        "small_field_maximum_blocks": startup["small_field_maximum_blocks"],
        "expected_point_revision": startup["expected_point_revision"],
        "expected_total_point_count": startup["expected_total_point_count"],
        "expected_active_point_count": startup["expected_active_point_count"],
        "minimum_fuel_sum": float(sums["fuel"]) - tolerance,
        "minimum_temperature_sum": float(sums["temperature"]) - tolerance,
        "minimum_smoke_sum": float(sums["smoke"]) - tolerance,
    }


def _startup(case_dir: Path, raw: dict, contract: dict) -> dict:
    source = raw.get("startup_live_point_emitter_contract") or {}
    probe = raw.get("startup_probe") or {}
    history = probe.get("history") or []
    classification = classify_startup(history, source, _startup_thresholds(contract))
    runtime_gate = raw.get("startup_liveness_gate") or {}
    stage_path = case_dir / "raw.scene.usda"
    expected_sums = contract["startup"]["expected_source_sums"]
    actual_sums = source.get("source_sums") or {}
    tolerance = float(contract["startup"]["source_sum_absolute_tolerance"])
    exact_source = all(
        abs(float(actual_sums.get(key, float("inf"))) - float(expected_sums[key])) <= tolerance
        for key in ("fuel", "temperature", "smoke")
    )
    identities = runtime_gate.get("identity_and_exact_source") or {}
    return {
        **classification,
        "runtime_gate": runtime_gate,
        "readback_permitted": runtime_gate.get("readback_permitted") is True,
        "exact_source_sums": exact_source,
        "identity_and_exact_source_pass": identities.get("pass") is True,
        "payload_sha256": raw.get("point_payload", {}).get("payload_sha256"),
        "stage_sha256": raw.get("stage_sha256"),
        "normalized_stage_sha256": normalized_stage_sha(stage_path) if stage_path.exists() else None,
        "frame_values": {
            str(frame): next((int(row["active_blocks"]) for row in history if int(row["frame"]) == frame), None)
            for frame in (1, 30, 60, 120)
        },
    }


def _runner_safety(case_dir: Path) -> dict:
    evidence = _json(case_dir / "runner_evidence.json") or {}
    outcome = evidence.get("outcome") or {}
    return {
        "fatal_count": len(evidence.get("fatal_lines") or []),
        "dump_count": len(evidence.get("dump_inventory") or []),
        "upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines") or []),
        "production_changed": evidence.get("production_changed"),
        "production_app_sha256_before": evidence.get("production_app_sha256_before"),
        "production_app_sha256_after": evidence.get("production_app_sha256_after"),
        "functional_status": outcome.get("functional_status"),
        "lifecycle_status": outcome.get("lifecycle_status"),
        "normal_exit_sample_accepted": outcome.get("normal_exit_sample_accepted"),
    }


def _case(root: Path, label: str, contract: dict) -> dict:
    case = base_case(root, label, label, contract)
    raw = _json(root / label / "raw.json") or {}
    case["startup"] = _startup(root / label, raw, contract)
    case["runner_safety"] = _runner_safety(root / label)
    legacy_condition = "C1_fuel_convert" if label == "C1_fuel_alias" else label
    passed, failures = base_gate(case, contract, legacy_condition)
    startup = case["startup"]
    safety = case["runner_safety"]
    if startup.get("classification") != "representative_ingestion":
        failures.append("startup_not_representative")
    if not startup.get("readback_permitted") or not startup.get("identity_and_exact_source_pass"):
        failures.append("startup_runtime_gate")
    if not startup.get("exact_source_sums"):
        failures.append("startup_source_sums")
    if startup.get("payload_sha256") != contract["expected_stage"]["payload_sha256"]:
        failures.append("payload_sha256")
    if startup.get("normalized_stage_sha256") != contract["expected_stage"]["normalized_stage_sha256"]:
        failures.append("normalized_stage_sha256")
    if not _ordered(case["boundary_marker_order"], ["startup_liveness_confirmed", "readback_call_before"]):
        failures.append("readback_before_startup_gate")
    boundary = case.get("boundary") or {}
    if int(boundary.get("weak_reference_alive_after_scope_count", -1)) != 0:
        failures.append("channel_weak_reference_residual")
    if any(int(safety.get(key, -1)) != 0 for key in ("fatal_count", "dump_count", "upload_attempt_count")):
        failures.append("fatal_dump_or_upload")
    if safety.get("production_changed") is not False:
        failures.append("production_hash")
    if safety.get("functional_status") != "pass" or safety.get("lifecycle_status") != "normal_exit":
        failures.append("shutdown_classification")
    case["condition_gate_failures"] = sorted(set(failures))
    case["condition_gate_pass"] = bool(passed and not case["condition_gate_failures"])
    return case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    for label in ("C0_acquire_discard", "C1_fuel_alias"):
        if (args.root / label).exists():
            cases[label] = _case(args.root, label, contract)
    c0 = cases.get("C0_acquire_discard")
    c1 = cases.get("C1_fuel_alias")
    comparison = None
    if c0 and c1:
        fuel = (c1.get("boundary") or {}).get("fuel_array") or {}
        conversion_delta = c1["memory_deltas_bytes"].get("fuel_conversion_immediate")
        logical = fuel.get("nbytes")
        active0 = c0["dynamic_stationarity"]["metrics"]["active_blocks"]["mean"]
        active1 = c1["dynamic_stationarity"]["metrics"]["active_blocks"]["mean"]
        active_scale_ratio = None if not active0 else active1 / active0
        comparison = {
            "allocation_classification": ((c1.get("boundary") or {}).get("observable_copy_contract") or {}).get("allocation_classification"),
            "new_data_buffer_allocated": ((c1.get("boundary") or {}).get("observable_copy_contract") or {}).get("new_data_buffer_allocated"),
            "fuel_logical_bytes": logical,
            "numpy_asarray_cpu_increment_bytes": conversion_delta,
            "numpy_asarray_cpu_increment_to_logical_ratio": None if not logical or conversion_delta is None else conversion_delta / logical,
            "numpy_asarray_gpu_increment_mib": c1["gpu_deltas_mib"].get("fuel_conversion_immediate"),
            "source_alias_release_delta_bytes": c1["memory_deltas_bytes"].get("original_alias_release"),
            "converted_alias_release_delta_bytes": c1["memory_deltas_bytes"].get("converted_buffer_release"),
            "next_frame_residual_bytes": c1["memory_deltas_bytes"].get("next_frame_residual"),
            "observation_end_residual_bytes": c1["memory_deltas_bytes"].get("observation_end_residual"),
            "stage_close_before_residual_bytes": c1["memory_deltas_bytes"].get("stage_close_before_residual"),
            "active_block_mean_c0": active0,
            "active_block_mean_c1": active1,
            "active_block_scale_ratio": active_scale_ratio,
            "process_peak_difference_is_conversion_evidence": bool(active_scale_ratio is not None and 0.9 <= active_scale_ratio <= 1.1),
            "c1_minus_c0_peak_private_bytes": c1["kit_peak_private_bytes"] - c0["kit_peak_private_bytes"],
            "c1_minus_c0_terminal_private_bytes": c1["terminal_kit_private_bytes"] - c0["terminal_kit_private_bytes"],
        }
    qualified = bool(c0 and c1 and c0["condition_gate_pass"] and c1["condition_gate_pass"])
    report = {
        "schema": "campfire.phase6fd.single-fuel-alias-lifetime-report.v1",
        "phase": "phase6fd",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": ["phase6ey", "phase6ez", "phase6fa", "phase6fb", "phase6fc"],
        "cases": cases,
        "c0_gate_pass": bool(c0 and c0["condition_gate_pass"]),
        "c1_started": c1 is not None,
        "c1_gate_pass": bool(c1 and c1["condition_gate_pass"]),
        "comparison": comparison,
        "qualified_boundary": qualified,
        "qualification_scope": "one representative-startup public readback and one fuel np.asarray alias lifetime" if qualified else None,
        "repeated_readback_qualified": False,
        "startup_issue_disposition": "low-frequency monitoring; no automatic recovery",
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
