"""Fail-closed Phase 6HB temperature-free lifecycle ladder runner."""

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

from phase6hb_candidate_lifecycle_contract import LADDER, classify_axes, validate_ladder
from run_phase6gv_repetition import classify, existing_campfire_kit, marker_digest, read_json

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > 512 * 1024:
        raise RuntimeError(f"bounded JSON exceeded 512 KiB: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def marker_names(path: Path) -> list[str]:
    names = []
    if not path.exists():
        return names
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("marker") or row.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def cleanup_temporary_files(run_root: Path, allowlist: set[str]) -> dict:
    root = run_root.resolve()
    observed, failures = [], []
    for path in sorted(root.rglob("*.nvdb")):
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            failures.append({"path": str(resolved), "reason": "outside_attempt_root"})
            continue
        allowed = resolved.name in allowlist
        row = {"relative_path": str(relative), "name": resolved.name,
               "bytes": resolved.stat().st_size, "allowlisted": allowed, "deleted": False}
        if not allowed:
            failures.append({"path": str(relative), "reason": "unknown_temporary_filename_not_deleted"})
        else:
            resolved.unlink()
            row["deleted"] = not resolved.exists()
            if not row["deleted"]:
                failures.append({"path": str(relative), "reason": "delete_not_confirmed"})
        observed.append(row)
    residual = [str(path.resolve().relative_to(root)) for path in root.rglob("*.nvdb")]
    return {"observed": observed, "failures": failures, "residual": residual,
            "residual_count": len(residual), "pass": not failures and not residual}


def build_command(name: str, mode: str, run_root: Path, contract: dict) -> list[str]:
    case = run_root / "case"
    logs = run_root / "runner-logs"
    logs.mkdir(parents=True)
    inner = [
        str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
        str(SCRIPT_DIR / "run_phase6fo_supply_case.ps1"),
        "-Scenario", "production_four", "-OutputDir", str(case), "-OffsetM", "-0.0125",
        "-SupportRadiusM", "0.05", "-Filtering", "true", "-Collision", "true",
        "-Policy", "allow_self_center", "-ReportPhase", "phase6hb",
        "-GeometryVariant", "phase6er_corrected", "-ExpectedGeometryConcept", "corrected",
        "-ProbePath", str(SCRIPT_DIR / "probe_phase6hb_candidate_lifecycle.py"),
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
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
        "-AbsoluteTimeoutSeconds", str(contract["execution"]["inner_timeout_seconds"]),
        "-ImportAuditPath", str(case / "kit_import_audit.json"),
        "-PostReadbackIsolationMode", mode, "-PostReadbackIsolationChannel", "temperature",
        "-PostReadbackIsolationReportPath", str(case / "post_readback_isolation.json"),
    ]
    safety = contract["safety"]
    return [
        sys.executable, str(SCRIPT_DIR / "phase6fu_resource_guard.py"),
        "--trace", str(logs / "resource.jsonl"), "--summary", str(logs / "guard.json"),
        "--stdout", str(logs / "stdout.log"), "--stderr", str(logs / "stderr.log"),
        "--timeout-seconds", str(contract["execution"]["outer_timeout_seconds"]), "--sample-seconds", "0.25",
        "--runner-private-limit", str(safety["runner_private_limit_bytes"]),
        "--diagnostic-private-limit", str(safety["diagnostic_private_limit_bytes"]),
        "--kit-private-limit", str(safety["kit_private_limit_bytes"]),
        "--tree-private-limit", str(safety["unique_tree_private_limit_bytes"]),
        "--available-memory-floor", str(safety["available_physical_floor_bytes"]),
        "--commit-headroom-floor", str(safety["commit_headroom_floor_bytes"]),
        "--cpu-telemetry", "--gpu-csv", str(logs / "gpu.csv"), "--gpu-sample-ms", "1000",
        "--lifecycle-path", str(case / "raw.json"),
        "--diagnostic-marker-path", str(case / "resource_markers.jsonl"),
        "--attempt-id", name,
        "--cleanup-suppression-lock", str(case / "sensitive-shutdown-diagnostics.ownership.json"),
        "--cleanup-suppression-deadline-seconds", "150",
        "--cleanup-marker-path", str(logs / "cleanup_markers.jsonl"), "--", *inner,
    ]


def run_one(sequence: int, condition: dict, output: Path, contract: dict) -> dict:
    name, mode = condition["name"], condition["mode"]
    if existing_campfire_kit():
        raise RuntimeError("a Kit process existed before the independent condition")
    run_root = output / "runs" / f"launch{sequence:02d}_{name}"
    run_root.mkdir(parents=True)
    command = build_command(name, mode, run_root, contract)
    atomic_json(run_root / "attempt.json", {
        "schema": "campfire.phase6hb.attempt.v1", "sequence": sequence, "name": name,
        "mode": mode, "features": list(condition["features"]), "command": command, "start_utc": utc_now(),
    })
    started = time.monotonic()
    guard_exit = subprocess.run(command, cwd=REPO).returncode
    elapsed = time.monotonic() - started
    case, logs = run_root / "case", run_root / "runner-logs"
    guard = read_json(logs / "guard.json")
    runner = read_json(case / "runner_evidence.json")
    raw = read_json(case / "raw.json")
    operation = read_json(case / "post_readback_isolation.json") or {}
    markers = marker_digest(case / "resource_markers.jsonl")
    names = marker_names(case / "resource_markers.jsonl")
    stderr_path = logs / "stderr.log"
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-4096:] if stderr_path.exists() else ""
    raw_classification, signature = classify(guard, runner, raw, markers, guard_exit, stderr_text)
    allowlist = set(contract["safety"]["temporary_file_allowlist"])
    temporary_cleanup = cleanup_temporary_files(run_root, allowlist)
    process_cleanup = (guard or {}).get("observed_process_cleanup") or {}
    residual = 0 if process_cleanup.get("all_observed_absent", False) else 1
    peaks = (guard or {}).get("peaks") or {}
    minima = (guard or {}).get("machine_minima") or {}
    resource_pass = not (guard or {}).get("stop_reason") and guard_exit == 0
    calls = operation.get("calls") or {}
    evidence = {
        "markers": names,
        "operation_result": operation.get("operation_result"),
        "references_released": operation.get("references_released") is True,
        "temperature_volume_calls": calls.get("temperature_buffer_to_volume", -1),
        "temperature_metadata_calls": calls.get("temperature_metadata", -1),
        "temperature_save_calls": calls.get("temperature_save", -1),
        "temperature_sampling_calls": calls.get("temperature_sampling", -1),
        "temperature_typed_read_calls": calls.get("temperature_typed_read", -1),
        "temperature_collector_calls": calls.get("temperature_collector", -1),
        "raw_classification": raw_classification,
        "process_exit_code": (runner or {}).get("process_exit_code"),
        "resource_pass": resource_pass,
        "cleanup_pass": temporary_cleanup["pass"] and process_cleanup.get("all_observed_absent", False),
        "residual_process_count": residual,
    }
    axes = classify_axes(evidence)
    if axes["classification"] == "normal_exit" and raw_classification != "normal_exit":
        axes["classification"] = raw_classification
        axes["continue_ladder"] = False
    summary = {
        "schema": "campfire.phase6hb.run-summary.v1", "sequence": sequence, "name": name,
        "mode": mode, "features": list(condition["features"]), "elapsed_seconds": elapsed,
        "classification": axes["classification"], "raw_classification": raw_classification,
        "failure_signature": signature, "guard_exit_code": guard_exit,
        "process_exit_code": (runner or {}).get("process_exit_code"),
        "last_operation_marker": markers.get("last_operation_marker"),
        "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
        "stage_close_seconds": markers.get("stage_close_seconds"),
        "operation_axis": {"complete": axes["operation_complete"], "report": operation},
        "lifecycle_axis": axes["lifecycle"], "safety_axis": axes["safety"],
        "peaks": {key: peaks.get(key) for key in ("kit", "tree", "runner", "diagnostic")},
        "machine_minima": minima, "temporary_cleanup": temporary_cleanup,
        "residual_process_count": residual, "end_utc": utc_now(),
    }
    atomic_json(run_root / "run_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=SCRIPT_DIR / "phase6hb_candidate_lifecycle_contract.json")
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HB refuses artifact root reuse: {output}")
    sha_path = contract_path.with_suffix(".sha256")
    expected = sha_path.read_text(encoding="utf-8").split()[0].upper()
    actual = sha256(contract_path)
    if expected != actual:
        raise RuntimeError("Phase 6HB contract SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ladder_check = validate_ladder([{"name": row["name"], "features": row["features"]} for row in LADDER])
    if not ladder_check["pass"]:
        raise RuntimeError(f"Phase 6HB ladder invalid: {ladder_check['reasons']}")
    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(sha_path, output / "frozen_contract.sha256")
    atomic_json(output / "fixed_sequence.json", {
        "schema": "campfire.phase6hb.fixed-sequence.v1",
        "conditions": [{"name": row["name"], "mode": row["mode"], "features": list(row["features"])} for row in LADDER],
        "retries": 0, "replacements": 0,
    })
    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "test_phase6hb_candidate_lifecycle.py")],
        cwd=REPO, capture_output=True, text=True,
    )
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        atomic_json(output / "phase6hb_summary.json", {
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
            atomic_json(output / "heartbeat.json", {
                "timestamp_utc": utc_now(), "completed_launches": len(rows),
                "last_condition": summary["name"], "last_classification": summary["classification"],
            })
            if summary["classification"] != "normal_exit":
                break
    first_failure = next((row for row in rows if row["classification"] != "normal_exit"), None)
    last_normal = next((row for row in reversed(rows) if row["classification"] == "normal_exit"), None)
    final = {
        "schema": "campfire.phase6hb.candidate-lifecycle-ladder-summary.v1",
        "status": "safe_stop" if first_failure else "bounded_ladder_complete",
        "contract_sha256": actual, "launches": len(rows), "maximum_launches": len(LADDER),
        "retries": 0, "replacements": 0, "last_natural_exit_condition": last_normal,
        "first_non_natural_exit_condition": first_failure,
        "first_boundary_difference": None if not first_failure else {
            "before": None if not last_normal else last_normal["name"],
            "after": first_failure["name"],
            "added_feature": next((row["adds"] for row in contract["ladder"] if row["name"] == first_failure["name"]), None),
        },
        "remaining_unseparated_if_all_normal": [
            "prohibited temperature schema-prefix conversion/metadata/save/typed-read",
            "interaction between prohibited temperature native work and velocity processing",
        ] if not first_failure else [],
        "temperature_conversion_failure_claimed": False,
        "formal_population_started": False, "production_changed": False, "runs": rows,
    }
    atomic_json(output / "phase6hb_summary.json", final)
    return 0 if not first_failure else 2


if __name__ == "__main__":
    raise SystemExit(main())
