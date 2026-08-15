"""Run exactly one Phase 6HZ Kit app-ready exact-import smoke."""

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
from phase6hx_point_policy_invariant import produce_report as point_policy_report


SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6hz_import_smoke_contract.json"
SIDECAR = SCRIPTS / "phase6hz_import_smoke_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")
GUARD = SCRIPTS / "phase6hr_resource_guard.py"
CASE = SCRIPTS / "run_phase6hz_import_smoke_case.ps1"
PROBE = SCRIPTS / "probe_phase6hz_import_smoke.py"
POINT_MANIFEST = SCRIPTS / "phase6hx_point_policy_source_set.json"
POINT_SIDECAR = SCRIPTS / "phase6hx_point_policy_source_set.sha256"
INVARIANTS = {
    "production_source_app": ROOT / "source/apps/campfire.simulator.kit",
    "production_built_app": ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit",
    "production_scene": ROOT / "source/extensions/campfire.app/campfire/app/scene.py",
    "wood_authority": ROOT / "source/extensions/campfire.app/campfire/app/wood.py",
    "v3": ROOT / "source/extensions/campfire.app/campfire/app/wood_visual_v3.py",
    "latest_demo": ROOT / "docs/devlog/assets/latest_demo.json",
}


def hashes() -> dict:
    result = {key: hashlib.sha256(path.read_bytes()).hexdigest().upper() for key, path in INVARIANTS.items()}
    point = point_policy_report(POINT_MANIFEST, POINT_SIDECAR, ROOT, "phase6hz-invariant")
    result["point_policy_manifest"] = point["manifest_sha256"]
    result["point_policy_order"] = point["ordered_entries_sha256"]
    result["point_policy_entries"] = {entry["path"]: entry["sha256"] for entry in point["entries"]}
    return result


def _contract() -> tuple[dict, str]:
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    if digest != SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6HZ contract digest mismatch")
    return json.loads(CONTRACT.read_text(encoding="utf-8")), digest


def run_smoke(root: Path, preflight_path: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6HZ smoke refuses root reuse")
    policy, digest = _contract()
    preflight = _read_bounded(preflight_path)
    if preflight.get("status") != "qualified" or preflight.get("contract_sha256") != digest:
        raise RuntimeError("Phase 6HZ preflight did not qualify this contract")
    root.mkdir(parents=True)
    attempt = root / "attempt01"
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json")
    shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    before = hashes()
    attempt_id = "phase6hz-import-smoke-attempt01"
    paths = {
        "output": attempt / "import_audit.json", "markers": attempt / "markers.jsonl",
        "runner_evidence": attempt / "runner_evidence.json", "kit_log": attempt / "kit.log",
        "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json",
        "child_stdout": logs / "powershell.stdout.log", "child_stderr": logs / "powershell.stderr.log",
        "cleanup": logs / "cleanup.jsonl", "lifecycle": attempt / "import_audit.json", "gpu": logs / "gpu.csv",
    }
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    target = [
        str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(CASE),
        "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE), "-MarkersPath", str(paths["markers"]),
        "-AuditPath", str(paths["output"]), "-RunnerEvidencePath", str(paths["runner_evidence"]), "-ContractPath", str(CONTRACT),
        "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]),
        "-AttemptId", attempt_id,
    ]
    write_json(attempt / "launch_contract.json", {
        "schema": "campfire.phase6hz.launch.v1", "phase": "phase6hz", "mode": "smoke", "target": target,
        "attempt_id": attempt_id, "stage_flow_collision_emitter_capture_forbidden": True, "cwd": str(ROOT),
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
    samples = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, roles = validate_trace_roles(samples)
    canonical = consume_guard_report(guard, policy, expected_attempt_id=attempt_id)
    after = hashes()
    cleanup = guard.get("observed_process_cleanup") or {}
    accepted = bool(
        guard_exit == 0 and canonical["accepted"] and audit.get("status") == "qualified" and
        runner.get("status") == "qualified" and roles_ok and before == after and cleanup.get("all_observed_absent") is True
    )
    markers = runner.get("marker_names") or []
    result = {
        "schema": "campfire.phase6hz.import-smoke-summary.v1", "phase": "phase6hz",
        "status": "qualified" if accepted else "safe_stop", "attempt_id": attempt_id, "contract_sha256": digest,
        "kit_launch_count": 1, "retry_count": 0, "replacement_count": 0, "guard_exit_code": guard_exit,
        "last_marker": markers[-1] if markers else None, "marker_names": markers,
        "exact_probe_import_complete": audit.get("loaded_module_file") == str((ROOT / policy["sources"]["probe_builder"]["path"]).resolve()),
        "required_callable_validated": bool(audit.get("required_callable_identity")),
        "canonical_lifecycle_classification": canonical["classification"], "canonical_consumer_reason": canonical["reason"],
        "kit_exit_code": runner.get("process_exit_code"), "resource_peaks_bytes": guard.get("peaks", {}),
        "resource_minima_bytes": guard.get("machine_minima", {}), "roles_pass": roles_ok, "roles": roles, "role_failures": role_failures,
        "exact_cleanup_all_absent": cleanup.get("all_observed_absent") is True,
        "residual_process_count": 0 if cleanup.get("all_observed_absent") is True else None,
        "invariants_pass": before == after, "invariant_hashes_before": before, "invariant_hashes_after": after,
        "stage_created": audit.get("stage_created"), "flow_interface_calls": audit.get("flow_interface_calls"),
        "readback_calls": audit.get("readback_calls"), "collision_proxy_created": audit.get("collision_proxy_created"),
        "capture_calls": audit.get("capture_calls"), "phase6hy_reclassified": False,
        "phase6hy_artifact_or_runtime_reused": False, "production_changed": False, "defaults_changed": False,
        "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
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

