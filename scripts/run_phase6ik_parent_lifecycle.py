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
from phase6hr_lifecycle_classification import consume_guard_report
from phase6ik_parent_lifecycle_boundary import classify_boundary, read_jsonl, validate_markers, validate_runner_evidence
from run_phase6hz_import_smoke import hashes as invariant_hashes

S = ROOT / "scripts"
CONTRACT = S / "phase6ik_parent_lifecycle_contract.json"
SIDECAR = S / "phase6ik_parent_lifecycle_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = S / "phase6ik_resource_guard.py"
CASE = S / "run_phase6ik_minimal_lifecycle_case.ps1"
PROBE = S / "probe_phase6ik_minimal_lifecycle.py"


def run(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6IK runtime refuses root reuse")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    preflight = _read_bounded(preflight_path)
    if digest != SIDECAR.read_text().split()[0].upper() or preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest:
        raise RuntimeError("Phase 6IK preflight/contract invalid")
    root.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json")
    shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    attempt_id = "phase6ik-parent-lifecycle-01"
    attempt = root / "attempt-01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    paths = {
        "output": attempt / "minimal_operation_report.json", "lifecycle": attempt / "minimal_operation_report.json",
        "markers": attempt / "boundary_markers.jsonl", "runner_evidence": attempt / "runner_evidence.json",
        "kit_log": attempt / "kit.log", "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log",
        "child_stderr": logs / "powershell.stderr.log", "cleanup": logs / "cleanup.jsonl", "gpu": logs / "gpu.csv",
    }
    ps = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    target = [str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE), "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE), "-MarkersPath", str(paths["markers"]), "-ReportPath", str(paths["output"]), "-RunnerEvidencePath", str(paths["runner_evidence"]), "-ContractPath", str(CONTRACT), "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]), "-AttemptId", attempt_id]
    write_json(attempt / "launch_contract.json", {"schema":"campfire.phase6ik.launch.v1","attempt_id":attempt_id,"target":target,"cwd":str(ROOT)})
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    index = command.index("--")
    command[index:index] = ["--runner-evidence-path", str(paths["runner_evidence"]), "--marker-path", str(paths["markers"]), "--contract-path", str(CONTRACT), "--mode", "smoke"]
    before = invariant_hashes()
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    after = invariant_hashes()
    rows = read_jsonl(paths["markers"]) if paths["markers"].is_file() else []
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}
    runner = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {}
    operation = _read_bounded(paths["output"]) if paths["output"].is_file() else {}
    trace = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, roles = validate_trace_roles(trace)
    marker_validation = validate_markers(rows, attempt_id) if rows else {"accepted":False,"reasons":["markers_missing"],"steps":[]}
    runner_validation = validate_runner_evidence(runner, rows, attempt_id) if runner else {"accepted":False,"reasons":["runner_evidence_missing"]}
    canonical = consume_guard_report(guard, policy, expected_attempt_id=attempt_id) if guard else {"accepted":False,"classification":"cleanup_failure","reason":"guard_missing"}
    cleanup = guard.get("observed_process_cleanup") or {}
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
    cleanup_pass = cleanup.get("all_observed_absent") is True
    fatal_or_dump = bool(runner.get("fatal_lines") or runner.get("dump_inventory") or runner.get("automatic_upload_attempt_lines"))
    decision = classify_boundary(rows, fixture_pass=True, runtime_started=True, resource_pass=resource_pass, cleanup_pass=cleanup_pass, fatal_or_dump=fatal_or_dump)
    complete = all((marker_validation["accepted"], runner_validation["accepted"], canonical.get("accepted"), roles_ok, resource_pass, cleanup_pass, guard_exit == 0, operation.get("operation_complete") is True, operation.get("shutdown_complete") is True, before == after))
    if complete:
        decision = {"status":"parent_lifecycle_evidence_boundary_qualified","last_completed_step":"outer_guard_return","first_incomplete_step":None,"cause_boundary":"complete"}
    result = {
        "schema":"campfire.phase6ik.summary.v1", "phase":"phase6ik", "status":decision["status"], "contract_sha256":digest,
        "attempt_id":attempt_id, "kit_launch_count":1, "retry_count":0, "replacement_count":0,
        "boundary_timeline":[{key:row.get(key) for key in ("step_id","actor","pid","creation_time_utc_epoch","timestamp_utc_epoch","monotonic_elapsed_seconds")} for row in rows],
        "last_completed_marker":decision["last_completed_step"], "first_incomplete_step":decision["first_incomplete_step"], "cause_boundary":decision["cause_boundary"],
        "operation_report":operation, "marker_validation":marker_validation, "runner_validation":runner_validation,
        "guard_exit_code":guard_exit, "kit_exit_code":runner.get("process_exit_code"), "canonical_lifecycle":canonical,
        "roles_pass":roles_ok, "role_failures":role_failures, "roles":roles,
        "resource_pass":resource_pass, "resource_peaks_bytes":peaks, "resource_minima_bytes":minima,
        "resource_headroom_bytes":{"kit":safety["kit_private_limit_bytes"]-peaks.get("kit",0),"tree":safety["unique_tree_private_limit_bytes"]-peaks.get("tree",0)},
        "cleanup_pass":cleanup_pass, "residual_process_count":0 if cleanup_pass else None,
        "fatal_lines":runner.get("fatal_lines") or [], "dump_inventory":runner.get("dump_inventory") or [], "automatic_upload_attempt_lines":runner.get("automatic_upload_attempt_lines") or [],
        "invariant_hashes_before":before, "invariant_hashes_after":after, "invariants_pass":before==after,
        "phase6ij_reclassified":False, "phase6ij_artifact_reused":False, "phase6ij_rerun":False, "abc_ladder_rerun":False,
        "production_changed":False, "defaults_changed":False, "point_policy_changed":False, "v3_changed":False, "latest_demo_changed":False,
    }
    write_json(root / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-summary", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.artifact_root.absolute(), args.preflight_summary.absolute())
    return 0 if result["status"] == "parent_lifecycle_evidence_boundary_qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
