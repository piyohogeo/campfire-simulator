"""Phase 6HE one-shot velocity sub-boundary lifecycle runner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import run_phase6hc_candidate_lifecycle as hc
from phase6he_operation_schema import CONDITIONS, validate_operation_files

ORIGINAL_HC_BUILD_COMMAND = hc.build_command


def build_command(name: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    # The frozen Phase 6HB implementation supplies Condition C as the shared
    # prefix.  Phase 6HE selects its V-level from the attempt label.
    command = ORIGINAL_HC_BUILD_COMMAND(name, "R2", run_root, contract)
    old_probe = str(hc.hb.SCRIPT_DIR / "probe_phase6hc_candidate_lifecycle.py")
    new_probe = str(hc.hb.SCRIPT_DIR / "probe_phase6he_velocity_lifecycle.py")
    return [new_probe if value == old_probe else "phase6he" if value == "phase6hc" else value for value in command]


hc.build_command = build_command
hc.evaluate_operation_files = validate_operation_files


def runtime_conditions() -> list[dict]:
    features = []
    rows = []
    for row in CONDITIONS:
        if row["adds"] != "none":
            features.append(row["adds"])
        rows.append({"name": row["name"], "mode": row["mode"], "features": list(features)})
    return rows


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    summary = hc.run_one(sequence, condition, output, contract)
    summary["schema"] = "campfire.phase6he.run-summary.v1"
    summary["phase"] = "phase6he"
    run_root = output / "runs" / f"launch{sequence:02d}_{condition['name']}"
    hc.hb.atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=hc.hb.SCRIPT_DIR / "phase6he_velocity_lifecycle_contract.json",
    )
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HE refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = hc.hb.sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HE contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    frozen_rows = contract.get("ladder")
    canonical_rows = [
        {key: row[key] for key in ("name", "mode", "stop_after", "adds")}
        for row in CONDITIONS
    ]
    if frozen_rows != canonical_rows:
        raise RuntimeError("Phase 6HE frozen ladder differs from canonical runtime conditions")

    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    rows_to_run = runtime_conditions()
    hc.hb.atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6he.fixed-sequence.v1",
        "conditions": rows_to_run,
        "retries": 0,
        "replacements": 0,
        "v8_policy": "not_scheduled_because_default-path-equivalence-is_an_offline_fixture",
    })

    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run(
        [sys.executable, str(hc.hb.SCRIPT_DIR / "test_phase6he_velocity_lifecycle.py")],
        cwd=hc.hb.REPO,
        capture_output=True,
        text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        hc.hb.atomic_json(output / "phase6he_summary.json", {
            "status": "preflight_safe_stop",
            "fixture_exit": fixture.returncode,
        })
        return 2

    rows = []
    with (output / "aggregate.jsonl").open("w", encoding="utf-8", buffering=1) as aggregate:
        for sequence, condition in enumerate(rows_to_run, 1):
            summary = run_one(sequence, condition, output, contract)
            rows.append(summary)
            aggregate.write(json.dumps(summary, sort_keys=True, allow_nan=False) + "\n")
            aggregate.flush()
            os.fsync(aggregate.fileno())
            hc.hb.atomic_json(output / "heartbeat.json", {
                "timestamp_utc": hc.hb.utc_now(),
                "completed_launches": len(rows),
                "last_condition": summary["name"],
                "last_classification": summary["classification"],
            })
            if summary["classification"] != "normal_exit":
                break

    first_failure = next((row for row in rows if row["classification"] != "normal_exit"), None)
    last_pass = next((row for row in reversed(rows) if row["classification"] == "normal_exit"), None)
    final = {
        "schema": "campfire.phase6he.velocity-lifecycle-summary.v1",
        "status": "safe_stop" if first_failure else "bounded_ladder_complete",
        "contract_sha256": actual,
        "launches": len(rows),
        "maximum_launches": len(CONDITIONS),
        "retries": 0,
        "replacements": 0,
        "last_fully_qualified_condition": last_pass,
        "first_failed_condition": first_failure,
        "first_boundary_difference": None if not first_failure else {
            "before": None if not last_pass else last_pass["name"],
            "after": first_failure["name"],
            "added_feature": next(row["adds"] for row in CONDITIONS if row["name"] == first_failure["name"]),
        },
        "v8_executed": False,
        "v8_not_required_reason": "V7 invokes the actual helper through its final profile boundary; offline fixture checks default-path call order",
        "phase6hd_reclassified": False,
        "phase6hd_sample_reused": False,
        "temperature_failure_claimed": False,
        "collector_used": False,
        "formal_population_started": False,
        "production_changed": False,
        "runs": rows,
    }
    hc.hb.atomic_json(output / "phase6he_summary.json", final)
    return 0 if first_failure is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
