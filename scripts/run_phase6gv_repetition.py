"""Bounded sequential A/B repetition runner. Reads only compact evidence during execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psutil


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(encoded) > 262144:
        raise RuntimeError(f"compact JSON exceeded 256 KiB: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def existing_campfire_kit() -> list[dict]:
    found = []
    for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
            if name in {"kit.exe", "campfire.simulator.exe"} or ("campfire" in exe and exe.endswith("kit.exe")):
                found.append({"pid": proc.pid, "name": name, "exe": exe, "create_time": proc.info.get("create_time")})
        except (psutil.Error, OSError):
            continue
    return found


def marker_digest(path: Path) -> dict:
    last_operation = None
    last_lifecycle = None
    active = []
    counts = Counter()
    before_close = None
    close_seconds = None
    if not path.exists():
        return {"last_operation_marker": None, "last_lifecycle_marker": None, "counts": {}, "active_blocks": {}}
    lifecycle_prefixes = ("timeline_", "renderer_", "stage_close_", "usd_context_", "post_close_", "app_close_", "shutdown_")
    operation_tokens = ("readback", "volume", "metadata", "channel", "sample", "spatial", "schema", "alias", "release")
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if len(line) > 1024 * 1024:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            marker = str(row.get("marker", ""))
            counts[marker] += 1
            if any(token in marker for token in operation_tokens):
                last_operation = marker
            if marker.startswith(lifecycle_prefixes):
                last_lifecycle = marker
            value = row.get("active_blocks")
            if isinstance(value, int):
                active.append(value)
            if marker == "stage_close_request_before":
                before_close = row.get("perf_counter_ns")
            if marker == "stage_close_complete" and isinstance(before_close, int) and isinstance(row.get("perf_counter_ns"), int):
                close_seconds = (row["perf_counter_ns"] - before_close) / 1e9
    return {
        "last_operation_marker": last_operation, "last_lifecycle_marker": last_lifecycle,
        "counts": dict(counts),
        "active_blocks": {"minimum": min(active) if active else None, "maximum": max(active) if active else None},
        "stage_close_seconds": close_seconds,
    }


def classify(guard: dict | None, runner: dict | None, raw: dict | None, markers: dict, guard_exit: int,
             stderr_text: str = "") -> tuple[str, str]:
    if guard:
        stop = str(guard.get("stop_reason") or "").lower()
        if any(token in stop for token in ("private", "memory", "commit", "resource", "disk")):
            return "resource_limit", stop or "resource_limit"
        cleanup = guard.get("observed_process_cleanup") or {}
        if cleanup and not cleanup.get("all_observed_absent", False):
            return "cleanup_failure", "observed_process_cleanup_not_absent"
    exit_code = (runner or {}).get("process_exit_code")
    bounded_error = (stderr_text or "")[-4096:]
    if not runner and any(token in bounded_error.lower() for token in
                          ("refuses output reuse", "parameterbinding", "cannot bind parameter", "traceback", "importerror", "typeerror")):
        boundary = "pre_kit_output_root_reuse" if "refuses output reuse" in bounded_error.lower() else "pre_kit_harness"
        return "python_or_harness_failure", boundary
    if exit_code in (3221225477, -1073741819):
        return "windows_native_exception", f"0x{int(exit_code) & 0xffffffff:08X}:{markers.get('last_operation_marker')}"
    shutdown = (runner or {}).get("shutdown_monitor") or {}
    outcome = (runner or {}).get("outcome") or {}
    last_lifecycle = str(shutdown.get("last_lifecycle_marker") or markers.get("last_lifecycle_marker") or "")
    if "stage_close_timeout" in last_lifecycle or any("stage_close" in str(x) and "timeout" in str(x) for x in outcome.get("reasons", [])):
        return "stage_close_timeout", last_lifecycle or "stage_close_timeout"
    if shutdown.get("absolute_timeout") or (exit_code is None and guard_exit != 0):
        return "os_exit_timeout", last_lifecycle or "outer_timeout"
    status_text = " ".join(str(x) for x in ((raw or {}).get("failures") or [])) + " " + str((raw or {}).get("error") or "")
    if "startup" in status_text.lower() and ("prerequisite" in status_text.lower() or "liveness" in status_text.lower()):
        return "startup_prerequisite_not_met", markers.get("last_operation_marker") or "startup"
    if outcome.get("lifecycle_status") == "normal_exit" and outcome.get("normal_exit_sample_accepted") and exit_code == 0 and guard_exit == 0:
        return "normal_exit", "normal_exit"
    if any(token in status_text.lower() for token in ("reserved marker", "traceback", "typeerror", "importerror", "module")):
        return "python_or_harness_failure", (markers.get("last_operation_marker") or status_text[-160:] or "python_failure")
    if exit_code not in (None, 0) or (raw and raw.get("status") in {"failed", "safe_stop"}):
        return "operation_failure", markers.get("last_operation_marker") or f"exit_{exit_code}"
    return "unknown_failure", markers.get("last_operation_marker") or last_lifecycle or "unknown"


def command_for(condition: str, root: Path, attempt_id: str, contract: dict) -> tuple[list[str], dict]:
    case = root / "case"
    logs = root / "runner-logs"
    logs.mkdir(parents=True)
    is_a = condition == "A"
    phase = "phase6gs" if is_a else "phase6gn"
    probe = SCRIPT_DIR / ("probe_phase6gs_volume_metadata.py" if is_a else "probe_phase6gn_supply_comparison.py")
    sample_frames = "60,120,180,240" if is_a else "60,120,180,360,540,600"
    operation_frames = "180" if is_a else "180,360,540"
    inner = [
        str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT_DIR / "run_phase6fo_supply_case.ps1"),
        "-Scenario", "production_four", "-OutputDir", str(case), "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05",
        "-Filtering", "true", "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", phase,
        "-GeometryVariant", "phase6er_corrected", "-ExpectedGeometryConcept", "corrected", "-ProbePath", str(probe),
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1", "-SampleFrames", sample_frames,
        "-OperationFrames", operation_frames, "-ReadbackFrames", operation_frames,
        "-ReadbackChannels", "velocity,temperature,smoke,fuel", "-ReadbackMode", "p3_spatial_release",
        "-ReferenceDisposal", "del", "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", ("0" if is_a else "0,1,2,3"), "-SpatialAllChannels",
        "-RunIndex", "1", "-LifecycleCalibration", "-RendererDrainUpdates", "8", "-LifecycleReferenceReleaseOrder", "after_stage_close",
        "-StageCloseTimeoutSeconds", "180", "-StabilityObservationStartFrame", ("240" if is_a else "600"),
        "-StabilityObservationExtraSeconds", "5", "-StabilityActiveBlockSampleSeconds", "0.5", "-FlowLivenessAudit", "true",
        "-StartupProbe", "true", "-StartupProbeLabel", attempt_id, "-StartupFlowAcquirePosition", "before_updates",
        "-StartupPreTimelineUpdateCount", "12", "-StartupExtraUpdateBeforePlayCount", "0", "-StartupLivenessGate", "true",
        "-StartupExpectedFuelSum", "1075.2", "-StartupExpectedTemperatureSum", "2688.0", "-StartupExpectedSmokeSum", "107.52",
        "-StartupSourceSumTolerance", "0.00001", "-StartupSourceContractMode", "payload_native_float32_v1",
        "-AbsoluteTimeoutSeconds", "900", "-ImportAuditPath", str(case / "kit_import_audit.json")
    ]
    if is_a:
        inner += ["-PostReadbackIsolationMode", "R2", "-PostReadbackIsolationChannel", "temperature",
                  "-PostReadbackIsolationReportPath", str(case / "post_readback_isolation.json"), "-SkipLowLevelShutdownDiagnostic"]
    else:
        inner += ["-MeasurementCommitAck", str(case / "memory-measurement/measurement_commit.ack"),
                  "-MeasurementCommitFailure", str(case / "memory-measurement/measurement_commit.failed"),
                  "-MeasurementCommitTimeoutSeconds", "90"]
    safety = contract["safety"]
    guard = [sys.executable, str(SCRIPT_DIR / "phase6fu_resource_guard.py"),
        "--trace", str(logs / "resource.jsonl"), "--summary", str(logs / "guard.json"),
        "--stdout", str(logs / "stdout.log"), "--stderr", str(logs / "stderr.log"),
        "--timeout-seconds", str(safety["outer_timeout_seconds"]), "--sample-seconds", "0.25",
        "--runner-private-limit", str(safety["runner_private_limit_bytes"]), "--diagnostic-private-limit", str(safety["diagnostic_private_limit_bytes"]),
        "--kit-private-limit", str(safety["kit_private_limit_bytes"]), "--tree-private-limit", str(safety["unique_tree_private_limit_bytes"]),
        "--available-memory-floor", str(safety["available_physical_floor_bytes"]), "--commit-headroom-floor", str(safety["commit_headroom_floor_bytes"]),
        "--cpu-telemetry", "--gpu-csv", str(logs / "gpu.csv"), "--gpu-sample-ms", "1000",
        "--lifecycle-path", str(case / "raw.json"), "--diagnostic-marker-path", str(case / "resource_markers.jsonl"),
        "--attempt-id", attempt_id, "--cleanup-suppression-lock", str(case / "sensitive-shutdown-diagnostics.ownership.json"),
        "--cleanup-suppression-deadline-seconds", "150", "--cleanup-marker-path", str(logs / "cleanup_markers.jsonl"), "--"] + inner
    meta = {"case": case, "logs": logs, "is_a": is_a, "inner": inner}
    return guard, meta


def run_one(condition: str, sequence: int, output: Path, contract: dict) -> dict:
    attempt_id = f"launch{sequence:02d}_{condition}"
    root = output / "runs" / attempt_id
    root.mkdir(parents=True)
    command, meta = command_for(condition, root, attempt_id, contract)
    atomic_json(root / "attempt.json", {"schema": "campfire.phase6gv.attempt.v1", "sequence": sequence,
        "phase": contract.get("phase", "phase6gv"), "condition": condition, "attempt_id": attempt_id,
        "start_utc": utc_now(), "command": command})
    started_utc, started = utc_now(), time.monotonic()
    committer = None
    guard = subprocess.Popen(command, cwd=REPO)
    if not meta["is_a"]:
        committer_command = [sys.executable, str(SCRIPT_DIR / "phase6fz_preclose_committer.py"),
            "--raw-path", str(meta["case"] / "raw.json"), "--resource-path", str(meta["logs"] / "resource.jsonl"),
            "--gpu-path", str(meta["logs"] / "gpu.csv"), "--marker-path", str(meta["case"] / "resource_markers.jsonl"),
            "--attempt-metadata", str(root / "attempt.json"), "--contract", str(output / "frozen_contract.json"),
            "--output-dir", str(meta["case"] / "memory-measurement"), "--stop-file", str(root / "committer.stop"),
            "--timeout-seconds", "960", "--private-limit-bytes", "536870912"]
        committer = subprocess.Popen(committer_command, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    guard_exit = guard.wait()
    (root / "committer.stop").write_text("guard-exited\n", encoding="utf-8")
    if committer:
        try:
            committer.wait(timeout=15)
        except subprocess.TimeoutExpired:
            committer.terminate()
            committer.wait(timeout=5)
    elapsed = time.monotonic() - started
    guard_report = read_json(meta["logs"] / "guard.json")
    runner = read_json(meta["case"] / "runner_evidence.json")
    raw = read_json(meta["case"] / "raw.json")
    operation = read_json(meta["case"] / "post_readback_isolation.json") if meta["is_a"] else None
    markers = marker_digest(meta["case"] / "resource_markers.jsonl")
    stderr_path = meta["logs"] / "stderr.log"
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-4096:] if stderr_path.exists() else ""
    classification, signature = classify(guard_report, runner, raw, markers, guard_exit, stderr_text)
    peaks = (guard_report or {}).get("peaks") or {}
    cleanup = (guard_report or {}).get("observed_process_cleanup") or {}
    temporary = list(root.rglob("*.nvdb"))
    counts = markers.get("counts", {})
    summary = {
        "schema": "campfire.phase6gv.run-summary.v1", "sequence": sequence, "condition": condition,
        "phase": contract.get("phase", "phase6gv"),
        "attempt_id": attempt_id, "start_utc": started_utc, "end_utc": utc_now(), "elapsed_seconds": elapsed,
        "classification": classification, "failure_signature": signature,
        "representative": classification != "startup_prerequisite_not_met",
        "last_operation_marker": markers.get("last_operation_marker"), "last_lifecycle_marker": markers.get("last_lifecycle_marker"),
        "process_exit_code": (runner or {}).get("process_exit_code"), "stage_close_seconds": markers.get("stage_close_seconds"),
        "peaks": {key: peaks.get(key) for key in ("kit", "tree", "runner", "diagnostic")},
        "active_blocks": markers.get("active_blocks"),
        "calls": {"readback": sum(v for k,v in counts.items() if "readback_call_before" in k or k.endswith("readback_before")),
                  "conversion": sum(v for k,v in counts.items() if "volume_conversion_before" in k or "buffer_to_volume_before" in k),
                  "metadata": sum(v for k,v in counts.items() if "metadata" in k and k.endswith("before")),
                  "save": sum(v for k,v in counts.items() if "save_volume_before" in k),
                  "sampling": sum(v for k,v in counts.items() if "sampling_before" in k)},
        "temporary_files_remaining": len(temporary),
        "residual_process_count": 0 if cleanup.get("all_observed_absent") else None,
        "guard_exit_code": guard_exit, "guard_stop_reason": (guard_report or {}).get("stop_reason"),
        "operation_status": (operation or {}).get("operation_result") if operation else (raw or {}).get("status"),
    }
    atomic_json(root / "run_summary.json", summary)
    return summary


def wilson(failures: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = failures / total
    denom = 1 + z*z/total
    center = (p + z*z/(2*total))/denom
    radius = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denom
    return [max(0.0, center-radius), min(1.0, center+radius)]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    pos = (len(values)-1)*q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] if lo == hi else values[lo]*(hi-pos)+values[hi]*(pos-lo)


def aggregate(rows: list[dict], started: float, stop_reason: str, phase: str = "phase6gv") -> dict:
    conditions = {}
    for condition in ("A", "B"):
        selected = [row for row in rows if row["condition"] == condition]
        representative = [row for row in selected if row["representative"]]
        failures = [row for row in representative if row["classification"] != "normal_exit"]
        stage = [row["stage_close_seconds"] for row in representative if isinstance(row.get("stage_close_seconds"), (int,float))]
        kit = [row["peaks"].get("kit") for row in representative if isinstance(row["peaks"].get("kit"), (int,float))]
        tree = [row["peaks"].get("tree") for row in representative if isinstance(row["peaks"].get("tree"), (int,float))]
        conditions[condition] = {
            "launches": len(selected), "representative_runs": len(representative),
            "normal_exits": sum(row["classification"] == "normal_exit" for row in representative),
            "classifications": dict(Counter(row["classification"] for row in selected)),
            "observed_failure_rate": len(failures)/len(representative) if representative else None,
            "wilson_95": wilson(len(failures), len(representative)),
            "rule_of_three_upper": 3/len(representative) if representative and not failures else None,
            "time_to_first_failure_seconds": next((row["elapsed_from_population_start_seconds"] for row in selected if row["classification"] != "normal_exit"), None),
            "same_marker_boundary_counts": dict(Counter(row.get("failure_signature") for row in failures)),
            "stage_close_seconds": {"median": percentile(stage,.5), "p95": percentile(stage,.95), "maximum": max(stage) if stage else None},
            "kit_peak_bytes": {"median": percentile(kit,.5), "p95": percentile(kit,.95), "maximum": max(kit) if kit else None},
            "tree_peak_bytes": {"median": percentile(tree,.5), "p95": percentile(tree,.95), "maximum": max(tree) if tree else None},
        }
    a, b = conditions["A"], conditions["B"]
    if any(row["classification"] in {"python_or_harness_failure","resource_limit","cleanup_failure","unknown_failure"} for row in rows):
        conclusion = "inconclusive due to harness or safety stop"
    elif b["representative_runs"] and b["normal_exits"] == 0 and len(b["same_marker_boundary_counts"]) == 1:
        conclusion = "deterministic-like reproduction"
    elif b["normal_exits"] and b["normal_exits"] < b["representative_runs"]:
        conclusion = "stochastic or state-dependent reproduction observed"
    elif b["representative_runs"] and b["normal_exits"] == b["representative_runs"]:
        conclusion = "no failure observed within this population"
    else:
        conclusion = "inconclusive due to harness or safety stop"
    return {"schema":"campfire.phase6gv.aggregate-report.v1", "phase":phase, "generated_utc":utc_now(),
            "elapsed_seconds":time.monotonic()-started, "stop_reason":stop_reason,
            "total_launches":len(rows), "conditions":conditions, "conclusion":conclusion}


def bound_repeated_failure_artifacts(run_root: Path, first_sequence: int) -> None:
    """Keep compact evidence; remove only large files inside this later repeated-failure run."""
    run_root = run_root.resolve()
    manifest = []
    keep_names = {"run_summary.json", "attempt.json", "guard.json", "runner_evidence.json", "raw.json",
                  "resource_markers.jsonl", "cleanup_markers.jsonl"}
    for path in sorted(run_root.rglob("*")):
        if not path.is_file() or path.name in keep_names:
            continue
        resolved = path.resolve()
        if run_root not in resolved.parents:
            raise RuntimeError("artifact bounding target escaped run root")
        size = resolved.stat().st_size
        if size <= 2 * 1024 * 1024:
            continue
        manifest.append({"relative_path": str(resolved.relative_to(run_root)), "bytes": size,
                         "retained_in_first_matching_sequence": first_sequence})
        resolved.unlink()
    atomic_json(run_root / "bounded_artifact_manifest.json", {
        "schema":"campfire.phase6gv.bounded-artifact-manifest.v1",
        "first_matching_sequence":first_sequence, "removed_large_files":manifest})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--contract", default=str(SCRIPT_DIR / "phase6gv_repetition_contract.json"))
    args = parser.parse_args()
    output = Path(args.output_root).resolve()
    contract_path = Path(args.contract).resolve()
    if output.exists():
        raise SystemExit(f"artifact root reuse refused: {output}")
    contract = read_json(contract_path)
    if not contract:
        raise SystemExit("contract unreadable")
    sidecar = contract_path.with_suffix(".sha256")
    expected_hash = sidecar.read_text(encoding="ascii").split()[0].upper()
    actual_hash = sha256(contract_path)
    if actual_hash != expected_hash:
        raise SystemExit("Phase 6GV contract hash mismatch")
    output.mkdir(parents=True)
    shutil.copy2(contract_path, output / "frozen_contract.json")
    (output / "frozen_contract.sha256").write_text(f"{actual_hash}  frozen_contract.json\n", encoding="ascii")
    preflight = output / "preflight"
    fixture_report = preflight / "runtime_contract_fixture.json"
    fixture_env = dict(os.environ)
    fixture_env["PHASE6GV_FIXTURE_REPORT"] = str(fixture_report)
    fixture = subprocess.run([sys.executable, str(SCRIPT_DIR / "test_phase6gv_runtime_contract.py")],
                             cwd=REPO, env=fixture_env, capture_output=True, text=True, timeout=120)
    preflight.mkdir(parents=True, exist_ok=True)
    (preflight / "fixture.stdout.log").write_text(fixture.stdout[-65536:], encoding="utf-8")
    (preflight / "fixture.stderr.log").write_text(fixture.stderr[-65536:], encoding="utf-8")
    fixture_value = read_json(fixture_report)
    if fixture.returncode != 0 or not fixture_value or not fixture_value.get("passed") or fixture_value.get("kit_started"):
        atomic_json(output / "heartbeat.json", {"schema":"campfire.phase6gv.heartbeat.v1", "status":"terminal",
                    "stop_reason":"no_kit_fixture_failure", "updated_utc":utc_now()})
        raise SystemExit("Phase 6GV no-Kit fixture failed; Kit was not launched")
    runner_fixture_env = dict(os.environ)
    runner_fixture_env["PHASE6GV_RUNNER_FIXTURE_CONTRACT"] = str(contract_path)
    runner_fixture = subprocess.run([sys.executable, str(SCRIPT_DIR / "test_phase6gv_repetition_runner.py")],
                                    cwd=REPO, env=runner_fixture_env, capture_output=True, text=True, timeout=120)
    (preflight / "runner_fixture.stdout.log").write_text(runner_fixture.stdout[-65536:], encoding="utf-8")
    (preflight / "runner_fixture.stderr.log").write_text(runner_fixture.stderr[-65536:], encoding="utf-8")
    try:
        runner_fixture_value = json.loads(runner_fixture.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        runner_fixture_value = None
    if runner_fixture.returncode != 0 or not runner_fixture_value or not runner_fixture_value.get("passed"):
        atomic_json(output / "heartbeat.json", {"schema":"campfire.phase6gv.heartbeat.v1", "status":"terminal",
                    "stop_reason":"runner_fixture_failure", "updated_utc":utc_now()})
        raise SystemExit("Phase 6GV runner fixture failed; Kit was not launched")
    sequence = [item for _ in range(contract["population"]["pattern_repetitions"]) for item in contract["population"]["fixed_order_pattern"]]
    atomic_json(output / "fixed_sequence.json", {"schema":"campfire.phase6gv.fixed-sequence.v1", "generated_before_runtime":True,
        "phase":contract.get("phase", "phase6gv"), "order":sequence, "maximum_launches":len(sequence)})
    aggregate_path = output / "aggregate.jsonl"
    rows, started = [], time.monotonic()
    first_failure_signature: dict[tuple[str, str], int] = {}
    stop_reason = "maximum_launches"
    for index, condition in enumerate(sequence, 1):
        elapsed = time.monotonic()-started
        if elapsed >= contract["population"]["maximum_elapsed_seconds"]:
            stop_reason = "maximum_elapsed_seconds"; break
        if shutil.disk_usage(output).free < contract["safety"]["minimum_free_disk_bytes"]:
            stop_reason = "disk_pressure"; break
        residual = existing_campfire_kit()
        if residual:
            stop_reason = "cleanup_failure"; break
        row = run_one(condition, index, output, contract)
        row["elapsed_from_population_start_seconds"] = time.monotonic()-started
        if row["classification"] != "normal_exit":
            signature_key = (row["classification"], row["failure_signature"])
            first = first_failure_signature.get(signature_key)
            if first is None:
                first_failure_signature[signature_key] = index
            else:
                bound_repeated_failure_artifacts(output / "runs" / row["attempt_id"], first)
                row["full_artifact_retained"] = False
                row["representative_artifact_sequence"] = first
        with aggregate_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, separators=(",",":"), allow_nan=False)+"\n"); stream.flush(); os.fsync(stream.fileno())
        rows.append(row)
        report = aggregate(rows, started, "running", contract.get("phase", "phase6gv"))
        atomic_json(output / "heartbeat.json", {"schema":"campfire.phase6gv.heartbeat.v1", "status":"running",
            "last_sequence":index, "last_condition":condition, "last_classification":row["classification"],
            "elapsed_seconds":row["elapsed_from_population_start_seconds"], "updated_utc":utc_now(),
            "counts":{key:value["classifications"] for key,value in report["conditions"].items()}})
        if row["classification"] in contract["safety"]["stop_population_on"]:
            stop_reason = row["classification"]; break
        needed = contract["population"]["early_stop"]["same_signature_and_boundary_consecutive_count"]
        if len(rows) >= needed:
            tail = rows[-needed:]
            if all(x["classification"] == "python_or_harness_failure" for x in tail) and len({x["failure_signature"] for x in tail}) == 1:
                stop_reason = "five_consecutive_deterministic_harness_failures"; break
    final = aggregate(rows, started, stop_reason, contract.get("phase", "phase6gv"))
    atomic_json(output / "aggregate_report.json", final)
    atomic_json(output / "heartbeat.json", {"schema":"campfire.phase6gv.heartbeat.v1", "status":"terminal",
        "stop_reason":stop_reason, "launches":len(rows), "elapsed_seconds":final["elapsed_seconds"], "updated_utc":utc_now()})
    return 0 if stop_reason in {"maximum_launches","maximum_elapsed_seconds"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
