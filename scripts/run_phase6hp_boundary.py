"""Run one Phase 6HP smoke or proxy boundary through the frozen guard."""

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
from phase6ho_app_ready_environment import write_json
from phase6hp_process_tree_topology import ROOT, build_target, validate_target


INVARIANTS = {
    "production_source_app": ROOT / "source/apps/campfire.simulator.kit",
    "production_built_app": ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit",
    "production_scene": ROOT / "source/extensions/campfire.app/campfire/app/scene.py",
    "wood_authority": ROOT / "source/extensions/campfire.app/campfire/app/wood.py",
    "v3": ROOT / "source/extensions/campfire.app/campfire/app/wood_visual_v3.py",
    "latest_demo": ROOT / "docs/devlog/assets/latest_demo.json",
}


def hashes() -> dict[str, str]:
    return {key: hashlib.sha256(path.read_bytes()).hexdigest().upper() for key, path in INVARIANTS.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "proxy"), required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--precondition-summary", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HP boundary refuses root reuse")
    precondition = json.loads(args.precondition_summary.read_text(encoding="utf-8"))
    if precondition.get("status") not in ("pass", "qualified"):
        raise RuntimeError("Phase 6HP precondition did not pass")
    if args.mode == "proxy":
        gate = ((precondition.get("runtime_report") or {}).get("module_path_gate") or {})
        if precondition.get("mode") != "smoke" or gate.get("passed") is not True:
            raise RuntimeError("proxy requires qualified junction-aware smoke summary")

    root.mkdir(parents=True)
    attempt = root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    contract = ROOT / "scripts/phase6hp_junction_app_ready_contract.json"
    sidecar = ROOT / "scripts/phase6hp_junction_app_ready_contract.sha256"
    shutil.copy2(contract, root / "frozen_contract.json")
    shutil.copy2(sidecar, root / "frozen_contract.sha256")
    digest = hashlib.sha256(contract.read_bytes()).hexdigest().upper()
    if digest != sidecar.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6HP contract digest mismatch")
    before = hashes()
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
    target = build_target(args.mode, paths)
    target_ok, target_reason = validate_target(target, args.mode)
    write_json(
        attempt / "launch_contract.json",
        {
            "schema": "campfire.phase6hp.launch.v1",
            "mode": args.mode,
            "target": target,
            "validation": [target_ok, target_reason],
            "lexical_paths_preserved": True,
            "cwd": str(ROOT),
        },
    )
    if not target_ok:
        write_json(root / "summary.json", {"status": "safe_stop_pre_kit", "reason": target_reason, "kit_launch_count": 0})
        return 1

    safety = json.loads(contract.read_text(encoding="utf-8"))["safety"]
    command = build_guard_command(
        Path(r"C:\Python38\python.exe"),
        ROOT / "scripts/phase6fu_resource_guard.py",
        paths,
        target,
        attempt_id="phase6hp-" + args.mode + "-attempt01",
        safety=safety,
        include_gpu=True,
    )
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(
            command,
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
    roles_ok, role_failures, roles = validate_trace_roles(samples)
    peaks = {} if guard is None else guard.get("peaks") or {}
    minima = {} if guard is None else guard.get("machine_minima") or {}
    cleanup = {} if guard is None else guard.get("observed_process_cleanup") or {}
    resource_pass = bool(guard) and all(
        (
            int(peaks.get("runner", 2**63)) <= safety["runner_private_limit_bytes"],
            int(peaks.get("kit", 2**63)) <= safety["kit_private_limit_bytes"],
            int(peaks.get("diagnostic", 2**63)) <= safety["diagnostic_private_limit_bytes"],
            int(peaks.get("tree", 2**63)) <= safety["unique_tree_private_limit_bytes"],
            int(minima.get("available_physical_bytes") or 0) >= safety["available_physical_floor_bytes"],
            int(minima.get("estimated_commit_headroom_bytes") or 0) >= safety["commit_headroom_floor_bytes"],
        )
    )
    cleanup_pass = bool(guard and guard.get("process_absent") and cleanup.get("all_observed_absent"))
    after = hashes()
    invariants_pass = before == after
    passed = bool(
        run
        and run.get("status") == "qualified"
        and case
        and case.get("status") == "qualified"
        and case.get("process_exit_code") == 0
        and roles_ok
        and resource_pass
        and cleanup_pass
        and invariants_pass
        and paths["markers"].is_file()
    )
    summary = {
        "schema": "campfire.phase6hp.boundary-summary.v1",
        "phase": "phase6hp",
        "mode": args.mode,
        "status": "qualified" if passed else "safe_stop",
        "contract_sha256": digest,
        "kit_launch_count": 1,
        "guard_exit_code": guard_exit,
        "run_status": None if run is None else run.get("status"),
        "case_status": None if case is None else case.get("status"),
        "natural_os_exit_code": None if case is None else case.get("process_exit_code"),
        "roles_pass": roles_ok,
        "roles": roles,
        "role_failures": role_failures,
        "resource_pass": resource_pass,
        "resource_peaks_bytes": peaks,
        "resource_minima_bytes": minima,
        "cleanup_pass": cleanup_pass,
        "residual_process_count": 0 if cleanup_pass else None,
        "invariants_pass": invariants_pass,
        "invariant_hashes_before": before,
        "invariant_hashes_after": after,
        "phase6ho_reclassified": False,
        "phase6ho_artifact_reused": False,
        "production_changed": False,
        "point_policy_changed": False,
        "v3_changed": False,
        "readback_calls": 0 if run is None else run.get("readback_calls"),
        "runtime_report": run,
    }
    write_json(root / "summary.json", summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
