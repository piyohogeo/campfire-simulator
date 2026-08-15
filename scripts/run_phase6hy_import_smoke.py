"""Run one exact Phase 6HY Kit app-ready import smoke behind Phase 6FU guard."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from phase6hl_guard_preflight import _read_bounded, build_guard_command
from phase6hm_process_tree_topology import build_powershell_target
from phase6ho_app_ready_environment import ROOT, write_json
from phase6ho_process_tree_topology import APP, KIT

SCRIPTS = ROOT / "scripts"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = SCRIPTS / "phase6fu_resource_guard.py"
CASE = SCRIPTS / "run_phase6hy_import_smoke_case.ps1"
PROBE = SCRIPTS / "probe_phase6hy_single_log_occlusion.py"


def run_smoke(root: Path, policy: dict) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6HY smoke refuses root reuse")
    root.mkdir(parents=True)
    logs = root / "runner-logs"
    logs.mkdir()
    attempt_id = "phase6hy-import-smoke-attempt01"
    paths = {
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log",
        "child_stderr": logs / "powershell.stderr.log", "cleanup": logs / "cleanup.jsonl", "lifecycle": root / "import_audit.json", "gpu": logs / "gpu.csv",
    }
    runner_evidence = root / "runner_evidence.json"
    markers = root / "markers.jsonl"
    target = build_powershell_target(CASE, [
        "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE), "-MarkersPath", str(markers),
        "-AuditPath", str(root / "import_audit.json"), "-RunnerEvidencePath", str(runner_evidence),
        "-KitLogPath", str(root / "kit.log"), "-KitStdoutPath", str(root / "kit.stdout.log"), "-KitStderrPath", str(root / "kit.stderr.log"),
        "-AttemptId", attempt_id,
    ])
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=False)
    with (logs / "launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}
    runner = _read_bounded(runner_evidence) if runner_evidence.is_file() else {}
    audit = _read_bounded(root / "import_audit.json") if (root / "import_audit.json").is_file() else {}
    cleanup = guard.get("observed_process_cleanup") or {}
    resource_pass = not guard.get("limit_reached") and guard.get("stop_reason") not in {"resource_limit", "machine_floor"}
    lifecycle = "natural_clean_exit" if runner.get("status") == "qualified" and runner.get("process_exit_code") == 0 else "cleanup_failure"
    accepted = bool(guard_exit == 0 and runner.get("status") == "qualified" and audit.get("status") == "qualified" and resource_pass and cleanup.get("all_observed_absent") is True)
    result = {
        "schema": "campfire.phase6hy.import-smoke-summary.v1", "phase": "phase6hy", "status": "qualified" if accepted else "safe_stop",
        "attempt_id": attempt_id, "kit_launch_count": 1, "guard_exit_code": guard_exit, "kit_exit_code": runner.get("process_exit_code"),
        "lifecycle_classification": lifecycle, "accepted_lifecycle": accepted, "resource_pass": resource_pass,
        "resource_peaks_bytes": guard.get("peaks", {}), "resource_minima_bytes": guard.get("machine_minima", {}),
        "exact_cleanup_all_absent": cleanup.get("all_observed_absent") is True, "residual_process_count": 0 if cleanup.get("all_observed_absent") is True else None,
        "audit": audit, "runner": runner, "guard_status": guard.get("status"), "guard_stop_reason": guard.get("stop_reason"),
        "flow_stage_or_capture_started": False,
    }
    write_json(root / "smoke_summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=SCRIPTS / "phase6hy_exact_kit_import_contract.json")
    args = parser.parse_args()
    policy = json.loads(args.contract.read_text(encoding="utf-8"))
    result = run_smoke(args.artifact_root.absolute(), policy)
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
