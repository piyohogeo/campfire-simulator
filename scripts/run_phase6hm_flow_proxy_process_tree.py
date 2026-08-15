"""Run the Phase 6HM no-Kit role gate, then one fresh guarded Kit boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from phase6hl_guard_preflight import _read_bounded, _write, build_guard_command
from phase6hm_process_role_fixture import _read_jsonl, run_fixture_suite
from phase6hm_process_tree_topology import ROOT, SCRIPTS, build_formal_target, norm_path, validate_formal_target, validate_trace_roles


RUNTIME_FILES = {
    "phase6fu_resource_guard": SCRIPTS / "phase6fu_resource_guard.py",
    "phase6fu_process_identity": SCRIPTS / "phase6fu_process_identity.py",
    "phase6eg_resource_guard": SCRIPTS / "phase6eg_resource_guard.py",
    "phase6fw_pid_reuse_policy": SCRIPTS / "phase6fw_pid_reuse_policy.py",
    "phase6hl_guard_preflight": SCRIPTS / "phase6hl_guard_preflight.py",
    "frozen_phase6hk_probe": SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py",
    "isolated_kit_crash_safety": SCRIPTS / "isolated_kit_crash_safety.ps1",
    "kit_shutdown_policy": SCRIPTS / "kit_shutdown_policy.ps1",
    "process_tree_topology": SCRIPTS / "phase6hm_process_tree_topology.py",
    "process_role_fixture": SCRIPTS / "phase6hm_process_role_fixture.py",
    "process_role_fixture_child": SCRIPTS / "phase6hm_process_role_fixture_child.py",
    "case_runner": SCRIPTS / "run_phase6hm_flow_proxy_case.ps1",
    "probe_wrapper": SCRIPTS / "probe_phase6hm_flow_proxy_boundary.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _runtime_hash_audit(contract: dict) -> dict:
    expected = contract["runtime_hashes"]
    observed = {name: _sha256(path) for name, path in RUNTIME_FILES.items()}
    return {"status": "pass" if expected == observed else "fail", "expected": expected, "observed": observed}


def _summary_base(contract_hash: str, runtime: dict) -> dict:
    return {
        "schema": "campfire.phase6hm.flow-proxy-process-tree-summary.v1",
        "phase": "phase6hm",
        "contract_sha256": contract_hash,
        "phase6hl_commit": "f1f5578",
        "phase6hl_status_preserved": "safe_stop_resource_role_harness_failure",
        "phase6hl_reclassified": False,
        "phase6hl_artifact_reused": False,
        "runtime_hashes": runtime,
        "retry_count": 0,
        "replacement_count": 0,
        "production_code_changed": False,
        "production_defaults_changed": False,
        "point_policy_changed": False,
        "v3_changed": False,
        "latest_demo_changed": False,
        "packman_environment_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    if artifact_root.exists():
        raise RuntimeError(f"Phase 6HM refuses artifact root reuse: {artifact_root}")
    artifact_root.mkdir(parents=True)
    contract_path = SCRIPTS / "phase6hm_flow_proxy_process_tree_contract.json"
    sidecar_path = SCRIPTS / "phase6hm_flow_proxy_process_tree_contract.sha256"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_hash = _sha256(contract_path)
    expected_hash = sidecar_path.read_text(encoding="ascii").split()[0].upper()
    shutil.copy2(contract_path, artifact_root / "frozen_contract.json")
    shutil.copy2(sidecar_path, artifact_root / "frozen_contract.sha256")
    runtime = _runtime_hash_audit(contract)
    summary = _summary_base(contract_hash, runtime)
    if contract_hash != expected_hash:
        summary.update({"status": "safe_stop_pre_kit", "failure_reason": "contract_hash_mismatch", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    if runtime["status"] != "pass":
        summary.update({"status": "safe_stop_pre_kit", "failure_reason": "runtime_hash_mismatch", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    interpreter = Path(contract["interpreter"]["guard_executable"])
    if norm_path(os.sys.executable) != norm_path(interpreter):
        summary.update({"status": "safe_stop_pre_kit", "failure_reason": "parent_interpreter_mismatch", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    fixture = run_fixture_suite(contract, artifact_root / "preflight")
    summary["process_role_fixture"] = {
        "status": fixture["status"],
        "cases": fixture["cases"],
        "negative_reasons": fixture["negative_reasons"],
        "kit_launch_count": fixture["kit_launch_count"],
    }
    if fixture["status"] != "pass":
        summary.update({"status": "safe_stop_pre_kit", "failure_reason": "process_role_fixture_failed", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1

    attempt = artifact_root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    paths = {
        "output": attempt / "run.json",
        "markers": attempt / "markers.jsonl",
        "runner_evidence": attempt / "runner_evidence.json",
        "kit_log": attempt / "kit.log",
        "kit_stdout": attempt / "kit.stdout.log",
        "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl",
        "summary": logs / "guard.json",
        "child_stdout": logs / "powershell.stdout.log",
        "child_stderr": logs / "powershell.stderr.log",
        "cleanup": logs / "cleanup.jsonl",
        "lifecycle": attempt / "run.json",
        "gpu": logs / "gpu.csv",
    }
    target = build_formal_target(paths, contract["safety"]["stage_close_timeout_seconds"])
    target_ok, target_reason = validate_formal_target(target)
    if not target_ok:
        summary.update({"status": "safe_stop_pre_kit", "failure_reason": target_reason, "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    guard_command = build_guard_command(
        interpreter,
        ROOT / contract["interpreter"]["guard_script"],
        paths,
        target,
        attempt_id="phase6hm-attempt01",
        safety=contract["safety"],
        include_gpu=True,
    )
    _write(attempt / "launch_contract.json", {
        "schema": "campfire.phase6hm.launch-contract.v1",
        "guard_launcher": str(interpreter.resolve()),
        "guard_command": guard_command,
        "guarded_root_command": target,
        "guarded_root_role": "runner",
        "kit_child_path_transmitted": target[target.index("-KitPath") + 1],
        "stdout_stderr_direct_to_files": True,
        "large_output_buffered_in_parent": False,
    })
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(guard_command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    run = _read_bounded(paths["output"]) if paths["output"].is_file() else None
    case = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else None
    samples = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, role_evidence = validate_trace_roles(samples)
    cleanup = {} if guard is None else guard.get("observed_process_cleanup") or {}
    residual_zero = bool(guard and guard.get("process_absent") and cleanup.get("all_observed_absent"))
    allowed_guard_stop = guard is not None and guard.get("stop_reason") in (None, "observed_descendant_residual")
    peaks = {} if guard is None else guard.get("peaks") or {}
    minima = {} if guard is None else guard.get("machine_minima") or {}
    safety = contract["safety"]
    resource_pass = bool(guard) and allowed_guard_stop and all((
        int(peaks.get("runner", 2**63)) <= safety["runner_private_limit_bytes"],
        int(peaks.get("kit", 2**63)) <= safety["kit_private_limit_bytes"],
        int(peaks.get("diagnostic", 2**63)) <= safety["diagnostic_private_limit_bytes"],
        int(peaks.get("tree", 2**63)) <= safety["unique_tree_private_limit_bytes"],
        int(minima.get("available_physical_bytes") or 0) >= safety["available_physical_floor_bytes"],
        int(minima.get("estimated_commit_headroom_bytes") or 0) >= safety["commit_headroom_floor_bytes"],
    ))
    functional = bool(run) and run.get("status") == "qualified" and run.get("readback_calls") == 0
    lifecycle = bool(case) and case.get("status") == "qualified" and case.get("process_exit_code") == 0
    artifact_pass = not list(attempt.rglob("*.nvdb")) and bool(paths["output"].is_file() and paths["markers"].is_file())
    passed = all((functional, lifecycle, resource_pass, roles_ok, residual_zero, artifact_pass))
    summary.update({
        "status": "qualified" if passed else "safe_stop",
        "failure_reason": None if passed else "formal_boundary_gate_failed",
        "kit_launch_count": 1,
        "accepted_runtime_samples": 1 if passed else 0,
        "guard_exit_code": guard_exit,
        "guard_status": None if guard is None else guard.get("status"),
        "guard_stop_reason": None if guard is None else guard.get("stop_reason"),
        "guard_cleanup_only_stop_accepted": bool(guard and guard.get("stop_reason") == "observed_descendant_residual" and residual_zero),
        "process_roles": role_evidence,
        "process_role_failures": role_failures,
        "functional_pass": functional,
        "lifecycle_pass": lifecycle,
        "resource_pass": resource_pass,
        "artifact_pass": artifact_pass,
        "run_status": None if run is None else run.get("status"),
        "last_marker": None if run is None else run.get("last_marker"),
        "readback_calls": None if run is None else run.get("readback_calls"),
        "case_runner_status": None if case is None else case.get("status"),
        "kit_natural_exit_code": None if case is None else case.get("process_exit_code"),
        "resource_peaks_bytes": peaks,
        "resource_minima_bytes": minima,
        "residual_zero": residual_zero,
        "nanovdb_residual_count": len(list(attempt.rglob("*.nvdb"))),
        "runtime_report": str(paths["output"]),
    })
    _write(artifact_root / "summary.json", summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
