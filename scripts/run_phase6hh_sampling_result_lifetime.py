"""Phase 6HH one-shot sampling-result lifetime runner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import run_phase6hf_velocity_roi_lifecycle as hf
from phase6hh_retention_contract import (
    CONDITIONS,
    build_read_only_audit,
    validate_operation_files,
)


def build_command(name: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    command = hf.build_command(name, mode, run_root, contract)
    old_probe = str(hf.hc.hb.SCRIPT_DIR / "probe_phase6hf_velocity_roi_lifecycle.py")
    new_probe = str(hf.hc.hb.SCRIPT_DIR / "probe_phase6hh_sampling_result_lifetime.py")
    return [new_probe if value == old_probe else "phase6hh" if value == "phase6hf" else value for value in command]


hf.hc.build_command = build_command
hf.hc.evaluate_operation_files = validate_operation_files


def runtime_conditions() -> list[dict]:
    return [
        {
            "name": row["name"],
            "mode": row["mode"],
            "features": [] if row["roi_count"] == 0 else ["scene", row["retention"]],
        }
        for row in CONDITIONS
    ]


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    summary = hf.run_one(sequence, condition, output, contract)
    summary["schema"] = "campfire.phase6hh.run-summary.v1"
    summary["phase"] = "phase6hh"
    report = hf.hc.hb.read_json(Path(summary["canonical_operation"]["canonical_source"])) or {}
    summary["retention_axis"] = {
        "mode": report.get("retention_mode"),
        "sample_result_type": (report.get("sampling_result_evidence") or {}).get("python_type"),
        "weakref_supported": (report.get("sampling_result_evidence") or {}).get("weakref_supported"),
        "contains_numpy": (report.get("sampling_result_evidence") or {}).get("contains_numpy"),
        "contains_native_wrapper": (report.get("sampling_result_evidence") or {}).get("contains_native_wrapper"),
        "local_clear_complete": report.get("sampling_local_result_clear_completed"),
        "retained_count": report.get("sampling_result_retained_count"),
        "retained_to_operation_report": report.get("sampling_result_retained_to_operation_report"),
        "bounded_metadata": report.get("sampling_bounded_metadata"),
    }
    run_root = output / "runs" / f"launch{sequence:02d}_{condition['name']}"
    hf.hc.hb.atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=hf.hc.hb.SCRIPT_DIR / "phase6hh_sampling_result_lifetime_contract.json",
    )
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HH refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = hf.hc.hb.sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HH contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    canonical = [dict(row) for row in CONDITIONS]
    if contract.get("ladder") != canonical:
        raise RuntimeError("Phase 6HH frozen ladder differs from runtime conditions")

    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    sequence = runtime_conditions()
    hf.hc.hb.atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6hh.fixed-sequence.v1",
        "conditions": sequence,
        "retries": 0,
        "replacements": 0,
    })
    preflight = output / "preflight"
    preflight.mkdir()
    hf.hc.hb.atomic_json(preflight / "phase6hf_read_only_audit.json", build_read_only_audit(hf.hc.hb.REPO))
    fixture = subprocess.run(
        [sys.executable, str(hf.hc.hb.SCRIPT_DIR / "test_phase6hh_sampling_result_lifetime.py")],
        cwd=hf.hc.hb.REPO,
        capture_output=True,
        text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        hf.hc.hb.atomic_json(output / "phase6hh_summary.json", {"status": "preflight_safe_stop", "fixture_exit": fixture.returncode})
        return 2

    rows = []
    with (output / "aggregate.jsonl").open("w", encoding="utf-8", buffering=1) as aggregate:
        for launch, condition in enumerate(sequence, 1):
            summary = run_one(launch, condition, output, contract)
            rows.append(summary)
            aggregate.write(json.dumps(summary, sort_keys=True, allow_nan=False) + "\n")
            aggregate.flush()
            os.fsync(aggregate.fileno())
            hf.hc.hb.atomic_json(output / "heartbeat.json", {
                "timestamp_utc": hf.hc.hb.utc_now(),
                "completed_launches": len(rows),
                "last_condition": summary["name"],
                "last_classification": summary["classification"],
            })
            if summary["classification"] != "normal_exit":
                break

    by_mode = {row["mode"]: row for row in rows}
    first_failure = next((row for row in rows if row["classification"] != "normal_exit"), None)
    all_normal = first_failure is None and len(rows) == len(CONDITIONS)
    if first_failure and first_failure["mode"] == "L0":
        conclusion = "comparison_invalid_control_non_normal"
    elif first_failure and first_failure["mode"] == "L1":
        conclusion = "immediate_clear_non_normal_retention_alone_insufficient"
    elif first_failure and first_failure["mode"] == "L2":
        conclusion = "retention_lifetime_association_strengthened"
    elif all_normal:
        conclusion = "not_reproduced_in_this_short_ladder"
    else:
        conclusion = "incomplete"
    final = {
        "schema": "campfire.phase6hh.sampling-result-lifetime-summary.v1",
        "status": "qualified_comparison" if all_normal else "safe_stop",
        "conclusion": conclusion,
        "contract_sha256": actual,
        "launches": len(rows),
        "maximum_launches": 3,
        "retries": 0,
        "replacements": 0,
        "runs": rows,
        "last_fully_qualified_condition": next((row for row in reversed(rows) if row["classification"] == "normal_exit"), None),
        "first_failed_condition": first_failure,
        "l0_normal": by_mode.get("L0", {}).get("classification") == "normal_exit",
        "l1_normal": by_mode.get("L1", {}).get("classification") == "normal_exit",
        "l2_normal": by_mode.get("L2", {}).get("classification") == "normal_exit",
        "phase6hf_reclassified": False,
        "phase6hf_sample_reused": False,
        "root_cause_claimed": False,
        "formal_population_started": False,
        "production_changed": False,
    }
    hf.hc.hb.atomic_json(output / "phase6hh_summary.json", final)
    return 0 if all_normal else 2


if __name__ == "__main__":
    raise SystemExit(main())
