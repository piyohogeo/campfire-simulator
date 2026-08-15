"""Run one fresh Phase 6HR smoke or one-proxy boundary."""

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
from phase6hr_lifecycle_classification import consume_guard_report


CONTRACT = ROOT / "scripts/phase6hr_ngx_cleanup_proxy_contract.json"
SIDECAR = ROOT / "scripts/phase6hr_ngx_cleanup_proxy_contract.sha256"
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


def _contract() -> tuple[dict, str]:
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    expected = SIDECAR.read_text(encoding="ascii").split()[0].upper()
    if digest != expected:
        raise RuntimeError("Phase 6HR contract digest mismatch")
    return json.loads(CONTRACT.read_text(encoding="utf-8")), digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "proxy"), required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--precondition-summary", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HR boundary refuses root reuse")
    policy, digest = _contract()
    precondition = json.loads(args.precondition_summary.read_text(encoding="utf-8"))
    if precondition.get("status") not in ("qualified", "pass"):
        raise RuntimeError("Phase 6HR precondition did not pass")
    if args.mode == "proxy" and (
        precondition.get("mode") != "smoke"
        or precondition.get("canonical_lifecycle_classification") not in policy["accepted_classifications"]
    ):
        raise RuntimeError("proxy requires an accepted fresh Phase 6HR smoke")

    root.mkdir(parents=True)
    attempt = root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json")
    shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    before = hashes()
    paths = {
        "output": attempt / "run.json", "markers": attempt / "markers.jsonl",
        "runner_evidence": attempt / "runner_evidence.json", "kit_log": attempt / "kit.log",
        "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json",
        "child_stdout": logs / "powershell.stdout.log", "child_stderr": logs / "powershell.stderr.log",
        "cleanup": logs / "cleanup.jsonl", "lifecycle": attempt / "run.json", "gpu": logs / "gpu.csv",
    }
    target = build_target(args.mode, paths)
    target_ok, target_reason = validate_target(target, args.mode)
    write_json(attempt / "launch_contract.json", {
        "schema": "campfire.phase6hr.launch.v1", "phase": "phase6hr", "mode": args.mode,
        "target": target, "validation": [target_ok, target_reason], "lexical_paths_preserved": True,
        "inherited_phase6hp_probe_and_case_runner": True, "cwd": str(ROOT),
    })
    if not target_ok:
        write_json(root / "summary.json", {"status":"safe_stop_pre_kit","reason":target_reason,"kit_launch_count":0})
        return 1

    attempt_id = "phase6hr-" + args.mode + "-attempt01"
    command = build_guard_command(
        Path(r"C:\Python38\python.exe"), ROOT / "scripts/phase6hr_resource_guard.py",
        paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True,
    )
    delimiter = command.index("--")
    command[delimiter:delimiter] = [
        "--runner-evidence-path", str(paths["runner_evidence"]),
        "--marker-path", str(paths["markers"]),
        "--contract-path", str(CONTRACT), "--mode", args.mode,
    ]
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()

    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    run = _read_bounded(paths["output"]) if paths["output"].is_file() else None
    case = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else None
    samples = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, roles = validate_trace_roles(samples)
    canonical = consume_guard_report(guard or {}, policy, expected_attempt_id=attempt_id)
    after = hashes()
    invariants_pass = before == after
    passed = bool(canonical["accepted"] and guard_exit == 0 and run and run.get("status") == "qualified" and case and case.get("status") == "qualified" and roles_ok and invariants_pass)
    evaluation = canonical.get("evaluation") or {}
    cleanup = {} if guard is None else guard.get("observed_process_cleanup") or {}
    summary = {
        "schema":"campfire.phase6hr.boundary-summary.v1","phase":"phase6hr","mode":args.mode,
        "status":"qualified" if passed else "safe_stop","contract_sha256":digest,
        "kit_launch_count":1,"retry_count":0,"replacement_count":0,
        "guard_exit_code":guard_exit,"guard_status":None if guard is None else guard.get("status"),
        "canonical_consumer_reason":canonical["reason"],"canonical_lifecycle_classification":canonical["classification"],
        "natural_clean_exit":evaluation.get("natural_exit") is True,"cleanup_intervention":evaluation.get("cleanup_intervention") is True,
        "allowed_helper_set":canonical.get("allowed_helper_set"),"cleanup_killed_pids":canonical.get("killed_pid_set"),
        "telemetry_helpers":evaluation.get("telemetry_helpers"),"ngx_tree":evaluation.get("ngx_tree"),
        "run_status":None if run is None else run.get("status"),"case_status":None if case is None else case.get("status"),
        "kit_exit_code":None if case is None else case.get("process_exit_code"),
        "roles_pass":roles_ok,"roles":roles,"role_failures":role_failures,
        "resource_peaks_bytes":{} if guard is None else guard.get("peaks"),
        "resource_minima_bytes":{} if guard is None else guard.get("machine_minima"),
        "exact_cleanup_all_absent":cleanup.get("all_observed_absent") is True,
        "residual_process_count":0 if cleanup.get("all_observed_absent") is True else None,
        "invariants_pass":invariants_pass,"invariant_hashes_before":before,"invariant_hashes_after":after,
        "phase6hq_reclassified":False,"phase6hq_artifact_reused":False,
        "production_changed":False,"point_policy_changed":False,"v3_changed":False,
        "readback_calls":None if run is None else run.get("readback_calls"),"runtime_report":run,
    }
    write_json(root / "summary.json", summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
