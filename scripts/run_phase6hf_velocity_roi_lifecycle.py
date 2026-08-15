"""Phase 6HF one-shot cumulative velocity ROI-sampling lifecycle runner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import run_phase6hc_candidate_lifecycle as hc
from phase6hf_operation_schema import CONDITIONS, validate_operation_files

ORIGINAL_HC_BUILD_COMMAND = hc.build_command


def build_command(name: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    command = ORIGINAL_HC_BUILD_COMMAND(name, "R2", run_root, contract)
    old_probe = str(hc.hb.SCRIPT_DIR / "probe_phase6hc_candidate_lifecycle.py")
    new_probe = str(hc.hb.SCRIPT_DIR / "probe_phase6hf_velocity_roi_lifecycle.py")
    return [new_probe if value == old_probe else "phase6hf" if value == "phase6hc" else value for value in command]


hc.build_command = build_command
hc.evaluate_operation_files = validate_operation_files


def runtime_conditions() -> list[dict]:
    return [
        {"name": row["name"], "mode": row["mode"], "features": list(row["roi_names"])}
        for row in CONDITIONS
    ]


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    summary = hc.run_one(sequence, condition, output, contract)
    summary["schema"] = "campfire.phase6hf.run-summary.v1"
    summary["phase"] = "phase6hf"
    report_path = Path(summary["canonical_operation"]["canonical_source"])
    report = hc.hb.read_json(report_path) or {}
    summary["functional_axis"] = {
        "operation_complete": summary["canonical_operation"]["pass"],
        "references_released": report.get("references_released") is True,
        "weak_residual_zero": report.get("weak_reference_alive_after_release_count") == 0,
        "executed_roi_names": report.get("executed_roi_names"),
        "sampling_call_count": (report.get("calls") or {}).get("velocity_roi_sampling"),
    }
    summary["os_exit_axis"] = {
        "natural_exit_code_zero": summary["lifecycle_axis"]["natural_os_exit"],
        "process_exit_code": summary.get("process_exit_code"),
    }
    run_root = output / "runs" / f"launch{sequence:02d}_{condition['name']}"
    hc.hb.atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=hc.hb.SCRIPT_DIR / "phase6hf_velocity_roi_lifecycle_contract.json",
    )
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HF refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = hc.hb.sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HF contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    frozen_rows = contract.get("ladder")
    canonical_rows = [
        {key: row[key] for key in ("name", "mode", "roi_count", "roi_names", "adds")}
        for row in CONDITIONS
    ]
    if frozen_rows != canonical_rows:
        raise RuntimeError("Phase 6HF frozen ladder differs from canonical runtime conditions")

    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    rows_to_run = runtime_conditions()
    hc.hb.atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6hf.fixed-sequence.v1",
        "conditions": rows_to_run,
        "retries": 0,
        "replacements": 0,
    })

    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run(
        [sys.executable, str(hc.hb.SCRIPT_DIR / "test_phase6hf_velocity_roi_lifecycle.py")],
        cwd=hc.hb.REPO,
        capture_output=True,
        text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        hc.hb.atomic_json(output / "phase6hf_summary.json", {
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
    all_normal = first_failure is None and len(rows) == len(CONDITIONS)
    final = {
        "schema": "campfire.phase6hf.velocity-roi-lifecycle-summary.v1",
        "status": "not_reproduced_in_bounded_ladder" if all_normal else "safe_stop",
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
            "added_roi": next(row["adds"] for row in CONDITIONS if row["name"] == first_failure["name"]),
        },
        "all_normal_interpretation": "short_ladder_did_not_reproduce_phase6he_v6" if all_normal else None,
        "phase6he_reclassified": False,
        "phase6he_sample_reused": False,
        "root_cause_claimed": False,
        "profile_used": False,
        "collector_used": False,
        "temperature_failure_claimed": False,
        "formal_population_started": False,
        "production_changed": False,
        "runs": rows,
    }
    hc.hb.atomic_json(output / "phase6hf_summary.json", final)
    return 0 if all_normal else 2


if __name__ == "__main__":
    raise SystemExit(main())
