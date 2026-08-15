"""Run Phase 6HN projection fixtures, then one fresh guarded Kit boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

from phase6hl_guard_preflight import _read_bounded, _write, build_guard_command
from phase6hm_process_role_fixture import _read_jsonl
from phase6hn_process_role_fixture import run_fixture_suite
from phase6hn_process_tree_topology import (
    ROOT,
    SCRIPTS,
    build_formal_target,
    norm_path,
    validate_formal_target,
    validate_trace_roles,
)


RUNTIME_FILES = {
    "phase6fu_resource_guard": SCRIPTS / "phase6fu_resource_guard.py",
    "phase6fu_process_identity": SCRIPTS / "phase6fu_process_identity.py",
    "phase6eg_resource_guard": SCRIPTS / "phase6eg_resource_guard.py",
    "phase6fw_pid_reuse_policy": SCRIPTS / "phase6fw_pid_reuse_policy.py",
    "phase6hl_guard_preflight": SCRIPTS / "phase6hl_guard_preflight.py",
    "frozen_phase6hk_probe": SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py",
    "isolated_kit_crash_safety": SCRIPTS / "isolated_kit_crash_safety.ps1",
    "kit_shutdown_policy": SCRIPTS / "kit_shutdown_policy.ps1",
    "shared_phase6hm_fixture": SCRIPTS / "phase6hm_process_role_fixture.py",
    "shared_phase6hm_topology": SCRIPTS / "phase6hm_process_tree_topology.py",
    "process_role_projection": SCRIPTS / "phase6hn_process_role_projection.py",
    "process_tree_topology": SCRIPTS / "phase6hn_process_tree_topology.py",
    "process_role_fixture": SCRIPTS / "phase6hn_process_role_fixture.py",
    "process_role_fixture_child": SCRIPTS / "phase6hm_process_role_fixture_child.py",
    "case_runner": SCRIPTS / "run_phase6hn_flow_proxy_case.ps1",
    "probe_wrapper": SCRIPTS / "probe_phase6hn_flow_proxy_boundary.py",
    "qualification_runner": SCRIPTS / "run_phase6hn_flow_proxy_process_tree.py",
}


INVARIANT_FILES = {
    "production_source_app": ROOT / "source/apps/campfire.simulator.kit",
    "production_built_app": ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit",
    "wood_authority": ROOT / "source/extensions/campfire.app/campfire/app/wood.py",
    "production_scene": ROOT / "source/extensions/campfire.app/campfire/app/scene.py",
    "wood_visual_v3": ROOT / "source/extensions/campfire.app/campfire/app/wood_visual_v3.py",
    "latest_demo": ROOT / "docs/devlog/assets/latest_demo.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _hashes(paths: Dict[str, Path]) -> Dict[str, str]:
    return {name: _sha256(path) for name, path in paths.items()}


def _runtime_hash_audit(contract: Dict[str, Any]) -> Dict[str, Any]:
    observed = _hashes(RUNTIME_FILES)
    expected = contract["runtime_hashes"]
    return {"status": "pass" if observed == expected else "fail", "expected": expected, "observed": observed}


def _summary_base(contract_hash: str, runtime: Dict[str, Any], invariants_before: Dict[str, str]) -> Dict[str, Any]:
    return {
        "schema": "campfire.phase6hn.flow-proxy-process-tree-summary.v1",
        "phase": "phase6hn",
        "contract_sha256": contract_hash,
        "phase6hm_commit": "d1dc873",
        "phase6hm_status_preserved": "safe_stop_pre_kit_harness_failure",
        "phase6hm_failure_reason_preserved": "bounded_json_oversize",
        "phase6hm_reclassified": False,
        "phase6hm_artifact_reused": False,
        "phase6fz_results_reclassified": False,
        "phase6fz_runtime_samples_reused": False,
        "runtime_hashes": runtime,
        "invariant_hashes_before": invariants_before,
        "retry_count": 0,
        "replacement_count": 0,
        "production_code_changed": False,
        "production_defaults_changed": False,
        "point_policy_changed": False,
        "wood_authority_changed": False,
        "v3_changed": False,
        "latest_demo_changed": False,
        "packman_environment_modified": False,
    }


def _peak_evidence(guard: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for role, row in (guard.get("peak_evidence") or {}).items():
        if isinstance(row, dict):
            result[role] = {key: row.get(key) for key in (
                "pid", "parent_pid", "create_time_utc_epoch", "path", "role", "private_bytes", "working_set_bytes"
            )}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    if artifact_root.exists():
        raise RuntimeError("Phase 6HN refuses artifact root reuse: %s" % artifact_root)
    artifact_root.mkdir(parents=True)

    contract_path = SCRIPTS / "phase6hn_flow_proxy_process_tree_contract.json"
    sidecar_path = SCRIPTS / "phase6hn_flow_proxy_process_tree_contract.sha256"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_hash = _sha256(contract_path)
    expected_hash = sidecar_path.read_text(encoding="ascii").split()[0].upper()
    shutil.copy2(contract_path, artifact_root / "frozen_contract.json")
    shutil.copy2(sidecar_path, artifact_root / "frozen_contract.sha256")
    runtime = _runtime_hash_audit(contract)
    invariants_before = _hashes(INVARIANT_FILES)
    summary = _summary_base(contract_hash, runtime, invariants_before)

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
    summary["bounded_projection_fixture"] = {
        "status": fixture["status"],
        "cases": fixture["cases"],
        "negative_reasons": fixture["negative_reasons"],
        "projection": fixture["projection"],
        "kit_launch_count": fixture["kit_launch_count"],
        "residual_process_count": fixture["residual_process_count"],
    }
    if fixture["status"] != "pass":
        summary.update({"status": "safe_stop_pre_kit", "failure_reason": "bounded_projection_or_role_fixture_failed", "kit_launch_count": 0})
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
        attempt_id="phase6hn-attempt01",
        safety=contract["safety"],
        include_gpu=True,
    )
    _write(attempt / "launch_contract.json", {
        "schema": "campfire.phase6hn.launch-contract.v1",
        "guard_launcher": str(interpreter.resolve()),
        "guard_command": guard_command,
        "guarded_root_command": target,
        "process_chain": ["guard", "runner", "kit"],
        "guarded_root_role": "runner",
        "kit_child_path_transmitted": target[target.index("-KitPath") + 1],
        "stdout_stderr_direct_to_files": True,
        "large_output_buffered_in_parent": False,
    })
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(
            guard_command,
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
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
    invariants_after = _hashes(INVARIANT_FILES)
    invariants_pass = invariants_before == invariants_after == contract["invariant_hashes"]
    passed = all((functional, lifecycle, resource_pass, roles_ok, residual_zero, artifact_pass, invariants_pass))
    fatal_lines = [] if case is None else case.get("fatal_lines") or []
    dump_inventory = [] if case is None else case.get("dump_inventory") or []
    uploads = [] if case is None else case.get("automatic_upload_attempt_lines") or []
    offline = {} if run is None else run.get("offline") or {}
    runtime_report = {} if run is None else run.get("runtime") or {}
    summary.update({
        "status": "qualified" if passed else "safe_stop",
        "failure_reason": None if passed else "formal_boundary_gate_failed",
        "kit_launch_count": 1,
        "accepted_runtime_samples": 1 if passed else 0,
        "guard_exit_code": guard_exit,
        "guard_status": None if guard is None else guard.get("status"),
        "guard_stop_reason": None if guard is None else guard.get("stop_reason"),
        "guard_cleanup_only_stop_accepted": bool(guard and guard.get("stop_reason") == "observed_descendant_residual" and residual_zero),
        "actual_process_tree": {
            "roles": role_evidence,
            "role_failures": role_failures,
            "role_private_bytes_peak": peaks,
            "role_peak_identity": {} if guard is None else _peak_evidence(guard),
        },
        "functional_pass": functional,
        "lifecycle_pass": lifecycle,
        "resource_pass": resource_pass,
        "artifact_pass": artifact_pass,
        "invariants_pass": invariants_pass,
        "invariant_hashes_after": invariants_after,
        "run_status": None if run is None else run.get("status"),
        "last_marker": None if run is None else run.get("last_marker"),
        "readback_calls": None if run is None else run.get("readback_calls"),
        "operation_evidence": {
            "proxy_path": contract["scope"]["proxy_path"],
            "offline": offline,
            "runtime": runtime_report,
        },
        "case_runner_status": None if case is None else case.get("status"),
        "kit_natural_exit_code": None if case is None else case.get("process_exit_code"),
        "stage_close_complete": bool(run and (run.get("lifecycle") or {}).get("stage_close_complete")),
        "shutdown_complete": bool(run and (run.get("lifecycle") or {}).get("shutdown_complete")),
        "fatal_count": len(fatal_lines),
        "dump_count": len(dump_inventory),
        "automatic_upload_count": len(uploads),
        "device_loss_or_tdr_count": sum(1 for line in fatal_lines if "device lost" in line.lower() or "tdr" in line.lower()),
        "cdb_invocation_count": 0 if case is None else int(bool((case.get("shutdown_monitor") or {}).get("diagnostic_invoked"))),
        "resource_peaks_bytes": peaks,
        "resource_minima_bytes": minima,
        "residual_zero": residual_zero,
        "residual_process_count": 0 if residual_zero else None,
        "nanovdb_residual_count": len(list(attempt.rglob("*.nvdb"))),
        "runtime_report": str(paths["output"]),
    })
    _write(artifact_root / "summary.json", summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
