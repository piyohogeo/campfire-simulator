"""No-Kit preflight for the Phase 6IF in-memory layer audit."""

from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path

import phase6ic_exact_dependency_loader as dependency_loader
from phase6hu_atomic_fixture import run_fixture as run_atomic
from phase6hx_point_policy_fixture import run_fixture as run_point
from phase6hy_exact_import_fixture import run_fixture as run_exact
from phase6ic_no_kit_fixture import run_fixture as run_dependencies
from phase6id_float3_fixture import run_fixture as run_float3
from phase6if_marker_fixture import run_fixture as run_markers
from phase6if_layer_opinion_fixture import run_fixture as run_layer

ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/"scripts"
CONTRACT=SCRIPTS/"phase6if_layer_opinion_contract.json";SIDECAR=SCRIPTS/"phase6if_layer_opinion_contract.sha256";MANIFEST=SCRIPTS/"phase6if_authoring_dependencies.json";MANIFEST_SHA=SCRIPTS/"phase6if_authoring_dependencies.sha256"
OLD_MANIFEST=SCRIPTS/"phase6id_authoring_dependencies.json";OLD_MANIFEST_SHA=SCRIPTS/"phase6id_authoring_dependencies.sha256";FROZEN=SCRIPTS/"phase6hx_single_log_occlusion_contract.json";POINT=SCRIPTS/"phase6hx_point_policy_source_set.json";POINT_SHA=SCRIPTS/"phase6hx_point_policy_source_set.sha256";REPORT_SCHEMA=SCRIPTS/"phase6hs_operation_report_schema.json"
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--output-root",type=Path,required=True);args=parser.parse_args();root=args.output_root.absolute()
 if root.exists():raise RuntimeError("Phase 6IF preflight refuses root reuse")
 root.mkdir(parents=True);policy=json.loads(CONTRACT.read_text(encoding="utf-8"));digest=sha(CONTRACT)
 layer=run_layer(root/"layer-opinion");markers=run_markers(root/"markers");float3=run_float3(root/"float3",FROZEN);dependencies=run_dependencies(root/"phase6id-dependencies",OLD_MANIFEST,OLD_MANIFEST_SHA,ROOT,FROZEN);exact=run_exact(root/"exact");point=run_point(root/"point",POINT,POINT_SHA,ROOT);atomic=run_atomic(root/"atomic",FROZEN,REPORT_SCHEMA)
 manifest,manifest_audit=dependency_loader.read_manifest(MANIFEST,MANIFEST_SHA,ROOT);selected=["stage_builder","atomic_report","stage_authoring","runtime_prim_policy","layer_opinion_audit"];modules,loaded=dependency_loader.load_dependencies(manifest,manifest_audit,module_ids=selected);modules["stage_authoring"].configure_repository_dependencies(modules["stage_builder"].topology);loaded_ok=[item["module_id"] for item in loaded]==selected and callable(modules["layer_opinion_audit"].snapshot_stage) and len(manifest_audit["modules"])==6;dependency_loader.unload_dependencies(loaded)
 checks={"contract_digest":digest==SIDECAR.read_text(encoding="ascii").split()[0].upper(),"manifest_digest":sha(MANIFEST)==MANIFEST_SHA.read_text(encoding="ascii").split()[0].upper()==policy["dependency_manifest"]["sha256"],"exact_dependency_load":loaded_ok,"phase6ie_frozen":policy["frozen_history"]["phase6ie"]["status"]=="safe_stop_runtime_prim_policy_and_lifecycle_failure" and policy["frozen_history"]["reclassified"] is False,"layer_fixture":layer["status"]=="qualified","marker_fixture":markers["status"]=="qualified","float3_fixture":float3["status"]=="qualified","dependency_fixture":dependencies["status"]=="qualified","exact_loader":exact["status"]=="qualified","point_policy":point["status"]=="qualified","atomic_report":atomic["status"]=="qualified","kit_not_launched":all(item["kit_launch_count"]==0 for item in (layer,markers,float3,dependencies,exact,point,atomic)),"one_runtime_launch":policy["smoke"]["launches"]==1 and policy["smoke"]["retry"]==policy["smoke"]["replacement"]==0,"forbidden_zero":all(policy["smoke"][name]==0 for name in ("timeline_play_calls","flow_simulation_update_calls","flow_interface_calls","readback_calls","capture_calls")),"single_stopped_update":policy["smoke"]["stopped_kit_update_calls"]==1,"legacy_policy_unqualified":policy["expected_phase6ie_observation"]["legacy_runtime_prim_policy"]=="remains_unqualified"}
 report={"schema":"campfire.phase6if.preflight.v1","phase":"phase6if","status":"qualified" if all(checks.values()) else "failed","contract_sha256":digest,"manifest_sha256":sha(MANIFEST),"kit_launch_count":0,"checks":checks,"fixture_counts":{"layer":layer["case_count"],"markers":markers["case_count"],"float3":float3["case_count"],"dependencies":dependencies["case_count"],"exact":[exact["case_count"],exact["case_count"]],"point":[point["case_count"],point["case_count"]],"atomic":[sum(item["passed"] for item in atomic["cases"]),len(atomic["cases"])],"manifest_modules":[len(loaded),len(manifest_audit["modules"])-1]},"phase6ie_reclassified":False,"phase6ie_artifact_or_runtime_reused":False}
 (root/"preflight_report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8");return 0 if report["status"]=="qualified" else 1
if __name__=="__main__":raise SystemExit(main())
