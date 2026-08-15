"""Phase 6HD ladder runner using the shared operation counter schema."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import run_phase6hc_candidate_lifecycle as hc
from phase6hb_candidate_lifecycle_contract import LADDER, validate_ladder
from phase6hd_operation_schema import validate_operation_files

ORIGINAL_HC_BUILD_COMMAND = hc.build_command


def build_command(name: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    command = ORIGINAL_HC_BUILD_COMMAND(name, mode, run_root, contract)
    old_probe = str(hc.hb.SCRIPT_DIR / "probe_phase6hc_candidate_lifecycle.py")
    new_probe = str(hc.hb.SCRIPT_DIR / "probe_phase6hd_candidate_lifecycle.py")
    return [new_probe if value == old_probe else "phase6hd" if value == "phase6hc" else value for value in command]


hc.build_command = build_command
hc.evaluate_operation_files = validate_operation_files


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    summary = hc.run_one(sequence, condition, output, contract)
    summary["schema"] = "campfire.phase6hd.run-summary.v1"
    summary["phase"] = "phase6hd"
    run_root = output / "runs" / f"launch{sequence:02d}_{condition['name']}"
    hc.hb.atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=hc.hb.SCRIPT_DIR / "phase6hd_candidate_lifecycle_contract.json")
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HD refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = hc.hb.sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HD contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ladder_check = validate_ladder([{"name": row["name"], "features": row["features"]} for row in LADDER])
    if not ladder_check["pass"]:
        raise RuntimeError(f"Phase 6HD ladder invalid: {ladder_check['reasons']}")
    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    hc.hb.atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6hd.fixed-sequence.v1",
        "conditions": [{"name": row["name"], "mode": row["mode"], "features": list(row["features"])} for row in LADDER],
        "retries": 0, "replacements": 0,
    })
    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run(
        [sys.executable, str(hc.hb.SCRIPT_DIR / "test_phase6hd_operation_schema.py")],
        cwd=hc.hb.REPO, capture_output=True, text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        hc.hb.atomic_json(output / "phase6hd_summary.json", {
            "status": "preflight_safe_stop", "fixture_exit": fixture.returncode,
        })
        return 2
    rows = []
    with (output / "aggregate.jsonl").open("w", encoding="utf-8", buffering=1) as aggregate:
        for sequence, condition in enumerate(LADDER, 1):
            summary = run_one(sequence, condition, output, contract)
            rows.append(summary)
            aggregate.write(json.dumps(summary, sort_keys=True, allow_nan=False) + "\n")
            aggregate.flush()
            os.fsync(aggregate.fileno())
            hc.hb.atomic_json(output / "heartbeat.json", {
                "timestamp_utc": hc.hb.utc_now(), "completed_launches": len(rows),
                "last_condition": summary["name"], "last_classification": summary["classification"],
            })
            if summary["classification"] != "normal_exit":
                break
    first_failure = next((row for row in rows if row["classification"] != "normal_exit"), None)
    last_pass = next((row for row in reversed(rows) if row["classification"] == "normal_exit"), None)
    final = {
        "schema": "campfire.phase6hd.candidate-lifecycle-summary.v1",
        "status": "safe_stop" if first_failure else "bounded_ladder_complete",
        "contract_sha256": actual, "launches": len(rows), "maximum_launches": len(LADDER),
        "retries": 0, "replacements": 0,
        "last_fully_qualified_condition": last_pass,
        "first_failed_condition": first_failure,
        "first_boundary_difference": None if not first_failure else {
            "before": None if not last_pass else last_pass["name"], "after": first_failure["name"],
            "added_feature": next(row["adds"] for row in contract["ladder"] if row["name"] == first_failure["name"]),
        },
        "remaining_unseparated_if_all_normal": [
            "prohibited temperature schema-prefix native work",
            "interaction between prohibited temperature work and the non-temperature Candidate prefix",
        ] if not first_failure else [],
        "phase6hc_reclassified": False, "phase6hc_sample_reused": False,
        "temperature_conversion_failure_claimed": False,
        "formal_population_started": False, "production_changed": False, "runs": rows,
    }
    hc.hb.atomic_json(output / "phase6hd_summary.json", final)
    return 0 if not first_failure else 2


if __name__ == "__main__":
    raise SystemExit(main())
