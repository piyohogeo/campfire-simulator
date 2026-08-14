"""Fail-closed Phase 6GZ one-process boundary ladder."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from phase6gz_boundary_contract import LADDER, ALLOWED_TEMPORARY_NAMES
from run_phase6gv_repetition import classify, existing_campfire_kit, marker_digest, read_json

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > 256 * 1024:
        raise RuntimeError(f"bounded JSON exceeded 256 KiB: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def cleanup_temporary_files(run_root: Path) -> dict:
    root = run_root.resolve()
    observed, failures = [], []
    for path in sorted(root.rglob("*.nvdb")):
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            failures.append({"path": str(resolved), "reason": "outside_attempt_root"})
            continue
        row = {"relative_path": str(relative), "name": resolved.name, "bytes": resolved.stat().st_size,
               "allowlisted": resolved.name in ALLOWED_TEMPORARY_NAMES, "deleted": False}
        if not row["allowlisted"]:
            failures.append({"path": str(relative), "reason": "unknown_temporary_filename_not_deleted"})
        else:
            resolved.unlink()
            row["deleted"] = not resolved.exists()
            if not row["deleted"]:
                failures.append({"path": str(relative), "reason": "delete_not_confirmed"})
        observed.append(row)
    remaining = [str(path.resolve().relative_to(root)) for path in root.rglob("*.nvdb")]
    return {"observed": observed, "failures": failures, "residual": remaining,
            "residual_count": len(remaining), "pass": not failures and not remaining}


def build_command(name: str, kind: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    case = run_root / "case"
    logs = run_root / "runner-logs"
    logs.mkdir(parents=True)
    control = kind == "control"
    probe = SCRIPT_DIR / ("probe_phase6gs_volume_metadata.py" if control else "probe_phase6gz_candidate_boundary.py")
    inner = [
        str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
        str(SCRIPT_DIR / "run_phase6fo_supply_case.ps1"),
        "-Scenario", "production_four", "-OutputDir", str(case), "-OffsetM", "-0.0125",
        "-SupportRadiusM", "0.05", "-Filtering", "true", "-Collision", "true",
        "-Policy", "allow_self_center", "-ReportPhase", ("phase6gs" if control else "phase6gz"),
        "-GeometryVariant", "phase6er_corrected", "-ExpectedGeometryConcept", "corrected",
        "-ProbePath", str(probe), "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "60,120,180,240", "-OperationFrames", "180", "-ReadbackFrames", "180",
        "-ReadbackChannels", "velocity,temperature,smoke,fuel", "-ReadbackMode", "p3_spatial_release",
        "-ReferenceDisposal", "del", "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", "0,1,2,3", "-SpatialAllChannels",
        "-RunIndex", "1", "-LifecycleCalibration", "-RendererDrainUpdates", "8",
        "-LifecycleReferenceReleaseOrder", "after_stage_close", "-StageCloseTimeoutSeconds", "180",
        "-StabilityObservationStartFrame", "240", "-StabilityObservationExtraSeconds", "5",
        "-StabilityActiveBlockSampleSeconds", "0.5", "-FlowLivenessAudit", "true", "-StartupProbe", "true",
        "-StartupProbeLabel", name, "-StartupFlowAcquirePosition", "before_updates",
        "-StartupPreTimelineUpdateCount", "12", "-StartupExtraUpdateBeforePlayCount", "0",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "1075.2",
        "-StartupExpectedTemperatureSum", "2688.0", "-StartupExpectedSmokeSum", "107.52",
        "-StartupSourceSumTolerance", "0.00001", "-StartupSourceContractMode", "payload_native_float32_v1",
        "-AbsoluteTimeoutSeconds", "900", "-ImportAuditPath", str(case / "kit_import_audit.json"),
        "-PostReadbackIsolationMode", mode, "-PostReadbackIsolationChannel", "temperature",
        "-PostReadbackIsolationReportPath", str(case / "post_readback_isolation.json"),
    ]
    safety = contract["safety"]
    return [sys.executable, str(SCRIPT_DIR / "phase6fu_resource_guard.py"),
        "--trace", str(logs / "resource.jsonl"), "--summary", str(logs / "guard.json"),
        "--stdout", str(logs / "stdout.log"), "--stderr", str(logs / "stderr.log"),
        "--timeout-seconds", str(contract["execution"]["absolute_condition_timeout_seconds"]),
        "--sample-seconds", "0.25", "--runner-private-limit", str(safety["runner_private_limit_bytes"]),
        "--diagnostic-private-limit", str(safety["diagnostic_private_limit_bytes"]),
        "--kit-private-limit", str(safety["kit_private_limit_bytes"]),
        "--tree-private-limit", str(safety["unique_tree_private_limit_bytes"]),
        "--available-memory-floor", str(safety["available_physical_floor_bytes"]),
        "--commit-headroom-floor", str(safety["commit_headroom_floor_bytes"]),
        "--cpu-telemetry", "--gpu-csv", str(logs / "gpu.csv"), "--gpu-sample-ms", "1000",
        "--lifecycle-path", str(case / "raw.json"), "--diagnostic-marker-path", str(case / "resource_markers.jsonl"),
        "--attempt-id", name, "--cleanup-suppression-lock", str(case / "sensitive-shutdown-diagnostics.ownership.json"),
        "--cleanup-suppression-deadline-seconds", "150", "--cleanup-marker-path", str(logs / "cleanup_markers.jsonl"),
        "--", *inner]


def run_one(sequence: int, row: tuple, output: Path, contract: dict) -> dict:
    name, kind, mode, level = row
    if existing_campfire_kit():
        raise RuntimeError("a Kit process existed before the independent condition")
    run_root = output / "runs" / f"launch{sequence:02d}_{name}"
    run_root.mkdir(parents=True)
    command = build_command(name, kind, mode, run_root, contract)
    atomic_json(run_root / "attempt.json", {"schema": "campfire.phase6gz.attempt.v1", "sequence": sequence,
                "name": name, "kind": kind, "mode": mode, "level": level, "command": command,
                "start_utc": utc_now()})
    started = time.monotonic()
    guard_exit = subprocess.run(command, cwd=REPO).returncode
    elapsed = time.monotonic() - started
    case, logs = run_root / "case", run_root / "runner-logs"
    guard = read_json(logs / "guard.json")
    runner = read_json(case / "runner_evidence.json")
    raw = read_json(case / "raw.json")
    operation = read_json(case / "post_readback_isolation.json")
    markers = marker_digest(case / "resource_markers.jsonl")
    stderr_path = logs / "stderr.log"
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-4096:] if stderr_path.exists() else ""
    classification, signature = classify(guard, runner, raw, markers, guard_exit, stderr_text)
    cleanup = cleanup_temporary_files(run_root)
    observed_cleanup = (guard or {}).get("observed_process_cleanup") or {}
    if not cleanup["pass"] or not observed_cleanup.get("all_observed_absent", False):
        classification, signature = "cleanup_failure", "attempt_cleanup_not_complete"
    operation_complete = bool(operation and operation.get("operation_result") == "pass")
    if classification == "normal_exit" and not operation_complete:
        classification, signature = "operation_failure", "operation_report_not_pass"
    peaks = (guard or {}).get("peaks") or {}
    summary = {"schema": "campfire.phase6gz.run-summary.v1", "sequence": sequence, "name": name,
        "kind": kind, "mode": mode, "level": level, "elapsed_seconds": elapsed,
        "classification": classification, "failure_signature": signature, "guard_exit_code": guard_exit,
        "process_exit_code": (runner or {}).get("process_exit_code"),
        "last_operation_marker": markers.get("last_operation_marker"),
        "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
        "stage_close_seconds": markers.get("stage_close_seconds"),
        "peaks": {key: peaks.get(key) for key in ("kit", "tree", "runner", "diagnostic")},
        "machine_minima": (guard or {}).get("machine_minima"), "operation": operation,
        "temporary_cleanup": cleanup, "residual_process_count": 0 if observed_cleanup.get("all_observed_absent") else None,
        "end_utc": utc_now()}
    atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=SCRIPT_DIR / "phase6gz_boundary_contract.json")
    args = parser.parse_args()
    output = args.output.resolve()
    contract_path = args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6GZ refuses artifact root reuse: {output}")
    expected = contract_path.with_suffix(".sha256").read_text(encoding="utf-8").split()[0].upper()
    actual = sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6GZ contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(contract_path.with_suffix(".sha256"), output / "frozen_contract.sha256")
    atomic_json(output / "fixed_sequence.json", {"schema": "campfire.phase6gz.fixed-sequence.v1",
                "conditions": [{"name": n, "kind": k, "mode": m, "level": l} for n, k, m, l in LADDER],
                "retries": 0, "replacements": 0})
    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run([sys.executable, str(SCRIPT_DIR / "test_phase6gz_boundary_contract.py")],
                             cwd=REPO, capture_output=True, text=True)
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        atomic_json(output / "phase6gz_summary.json", {"status": "preflight_safe_stop", "fixture_exit": fixture.returncode})
        return 2
    audit = subprocess.run([sys.executable, str(SCRIPT_DIR / "analyze_phase6gz_existing_evidence.py"),
                            "--repo", str(REPO), "--output", str(preflight / "historical_boundary_audit.json")],
                           cwd=REPO, capture_output=True, text=True)
    (preflight / "audit.stdout.log").write_text(audit.stdout, encoding="utf-8")
    (preflight / "audit.stderr.log").write_text(audit.stderr, encoding="utf-8")
    if audit.returncode:
        atomic_json(output / "phase6gz_summary.json", {"status": "historical_audit_safe_stop", "audit_exit": audit.returncode})
        return 2
    rows = []
    with (output / "aggregate.jsonl").open("w", encoding="utf-8", buffering=1) as aggregate:
        for sequence, row in enumerate(LADDER, 1):
            summary = run_one(sequence, row, output, contract)
            rows.append(summary)
            aggregate.write(json.dumps(summary, sort_keys=True, allow_nan=False) + "\n")
            aggregate.flush()
            os.fsync(aggregate.fileno())
            atomic_json(output / "heartbeat.json", {"timestamp_utc": utc_now(), "completed_launches": len(rows),
                        "last_condition": summary["name"], "last_classification": summary["classification"]})
            if summary["classification"] != "normal_exit":
                break
    stopped = len(rows) < len(LADDER) or rows[-1]["classification"] != "normal_exit"
    final = {"schema": "campfire.phase6gz.boundary-ladder-summary.v1", "status": "safe_stop" if stopped else "qualified",
        "contract_sha256": actual, "launches": len(rows), "maximum_launches": len(LADDER), "retries": 0,
        "replacements": 0, "first_non_normal": next((row for row in rows if row["classification"] != "normal_exit"), None),
        "last_qualified_condition": next((row["name"] for row in reversed(rows) if row["classification"] == "normal_exit"), None),
        "formal_population_started": False, "other_channels_started": False, "production_changed": False,
        "phase6gy_launch23_mechanism_population": "excluded-user-intervention-contaminated", "runs": rows}
    atomic_json(output / "phase6gz_summary.json", final)
    return 2 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
