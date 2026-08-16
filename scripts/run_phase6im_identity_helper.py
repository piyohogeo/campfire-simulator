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
from phase6im_process_identity import read_bounded_json, read_bounded_jsonl, validate_report
from run_phase6hz_import_smoke import hashes as invariant_hashes

SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6im_process_identity_contract.json"
SIDECAR = SCRIPTS / "phase6im_process_identity_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = SCRIPTS / "phase6im_resource_guard.py"
CASE = SCRIPTS / "run_phase6im_identity_helper_case.ps1"
PROBE = SCRIPTS / "probe_phase6im_identity_helper.py"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6IM runtime refuses root reuse")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = _sha(CONTRACT)
    preflight = _read_bounded(preflight_path)
    if preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest or SIDECAR.read_text(encoding="ascii").split()[0].upper() != digest:
        raise RuntimeError("Phase 6IM preflight or contract invalid")
    root.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json")
    shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    attempt_id = "phase6im-identity-helper-01"
    attempt = root / "attempt-01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    paths = {
        "output": attempt / "identity_helper_report.json", "lifecycle": attempt / "identity_helper_report.json",
        "markers": attempt / "identity_markers.jsonl", "runner_evidence": attempt / "runner_evidence.json",
        "kit_log": attempt / "kit.log", "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log",
        "child_stderr": logs / "powershell.stderr.log", "cleanup": logs / "cleanup.jsonl", "gpu": logs / "gpu.csv",
    }
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    target = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE),
              "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE), "-MarkersPath", str(paths["markers"]),
              "-ReportPath", str(paths["output"]), "-RunnerEvidencePath", str(paths["runner_evidence"]),
              "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]), "-AttemptId", attempt_id]
    write_json(attempt / "launch_contract.json", {"schema": "campfire.phase6im.launch.v1", "attempt_id": attempt_id, "target": target, "cwd": str(ROOT)})
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    before = invariant_hashes()
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    after = invariant_hashes()
    report = read_bounded_json(paths["output"]) if paths["output"].is_file() else {}
    rows = read_bounded_jsonl(paths["markers"]) if paths["markers"].is_file() else []
    runner = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {}
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}
    trace = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    validation = validate_report(report, rows, attempt_id=attempt_id) if report and rows else {"accepted": False, "reasons": ["helper_evidence_missing"], "steps": []}
    helper_axis = "qualified" if validation["accepted"] else "failed"
    lifecycle = runner.get("lifecycle") or {}
    if lifecycle.get("lifecycle_candidate") == "normal_exit" and lifecycle.get("exit_code") == 0:
        lifecycle_axis = "normal_exit"
    elif report.get("shutdown_complete") is True:
        lifecycle_axis = "post_shutdown_anomaly"
    else:
        lifecycle_axis = "incomplete"
    cleanup = guard.get("observed_process_cleanup") or {}
    cleanup_pass = cleanup.get("all_observed_absent") is True
    peaks = guard.get("peaks") or {}
    minima = guard.get("machine_minima") or {}
    safety = policy["safety"]
    resource_pass = all((
        isinstance(peaks.get("runner"), int) and peaks["runner"] <= safety["runner_private_limit_bytes"],
        isinstance(peaks.get("kit"), int) and peaks["kit"] <= safety["kit_private_limit_bytes"],
        isinstance(peaks.get("diagnostic"), int) and peaks["diagnostic"] <= safety["diagnostic_private_limit_bytes"],
        isinstance(peaks.get("tree"), int) and peaks["tree"] <= safety["unique_tree_private_limit_bytes"],
        isinstance(minima.get("available_physical_bytes"), int) and minima["available_physical_bytes"] >= safety["available_physical_floor_bytes"],
        isinstance(minima.get("estimated_commit_headroom_bytes"), int) and minima["estimated_commit_headroom_bytes"] >= safety["commit_headroom_floor_bytes"],
    ))
    roles_ok, role_failures, roles = validate_trace_roles(trace)
    safety_pass = resource_pass and cleanup_pass and roles_ok and not (runner.get("fatal_lines") or []) and not (runner.get("dump_inventory") or []) and not (runner.get("automatic_upload_attempt_lines") or [])
    if helper_axis == "qualified" and lifecycle_axis == "normal_exit" and safety_pass:
        status = "kit_process_identity_helper_qualified"
    elif helper_axis == "qualified" and report.get("shutdown_complete") is True:
        status = "helper_qualified_with_post_shutdown_anomaly"
    elif preflight.get("status") != "qualified":
        status = "safe_stop_identity_helper_harness_failure"
    else:
        status = "safe_stop_kit_process_identity_helper_failure"
    result = {
        "schema": "campfire.phase6im.summary.v1", "phase": "phase6im", "status": status,
        "contract_sha256": digest, "attempt_id": attempt_id, "kit_launch_count": 1, "retry_count": 0, "replacement_count": 0,
        "phase6il_reclassified": False, "phase6il_runtime_reused": False, "phase6il_post_shutdown_monitor_started": False, "abc_ladder_started": False,
        "helper_axis": helper_axis, "lifecycle_axis": lifecycle_axis, "helper_validation": validation,
        "identity_report": report, "last_marker": rows[-1].get("step_id") if rows else None,
        "lifecycle": lifecycle, "kit_exit_code": lifecycle.get("exit_code"), "guard_exit_code": guard_exit,
        "resource_pass": resource_pass, "resource_peaks_bytes": peaks, "resource_minima_bytes": minima,
        "resource_headroom_bytes": {"kit": safety["kit_private_limit_bytes"] - peaks.get("kit", 0), "tree": safety["unique_tree_private_limit_bytes"] - peaks.get("tree", 0)},
        "cleanup_pass": cleanup_pass, "residual_process_count": 0 if cleanup_pass else None,
        "roles_pass": roles_ok, "role_failures": role_failures, "roles": roles,
        "fatal_lines": runner.get("fatal_lines") or [], "dump_inventory": runner.get("dump_inventory") or [],
        "automatic_upload_attempt_lines": runner.get("automatic_upload_attempt_lines") or [], "cdb_attempted": False,
        "invariant_hashes_before": before, "invariant_hashes_after": after, "invariants_pass": before == after,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-summary", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.artifact_root.resolve(), args.preflight_summary.resolve())
    return 0 if result["status"] in {"kit_process_identity_helper_qualified", "helper_qualified_with_post_shutdown_anomaly"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

