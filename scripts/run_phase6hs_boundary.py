"""Run the one fresh Phase 6HS canonical-report proxy boundary."""

from __future__ import annotations

import argparse
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


CONTRACT = ROOT / "scripts/phase6hs_canonical_proxy_contract.json"
CONTRACT_SIDECAR = ROOT / "scripts/phase6hs_canonical_proxy_contract.sha256"
SCHEMA = ROOT / "scripts/phase6hs_operation_report_schema.json"
SCHEMA_SIDECAR = ROOT / "scripts/phase6hs_operation_report_schema.sha256"
CASE = ROOT / "scripts/run_phase6hs_kit_case.ps1"
PROBE = ROOT / "scripts/probe_phase6hs_flow_proxy_boundary.py"
PRODUCER = ROOT / "scripts/phase6hs_operation_report.py"
SYSTEM_PYTHON = Path(r"C:\Python38\python.exe")
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


def frozen_contract() -> tuple[dict, str, str]:
    contract_sha = sha256_bytes(CONTRACT.read_bytes())
    schema_sha = sha256_bytes(SCHEMA.read_bytes())
    if contract_sha != CONTRACT_SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6HS contract digest mismatch")
    if schema_sha != SCHEMA_SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6HS schema digest mismatch")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if policy["operation_report"]["schema_sha256"] != schema_sha:
        raise RuntimeError("Phase 6HS contract/schema binding mismatch")
    return policy, contract_sha, schema_sha


def build_target(paths: dict[str, Path], attempt_id: str, contract_sha: str) -> list[str]:
    return build_powershell_target(CASE, [
        "-RawOutputPath", str(paths["raw_output"]), "-CanonicalOutputPath", str(paths["output"]),
        "-MarkersPath", str(paths["markers"]), "-RunnerEvidencePath", str(paths["runner_evidence"]),
        "-KitLogPath", str(paths["kit_log"]), "-KitStdoutPath", str(paths["kit_stdout"]), "-KitStderrPath", str(paths["kit_stderr"]),
        "-KitPath", str(KIT), "-AppPath", str(APP), "-ProbePath", str(PROBE),
        "-ExpectedCampfirePath", str(CAMPFIRE), "-ExpectedAnimPath", str(ANIM),
        "-AttemptId", attempt_id, "-ProducerPath", str(PRODUCER), "-SchemaPath", str(SCHEMA),
        "-ContractSha256", contract_sha, "-SystemPythonPath", str(SYSTEM_PYTHON), "-StageCloseTimeoutSeconds", "180",
    ])


def validate_target(target: list[str]) -> tuple[bool, str]:
    checks = ((target[0],POWERSHELL,"root"),(target[target.index("-KitPath")+1],KIT,"kit"),(target[target.index("-AppPath")+1],APP,"app"),(target[target.index("-ProbePath")+1],PROBE,"probe"),(target[target.index("-ProducerPath")+1],PRODUCER,"producer"),(target[target.index("-SystemPythonPath")+1],SYSTEM_PYTHON,"python"))
    for actual, expected, name in checks:
        if norm(actual) != norm(expected):
            return False, name + "_path_mismatch"
    return True, "pass"


