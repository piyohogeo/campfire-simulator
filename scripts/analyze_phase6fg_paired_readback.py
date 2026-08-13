"""Aggregate Phase 6FG balanced A/B/C single-operation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from pathlib import Path

try:
    from .analyze_phase6ff_memory_boundedness import case_for as legacy_case_for
    from .analyze_phase6ew_r0_lifecycle import _json
    from .phase6fg_paired_readback_policy import evaluate_hard_gate
except ImportError:
    from analyze_phase6ff_memory_boundedness import case_for as legacy_case_for
    from analyze_phase6ew_r0_lifecycle import _json
    from phase6fg_paired_readback_policy import evaluate_hard_gate


LABELS = {
    "A_control": ("R0_none", "control"),
    "B_readback": ("C0_acquire_discard", "c0"),
    "C_fuel_alias": ("C1_fuel_alias", "c1"),
}


def _adapter(contract: dict) -> dict:
    result = json.loads(json.dumps(contract))
    result["gates"] = {
        "required_c1_numpy_asarray_calls": 1,
        "maximum_fuel_logical_bytes": contract["operation_gates"]["maximum_fuel_logical_bytes"],
    }
    result["control_comparison"] = {"maximum_absolute_c1_asarray_delta_bytes": 2**63 - 1}
    return result


def _guard_evidence(group_root: Path, prefix: str, case_dir: Path) -> tuple[dict, dict]:
    guard = _json(group_root / "runner-logs" / f"{prefix}.guard.json") or {}
    runner = _json(case_dir / "runner_evidence.json") or {}
    monitor = runner.get("shutdown_monitor") or {}
    peaks = guard.get("peaks") or {}
    minima = guard.get("machine_minima") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    exception_present = monitor.get("windows_exception_present") is True
    evidence = {
        "guard_status": guard.get("status"),
        "guard_exit_code": guard.get("exit_code"),
        "process_absent": guard.get("process_absent"),
        "cleanup_residual_count": len(cleanup.get("remaining") or []),
        "runner_peak_bytes": peaks.get("runner"),
        "diagnostic_peak_bytes": peaks.get("diagnostic"),
        "kit_peak_bytes": peaks.get("kit"),
        "tree_peak_bytes": peaks.get("tree"),
        "minimum_available_physical_bytes": minima.get("available_physical_bytes"),
        "minimum_commit_headroom_bytes": minima.get("estimated_commit_headroom_bytes"),
        "fatal_count": len(runner.get("fatal_lines") or []),
        "access_violation_count": int(exception_present),
        "dump_count": len(runner.get("dump_inventory") or []),
        "upload_attempt_count": len(runner.get("automatic_upload_attempt_lines") or []),
        "lifecycle_complete": (runner.get("outcome") or {}).get("shutdown_complete_reached") is True,
        "normal_os_exit": (runner.get("outcome") or {}).get("os_process_normal_exit") is True,
    }
    return evidence, guard


def _versioned_context(case_dir: Path, guard: dict, case: dict) -> dict:
    log = case_dir / "kit.log"
    patterns = {
        "shader_compile": re.compile(r"(?i)shader.{0,40}compil"),
        "shader_cache": re.compile(r"(?i)shadercache|shader cache"),
        "flow_version": re.compile(r"(?i)omni\.flow[^\s]*-110\.0\.0|Flow 110\.0\.0"),
        "kit_version": re.compile(r"(?i)Kit[/\\ ]110\.2|110\.2\.0"),
        "driver": re.compile(r"(?i)driver.{0,30}(?:version|[0-9]{3}\.[0-9]{2})"),
    }
    counts = {key: 0 for key in patterns}
    if log.exists():
        with log.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                for key, pattern in patterns.items():
                    counts[key] += int(bool(pattern.search(line)))
    active = (case.get("memory_boundedness") or {}).get("metrics", {}).get("active_blocks", {})
    gpu = (guard.get("cpu_telemetry") or {}).get("gpu_sampling") or {}
    return {
        "hardware_gpu_telemetry_scope": gpu.get("scope"),
        "kit_log_sha256": hashlib.sha256(log.read_bytes()).hexdigest().upper() if log.exists() else None,
        "kit_log_bytes": log.stat().st_size if log.exists() else None,
        "bounded_log_token_counts": counts,
        "cache_state_classification": "compile_activity_observed" if counts["shader_compile"] else "no_compile_activity_observed_in_log",
        "active_block_range": [active.get("minimum"), active.get("maximum")],
        "fixture": "production_four/phase6er_corrected/allow_self_center/-0.0125m",
    }


def _case(group_root: Path, condition: str, contract: dict) -> dict:
    label, mode = LABELS[condition]
    case_dir = group_root / label
    case = legacy_case_for(group_root, label, label, mode, _adapter(contract))
    old_failures = set(case.pop("condition_gate_failures", []))
    old_failures.discard("memory_boundedness")
    old_failures.discard("asarray_adjacent_delta")
    waveform = case.pop("memory_boundedness")
    warning_checks = sorted(name for name, passed in (waveform.get("checks") or {}).items() if not passed)
    evidence, guard = _guard_evidence(group_root, label, case_dir)
    hard = evaluate_hard_gate(evidence, contract["safety"])
    failures = sorted(old_failures | set(hard["failures"]))
    case.update({
        "condition": condition,
        "absolute_hard_gate": hard,
        "absolute_evidence": evidence,
        "waveform_telemetry": {
            **waveform,
            "formal_gate": False,
            "warning_checks": warning_checks,
            "warning_count": len(warning_checks),
        },
        "versioned_telemetry_context": _versioned_context(case_dir, guard, {**case, "memory_boundedness": waveform}),
        "condition_gate_failures": failures,
        "condition_gate_pass": not failures,
    })
    return case


def _median(values: list[float | int | None]) -> float | None:
    finite = [float(value) for value in values if value is not None]
    return statistics.median(finite) if finite else None


def _group(cases: list[dict]) -> dict:
    if len(cases) != 3:
        return {"complete": False, "gate_pass": False, "failures": ["population_incomplete"]}
    failures = [] if all(case["condition_gate_pass"] for case in cases) else ["condition_hard_or_operation_gate"]
    return {
        "complete": True,
        "gate_pass": not failures,
        "failures": failures,
        "kit_peak_bytes": [case["absolute_evidence"]["kit_peak_bytes"] for case in cases],
        "tree_peak_bytes": [case["absolute_evidence"]["tree_peak_bytes"] for case in cases],
        "stage_close_seconds": [case.get("stage_close_seconds") for case in cases],
        "waveform_warning_counts": [case["waveform_telemetry"]["warning_count"] for case in cases],
    }


def _comparison(cases: dict, sequence: int) -> dict | None:
    keys = {name: f"sequence{sequence:02d}_{name}" for name in LABELS}
    if not all(key in cases for key in keys.values()):
        return None
    a, b, c = (cases[keys[name]] for name in LABELS)
    active = [
        case["waveform_telemetry"]["metrics"]["active_blocks"]["mean"]
        for case in (a, b, c)
    ]
    ratio = max(active) / max(1.0, min(active))
    return {
        "active_block_means": {name: value for name, value in zip(LABELS, active)},
        "active_scale_ratio": ratio,
        "active_scale_warning": ratio > 1.25,
        "process_peak_differences_are_primary_operation_evidence": False,
        "b_readback_immediate_bytes": b.get("memory_deltas_bytes", {}).get("readback_immediate"),
        "b_readback_immediate_gpu_mib": b.get("gpu_deltas_mib", {}).get("readback_immediate"),
        "b_settled_residual_bytes": b.get("memory_deltas_bytes", {}).get("observation_end_residual"),
        "c_readback_immediate_bytes": c.get("memory_deltas_bytes", {}).get("readback_immediate"),
        "c_numpy_asarray_immediate_bytes": c.get("memory_deltas_bytes", {}).get("fuel_conversion_immediate"),
        "c_numpy_asarray_immediate_gpu_mib": c.get("gpu_deltas_mib", {}).get("fuel_conversion_immediate"),
        "c_source_release_bytes": c.get("memory_deltas_bytes", {}).get("original_alias_release"),
        "c_converted_release_bytes": c.get("memory_deltas_bytes", {}).get("converted_buffer_release"),
        "c_settled_residual_bytes": c.get("memory_deltas_bytes", {}).get("observation_end_residual"),
        "c_allocation_classification": ((c.get("boundary") or {}).get("observable_copy_contract") or {}).get("allocation_classification"),
        "c_weak_reference_residual": (c.get("boundary") or {}).get("weak_reference_alive_after_scope_count"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    cases: dict[str, dict] = {}
    for sequence, order in enumerate(contract["balanced_order"], 1):
        group_root = args.root / f"sequence{sequence:02d}"
        for condition in order:
            label = LABELS[condition][0]
            if (group_root / label).exists():
                cases[f"sequence{sequence:02d}_{condition}"] = _case(group_root, condition, contract)
    by_condition = {
        condition: [case for key, case in sorted(cases.items()) if key.endswith(condition)]
        for condition in LABELS
    }
    groups = {condition: _group(items) for condition, items in by_condition.items()}
    comparisons = [_comparison(cases, sequence) for sequence in range(1, 4)]
    comparisons = [item for item in comparisons if item is not None]
    qualified = len(cases) == 9 and all(group["gate_pass"] for group in groups.values())
    report = {
        "schema": "campfire.phase6fg.paired-single-readback-report.v1",
        "phase": "phase6fg",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": ["phase6fd", "phase6fe", "phase6ff"],
        "completed_conditions": len(cases),
        "cases": cases,
        "groups": groups,
        "paired_comparisons": comparisons,
        "waveform_metrics_formal_gate": False,
        "qualified": qualified,
        "one_readback_and_fuel_alias_qualified": qualified,
        "repeated_readback_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
