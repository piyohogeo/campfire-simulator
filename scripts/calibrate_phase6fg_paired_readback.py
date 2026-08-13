"""Read-only historical audit and synthetic calibration for Phase 6FG."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

try:
    from .phase6fg_paired_readback_policy import evaluate_hard_gate, evaluate_repetition_candidate
except ImportError:
    from phase6fg_paired_readback_policy import evaluate_hard_gate, evaluate_repetition_candidate


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_evidence(contract: dict) -> dict:
    safety = contract["safety"]
    return {
        "guard_status": "ok", "guard_exit_code": 0, "process_absent": True,
        "cleanup_residual_count": 0, "runner_peak_bytes": 128 * 2**20,
        "diagnostic_peak_bytes": 64 * 2**20, "kit_peak_bytes": 12 * 2**30,
        "tree_peak_bytes": 14 * 2**30, "minimum_available_physical_bytes": 32 * 2**30,
        "minimum_commit_headroom_bytes": 24 * 2**30, "fatal_count": 0,
        "access_violation_count": 0, "dump_count": 0, "upload_attempt_count": 0,
        "lifecycle_complete": True, "normal_os_exit": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Phase 6FG calibration refuses output reuse: {args.output}")
    contract = _json(args.contract)
    base = _base_evidence(contract)
    transient = evaluate_hard_gate(base, contract["safety"])
    ceiling_evidence = deepcopy(base)
    ceiling_evidence["kit_peak_bytes"] = int(contract["safety"]["kit_private_limit_bytes"]) + 1
    ceiling = evaluate_hard_gate(ceiling_evidence, contract["safety"])
    lifecycle_evidence = deepcopy(base)
    lifecycle_evidence["lifecycle_complete"] = False
    lifecycle = evaluate_hard_gate(lifecycle_evidence, contract["safety"])
    plateau = evaluate_repetition_candidate(
        [10 * 2**30, 10 * 2**30 + 128 * 2**20, 10 * 2**30 + 132 * 2**20,
         10 * 2**30 + 129 * 2**20, 10 * 2**30 + 134 * 2**20, 10 * 2**30 + 131 * 2**20], contract
    )
    staircase = evaluate_repetition_candidate(
        [10 * 2**30 + index * 64 * 2**20 for index in range(6)], contract
    )
    historical = {}
    paths = {
        "phase6fd": args.repo / "artifacts/phase6fd-fuel-alias-lifetime-1/fuel_alias_lifetime_report.json",
        "phase6fe": args.repo / "artifacts/phase6fe-lagged-memory-response-2/lagged_memory_response_report.json",
        "phase6ff": args.repo / "artifacts/phase6ff-memory-boundedness-1/memory_boundedness_report.json",
    }
    for phase, path in paths.items():
        historical[phase] = {
            "available": path.exists(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.exists() else None,
            "read_only_design_evidence": True, "formal_population_reuse": False,
        }
    checks = {
        "transient_recovery_is_not_a_hard_failure": transient["gate_pass"],
        "absolute_ceiling_is_rejected": not ceiling["gate_pass"] and "kit_peak" in ceiling["failures"],
        "lifecycle_incomplete_is_rejected": not lifecycle["gate_pass"] and "lifecycle" in lifecycle["failures"],
        "first_cache_then_plateau_is_accepted": plateau["gate_pass"],
        "iteration_staircase_is_rejected": not staircase["gate_pass"],
    }
    report = {
        "schema": "campfire.phase6fg.synthetic-calibration.v1", "phase": "phase6fg",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "status": "pass" if all(checks.values()) else "fail", "checks": checks,
        "fixtures": {"transient": transient, "absolute_ceiling": ceiling, "lifecycle": lifecycle,
                     "first_cache_plateau": plateau, "staircase": staircase},
        "historical_audit": historical,
        "waveform_warning_does_not_change_hard_gate": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "pass":
        raise SystemExit("Phase 6FG synthetic calibration failed")


if __name__ == "__main__":
    main()
