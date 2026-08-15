"""Run exactly one Phase 6IE actual-Kit bounded live-stage Prim smoke."""

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
from phase6ie_runtime_prim_policy import read_evidence
from run_phase6hz_import_smoke import hashes as invariant_hashes


SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6ie_stage_open_contract.json"
SIDECAR = SCRIPTS / "phase6ie_stage_open_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = SCRIPTS / "phase6hr_resource_guard.py"
CASE = SCRIPTS / "run_phase6ic_stage_open_case.ps1"
PROBE = SCRIPTS / "probe_phase6ie_stage_open_smoke.py"


def _contract() -> tuple[dict, str]:
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    if digest != SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6IE contract digest mismatch")
    return json.loads(CONTRACT.read_text(encoding="utf-8")), digest


def run_smoke(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6IE smoke refuses root reuse")
    policy, digest = _contract()
    preflight = _read_bounded(preflight_path)
    if preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest:
        raise RuntimeError("Phase 6IE preflight did not qualify this contract")
    root.mkdir(parents=True)
    attempt = root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    for source, target in (
        (CONTRACT, "frozen_contract.json"),
        (SIDECAR, "frozen_contract.sha256"),
        (SCRIPTS / "phase6ie_authoring_dependencies.json", "frozen_dependency_manifest.json"),
        (SCRIPTS / "phase6ie_authoring_dependencies.sha256", "frozen_dependency_manifest.sha256"),
    ):
        shutil.copy2(source, root / target)
    before = invariant_hashes()
    attempt_id = "phase6ie-stage-open-attempt01"
    paths = {
        "output": attempt / "stage_open_audit.json",
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
        "lifecycle": attempt / "stage_open_audit.json",
        "gpu": logs / "gpu.csv",
    }
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    target = [
        str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE),
        "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE),
        "-MarkersPath", str(paths["markers"]), "-AuditPath", str(paths["output"]),
        "-StageRoot", str(attempt / "generated-stages"), "-RunnerEvidencePath", str(paths["runner_evidence"]),
        "-ContractPath", str(CONTRACT), "-KitLogPath", str(paths["kit_log"]),
        "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]),
        "-AttemptId", attempt_id, "-SettingsPrefix", "phase6ie",
    ]
    write_json(attempt / "launch_contract.json", {
        "schema": "campfire.phase6ie.launch.v1", "phase": "phase6ie", "attempt_id": attempt_id,
        "target": target, "cwd": str(ROOT), "forbidden_runtime_operations": True,
    })
    command = build_guard_command(PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    delimiter = command.index("--")
    command[delimiter:delimiter] = [
        "--runner-evidence-path", str(paths["runner_evidence"]), "--marker-path", str(paths["markers"]),
        "--contract-path", str(CONTRACT), "--mode", "smoke",
    ]
    with (logs / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (logs / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()

    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else {}
    audit = _read_bounded(paths["output"]) if paths["output"].is_file() else {}
    runner = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {}
    runtime_evidence_path = attempt / "runtime_prim_policy.json"
    runtime_evidence = read_evidence(runtime_evidence_path) if runtime_evidence_path.is_file() else {}
    samples = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, roles = validate_trace_roles(samples)
    canonical = consume_guard_report(guard, policy, expected_attempt_id=attempt_id)
    after = invariant_hashes()
    cleanup = guard.get("observed_process_cleanup") or {}
    markers = runner.get("marker_names") or []
    parser_fixture = audit.get("parser_fixture") or {}
    stage = audit.get("stage") or {}
    float3_evidence = audit.get("float3_evidence") or []
    required_markers = policy["smoke"]["required_markers"]
    markers_complete = all(name in markers for name in required_markers)
    root_before = runtime_evidence.get("root_layer_sha256_before")
    root_after = runtime_evidence.get("root_layer_sha256_after")
    accepted = bool(
        guard_exit == 0
        and canonical["accepted"]
        and audit.get("status") == "qualified"
        and audit.get("operation_complete") is True
        and audit.get("shutdown_complete") is True
        and (audit.get("lifecycle") or {}).get("stage_close_complete") is True
        and parser_fixture.get("positive_count") == 2
        and parser_fixture.get("negative_count") == 6
        and (parser_fixture.get("one_variable_difference") or {}).get("accepted") is True
        and (stage.get("validation") or {}).get("condition") == "collision_off"
        and len(float3_evidence) >= 3
        and all(item.get("accepted") is True and item.get("maximum_ulp_distance") == 0 for item in float3_evidence)
        and runtime_evidence.get("accepted") is True
        and runtime_evidence.get("runtime_prim_count", 99) <= policy["runtime_prim_policy"]["maximum_runtime_prims"]
        and runtime_evidence.get("unknown_prims") == []
        and runtime_evidence.get("protected_conflicts") == []
        and runtime_evidence.get("authored_prim_missing") == []
        and runtime_evidence.get("authored_prim_changed") == []
        and root_before == root_after == stage.get("root_layer_sha256")
        and markers_complete
        and runner.get("status") == "qualified"
        and roles_ok
        and before == after
        and cleanup.get("all_observed_absent") is True
    )
    result = {
        "schema": "campfire.phase6ie.stage-open-summary.v1", "phase": "phase6ie",
        "status": "qualified" if accepted else "safe_stop", "attempt_id": attempt_id,
        "contract_sha256": digest, "kit_launch_count": 1, "retry_count": 0, "replacement_count": 0,
        "guard_exit_code": guard_exit, "last_marker": markers[-1] if markers else None,
        "marker_names": markers, "required_markers_complete": markers_complete,
        "float3_evidence": float3_evidence, "parser_fixture": parser_fixture, "stage": stage,
        "runtime_prim_policy": runtime_evidence,
        "canonical_lifecycle_classification": canonical["classification"], "canonical_consumer_reason": canonical["reason"],
        "kit_exit_code": runner.get("process_exit_code"), "resource_peaks_bytes": guard.get("peaks", {}),
        "resource_minima_bytes": guard.get("machine_minima", {}), "roles_pass": roles_ok,
        "roles": roles, "role_failures": role_failures,
        "exact_cleanup_all_absent": cleanup.get("all_observed_absent") is True,
        "residual_process_count": 0 if cleanup.get("all_observed_absent") is True else None,
        "fatal_lines": runner.get("fatal_lines") or [], "dump_inventory": runner.get("dump_inventory") or [],
        "automatic_upload_attempt_lines": runner.get("automatic_upload_attempt_lines") or [],
        "invariants_pass": before == after, "invariant_hashes_before": before, "invariant_hashes_after": after,
        "phase6id_reclassified": False, "phase6id_artifact_or_runtime_reused": False,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False,
        "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-summary", type=Path, required=True)
    args = parser.parse_args()
    result = run_smoke(args.artifact_root.absolute(), args.preflight_summary.absolute())
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
