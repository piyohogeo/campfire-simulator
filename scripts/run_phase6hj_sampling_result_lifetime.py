"""Phase 6HJ runner with isolated no-Kit fixture and frozen 6HH runtime path."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import run_phase6hh_sampling_result_lifetime as hh
from phase6hh_retention_contract import CONDITIONS, build_read_only_audit


def runtime_conditions() -> list[dict]:
    return hh.runtime_conditions()


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    summary = hh.run_one(sequence, condition, output, contract)
    summary["schema"] = "campfire.phase6hj.run-summary.v1"
    summary["phase"] = "phase6hj"
    summary["runtime_operation_schema"] = "campfire.phase6hh.operation-report.v1"
    summary["runtime_probe_unchanged_from_phase6hh"] = True
    run_root = output / "runs" / f"launch{sequence:02d}_{condition['name']}"
    hh.hf.hc.hb.atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=hh.hf.hc.hb.SCRIPT_DIR / "phase6hj_sampling_result_lifetime_contract.json",
    )
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HJ refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = hh.hf.hc.hb.sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HJ contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("ladder") != [dict(row) for row in CONDITIONS]:
        raise RuntimeError("Phase 6HJ frozen ladder differs from runtime conditions")

    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    sequence = runtime_conditions()
    hh.hf.hc.hb.atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6hj.fixed-sequence.v1",
        "conditions": sequence,
        "retries": 0,
        "replacements": 0,
    })
    preflight = output / "preflight"
    preflight.mkdir()
    hh.hf.hc.hb.atomic_json(preflight / "phase6hf_read_only_audit.json", build_read_only_audit(hh.hf.hc.hb.REPO))
    fixture = subprocess.run(
        [sys.executable, str(hh.hf.hc.hb.SCRIPT_DIR / "test_phase6hj_sampling_result_lifetime.py")],
        cwd=hh.hf.hc.hb.REPO,
        capture_output=True,
        text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        hh.hf.hc.hb.atomic_json(output / "phase6hj_summary.json", {"status": "preflight_safe_stop", "fixture_exit": fixture.returncode})
        return 2

    rows = []
    with (output / "aggregate.jsonl").open("w", encoding="utf-8", buffering=1) as aggregate:
        for launch, condition in enumerate(sequence, 1):
            summary = run_one(launch, condition, output, contract)
            rows.append(summary)
            aggregate.write(json.dumps(summary, sort_keys=True, allow_nan=False) + "\n")
            aggregate.flush()
            os.fsync(aggregate.fileno())
            hh.hf.hc.hb.atomic_json(output / "heartbeat.json", {
                "timestamp_utc": hh.hf.hc.hb.utc_now(),
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
        "schema": "campfire.phase6hj.sampling-result-lifetime-summary.v1",
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
        "phase6hh_preflight_safe_stop_preserved": True,
        "phase6hh_runtime_samples_reused": False,
        "phase6hf_reclassified": False,
        "phase6hf_sample_reused": False,
        "root_cause_claimed": False,
        "formal_population_started": False,
        "production_changed": False,
    }
    hh.hf.hc.hb.atomic_json(output / "phase6hj_summary.json", final)
    return 0 if all_normal else 2


if __name__ == "__main__":
    raise SystemExit(main())
