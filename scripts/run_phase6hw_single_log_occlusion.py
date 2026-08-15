"""Run the fixed fresh OFF/ON Phase 6HW diagnostic comparison."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from phase6hl_guard_preflight import _read_bounded, build_guard_command
from phase6hm_process_role_fixture import _read_jsonl
from phase6hm_process_tree_topology import build_powershell_target
from phase6hn_process_tree_topology import validate_trace_roles
from phase6ho_app_ready_environment import write_json
from phase6ho_process_tree_topology import ANIM, APP, CAMPFIRE, KIT, POWERSHELL, norm
from phase6hp_process_tree_topology import ROOT
from phase6hs_lifecycle_classification import consume_guard_report
from phase6hs_operation_report import sha256_bytes, validate_paths
from phase6hw_stage_builder import write_stage
from phase6hw_stage_contract import validate_stage
from phase6hw_temporal_occlusion import build_media, evaluate


CONTRACT = ROOT / "scripts/phase6hw_single_log_occlusion_contract.json"
SIDECAR = ROOT / "scripts/phase6hw_single_log_occlusion_contract.sha256"
SCHEMA = ROOT / "scripts/phase6hs_operation_report_schema.json"
CASE = ROOT / "scripts/run_phase6hw_kit_case.ps1"
PROBE = ROOT / "scripts/probe_phase6hw_single_log_occlusion.py"
PRODUCER = ROOT / "scripts/phase6hs_operation_report.py"
GUARD = ROOT / "scripts/phase6hs_resource_guard.py"
SYSTEM_PYTHON = Path(r"C:\Python38\python.exe")
INVARIANTS = {
    "production_source_app": ROOT / "source/apps/campfire.simulator.kit",
    "production_built_app": ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit",
    "production_scene": ROOT / "source/extensions/campfire.app/campfire/app/scene.py",
    "wood_authority": ROOT / "source/extensions/campfire.app/campfire/app/wood.py",
    "point_policy": ROOT / "source/extensions/campfire.app/campfire/app/point_emitter.py",
    "v3": ROOT / "source/extensions/campfire.app/campfire/app/wood_visual_v3.py",
    "latest_demo": ROOT / "docs/devlog/assets/latest_demo.json",
}


def hashes() -> dict[str, str]:
    return {name: hashlib.sha256(path.read_bytes()).hexdigest().upper() for name, path in INVARIANTS.items()}


def frozen_contract() -> tuple[dict, str, str]:
    data = CONTRACT.read_bytes()
    digest = sha256_bytes(data)
    if digest != SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6HW contract digest mismatch")
    policy = json.loads(data)
    schema_digest = sha256_bytes(SCHEMA.read_bytes())
    if policy["operation_report"]["schema_sha256"] != schema_digest:
        raise RuntimeError("Phase 6HW operation schema binding mismatch")
    return policy, digest, schema_digest


def paths_for(attempt: Path) -> dict[str, Path]:
    logs = attempt / "runner-logs"
    logs.mkdir(parents=True)
    return {
        "raw_output": attempt / "raw_operation.json", "output": attempt / "canonical_operation.json", "markers": attempt / "markers.jsonl",
        "runner_evidence": attempt / "runner_evidence.json", "kit_log": attempt / "kit.log", "kit_stdout": attempt / "kit.stdout.log", "kit_stderr": attempt / "kit.stderr.log",
        "trace": logs / "resource.jsonl", "summary": logs / "guard.json", "child_stdout": logs / "powershell.stdout.log", "child_stderr": logs / "powershell.stderr.log",
        "cleanup": logs / "cleanup.jsonl", "lifecycle": attempt / "canonical_operation.json", "gpu": logs / "gpu.csv",
    }


def build_target(paths: dict[str, Path], attempt_id: str, condition: str, stage: Path, contract_sha: str) -> list[str]:
    return build_powershell_target(CASE, [
        "-RawOutputPath", str(paths["raw_output"]), "-CanonicalOutputPath", str(paths["output"]), "-MarkersPath", str(paths["markers"]),
        "-RunnerEvidencePath", str(paths["runner_evidence"]), "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]),
        "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE), "-ExpectedCampfirePath", str(CAMPFIRE), "-ExpectedAnimPath", str(ANIM),
        "-AttemptId", attempt_id, "-Condition", condition, "-StagePath", str(stage), "-ProducerPath", str(PRODUCER), "-SchemaPath", str(SCHEMA),
        "-ContractPath", str(CONTRACT), "-ContractSha256", contract_sha, "-SystemPythonPath", str(SYSTEM_PYTHON), "-StageCloseTimeoutSeconds", "180",
    ])


def validate_target(target: list[str], condition: str, stage: Path) -> tuple[bool, str]:
    checks = ((target[0], POWERSHELL, "root"), (target[target.index("-KitPath") + 1], KIT, "kit"), (target[target.index("-AppPath") + 1], APP, "app"),
              (target[target.index("-ProbePath") + 1], PROBE, "probe"), (target[target.index("-ProducerPath") + 1], PRODUCER, "producer"),
              (target[target.index("-SystemPythonPath") + 1], SYSTEM_PYTHON, "python"), (target[target.index("-StagePath") + 1], stage, "stage"))
    for actual, expected, name in checks:
        if norm(actual) != norm(expected):
            return False, name + "_path_mismatch"
    if target[target.index("-Condition") + 1] != condition:
        return False, "condition_mismatch"
    return True, "pass"


def functional_gates(operation: dict, condition: str, policy: dict) -> tuple[dict, dict]:
    raw = operation.get("functional_evidence") or {}
    runtime = raw.get("runtime") or {}
    samples = runtime.get("active_blocks") or []
    captures = runtime.get("stable_captures") or []
    scene = policy["fixed_scene"]
    stage = raw.get("stage_contract") or {}
    gates = {
        "phase_and_condition": raw.get("phase") == "phase6hw" and raw.get("condition") == condition,
        "collision_switch": raw.get("collision_enabled") is (condition == "collision_on"),
        "stage_contract": stage.get("passed") is True,
        "topology_and_gap": ((stage.get("gates") or {}).get("topology_26_36_120") is True and (stage.get("gates") or {}).get("gap_at_least_one_velocity_voxel") is True and (stage.get("gates") or {}).get("end_clearance_at_least_16_velocity_voxels") is True),
        "flow_only_display": ((stage.get("gates") or {}).get("no_opaque_render_mesh") is True),
        "fixed_updates": runtime.get("simulation_updates") == scene["simulation_updates"] and runtime.get("preplay_updates") == scene["preplay_updates"] and runtime.get("renderer_drain_updates") == scene["renderer_drain_updates"],
        "active_block_frames": [item.get("frame") for item in samples] == scene["active_block_frames"],
        "flow_liveness": len(samples) == 4 and all(item.get("active_blocks", 0) >= policy["flow_liveness"]["active_blocks_each_sample_minimum"] for item in samples),
        "stable_capture_frames": [item.get("frame") for item in captures] == scene["stable_capture_frames"],
        "capture_count": raw.get("capture_calls") == 1 + len(scene["stable_capture_frames"]),
        "source_contract": runtime.get("source_center_m") == scene["source_center_m"] and runtime.get("source_radius_m") == scene["source_radius_m"] and runtime.get("source_surface_gap_m") == scene["source_surface_gap_m"],
        "end_clearance": runtime.get("end_clearance_m") == scene["source_to_nearest_end_clearance_m"],
        "timeline_stopped": runtime.get("timeline_playing_at_operation_complete") is False,
        "flow_interface_once": raw.get("flow_interface_calls") == 1,
        "readback_zero": raw.get("readback_calls") == 0,
    }
    return gates, raw


def prepare_stages(root: Path, policy: dict) -> dict:
    results = {}
    for condition in [item["name"] for item in policy["condition_order"]]:
        attempt = root / condition
        attempt.mkdir(parents=True)
        stage = attempt / "stages/candidate.usda"
        write_stage(stage, policy, condition)
        results[condition] = validate_stage(stage, policy, condition)
    off = (root / "collision_off/stages/candidate.usda").read_text(encoding="utf-8").splitlines()
    on = (root / "collision_on/stages/candidate.usda").read_text(encoding="utf-8").splitlines()
    changes = [line for line in difflib.ndiff(off, on) if line.startswith(("- ", "+ "))]
    result = {
        "schema": "campfire.phase6hw.prelaunch-stage-audit.v1",
        "conditions": results,
        "changed_lines": changes,
        "only_collision_switch": len(changes) == 2 and all("physicsCollisionEnabled" in line for line in changes),
        "passed": all(item["passed"] for item in results.values()) and len(changes) == 2 and all("physicsCollisionEnabled" in line for line in changes),
    }
    write_json(root / "prelaunch_stage_audit.json", result)
    return result


def run_condition(root: Path, condition: str, policy: dict, contract_sha: str, schema_sha: str) -> dict:
    attempt = root / condition
    stage = attempt / "stages/candidate.usda"
    paths = paths_for(attempt)
    attempt_id = f"phase6hw-{condition}-attempt01"
    target = build_target(paths, attempt_id, condition, stage, contract_sha)
    target_ok, target_reason = validate_target(target, condition, stage)
    write_json(attempt / "launch_contract.json", {"schema": "campfire.phase6hw.launch.v1", "attempt_id": attempt_id, "condition": condition, "target": target, "validation": [target_ok, target_reason], "cwd": str(ROOT)})
    if not target_ok:
        return {"status": "safe_stop_pre_kit", "reason": target_reason, "kit_launch_count": 0}
    command = build_guard_command(SYSTEM_PYTHON, GUARD, paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    delimiter = command.index("--")
    command[delimiter:delimiter] = ["--runner-evidence-path", str(paths["runner_evidence"]), "--marker-path", str(paths["markers"]), "--contract-path", str(CONTRACT), "--schema-path", str(SCHEMA)]
    with (attempt / "runner-logs/guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (attempt / "runner-logs/guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_exit = process.wait()
    guard = _read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    validation, operation, _, _ = validate_paths(paths["output"], paths["markers"], expected_attempt_id=attempt_id, expected_schema_sha256=schema_sha, expected_contract_sha256=contract_sha) if paths["output"].is_file() else ({"accepted": False, "reason": "report_missing"}, {}, [], b"")
    canonical = consume_guard_report(guard or {}, policy, expected_attempt_id=attempt_id, operation_validation=validation)
    case = _read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else None
    samples = _read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok, role_failures, roles = validate_trace_roles(samples)
    gates, raw = functional_gates(operation, condition, policy)
    cleanup = {} if guard is None else guard.get("observed_process_cleanup") or {}
    passed = bool(validation.get("accepted") and canonical.get("accepted") and guard_exit == 0 and case and case.get("status") == "qualified" and all(gates.values()) and roles_ok and cleanup.get("all_observed_absent") is True)
    result = {
        "schema": "campfire.phase6hw.condition-summary.v1", "condition": condition, "status": "qualified" if passed else "safe_stop", "attempt_id": attempt_id,
        "kit_launch_count": 1, "retry_count": 0, "replacement_count": 0, "canonical_operation_validation": validation,
        "canonical_lifecycle_classification": canonical.get("classification"), "canonical_consumer_reason": canonical.get("reason"),
        "functional_gates": gates, "functional_evidence": raw, "roles_pass": roles_ok, "roles": roles, "role_failures": role_failures,
        "resource_peaks_bytes": {} if guard is None else guard.get("peaks"), "resource_minima_bytes": {} if guard is None else guard.get("machine_minima"),
        "kit_exit_code": operation.get("kit_exit_code"), "exact_cleanup_all_absent": cleanup.get("all_observed_absent") is True,
        "residual_process_count": 0 if cleanup.get("all_observed_absent") is True else None, "guard_exit_code": guard_exit, "case_status": None if case is None else case.get("status"),
    }
    write_json(attempt / "condition_summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HW refuses artifact root reuse")
    if json.loads(args.preflight_report.read_text(encoding="utf-8")).get("status") != "qualified":
        raise RuntimeError("Phase 6HW no-Kit preflight missing")
    policy, contract_sha, schema_sha = frozen_contract()
    root.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json")
    shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    before = hashes()
    stage_audit = prepare_stages(root, policy)
    if not stage_audit["passed"]:
        write_json(root / "summary.json", {"schema": "campfire.phase6hw.summary.v1", "phase": "phase6hw", "status": "safe_stop_pre_kit", "stage_audit": stage_audit})
        return 1
    results = {}
    for condition in [item["name"] for item in policy["condition_order"]]:
        results[condition] = run_condition(root, condition, policy, contract_sha, schema_sha)
        if results[condition]["status"] != "qualified":
            write_json(root / "summary.json", {"schema": "campfire.phase6hw.summary.v1", "phase": "phase6hw", "status": "safe_stop", "conditions": results, "stopped_after": condition, "stage_audit": stage_audit, "phase6hv_reclassified": False, "production_changed": False})
            return 1
    visual, arrays = evaluate(root, policy, "pending")
    visual["media"] = build_media(root, policy, visual, arrays, root / "media")
    write_json(root / "temporal_evidence.json", visual)
    after = hashes()
    invariant = before == after
    status = "awaiting_human_review" if visual["automated_pass"] and invariant else "safe_stop"
    summary = {
        "schema": "campfire.phase6hw.summary.v1", "phase": "phase6hw", "status": status, "contract_sha256": contract_sha,
        "conditions": results, "stage_audit": stage_audit, "temporal_evidence": visual,
        "invariant_hashes_before": before, "invariant_hashes_after": after, "invariants_pass": invariant,
        "phase6hs_reclassified": False, "phase6hu_reclassified": False, "phase6hv_reclassified": False,
        "phase6hv_runtime_or_images_reused": False, "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", summary)
    return 0 if status == "awaiting_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
