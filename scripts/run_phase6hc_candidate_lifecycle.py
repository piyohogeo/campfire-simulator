"""Phase 6HC fail-closed lifecycle ladder using canonical operation evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import run_phase6hb_candidate_lifecycle as hb
from phase6hb_candidate_lifecycle_contract import LADDER, validate_ladder
from phase6hc_operation_evidence import evaluate_operation_files


def build_command(name: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    command = hb.build_command(name, mode, run_root, contract)
    old_probe = str(hb.SCRIPT_DIR / "probe_phase6hb_candidate_lifecycle.py")
    new_probe = str(hb.SCRIPT_DIR / "probe_phase6hc_candidate_lifecycle.py")
    return [new_probe if value == old_probe else "phase6hc" if value == "phase6hb" else value for value in command]


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    name, mode = condition["name"], condition["mode"]
    if hb.existing_campfire_kit():
        raise RuntimeError("a Kit process existed before the independent condition")
    run_root = output / "runs" / f"launch{sequence:02d}_{name}"
    run_root.mkdir(parents=True)
    command = build_command(name, mode, run_root, contract)
    hb.atomic_json(run_root / "attempt.json", {
        "schema": "campfire.phase6hc.attempt.v1", "sequence": sequence,
        "name": name, "attempt_id": name, "mode": mode,
        "features": list(condition["features"]), "command": command, "start_utc": hb.utc_now(),
    })
    started = time.monotonic()
    guard_exit = subprocess.run(command, cwd=hb.REPO).returncode
    elapsed = time.monotonic() - started
    case, logs = run_root / "case", run_root / "runner-logs"
    guard = hb.read_json(logs / "guard.json")
    runner = hb.read_json(case / "runner_evidence.json")
    raw = hb.read_json(case / "raw.json")
    markers = hb.marker_digest(case / "resource_markers.jsonl")
    names = hb.marker_names(case / "resource_markers.jsonl")
    stderr_path = logs / "stderr.log"
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-4096:] if stderr_path.exists() else ""
    raw_classification, signature = hb.classify(guard, runner, raw, markers, guard_exit, stderr_text)
    temporary_cleanup = hb.cleanup_temporary_files(
        run_root, set(contract["safety"]["temporary_file_allowlist"])
    )
    process_cleanup = (guard or {}).get("observed_process_cleanup") or {}
    cleanup_pass = temporary_cleanup["pass"] and process_cleanup.get("all_observed_absent", False)
    residual = 0 if process_cleanup.get("all_observed_absent", False) else 1
    stop_reason = str((guard or {}).get("stop_reason") or "").lower()
    resource_pass = not any(token in stop_reason for token in (
        "private", "memory", "commit", "resource", "disk", "tree_limit",
    ))
    canonical = evaluate_operation_files(
        case / "post_readback_isolation.json",
        case / "resource_markers.jsonl",
        expected_condition=name,
        expected_attempt_id=name,
        resource_pass=resource_pass,
        cleanup_pass=cleanup_pass,
    )
    lifecycle = {
        "stage_close_complete": "stage_close_complete" in names,
        "shutdown_complete": "shutdown_complete" in names,
        "natural_os_exit": raw_classification == "normal_exit" and (runner or {}).get("process_exit_code") == 0,
    }
    safety = {"resource_pass": resource_pass, "cleanup_pass": cleanup_pass, "residual_zero": residual == 0}
    normal = canonical["pass"] and all(lifecycle.values()) and all(safety.values())
    if normal:
        classification = "normal_exit"
    elif not canonical["pass"]:
        classification = "operation_evidence_failure"
    elif not lifecycle["stage_close_complete"]:
        classification = "stage_close_failure"
    elif not lifecycle["shutdown_complete"]:
        classification = "shutdown_marker_failure"
    elif not lifecycle["natural_os_exit"]:
        classification = "post_shutdown_os_exit_failure"
    else:
        classification = "safety_failure"
    peaks = (guard or {}).get("peaks") or {}
    summary = {
        "schema": "campfire.phase6hc.run-summary.v1", "sequence": sequence,
        "name": name, "attempt_id": name, "mode": mode, "features": list(condition["features"]),
        "elapsed_seconds": elapsed, "classification": classification,
        "raw_classification": raw_classification, "failure_signature": signature,
        "guard_exit_code": guard_exit, "process_exit_code": (runner or {}).get("process_exit_code"),
        "last_operation_marker": (hb.read_json(case / "post_readback_isolation.json") or {}).get("last_operation_marker"),
        "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
        "stage_close_seconds": markers.get("stage_close_seconds"),
        "canonical_operation": canonical, "lifecycle_axis": lifecycle, "safety_axis": safety,
        "peaks": {key: peaks.get(key) for key in ("kit", "tree", "runner", "diagnostic")},
        "machine_minima": (guard or {}).get("machine_minima"),
        "temporary_cleanup": temporary_cleanup, "residual_process_count": residual,
        "end_utc": hb.utc_now(),
    }
    hb.atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=hb.SCRIPT_DIR / "phase6hc_candidate_lifecycle_contract.json")
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HC refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = hb.sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HC contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ladder_check = validate_ladder([{"name": row["name"], "features": row["features"]} for row in LADDER])
    if not ladder_check["pass"]:
        raise RuntimeError(f"Phase 6HC ladder invalid: {ladder_check['reasons']}")
    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    hb.atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6hc.fixed-sequence.v1",
        "conditions": [{"name": row["name"], "mode": row["mode"], "features": list(row["features"])} for row in LADDER],
        "retries": 0, "replacements": 0,
    })
    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run(
        [sys.executable, str(hb.SCRIPT_DIR / "test_phase6hc_operation_evidence.py")],
        cwd=hb.REPO, capture_output=True, text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        hb.atomic_json(output / "phase6hc_summary.json", {
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
            hb.atomic_json(output / "heartbeat.json", {
                "timestamp_utc": hb.utc_now(), "completed_launches": len(rows),
                "last_condition": summary["name"], "last_classification": summary["classification"],
            })
            if summary["classification"] != "normal_exit":
                break
    first_failure = next((row for row in rows if row["classification"] != "normal_exit"), None)
    last_pass = next((row for row in reversed(rows) if row["classification"] == "normal_exit"), None)
    final = {
        "schema": "campfire.phase6hc.candidate-lifecycle-summary.v1",
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
        "phase6hb_reclassified": False, "phase6hb_sample_reused": False,
        "temperature_conversion_failure_claimed": False,
        "formal_population_started": False, "production_changed": False, "runs": rows,
    }
    hb.atomic_json(output / "phase6hc_summary.json", final)
    return 0 if not first_failure else 2


if __name__ == "__main__":
    raise SystemExit(main())
