"""Run exactly one guarded Phase 6HK hierarchy-boundary process."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    if artifact_root.exists():
        raise RuntimeError(f"Phase 6HK refuses artifact reuse: {artifact_root}")
    artifact_root.mkdir(parents=True)
    contract_path = SCRIPT_DIR / "phase6hk_flow_proxy_boundary_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_hash = _sha256(contract_path)
    (artifact_root / "contract.sha256").write_text(contract_hash + "\n", encoding="ascii")
    attempt = artifact_root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    output = attempt / "run.json"
    markers = attempt / "markers.jsonl"
    kit = ROOT / "_build/windows-x86_64/release/kit/kit.exe"
    app = ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit"
    probe = SCRIPT_DIR / "probe_phase6hk_flow_proxy_boundary.py"
    guard = SCRIPT_DIR / "phase6fu_resource_guard.py"
    command = [
        str(kit), str(app), "--no-window", "--/app/file/ignoreUnsavedOnExit=true",
        "--/app/fastShutdown=0", "--/app/quitAfter=300000", "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0", "--/app/window/hideUi=true", "--/app/asyncRendering=false",
        "--/app/useFabricSceneDelegate=true", "--/renderer/multiGpu/enabled=false",
        "--/renderer/multiGpu/autoEnable=false", "--/renderer/enabled=rtx", "--/renderer/active=rtx",
        "--/exts/campfire.app/autoCreateScene=false", "--/rtx/flow/enabled=true",
        "--enable", "omni.usd", "--enable", "omni.hydra.rtx", "--enable", "omni.hydra.usdrt_delegate",
        "--enable", "omni.kit.viewport.utility", "--enable", "omni.flowusd",
        f"--/phase6hk/output={output}", f"--/phase6hk/markers={markers}", "--exec", str(probe),
    ]
    safety = contract["safety"]
    guard_command = [
        sys.executable, str(guard), "--trace", str(logs / "resource.jsonl"),
        "--summary", str(logs / "guard.json"), "--stdout", str(logs / "stdout.log"),
        "--stderr", str(logs / "stderr.log"), "--timeout-seconds", str(safety["outer_timeout_seconds"]),
        "--sample-seconds", "0.25", "--runner-private-limit", str(safety["runner_private_limit_bytes"]),
        "--kit-private-limit", str(safety["kit_private_limit_bytes"]),
        "--diagnostic-private-limit", str(safety["diagnostic_private_limit_bytes"]),
        "--tree-private-limit", str(safety["unique_tree_private_limit_bytes"]),
        "--available-memory-floor", str(safety["available_physical_floor_bytes"]),
        "--commit-headroom-floor", str(safety["commit_headroom_floor_bytes"]),
        "--cpu-telemetry", "--lifecycle-path", str(output), "--attempt-id", "phase6hk-attempt01",
        "--cleanup-marker-path", str(logs / "cleanup.jsonl"), "--gpu-csv", str(logs / "gpu.csv"),
        "--", *command,
    ]
    process = subprocess.run(guard_command, cwd=ROOT, check=False)
    guard_result = json.loads((logs / "guard.json").read_text(encoding="utf-8"))
    run = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else None
    residual_zero = bool(guard_result.get("process_absent")) and bool(
        guard_result.get("observed_process_cleanup", {}).get("all_observed_absent")
    )
    passed = process.returncode == 0 and run is not None and run.get("status") == "qualified" and residual_zero
    summary = {
        "schema": "campfire.phase6hk.flow-proxy-hierarchy-boundary-summary.v1",
        "phase": "phase6hk",
        "status": "qualified" if passed else "safe_stop",
        "contract_sha256": contract_hash,
        "attempt_count": 1,
        "retry_count": 0,
        "guard_exit_code": process.returncode,
        "run_status": None if run is None else run.get("status"),
        "last_marker": None if run is None else run.get("last_marker"),
        "resource_peaks_bytes": guard_result.get("peaks", {}),
        "resource_minima_bytes": guard_result.get("machine_minima", {}),
        "residual_zero": residual_zero,
        "production_code_changed": False,
        "production_defaults_changed": False,
        "point_policy_changed": False,
        "v3_changed": False,
        "latest_demo_changed": False,
        "readback_calls": 0 if run is None else run.get("readback_calls"),
        "details": str(output),
    }
    _write(artifact_root / "summary.json", summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
