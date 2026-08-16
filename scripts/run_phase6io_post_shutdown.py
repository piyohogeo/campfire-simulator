from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from phase6hl_guard_preflight import _read_bounded, build_guard_command
from phase6hm_process_role_fixture import _read_jsonl
from phase6hn_process_tree_topology import validate_trace_roles
from phase6ho_app_ready_environment import ROOT, write_json
from phase6ho_process_tree_topology import APP, KIT
from phase6in_post_shutdown_boundary import classify, read_json, read_jsonl, validate_markers, validate_operation, validate_runner
from phase6io_executable_identity import read_report, validate_path_identity_report
from run_phase6hz_import_smoke import hashes as invariant_hashes

SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6io_post_shutdown_contract.json"
SIDECAR = SCRIPTS / "phase6io_post_shutdown_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = SCRIPTS / "phase6in_resource_guard.py"
CASE = SCRIPTS / "run_phase6io_minimal_post_shutdown_case.ps1"
PROBE = SCRIPTS / "probe_phase6io_minimal_post_shutdown.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6IO runtime refuses root reuse")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8")); digest = sha(CONTRACT)
    preflight = _read_bounded(preflight_path)
    if preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest or SIDECAR.read_text(encoding="ascii").split()[0].upper() != digest:
        raise RuntimeError("Phase 6IO preflight or contract invalid")
    root.mkdir(parents=True); shutil.copy2(CONTRACT, root / "frozen_contract.json"); shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    attempt_id = "phase6io-post-shutdown-monitor-01"; attempt = root / "attempt-01"; logs = attempt / "runner-logs"; logs.mkdir(parents=True)
    paths = {
        "output": attempt / "operation_report.json", "lifecycle": attempt / "operation_report.json",
        "child_markers": attempt / "child_markers.jsonl", "parent_markers": attempt / "parent_markers.jsonl", "cleanup_markers": attempt / "cleanup_markers.jsonl",
        "path_identity": attempt / "path_identity_report.json", "runner_evidence": attempt / "runner_evidence.json",
        "kit_log": attempt / "kit.log", "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log", "child_stderr": logs / "powershell.stderr.log", "cleanup": logs / "cleanup.jsonl", "gpu": logs / "gpu.csv",
    }
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    expected_canonical = policy["path_identity"]["expected_canonical_path"]
    target = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE),
              "-KitPath", str(KIT), "-ExpectedCanonicalKitPath", expected_canonical, "-AppPath", str(APP), "-ProbePath", str(PROBE),
              "-ChildMarkersPath", str(paths["child_markers"]), "-ParentMarkersPath", str(paths["parent_markers"]), "-OperationReportPath", str(paths["output"]), "-PathIdentityReportPath", str(paths["path_identity"]), "-RunnerEvidencePath", str(paths["runner_evidence"]), "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]), "-AttemptId", attempt_id]
    write_json(attempt / "launch_contract.json", {"schema": "campfire.phase6io.launch.v1", "attempt_id": attempt_id, "target": target, "cwd": str(ROOT), "kit_launch_count": 1})
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    separator = command.index("--"); command[separator:separator] = ["--phase6in-cleanup-markers", str(paths["cleanup_markers"])]
    before = invariant_hashes()
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)); guard_exit = process.wait()
    after = invariant_hashes()
    operation = read_json(paths["output"]) if paths["output"].is_file() else {}
    runner = read_json(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {}
    path_envelope = read_report(paths["path_identity"]) if paths["path_identity"].is_file() else {}
    path_report = path_envelope.get("report") if isinstance(path_envelope, dict) else None
    path_validation = validate_path_identity_report(path_report, attempt_id=attempt_id) if isinstance(path_report, dict) else {"accepted": False, "reasons": ["path_identity_report_missing"]}
    if path_envelope.get("validation") != path_validation:
        path_validation = {"accepted": False, "reasons": ["path_identity_producer_consumer_conflict"]}
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}; trace = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    child_rows = read_jsonl(paths["child_markers"]) if paths["child_markers"].is_file() else []; parent_rows = read_jsonl(paths["parent_markers"]) if paths["parent_markers"].is_file() else []; cleanup_rows = read_jsonl(paths["cleanup_markers"]) if paths["cleanup_markers"].is_file() else []
    rows = parent_rows[:2] + child_rows + parent_rows[2:] + cleanup_rows
    identity = operation.get("process_identity") or {}
    if path_validation["accepted"]:
        identity = dict(identity); identity["executable_path"] = path_report["process_executable_file"]["canonical_path"]
    operation_validation = validate_operation(operation, attempt_id=attempt_id, helper_contract_sha256=policy["dependencies"]["phase6im_contract_sha256"]) if operation else {"accepted": False, "reasons": ["operation_missing"]}
    marker_validation = validate_markers(rows, attempt_id=attempt_id, identity=identity) if rows and identity else {"accepted": False, "reasons": ["markers_or_identity_missing"], "steps": []}
    runner_validation = validate_runner(runner, attempt_id=attempt_id, identity=identity) if runner and identity else {"accepted": False, "reasons": ["runner_or_identity_missing"]}
    cleanup = guard.get("observed_process_cleanup") or {}; cleanup_pass = cleanup.get("all_observed_absent") is True; killed = cleanup.get("killed") or []
    killed_paths = [str((item.get("identity") or {}).get("path") or "").lower() for item in killed if isinstance(item, dict)]
    killed_kit = any(path.endswith("\\kit.exe") for path in killed_paths)
    known_auxiliary = all(any(token in path for token in ("omni.telemetry.transmitter.exe", "nvngx_update.exe", "conhost.exe", "\\python\\python.exe")) for path in killed_paths) if killed_paths else False
    cleanup_assisted = bool(killed_paths) and known_auxiliary and not killed_kit
    peaks = guard.get("peaks") or {}; minima = guard.get("machine_minima") or {}; safety = policy["safety"]
    resource_pass = all((isinstance(peaks.get("runner"), int) and peaks["runner"] <= safety["runner_private_limit_bytes"], isinstance(peaks.get("kit"), int) and peaks["kit"] <= safety["kit_private_limit_bytes"], isinstance(peaks.get("diagnostic"), int) and peaks["diagnostic"] <= safety["diagnostic_private_limit_bytes"], isinstance(peaks.get("tree"), int) and peaks["tree"] <= safety["unique_tree_private_limit_bytes"], isinstance(minima.get("available_physical_bytes"), int) and minima["available_physical_bytes"] >= safety["available_physical_floor_bytes"], isinstance(minima.get("estimated_commit_headroom_bytes"), int) and minima["estimated_commit_headroom_bytes"] >= safety["commit_headroom_floor_bytes"]))
    roles_ok, role_failures, roles = validate_trace_roles(trace)
    monitor = runner.get("monitor") or {}; exit_code = monitor.get("exit_code")
    post_exception = (exit_code not in (None, 0)) or bool(runner.get("fatal_lines") or []) or bool(runner.get("dump_inventory") or []) or monitor.get("crash_reporter_observed") is True
    monitor_evidence_valid = runner_validation["accepted"] and marker_validation["accepted"]
    base_axes = classify(operation_valid=operation_validation["accepted"], monitor_valid=monitor_evidence_valid, identity_reuse=monitor.get("identity_reuse") is True, exit_observed=monitor.get("exit_observed") is True, exit_code=exit_code, exit_seconds=monitor.get("exit_observed_seconds"), post_shutdown_exception=post_exception, resource_pass=resource_pass and roles_ok, cleanup_pass=cleanup_pass, cleanup_assisted=cleanup_assisted)
    base_axes["path_identity"] = "qualified" if path_validation["accepted"] else "failed"
    if cleanup_pass and killed_kit:
        base_axes["cleanup"] = "failure"
    safety_pass = resource_pass and roles_ok and cleanup_pass and not (runner.get("automatic_upload_attempt_lines") or []) and before == after
    qualified = path_validation["accepted"] and operation_validation["accepted"] and monitor_evidence_valid and safety_pass
    status = "minimal_post_shutdown_monitor_qualified" if qualified else "safe_stop_phase6io_monitor_failure"
    comparison = "indeterminate"
    if base_axes["lifecycle"] in {"normal_exit", "delayed_exit"} and exit_code == 0 and not post_exception:
        comparison = "phase6ik_access_violation_not_reproduced_in_single_process"
    elif exit_code == 0xC0000005:
        comparison = "phase6ik_exit_code_matched_timing_comparison_required"
    result = {
        "schema": "campfire.phase6io.summary.v1", "phase": "phase6io", "status": status, "contract_sha256": digest,
        "attempt_id": attempt_id, "kit_launch_count": 1, "retry_count": 0, "replacement_count": 0,
        "phase6in_frozen": True, "phase6in_artifact_reused": False, "phase6im_helper_reused_unchanged": sha(SCRIPTS / "phase6im_process_identity.py") == policy["dependencies"]["phase6im_helper"]["sha256"],
        "path_identity_validation": path_validation, "path_identity_report": path_report, "axes": base_axes,
        "operation_validation": operation_validation, "marker_validation": marker_validation, "runner_validation": runner_validation,
        "samples": monitor.get("samples") or [], "last_marker": rows[-1].get("step_id") if rows else None,
        "kit_exit_code": exit_code, "guard_exit_code": guard_exit, "phase6ik_access_violation_comparison": comparison,
        "fatal_lines": runner.get("fatal_lines") or [], "dump_inventory": runner.get("dump_inventory") or [], "crash_reporter_observed": monitor.get("crash_reporter_observed") is True, "automatic_upload_attempt_lines": runner.get("automatic_upload_attempt_lines") or [], "cdb_attempted": False,
        "resource_peaks_bytes": peaks, "resource_minima_bytes": minima, "resource_headroom_bytes": {"kit": safety["kit_private_limit_bytes"] - peaks.get("kit", 0), "tree": safety["unique_tree_private_limit_bytes"] - peaks.get("tree", 0)},
        "cleanup_pass": cleanup_pass, "cleanup_assisted_known_auxiliary": cleanup_assisted, "cleanup_intervened_on_kit": killed_kit, "residual_process_count": 0 if cleanup_pass else None,
        "roles_pass": roles_ok, "role_failures": role_failures, "roles": roles,
        "abc_restart_ready": qualified and base_axes["lifecycle"] == "normal_exit" and base_axes["cleanup"] in {"natural", "assisted_known_auxiliary"},
        "abc_ladder_started": False, "four_boundary_audit_started": False, "collision_comparison_started": False,
        "invariant_hashes_before": before, "invariant_hashes_after": after, "invariants_pass": before == after,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-root", type=Path, required=True); parser.add_argument("--preflight-summary", type=Path, required=True); args = parser.parse_args()
    value = run(args.artifact_root.resolve(), args.preflight_summary.resolve()); raise SystemExit(0 if value["status"] == "minimal_post_shutdown_monitor_qualified" else 1)
