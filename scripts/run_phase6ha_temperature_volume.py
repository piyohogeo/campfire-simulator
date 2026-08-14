"""Phase 6HA single temperature conversion with one lifecycle-only replacement."""

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

from phase6ha_lifecycle_replacement_contract import classify_attempt, population_decision
from run_phase6gv_repetition import classify, existing_campfire_kit, marker_digest, read_json
from run_phase6gz_boundary_ladder import cleanup_temporary_files

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


def read_marker_names(path: Path) -> list[str]:
    names = []
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        marker = row.get("marker")
        if isinstance(marker, str):
            names.append(marker)
    return names


def build_command(attempt_id: str, root: Path, contract: dict) -> list[str]:
    case = root / "case"
    logs = root / "runner-logs"
    logs.mkdir(parents=True)
    safety = contract["safety"]
    inner = [
        str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
        str(SCRIPT_DIR / "run_phase6fo_supply_case.ps1"), "-Scenario", "production_four",
        "-OutputDir", str(case), "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05",
        "-Filtering", "true", "-Collision", "true", "-Policy", "allow_self_center",
        "-ReportPhase", "phase6ha", "-GeometryVariant", "phase6er_corrected",
        "-ExpectedGeometryConcept", "corrected", "-ProbePath", str(SCRIPT_DIR / "probe_phase6ha_temperature_volume.py"),
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "60,120,180,240", "-OperationFrames", "180", "-ReadbackFrames", "180",
        "-ReadbackChannels", "velocity,temperature,smoke,fuel", "-ReadbackMode", "p3_spatial_release",
        "-ReferenceDisposal", "del", "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", "0,1,2,3", "-SpatialAllChannels",
        "-RunIndex", "1", "-LifecycleCalibration", "-RendererDrainUpdates", "8",
        "-LifecycleReferenceReleaseOrder", "after_stage_close", "-StageCloseTimeoutSeconds", "180",
        "-StabilityObservationStartFrame", "240", "-StabilityObservationExtraSeconds", "5",
        "-StabilityActiveBlockSampleSeconds", "0.5", "-FlowLivenessAudit", "true", "-StartupProbe", "true",
        "-StartupProbeLabel", attempt_id, "-StartupFlowAcquirePosition", "before_updates",
        "-StartupPreTimelineUpdateCount", "12", "-StartupExtraUpdateBeforePlayCount", "0",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "1075.2",
        "-StartupExpectedTemperatureSum", "2688.0", "-StartupExpectedSmokeSum", "107.52",
        "-StartupSourceSumTolerance", "0.00001", "-StartupSourceContractMode", "payload_native_float32_v1",
        "-AbsoluteTimeoutSeconds", str(safety["inner_timeout_seconds"]),
        "-ImportAuditPath", str(case / "kit_import_audit.json"),
        "-PostReadbackIsolationMode", "R1", "-PostReadbackIsolationChannel", "temperature",
        "-PostReadbackIsolationReportPath", str(case / "post_readback_isolation.json"),
    ]
    return [sys.executable, str(SCRIPT_DIR / "phase6fu_resource_guard.py"),
        "--trace", str(logs / "resource.jsonl"), "--summary", str(logs / "guard.json"),
        "--stdout", str(logs / "stdout.log"), "--stderr", str(logs / "stderr.log"),
        "--timeout-seconds", str(safety["outer_timeout_seconds"]), "--sample-seconds", "0.25",
        "--runner-private-limit", str(safety["runner_private_limit_bytes"]),
        "--diagnostic-private-limit", str(safety["diagnostic_private_limit_bytes"]),
        "--kit-private-limit", str(safety["kit_private_limit_bytes"]),
        "--tree-private-limit", str(safety["unique_tree_private_limit_bytes"]),
        "--available-memory-floor", str(safety["available_physical_floor_bytes"]),
        "--commit-headroom-floor", str(safety["commit_headroom_floor_bytes"]),
        "--cpu-telemetry", "--gpu-csv", str(logs / "gpu.csv"), "--gpu-sample-ms", "1000",
        "--lifecycle-path", str(case / "raw.json"), "--diagnostic-marker-path", str(case / "resource_markers.jsonl"),
        "--attempt-id", attempt_id, "--cleanup-suppression-lock", str(case / "sensitive-shutdown-diagnostics.ownership.json"),
        "--cleanup-suppression-deadline-seconds", "150", "--cleanup-marker-path", str(logs / "cleanup_markers.jsonl"),
        "--", *inner]


