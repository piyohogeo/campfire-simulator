"""No-Kit audit and fixtures for Phase 6HO."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from phase6ho_app_ready_environment import deployment_descriptor, historical_audit, validate_deployment, write_json
from phase6ho_process_tree_topology import APP, KIT, build_target, validate_target
from phase6hl_guard_preflight import build_guard_command

ROOT = Path(__file__).absolute().parents[1]

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--artifact-root",type=Path,required=True);args=parser.parse_args()
    root=args.artifact_root.absolute()
    if root.exists(): raise RuntimeError("Phase 6HO preflight refuses root reuse")
    root.mkdir(parents=True)
    contract=ROOT/"scripts/phase6ho_app_ready_contract.json";sidecar=ROOT/"scripts/phase6ho_app_ready_contract.sha256"
    digest=hashlib.sha256(contract.read_bytes()).hexdigest().upper();expected=sidecar.read_text(encoding="ascii").split()[0].upper()
    audit=historical_audit();write_json(root/"environment_audit.json",audit)
    base=deployment_descriptor();cases=[]
    def check(name,value,expected_ok,expected_reason):
        outcome=validate_deployment(value);passed=outcome==(expected_ok,expected_reason);cases.append({"name":name,"status":"pass" if passed else "fail","observed":outcome,"expected":[expected_ok,expected_reason]})
    check("positive",base,True,"pass")
    mutations=(
      ("missing_extension","campfire_extension_lexical_path",str(root/"missing"),"campfire_extension_lexical_path_mismatch"),
      ("wrong_app_config","app_lexical_path",str(root/"wrong.kit"),"app_lexical_path_mismatch"),
      ("wrong_cwd","working_directory",str(root),"working_directory_mismatch"),
      ("campfire_path_missing","campfire_extension_resolved_path",str(root/"missing"),"campfire_extension_resolved_path_mismatch"),
      ("lock_not_writable","registry_lock_writable",False,"registry_lock_not_writable"),
      ("app_ready_missing","app_ready_marker",False,"app_ready_marker_missing"),
      ("resolved_path_conflict","anim_extension_resolved_path",str(root/"conflict"),"anim_extension_resolved_path_mismatch"),
    )
    for name,key,value,reason in mutations:
        row=copy.deepcopy(base);row[key]=value;check(name,row,False,reason)
    paths={name:root/(name+".json") for name in ("output","markers","runner_evidence","kit_log","kit_stdout","kit_stderr")}
    target=build_target("smoke",paths);target_result=validate_target(target,"smoke")
    cases.append({"name":"lexical_formal_command","status":"pass" if target_result==(True,"pass") else "fail","observed":target_result})
    resolved_target=list(target);resolved_target[resolved_target.index("-KitPath")+1]=str(KIT.resolve())
    cases.append({"name":"resolved_kit_rejected","status":"pass" if validate_target(resolved_target,"smoke")== (False,"kit_path_mismatch") else "fail","observed":validate_target(resolved_target,"smoke")})
    wrong_app=list(target);wrong_app[wrong_app.index("-AppPath")+1]=str(APP.resolve())
    cases.append({"name":"resolved_app_rejected","status":"pass" if validate_target(wrong_app,"smoke")== (False,"app_path_mismatch") else "fail","observed":validate_target(wrong_app,"smoke")})
    guard_paths={"trace":root/"guard-shape-resource.jsonl","summary":root/"guard-shape-summary.json","child_stdout":root/"guard-shape.stdout.log","child_stderr":root/"guard-shape.stderr.log","cleanup":root/"guard-shape-cleanup.jsonl","lifecycle":paths["output"],"gpu":root/"guard-shape-gpu.csv"}
    safety=json.loads(contract.read_text(encoding="utf-8"))["safety"]
    guard_command=build_guard_command(Path(r"C:\Python38\python.exe"),ROOT/"scripts/phase6fu_resource_guard.py",guard_paths,target,attempt_id="phase6ho-shape",safety=safety,include_gpu=True)
    guard_shape_ok=guard_command[-len(target):]==target and guard_command[guard_command.index("--") + 1:]==target
    cases.append({"name":"actual_guard_builder_binding","status":"pass" if guard_shape_ok else "fail","target_preserved":guard_shape_ok,"kit_launch_count":0})
    status="pass" if digest==expected and all(row["status"]=="pass" for row in cases) and audit["confirmed_delta"]["phase6hn_kit_resolved_away_from_build"] and audit["confirmed_delta"]["phase6hn_app_resolved_away_from_build"] else "fail"
    summary={"schema":"campfire.phase6ho.preflight.v1","status":status,"contract_sha256":digest,"case_count":len(cases),"cases":cases,"kit_launch_count":0,"phase6hn_preserved":True,"root_reused":False,"audit_path":str(root/"environment_audit.json")}
    write_json(root/"summary.json",summary);return 0 if status=="pass" else 1
if __name__=="__main__": raise SystemExit(main())
