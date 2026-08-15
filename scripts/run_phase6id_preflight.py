"""No-Kit preflight for Phase 6ID float3 stage-open boundary."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from phase6hu_atomic_fixture import run_fixture as run_atomic
from phase6hx_point_policy_fixture import run_fixture as run_point
from phase6hy_exact_import_fixture import run_fixture as run_exact
from phase6ic_no_kit_fixture import run_fixture as run_dependencies
from phase6id_float3_fixture import run_fixture as run_float3

ROOT=Path(__file__).resolve().parents[1]; SCRIPTS=ROOT/"scripts"
CONTRACT=SCRIPTS/"phase6id_stage_open_contract.json"; SIDECAR=SCRIPTS/"phase6id_stage_open_contract.sha256"; MANIFEST=SCRIPTS/"phase6id_authoring_dependencies.json"; MANIFEST_SHA=SCRIPTS/"phase6id_authoring_dependencies.sha256"; FROZEN=SCRIPTS/"phase6hx_single_log_occlusion_contract.json"; POINT=SCRIPTS/"phase6hx_point_policy_source_set.json"; POINT_SHA=SCRIPTS/"phase6hx_point_policy_source_set.sha256"; SCHEMA=SCRIPTS/"phase6hs_operation_report_schema.json"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output-root",type=Path,required=True); args=parser.parse_args(); root=args.output_root.absolute()
    if root.exists(): raise RuntimeError("Phase 6ID preflight refuses root reuse")
    root.mkdir(parents=True); policy=json.loads(CONTRACT.read_text(encoding="utf-8")); digest=sha(CONTRACT)
    float3=run_float3(root/"float3",FROZEN); dependencies=run_dependencies(root/"dependencies",MANIFEST,MANIFEST_SHA,ROOT,FROZEN); exact=run_exact(root/"exact"); point=run_point(root/"point",POINT,POINT_SHA,ROOT); atomic=run_atomic(root/"atomic",FROZEN,SCHEMA)
    checks={"contract_digest":digest==SIDECAR.read_text(encoding="ascii").split()[0].upper(),"manifest_digest":sha(MANIFEST)==MANIFEST_SHA.read_text(encoding="ascii").split()[0].upper()==policy["dependency_manifest"]["sha256"],"phase6ic_frozen":policy["frozen_history"]["phase6ic"]["status"]=="safe_stop_stage_attribute_validation_failure" and policy["frozen_history"]["reclassified"] is False,"float3_fixture":float3["status"]=="qualified","dependency_fixture":dependencies["status"]=="qualified","exact_loader":exact["status"]=="qualified","point_policy":point["status"]=="qualified","atomic_report":atomic["status"]=="qualified","kit_not_launched":all(item["kit_launch_count"]==0 for item in (float3,dependencies,exact,point,atomic)),"one_runtime_launch":policy["smoke"]["launches"]==1 and policy["smoke"]["retry"]==policy["smoke"]["replacement"]==0,"forbidden_zero":all(policy["smoke"][name]==0 for name in ("timeline_play_calls","flow_update_calls","flow_interface_calls","readback_calls","capture_calls"))}
    report={"schema":"campfire.phase6id.preflight.v1","phase":"phase6id","status":"qualified" if all(checks.values()) else "failed","contract_sha256":digest,"manifest_sha256":sha(MANIFEST),"kit_launch_count":0,"checks":checks,"fixture_counts":{"float3":float3["case_count"],"dependencies":dependencies["case_count"],"exact":[exact["case_count"],exact["case_count"]],"point":[point["case_count"],point["case_count"]],"atomic":[sum(item["passed"] for item in atomic["cases"]),len(atomic["cases"])]},"phase6ic_reclassified":False,"phase6ic_artifact_or_runtime_reused":False}
    (root/"preflight_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); return 0 if report["status"]=="qualified" else 1
if __name__=="__main__": raise SystemExit(main())