def run_attempt(index: int, output: Path, contract: dict) -> dict:
    attempt_id = "original" if index == 1 else "replacement01"
    if existing_campfire_kit():
        raise RuntimeError("Kit already existed before Phase 6HA independent attempt")
    root = output / "attempts" / attempt_id
    root.mkdir(parents=True)
    command = build_command(attempt_id, root, contract)
    atomic_json(root / "attempt.json", {"schema": "campfire.phase6ha.attempt.v1", "attempt_index": index,
                "attempt_id": attempt_id, "replacement": index > 1, "command": command, "start_utc": utc_now()})
    started = time.monotonic()
    guard_exit = subprocess.run(command, cwd=REPO).returncode
    elapsed = time.monotonic() - started
    case, logs = root / "case", root / "runner-logs"
    guard = read_json(logs / "guard.json")
    runner = read_json(case / "runner_evidence.json")
    raw = read_json(case / "raw.json")
    operation = read_json(case / "post_readback_isolation.json")
    markers = marker_digest(case / "resource_markers.jsonl")
    marker_names = read_marker_names(case / "resource_markers.jsonl")
    stderr_path = logs / "stderr.log"
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-4096:] if stderr_path.exists() else ""
    raw_classification, signature = classify(guard, runner, raw, markers, guard_exit, stderr_text)
    temporary_cleanup = cleanup_temporary_files(root)
    observed_cleanup = (guard or {}).get("observed_process_cleanup") or {}
    safety = contract["safety"]
    peaks = (guard or {}).get("peaks") or {}
    minima = (guard or {}).get("machine_minima") or {}
    resource_pass = bool(guard and peaks.get("kit", safety["kit_private_limit_bytes"] + 1) <= safety["kit_private_limit_bytes"]
        and peaks.get("tree", safety["unique_tree_private_limit_bytes"] + 1) <= safety["unique_tree_private_limit_bytes"]
        and peaks.get("runner", safety["runner_private_limit_bytes"] + 1) <= safety["runner_private_limit_bytes"]
        and peaks.get("diagnostic", safety["diagnostic_private_limit_bytes"] + 1) <= safety["diagnostic_private_limit_bytes"]
        and minima.get("available_physical_bytes", 0) >= safety["available_physical_floor_bytes"]
        and minima.get("estimated_commit_headroom_bytes", 0) >= safety["commit_headroom_floor_bytes"])
    process_cleanup_pass = bool(observed_cleanup.get("all_observed_absent", False))
    evidence = {
        "markers": marker_names,
        "operation_result": (operation or {}).get("operation_result"),
        "temperature_conversion_calls": (operation or {}).get("temperature_buffer_to_volume_calls", -1),
        "forbidden_content_access_calls": (operation or {}).get("forbidden_content_access_calls", -1),
        "resource_pass": resource_pass,
        "temporary_cleanup_pass": temporary_cleanup["pass"],
        "process_cleanup_pass": process_cleanup_pass,
        "residual_process_count": 0 if process_cleanup_pass else -1,
        "python_exception": bool(operation and operation.get("error_type")),
        "native_exception": raw_classification == "windows_native_exception",
        "cleanup_failure": raw_classification == "cleanup_failure" or not temporary_cleanup["pass"],
        "natural_os_exit": raw_classification == "normal_exit",
        "process_exit_code": (runner or {}).get("process_exit_code"),
        "raw_classification": raw_classification,
        "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
    }
    replacement = classify_attempt(evidence)
    summary = {"schema": "campfire.phase6ha.attempt-summary.v1", "attempt_index": index,
        "attempt_id": attempt_id, "replacement": index > 1, "elapsed_seconds": elapsed,
        "raw_classification": raw_classification, "failure_signature": signature,
        "replacement_classification": replacement, "operation": operation,
        "last_operation_marker": (operation or {}).get("last_operation_marker") or markers.get("last_operation_marker"),
        "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
        "process_exit_code": (runner or {}).get("process_exit_code"), "guard_exit_code": guard_exit,
        "stage_close_seconds": markers.get("stage_close_seconds"), "peaks": peaks, "machine_minima": minima,
        "resource_pass": resource_pass, "temporary_cleanup": temporary_cleanup,
        "process_cleanup_pass": process_cleanup_pass, "residual_process_count": evidence["residual_process_count"],
        "end_utc": utc_now()}
    atomic_json(root / "attempt_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=SCRIPT_DIR / "phase6ha_temperature_volume_contract.json")
    args = parser.parse_args()
    output, contract_path = args.output.resolve(), args.contract.resolve()
    if output.exists():
        raise RuntimeError(f"Phase 6HA refuses artifact root reuse: {output}")
    hash_path = contract_path.with_suffix(".sha256")
    expected = hash_path.read_text(encoding="utf-8").split()[0].upper()
    actual = sha256(contract_path)
    if actual != expected:
        raise RuntimeError("Phase 6HA contract hash mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    shutil.copy2(hash_path, output / "frozen_contract.sha256")
    preflight = output / "preflight"
    preflight.mkdir()
    fixture = subprocess.run([sys.executable, str(SCRIPT_DIR / "test_phase6ha_lifecycle_replacement.py")],
                             cwd=REPO, capture_output=True, text=True)
    (preflight / "fixture.stdout.log").write_text(fixture.stdout, encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr, encoding="utf-8")
    if fixture.returncode:
        atomic_json(output / "phase6ha_summary.json", {"status": "preflight_safe_stop", "fixture_exit": fixture.returncode})
        return 2
    production = REPO / "_build/windows-x86_64/release/apps/campfire.simulator.kit"
    demo = REPO / "docs/devlog/assets/latest_demo.json"
    before = {"production": sha256(production), "latest_demo": sha256(demo)}
    attempts = []
    classifications = []
    while len(attempts) < 2:
        summary = run_attempt(len(attempts) + 1, output, contract)
        attempts.append(summary)
        classifications.append(summary["replacement_classification"])
        decision = population_decision(classifications, replacement_budget=1)
        atomic_json(output / "incremental_state.json", {"schema": "campfire.phase6ha.incremental-state.v1",
                    "attempts_completed": len(attempts), "decision": decision, "timestamp_utc": utc_now()})
        if decision["action"] != "launch_single_replacement":
            break
    decision = population_decision(classifications, replacement_budget=1)
    final = {"schema": "campfire.phase6ha.temperature-volume-summary.v1",
        "status": "qualified" if decision["qualified"] else "safe_stop", "contract_sha256": actual,
        "attempt_count": len(attempts), "replacement_count": max(0, len(attempts) - 1),
        "replacement_budget": 1, "decision": decision, "attempts": attempts,
        "phase6gz_frozen": True, "phase6gz_reclassified": False, "phase6gz_runtime_sample_reused": False,
        "temperature_metadata_started": False, "temperature_save_started": False,
        "temperature_sampling_started": False, "formal_population_started": False,
        "production_sha256_before": before["production"], "production_sha256_after": sha256(production),
        "latest_demo_sha256_before": before["latest_demo"], "latest_demo_sha256_after": sha256(demo)}
    atomic_json(output / "phase6ha_summary.json", final)
    return 0 if decision["qualified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
