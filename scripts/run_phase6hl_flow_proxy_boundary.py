"""Preflight and run exactly one guarded Phase 6HL hierarchy boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from phase6hl_guard_preflight import ROOT, SCRIPTS, _norm, _read_bounded, _write, build_guard_command, run_preflight_suite


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _runtime_hashes_pass(contract: dict) -> tuple[bool, dict]:
    interpreter = Path(contract["interpreter"]["guard_executable"])
    packman = Path(contract["interpreter"]["packman_executable"])
    observed = {
        "guard_executable": _sha256(interpreter) if interpreter.is_file() else None,
        "guard_script": _sha256(ROOT / contract["interpreter"]["guard_script"]),
        "process_identity": _sha256(SCRIPTS / "phase6fu_process_identity.py"),
        "legacy_guard": _sha256(SCRIPTS / "phase6eg_resource_guard.py"),
        "packman_executable": _sha256(packman) if packman.is_file() else None,
        "frozen_phase6hk_probe": _sha256(SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py"),
    }
    expected = {
        "guard_executable": contract["interpreter"]["guard_executable_sha256"],
        "guard_script": contract["interpreter"]["guard_script_sha256"],
        "process_identity": contract["interpreter"]["process_identity_sha256"],
        "legacy_guard": contract["interpreter"]["legacy_guard_sha256"],
        "packman_executable": contract["interpreter"]["packman_executable_sha256"],
        "frozen_phase6hk_probe": contract["scope"]["frozen_phase6hk_probe_sha256"],
    }
    return observed == expected, {"expected": expected, "observed": observed}


def _summary_base(contract_hash: str, preflight: dict, runtime_hashes: dict) -> dict:
    return {
        "schema": "campfire.phase6hl.flow-proxy-hierarchy-boundary-summary.v1",
        "phase": "phase6hl",
        "contract_sha256": contract_hash,
        "phase6hk_frozen": True,
        "phase6hk_reclassified": False,
        "phase6hk_artifact_reused": False,
        "preflight": {"status": preflight.get("status"), "cases": preflight.get("cases")},
        "runtime_hashes": runtime_hashes,
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
        raise RuntimeError(f"Phase 6HL refuses artifact reuse: {artifact_root}")
    artifact_root.mkdir(parents=True)
    contract_path = SCRIPTS / "phase6hl_flow_proxy_boundary_contract.json"
    sidecar_path = SCRIPTS / "phase6hl_flow_proxy_boundary_contract.sha256"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_hash = _sha256(contract_path)
    expected_hash = sidecar_path.read_text(encoding="ascii").split()[0].upper()
    if contract_hash != expected_hash:
        raise RuntimeError("Phase 6HL contract hash mismatch")
    shutil.copy2(contract_path, artifact_root / "frozen_contract.json")
    shutil.copy2(sidecar_path, artifact_root / "frozen_contract.sha256")
    hash_pass, runtime_hashes = _runtime_hashes_pass(contract)
    if not hash_pass:
        summary = _summary_base(contract_hash, {"status": "not_run", "cases": {}}, runtime_hashes)
        summary.update({"status": "safe_stop_preflight", "failure_reason": "runtime_hash_mismatch", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    preflight = run_preflight_suite(contract, artifact_root / "preflight")
    summary = _summary_base(contract_hash, preflight, runtime_hashes)
    if preflight.get("status") != "pass":
        summary.update({"status": "safe_stop_preflight", "failure_reason": "guard_interpreter_preflight_failed", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    interpreter = Path(contract["interpreter"]["guard_executable"])
    if _norm(os.sys.executable) != _norm(interpreter):
        summary.update({"status": "safe_stop_preflight", "failure_reason": "parent_runner_interpreter_mismatch", "kit_launch_count": 0})
        _write(artifact_root / "summary.json", summary)
        return 1
    attempt = artifact_root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    output = attempt / "run.json"
    markers = attempt / "markers.jsonl"
    kit = ROOT / "_build/windows-x86_64/release/kit/kit.exe"
    app = ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit"
    probe = SCRIPTS / "probe_phase6hl_flow_proxy_boundary.py"
    guard = ROOT / contract["interpreter"]["guard_script"]
    target = [
        str(kit), str(app), "--no-window", "--/app/file/ignoreUnsavedOnExit=true",
        "--/app/fastShutdown=0", "--/app/quitAfter=300000", "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0", "--/app/window/hideUi=true", "--/app/asyncRendering=false",
        "--/app/useFabricSceneDelegate=true", "--/renderer/multiGpu/enabled=false",
        "--/renderer/multiGpu/autoEnable=false", "--/renderer/enabled=rtx", "--/renderer/active=rtx",
        "--/exts/campfire.app/autoCreateScene=false", "--/rtx/flow/enabled=true",
        "--enable", "omni.usd", "--enable", "omni.hydra.rtx", "--enable", "omni.hydra.usdrt_delegate",
        "--enable", "omni.kit.viewport.utility", "--enable", "omni.flowusd",
        f"--/phase6hl/output={output}", f"--/phase6hl/markers={markers}", "--exec", str(probe),
    ]
    paths = {
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json",
        "child_stdout": logs / "stdout.log", "child_stderr": logs / "stderr.log",
        "cleanup": logs / "cleanup.jsonl", "lifecycle": output, "gpu": logs / "gpu.csv",
    }
    guard_command = build_guard_command(
        interpreter, guard, paths, target, attempt_id="phase6hl-attempt01",
        safety=contract["safety"], include_gpu=True,
    )
    _write(attempt / "launch_contract.json", {
        "schema": "campfire.phase6hl.launch-contract.v1",
        "parent_runner_interpreter": str(Path(os.sys.executable).resolve()),
        "guard_interpreter": str(interpreter.resolve()),
        "guard_command": guard_command,
        "target_command": target,
        "environment": {key: os.environ.get(key) for key in ("PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONUNBUFFERED")},
        "large_output_buffered_in_parent": False,
    })
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(guard_command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process_return_code = process.wait()
    guard_result = _read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    run = _read_bounded(output) if output.is_file() else None
    residual_zero = bool(guard_result and guard_result.get("process_absent")) and bool(
        (guard_result.get("observed_process_cleanup") or {}).get("all_observed_absent")
    )
    passed = (
        process_return_code == 0 and guard_result is not None and guard_result.get("status") == "ok"
        and run is not None and run.get("status") == "qualified" and residual_zero
    )
    summary.update({
        "status": "qualified" if passed else "safe_stop",
        "kit_launch_count": 1,
        "accepted_runtime_samples": 1 if passed else 0,
        "guard_exit_code": process_return_code,
        "guard_status": None if guard_result is None else guard_result.get("status"),
        "guard_stop_reason": None if guard_result is None else guard_result.get("stop_reason"),
        "run_status": None if run is None else run.get("status"),
        "last_marker": None if run is None else run.get("last_marker"),
        "resource_peaks_bytes": {} if guard_result is None else guard_result.get("peaks", {}),
        "resource_minima_bytes": {} if guard_result is None else guard_result.get("machine_minima", {}),
        "residual_zero": residual_zero,
        "readback_calls": None if run is None else run.get("readback_calls"),
        "runtime_report": str(output),
    })
    _write(artifact_root / "summary.json", summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
