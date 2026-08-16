from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from phase6hl_guard_preflight import _read_bounded, build_guard_command
from phase6hm_process_role_fixture import _read_jsonl
from phase6hn_process_tree_topology import validate_trace_roles
from phase6ho_app_ready_environment import ROOT, write_json
from phase6ho_process_tree_topology import APP, KIT
from phase6in_post_shutdown_boundary import classify, read_json, read_jsonl, validate_markers, validate_operation, validate_runner
from run_phase6hz_import_smoke import hashes as invariant_hashes

SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6in_post_shutdown_contract.json"
SIDECAR = SCRIPTS / "phase6in_post_shutdown_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = SCRIPTS / "phase6in_resource_guard.py"
CASE = SCRIPTS / "run_phase6in_minimal_post_shutdown_case.ps1"
PROBE = SCRIPTS / "probe_phase6in_minimal_post_shutdown.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6IN runtime refuses root reuse")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = sha(CONTRACT)
    preflight = _read_bounded(preflight_path)
    if preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest or SIDECAR.read_text(encoding="ascii").split()[0].upper() != digest:
        raise RuntimeError("Phase 6IN preflight or contract invalid")
    root.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json");shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    attempt_id = "phase6in-post-shutdown-monitor-01"
    attempt = root / "attempt-01";logs = attempt / "runner-logs";logs.mkdir(parents=True)
    paths = {
        "output": attempt / "operation_report.json", "lifecycle": attempt / "operation_report.json",
        "child_markers": attempt / "child_markers.jsonl", "parent_markers": attempt / "parent_markers.jsonl",
        "cleanup_markers": attempt / "cleanup_markers.jsonl", "runner_evidence": attempt / "runner_evidence.json",
        "kit_log": attempt / "kit.log", "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log",
        "child_stderr": logs / "powershell.stderr.log", "cleanup": logs / "cleanup.jsonl", "gpu": logs / "gpu.csv",
    }
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    target = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE),
              "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE),
              "-ChildMarkersPath", str(paths["child_markers"]), "-ParentMarkersPath", str(paths["parent_markers"]),
              "-OperationReportPath", str(paths["output"]), "-RunnerEvidencePath", str(paths["runner_evidence"]),
              "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]),
              "-KitStderrPath", str(paths["kit_stderr"]), "-AttemptId", attempt_id]
    write_json(attempt / "launch_contract.json", {"schema": "campfire.phase6in.launch.v1", "attempt_id": attempt_id, "target": target, "cwd": str(ROOT), "kit_launch_count": 1})
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    separator = command.index("--")
    command[separator:separator] = ["--phase6in-cleanup-markers", str(paths["cleanup_markers"])]
    before = invariant_hashes()
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    after = invariant_hashes()
    operation = read_json(paths["output"]) if paths["output"].is_file() else {}
    runner = read_json(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {}
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}
    trace = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    child_rows = read_jsonl(paths["child_markers"]) if paths["child_markers"].is_file() else []
    parent_rows = read_jsonl(paths["parent_markers"]) if paths["parent_markers"].is_file() else []
    cleanup_rows = read_jsonl(paths["cleanup_markers"]) if paths["cleanup_markers"].is_file() else []
    rows = parent_rows[:2] + child_rows + parent_rows[2:] + cleanup_rows
    identity = operation.get("process_identity") or {}
    operation_validation = validate_operation(operation, attempt_id=attempt_id, helper_contract_sha256=policy["dependencies"]["phase6im_contract_sha256"]) if operation else {"accepted": False, "reasons": ["operation_missing"]}
    marker_validation = validate_markers(rows, attempt_id=attempt_id, identity=identity) if rows and identity else {"accepted": False, "reasons": ["markers_or_identity_missing"], "steps": []}
    runner_validation = validate_runner(runner, attempt_id=attempt_id, identity=identity) if runner and identity else {"accepted": False, "reasons": ["runner_or_identity_missing"]}
    cleanup = guard.get("observed_process_cleanup") or {}
    cleanup_pass = cleanup.get("all_observed_absent") is True
    assisted = bool(cleanup.get("killed") or [])
    peaks = guard.get("peaks") or {};minima = guard.get("machine_minima") or {};safety = policy["safety"]
    resource_pass = all((isinstance(peaks.get("runner"), int) and peaks["runner"] <= safety["runner_private_limit_bytes"], isinstance(peaks.get("kit"), int) and peaks["kit"] <= safety["kit_private_limit_bytes"], isinstance(peaks.get("diagnostic"), int) and peaks["diagnostic"] <= safety["diagnostic_private_limit_bytes"], isinstance(peaks.get("tree"), int) and peaks["tree"] <= safety["unique_tree_private_limit_bytes"], isinstance(minima.get("available_physical_bytes"), int) and minima["available_physical_bytes"] >= safety["available_physical_floor_bytes"], isinstance(minima.get("estimated_commit_headroom_bytes"), int) and minima["estimated_commit_headroom_bytes"] >= safety["commit_headroom_floor_bytes"]))
    roles_ok, role_failures, roles = validate_trace_roles(trace)
    monitor = runner.get("monitor") or {};exit_code = monitor.get("exit_code")
    post_exception = (exit_code not in (None, 0)) or bool(runner.get("fatal_lines") or []) or bool(runner.get("dump_inventory") or []) or monitor.get("crash_reporter_observed") is True
    axes = classify(operation_valid=operation_validation["accepted"], monitor_valid=runner_validation["accepted"] and marker_validation["accepted"], identity_reuse=monitor.get("identity_reuse") is True, exit_observed=monitor.get("exit_observed") is True, exit_code=exit_code, exit_seconds=monitor.get("exit_observed_seconds"), post_shutdown_exception=post_exception, resource_pass=resource_pass and roles_ok, cleanup_pass=cleanup_pass, cleanup_assisted=assisted)
    safety_pass = resource_pass and roles_ok and cleanup_pass and not (runner.get("automatic_upload_attempt_lines") or [])
    if axes["monitor_boundary_qualified"] and safety_pass:
        status = "minimal_post_shutdown_monitor_qualified"
    elif not operation_validation["accepted"] or not marker_validation["accepted"] or not runner_validation["accepted"]:
        status = "safe_stop_post_shutdown_monitor_harness_failure"
    else:
        status = "safe_stop_post_shutdown_monitor_safety_failure"
    phase6ik_comparison = "indeterminate"
    if axes["lifecycle"] in {"normal_exit", "delayed_exit"} and exit_code == 0 and not post_exception:
        phase6ik_comparison = "not_reproduced_in_single_phase6in_process"
    elif exit_code == 0xC0000005:
        phase6ik_comparison = "same_exit_code_observed_timing_requires_comparison"
    result = {
        "schema": "campfire.phase6in.summary.v1", "phase": "phase6in", "status": status,
        "contract_sha256": digest, "attempt_id": attempt_id, "kit_launch_count": 1, "retry_count": 0, "replacement_count": 0,
        "phase6il_frozen": True, "phase6il_artifact_reused": False, "phase6il_monitor_reused": False,
        "phase6im_helper_reused_unchanged": sha(SCRIPTS / "phase6im_process_identity.py") == policy["dependencies"]["phase6im_helper"]["sha256"],
        "axes": axes, "operation_validation": operation_validation, "marker_validation": marker_validation, "runner_validation": runner_validation,
        "samples": monitor.get("samples") or [], "last_marker": rows[-1].get("step_id") if rows else None,
        "kit_exit_code": exit_code, "guard_exit_code": guard_exit, "phase6ik_access_violation_comparison": phase6ik_comparison,
        "fatal_lines": runner.get("fatal_lines") or [], "dump_inventory": runner.get("dump_inventory") or [],
        "crash_reporter_observed": monitor.get("crash_reporter_observed") is True, "automatic_upload_attempt_lines": runner.get("automatic_upload_attempt_lines") or [], "cdb_attempted": False,
        "resource_peaks_bytes": peaks, "resource_minima_bytes": minima,
        "resource_headroom_bytes": {"kit": safety["kit_private_limit_bytes"] - peaks.get("kit", 0), "tree": safety["unique_tree_private_limit_bytes"] - peaks.get("tree", 0)},
        "cleanup_pass": cleanup_pass, "cleanup_assisted": assisted, "residual_process_count": 0 if cleanup_pass else None,
        "roles_pass": roles_ok, "role_failures": role_failures, "roles": roles,
        "abc_restart_ready": axes["monitor"] == "qualified" and axes["operation"] == "complete" and axes["lifecycle"] == "normal_exit" and safety_pass,
        "abc_ladder_started": False, "four_boundary_audit_started": False, "collision_comparison_started": False,
        "invariant_hashes_before": before, "invariant_hashes_after": after, "invariants_pass": before == after,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser();parser.add_argument("--artifact-root", type=Path, required=True);parser.add_argument("--preflight-summary", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.artifact_root.resolve(), args.preflight_summary.resolve())
    return 0 if value["status"] == "minimal_post_shutdown_monitor_qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
