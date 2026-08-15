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
from run_phase6hz_import_smoke import hashes as invariant_hashes
import phase6ii_marker_contract as marker_contract
import phase6ii_stage_composition_ladder as ladder

S = ROOT / "scripts"
CONTRACT = S / "phase6ii_stage_open_composition_contract.json"
SIDECAR = S / "phase6ii_stage_open_composition_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = S / "phase6hr_resource_guard.py"
CASE = S / "run_phase6ii_stage_open_composition_case.ps1"
PROBE = S / "probe_phase6ii_stage_open_composition.py"


def _attempt(root: Path, condition: str, policy: dict, digest: str) -> dict:
    attempt_id = "phase6ii-stage-open-" + condition.lower()
    attempt = root / ("attempt-" + condition)
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    paths = {
        "output": attempt / "operation_report.json", "identity": attempt / "opened_stage_identity.json",
        "markers": attempt / "markers.jsonl", "runner_evidence": attempt / "runner_evidence.json",
        "kit_log": attempt / "kit.log", "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log",
        "child_stderr": logs / "powershell.stderr.log", "cleanup": logs / "cleanup.jsonl", "lifecycle": attempt / "operation_report.json", "gpu": logs / "gpu.csv",
    }
    ps = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    target = [str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE), "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE), "-MarkersPath", str(paths["markers"]), "-ReportPath", str(paths["output"]), "-IdentityPath", str(paths["identity"]), "-StageRoot", str(attempt / "generated-stages"), "-RunnerEvidencePath", str(paths["runner_evidence"]), "-ContractPath", str(CONTRACT), "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]), "-Condition", condition, "-AttemptId", attempt_id]
    write_json(attempt / "launch_contract.json", {"schema": "campfire.phase6ii.launch.v1", "phase": "phase6ii", "attempt_id": attempt_id, "condition": condition, "target": target, "cwd": str(ROOT)})
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    index = command.index("--")
    command[index:index] = ["--runner-evidence-path", str(paths["runner_evidence"]), "--marker-path", str(paths["markers"]), "--contract-path", str(CONTRACT), "--mode", "smoke"]
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as out, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as err:
        process = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=err, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}
    operation = ladder.read_bounded(paths["output"]) if paths["output"].is_file() else {}
    runner = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {}
    samples = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, roles = validate_trace_roles(samples)
    canonical = consume_guard_report(guard, policy, expected_attempt_id=attempt_id)
    cleanup = guard.get("observed_process_cleanup") or {}
    marker_rows = _read_jsonl(paths["markers"]) if paths["markers"].is_file() else []
    marker_result = marker_contract.validate_sequence(marker_rows)
    operation_result = ladder.validate_operation(operation, attempt_id, condition) if operation else {"accepted": False, "reasons": ["operation_report_missing"]}
    qualified = operation_result["accepted"] and marker_result["accepted"] and runner.get("process_exit_code") == 0 and canonical.get("accepted") and cleanup.get("all_observed_absent") is True and roles_ok and not runner.get("fatal_lines") and not runner.get("dump_inventory") and not runner.get("automatic_upload_attempt_lines")
    return {
        "condition": condition, "attempt_id": attempt_id, "qualified": qualified, "guard_exit_code": guard_exit,
        "operation_validation": operation_result, "marker_validation": marker_result, "operation_report": operation,
        "kit_exit_code": runner.get("process_exit_code"), "lifecycle_classification": canonical.get("classification"), "lifecycle_reason": canonical.get("reason"),
        "resource_peaks_bytes": guard.get("peaks", {}), "resource_minima_bytes": guard.get("machine_minima", {}),
        "roles_pass": roles_ok, "roles": roles, "role_failures": role_failures,
        "exact_cleanup_all_absent": cleanup.get("all_observed_absent") is True,
        "residual_process_count": 0 if cleanup.get("all_observed_absent") is True else None,
        "fatal_lines": runner.get("fatal_lines") or [], "dump_inventory": runner.get("dump_inventory") or [],
        "automatic_upload_attempt_lines": runner.get("automatic_upload_attempt_lines") or [],
        "last_marker": marker_rows[-1].get("marker") if marker_rows else None,
        "first_failure_boundary": operation.get("first_failure_boundary") if operation else "operation_report_missing",
        "kit_launch_count": runner.get("kit_launch_count", 0),
    }


def run(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6II runtime refuses root reuse")
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    policy = json.loads(CONTRACT.read_text())
    preflight = _read_bounded(preflight_path)
    if digest != SIDECAR.read_text().split()[0].upper() or preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest:
        raise RuntimeError("Phase 6II preflight/contract invalid")
    root.mkdir(parents=True)
    for source, target in ((CONTRACT, "frozen_contract.json"), (SIDECAR, "frozen_contract.sha256"), (S / "phase6ii_authoring_dependencies.json", "frozen_dependency_manifest.json"), (S / "phase6ii_authoring_dependencies.sha256", "frozen_dependency_manifest.sha256")):
        shutil.copy2(source, root / target)
    before = invariant_hashes()
    attempts = []
    for condition in policy["operation_contract"]["condition_order"]:
        result = _attempt(root, condition, policy, digest)
        attempts.append(result)
        write_json(root / "aggregate.partial.json", {"phase": "phase6ii", "attempts": attempts})
        if not result["qualified"]:
            break
    after = invariant_hashes()
    all_pass = len(attempts) == 3 and all(row["qualified"] for row in attempts)
    failed = next((row for row in attempts if not row["qualified"]), None)
    if all_pass:
        status = "stage_open_composition_ladder_qualified"
    elif failed and (failed["kit_launch_count"] == 0 or failed["first_failure_boundary"] == "pre_open_harness"):
        status = "safe_stop_stage_open_harness_failure"
    elif failed and (failed["dump_inventory"] or failed["fatal_lines"] or failed["kit_exit_code"] == 3221225477):
        status = "safe_stop_stage_open_native_failure_unlocalized"
    elif failed and failed["condition"] in ("B", "C") and all(row["qualified"] for row in attempts[:-1]):
        status = "safe_stop_stage_open_composition_specific_failure"
    else:
        status = "safe_stop_stage_open_native_failure_unlocalized"
    result = {
        "schema": "campfire.phase6ii.summary.v1", "phase": "phase6ii", "status": status,
        "contract_sha256": digest, "condition_order": ["A", "B", "C"], "requested_D_mapping": "C",
        "attempts": attempts, "kit_launch_count": sum(row["kit_launch_count"] for row in attempts), "retry_count": 0, "replacement_count": 0,
        "last_fully_qualified_condition": next((row["condition"] for row in reversed(attempts) if row["qualified"]), None),
        "first_failed_condition": failed["condition"] if failed else None,
        "invariant_hashes_before": before, "invariant_hashes_after": after, "invariants_pass": before == after,
        "phase6ih_reclassified": False, "phase6ih_contract_artifact_dump_reused": False,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-summary", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.artifact_root.absolute(), args.preflight_summary.absolute())
    return 0 if result["status"] == "stage_open_composition_ladder_qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