def functional_gates(report: dict) -> tuple[dict, dict]:
    raw = report.get("functional_evidence") or {}
    offline = raw.get("offline") or {}
    gates = offline.get("gates") or {}
    runtime = raw.get("runtime") or {}
    geometry = offline.get("geometry") or {}
    required_offline = (
        "baseline_digest_unchanged_after_proxy_exclusion", "only_proxy_prim_added", "proxy_mesh_type",
        "proxy_collision_api", "proxy_mesh_collision_api", "proxy_approximation", "proxy_invisible",
        "proxy_no_rigid_body", "topology_26_36_120", "topology_closed_outward", "world_matrices_equal",
        "point_prim_count_zero", "revision_attribute_count_zero",
    )
    result = {
        "all_offline_gates": all(gates.get(key) is True for key in required_offline),
        "baseline_digest_equal": offline.get("baseline_digest") == offline.get("candidate_without_proxy_digest"),
        "one_expected_proxy": offline.get("added_prims") == ["/World/Logs/Log_00/FlowCollisionProxy"],
        "geometry_exact": (geometry.get("vertex_count"),geometry.get("face_count"),geometry.get("index_count"),geometry.get("degenerate_face_count"),geometry.get("closed_manifold"),geometry.get("outward_winding")) == (26,36,120,0,True,True),
        "renderer_updates_30": runtime.get("renderer_updates") == 30,
        "timeline_stopped": runtime.get("timeline_playing") is False and raw.get("timeline_play_calls") == 0,
        "flow_interface_once": raw.get("flow_interface_calls") == 1 and isinstance(runtime.get("flow_identity"), int),
        "readback_zero": raw.get("readback_calls") == 0,
        "app_ready_gate": ((raw.get("app_ready_evidence") or {}).get("module_path_gate") or {}).get("passed") is True,
    }
    return result, raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--precondition-summary", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HS boundary refuses root reuse")
    policy, contract_sha, schema_sha = frozen_contract()
    precondition = json.loads(args.precondition_summary.read_text(encoding="utf-8"))
    if precondition.get("status") != "qualified":
        raise RuntimeError("Phase 6HS precondition did not pass")
    root.mkdir(parents=True)
    attempt = root / "attempt01"; logs = attempt / "runner-logs"; logs.mkdir(parents=True)
    for source, target in ((CONTRACT,root/"frozen_contract.json"),(CONTRACT_SIDECAR,root/"frozen_contract.sha256"),(SCHEMA,root/"frozen_operation_schema.json"),(SCHEMA_SIDECAR,root/"frozen_operation_schema.sha256")):
        shutil.copy2(source, target)
    before = hashes()
    paths = {
        "raw_output":attempt/"raw_operation.json", "output":attempt/"canonical_operation.json", "markers":attempt/"markers.jsonl",
        "runner_evidence":attempt/"runner_evidence.json", "kit_log":attempt/"kit.log", "kit_stdout":attempt/"kit.stdout.log", "kit_stderr":attempt/"kit.stderr.log",
        "trace":logs/"resource.jsonl", "summary":logs/"guard.json", "child_stdout":logs/"powershell.stdout.log", "child_stderr":logs/"powershell.stderr.log",
        "cleanup":logs/"cleanup.jsonl", "lifecycle":attempt/"canonical_operation.json", "gpu":logs/"gpu.csv",
    }
    attempt_id = "phase6hs-proxy-attempt01"
    target = build_target(paths, attempt_id, contract_sha)
    target_ok, target_reason = validate_target(target)
    write_json(attempt/"launch_contract.json", {"schema":"campfire.phase6hs.launch.v1","phase":"phase6hs","attempt_id":attempt_id,"target":target,"validation":[target_ok,target_reason],"cwd":str(ROOT)})
    if not target_ok:
        write_json(root/"summary.json", {"status":"safe_stop_pre_kit","reason":target_reason,"kit_launch_count":0})
        return 1
    command = build_guard_command(SYSTEM_PYTHON, ROOT/"scripts/phase6hs_resource_guard.py", paths, target, attempt_id=attempt_id, safety=policy["safety"], include_gpu=True)
    delimiter = command.index("--")
    command[delimiter:delimiter] = ["--runner-evidence-path",str(paths["runner_evidence"]),"--marker-path",str(paths["markers"]),"--contract-path",str(CONTRACT),"--schema-path",str(SCHEMA)]
    with (logs/"guard-launcher.stdout.log").open("wb",buffering=0) as stdout, (logs/"guard-launcher.stderr.log").open("wb",buffering=0) as stderr:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)); guard_exit=process.wait()

    guard=_read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    operation_validation, operation, _, _ = validate_paths(paths["output"],paths["markers"],expected_attempt_id=attempt_id,expected_schema_sha256=schema_sha,expected_contract_sha256=contract_sha) if paths["output"].is_file() else ({"accepted":False,"reason":"report_missing"},{},[],b"")
    canonical=consume_guard_report(guard or {},policy,expected_attempt_id=attempt_id,operation_validation=operation_validation)
    case=_read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else None
    samples=_read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
    roles_ok,role_failures,roles=validate_trace_roles(samples)
    gates,raw=functional_gates(operation)
    after=hashes(); invariants_pass=before==after
    passed=bool(operation_validation["accepted"] and canonical["accepted"] and guard_exit==0 and case and case.get("status")=="qualified" and all(gates.values()) and roles_ok and invariants_pass)
    cleanup={} if guard is None else guard.get("observed_process_cleanup") or {}
    evaluation=canonical.get("evaluation") or {}
    summary={
        "schema":"campfire.phase6hs.boundary-summary.v1","phase":"phase6hs","status":"qualified" if passed else "safe_stop",
        "contract_sha256":contract_sha,"operation_schema_sha256":schema_sha,"kit_launch_count":1,"retry_count":0,"replacement_count":0,
        "canonical_operation_validation":operation_validation,"guard_operation_validation":None if guard is None else guard.get("canonical_operation_validation"),
        "guard_parent_operation_validation_equal":guard is not None and guard.get("canonical_operation_validation")==operation_validation,
        "canonical_lifecycle_classification":canonical["classification"],"canonical_consumer_reason":canonical["reason"],
        "natural_clean_exit":evaluation.get("natural_exit") is True,"cleanup_intervention":evaluation.get("cleanup_intervention") is True,
        "allowed_helper_set":canonical.get("allowed_helper_set"),"cleanup_killed_pids":canonical.get("killed_pid_set"),
        "functional_gates":gates,"functional_evidence":raw,"kit_exit_code":operation.get("kit_exit_code"),
        "operation_completion":{"operation_complete":operation.get("operation_complete"),"stage_close_complete":operation.get("stage_close_complete"),"shutdown_complete":operation.get("shutdown_complete"),"last_marker":operation.get("last_marker")},
        "roles_pass":roles_ok,"roles":roles,"role_failures":role_failures,
        "resource_peaks_bytes":{} if guard is None else guard.get("peaks"),"resource_minima_bytes":{} if guard is None else guard.get("machine_minima"),
        "exact_cleanup_all_absent":cleanup.get("all_observed_absent") is True,"residual_process_count":0 if cleanup.get("all_observed_absent") is True else None,
        "guard_exit_code":guard_exit,"case_status":None if case is None else case.get("status"),"invariants_pass":invariants_pass,
        "invariant_hashes_before":before,"invariant_hashes_after":after,"phase6hr_reclassified":False,"phase6hr_artifact_reused":False,
        "production_changed":False,"defaults_changed":False,"point_policy_changed":False,"v3_changed":False,
    }
    write_json(root/"summary.json",summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
