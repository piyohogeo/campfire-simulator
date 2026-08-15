"""One app-ready, audit-only Phase 6IF stage-open boundary."""

from __future__ import annotations

import asyncio, hashlib, json, traceback
from pathlib import Path

import omni.kit.app
import omni.timeline
import omni.usd


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def start_audit(authoring, runtime_policy, layer_audit, atomic_report, emit, policy: dict, audit_path: Path, stage_root: Path, attempt_id: str) -> None:
 async def run() -> None:
  from pxr import Sdf, Usd
  write=atomic_report.atomic_write_json;app=omni.kit.app.get_app();context=omni.usd.get_context();timeline=omni.timeline.get_timeline_interface()
  report={"schema":"campfire.phase6if.layer-opinion-audit.v1","phase":"phase6if","attempt_id":attempt_id,"status":"running","operation_complete":False,"shutdown_complete":False,"timeline_play_calls":0,"stopped_kit_update_calls":0,"flow_simulation_update_calls":0,"flow_interface_calls":0,"readback_calls":0,"capture_calls":0,"snapshots":{},"diffs":{},"legacy_runtime_policy":{},"after_close":{},"lifecycle":{}}
  opened_identifier=None;root_identifier=None;session_identifier=None;exit_code=1
  def persist():write(audit_path,report)
  def snapshot(stage,boundary,index,off_sha,authored_paths,template=None):
   emit("layer_snapshot_started",boundary=boundary,sequence_index=index)
   value=layer_audit.snapshot_stage(stage,boundary,index,audit_path.parent/"layer-exports",off_sha,authored_paths,template)
   path=audit_path.parent/(boundary+"_layer_snapshot.json");layer_audit.write_snapshot(path,value,write);report["snapshots"][boundary]={"path":str(path),"snapshot_sha256":value["snapshot_sha256"],"root":value["root_layer"],"session":value["session_layer"]};persist();emit("layer_snapshot_complete",boundary=boundary,sequence_index=index,snapshot_sha256=value["snapshot_sha256"]);return value
  def difference(before,after):
   emit("layer_diff_started",before_boundary=before["boundary"],after_boundary=after["boundary"]);value=layer_audit.diff_snapshots(before,after);path=audit_path.parent/(before["boundary"]+"_to_"+after["boundary"]+"_diff.json");write(path,value);report["diffs"][before["boundary"]+"_to_"+after["boundary"]]={"path":str(path),**value};persist();emit("layer_diff_complete",before_boundary=before["boundary"],after_boundary=after["boundary"],changed_target_count=int(value.get("changed_target_count",0)),protected_unchanged=value.get("protected_semantics_unchanged") is True);return value
  try:
   frozen=policy["frozen_contract"];stage_root.mkdir(parents=True,exist_ok=False);off_path=stage_root/"collision_off.usda";on_path=stage_root/"collision_on.usda"
   emit("stage_generation_started",condition="collision_off_and_collision_on_fixture");off_authored=authoring.author_stage(off_path,frozen,"collision_off");on_authored=authoring.author_stage(on_path,frozen,"collision_on");off_sha,on_sha=_sha(off_path),_sha(on_path);emit("stage_generation_complete",off_sha256=off_sha,on_sha256=on_sha)
   emit("stage_parse_started",parser="pxr.Usd.Stage.Open and pxr.Sdf.Layer.FindOrOpen");off=Usd.Stage.Open(str(off_path));on=Usd.Stage.Open(str(on_path))
   if off is None or on is None:raise RuntimeError("openusd_positive_parse_failed")
   off_validation=authoring.validate_stage(off,frozen,"collision_off");on_validation=authoring.validate_stage(on,frozen,"collision_on");one_variable=authoring.one_variable_diff(off,on)
   if not one_variable["accepted"]:raise RuntimeError("off_on_semantic_difference_invalid")
   negative=[];legacy=stage_root/"negative_legacy_inline.usda";legacy.write_text('#usda 1.0\ndef Xform "World"\n{\n def FlowAdvectionCombustionParams "advection"\n {\n  def FlowAdvectionChannelParams "temperature" { float secondOrderBlendFactor = 0.9 }\n }\n}\n',encoding="utf-8")
   try:layer=Sdf.Layer.FindOrOpen(str(legacy));rejected=layer is None;reason="parser_rejected" if rejected else "unexpectedly_parsed"
   except Exception as error:rejected=True;reason=f"{type(error).__name__}:{error}"
   negative.append({"name":"legacy_inline_rejected","passed":rejected,"reason":reason})
   def mutated(name,mutate):
    path=stage_root/("negative_"+name+".usda");rejected=False;reason=None
    try:
     stage=authoring.author_stage(path,frozen,"collision_off");mutate(stage)
     if not stage.GetRootLayer().Save():raise RuntimeError("negative_stage_save_failed:"+name)
     reopened=Usd.Stage.Open(str(path))
     if reopened is None:rejected=True;reason="parser_rejected"
     else:authoring.validate_stage(reopened,frozen,"collision_off")
    except Exception as error:rejected=True;reason=f"{type(error).__name__}:{error}"
    negative.append({"name":name,"passed":rejected,"reason":reason})
   mutated("missing",lambda s:s.RemovePrim("/World/Flow/Simulate/advection/burn"));mutated("duplicate",lambda s:s.DefinePrim("/World/Flow/Simulate/advection/temperatureDuplicate","FlowAdvectionChannelParams"));mutated("type_mismatch",lambda s:s.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").SetTypeName("Xform"));mutated("nan",lambda s:s.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").GetAttribute("secondOrderBlendFactor").Set(float("nan")));mutated("unknown_schema",lambda s:s.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").SetTypeName("FutureFlowChannelParams"))
   if not all(item["passed"] for item in negative):raise RuntimeError("openusd_negative_fixture_failed")
   authored_map=runtime_policy.snapshot_authored_stage(off,off_sha);authored_paths=sorted(authored_map["authored"])
   generated=snapshot(off,"generated",0,off_sha,authored_paths);template=generated["protected_semantics"]["template"]
   report["parser_fixture"]={"positive_count":2,"negative_count":len(negative),"positive":{"off":off_validation,"on":on_validation},"negative":negative,"one_variable_difference":one_variable,"stage_sha256":{"collision_off":off_sha,"collision_on":on_sha}}
   emit("stage_parse_complete",positive_count=2,negative_count=len(negative));del off_authored,on_authored,off,on
   timeline.stop();opened,error=await context.open_stage_async(str(off_path))
   if not opened or error:raise RuntimeError("usd_context_stage_open_failed:"+str(error))
   live=context.get_stage()
   if live is None:raise RuntimeError("usd_context_stage_missing")
   opened_identifier=str(live.GetRootLayer().identifier);root_identifier=opened_identifier;session_identifier=str(live.GetSessionLayer().identifier);emit("stage_open_complete",stage_identifier=opened_identifier,root_layer_identifier=str(live.GetRootLayer().realPath or live.GetRootLayer().identifier))
   live_open=snapshot(live,"live_open",1,off_sha,authored_paths,template);difference(generated,live_open)
   emit("minimal_stopped_update_started",update_count=1);await app.next_update_async();report["stopped_kit_update_calls"]=1;emit("minimal_stopped_update_complete",update_count=1,timeline_play_calls=0)
   post=snapshot(live,"post_stopped_update",2,off_sha,authored_paths,template);generated_post=difference(generated,post);difference(live_open,post)
   projection=runtime_policy.project_live_stage(live,authored_map,_sha(off_path));legacy_policy=runtime_policy.validate_projection(authored_map,projection);report["legacy_runtime_policy"]=legacy_policy;persist()
   emit("runtime_prim_audit_started",observed_count=legacy_policy["runtime_prim_count"]);emit("runtime_prim_audit_complete",observed_count=legacy_policy["runtime_prim_count"],unknown_count=len(legacy_policy["unknown_prims"]),protected_conflict_count=len(legacy_policy["protected_conflicts"]),legacy_policy_accepted=legacy_policy["accepted"])
   changed_paths=sorted(item["path"] for item in legacy_policy["authored_prim_changed"]);unaccepted_runtime=sorted(item["path"] for item in legacy_policy["runtime_prims"] if not item["accepted"])
   emit("authored_change_audit_started",path_count=len(layer_audit.AUTHORED_CHANGED_PATHS));emit("authored_change_audit_complete",path_count=len(changed_paths),protected_unchanged=generated_post.get("protected_semantics_unchanged") is True)
   emit("root_session_opinion_audit_complete",root_dirty=post["root_layer"]["dirty"],session_dirty=post["session_layer"]["dirty"],root_memory_changed=generated_post["root_memory_export_changed"],session_memory_changed=generated_post["session_memory_export_changed"])
   protected_changed=0 if generated_post.get("protected_semantics_unchanged") else 1;emit("protected_semantics_validation_complete",path_count=post["protected_semantics"]["path_count"],changed_count=protected_changed)
   expected_runtime=sorted(layer_audit.RUNTIME_PATHS);expected_authored=sorted(layer_audit.AUTHORED_CHANGED_PATHS)
   report["audit_assertions"]={"root_file_sha256_unchanged":_sha(off_path)==off_sha,"protected_semantics_unchanged":protected_changed==0,"legacy_policy_remains_unqualified":legacy_policy["accepted"] is False,"unknown_runtime_prim_count":len(legacy_policy["unknown_prims"]),"protected_conflict_count":len(legacy_policy["protected_conflicts"]),"exact_unaccepted_runtime_paths":unaccepted_runtime,"expected_unaccepted_runtime_paths":expected_runtime,"exact_authored_changed_paths":changed_paths,"expected_authored_changed_paths":expected_authored}
   if _sha(off_path)!=off_sha:raise RuntimeError("root_file_hash_changed")
   if protected_changed:raise RuntimeError("protected_semantics_changed")
   if legacy_policy["accepted"] is not False:raise RuntimeError("legacy_policy_unexpectedly_accepted")
   if legacy_policy["unknown_prims"] or legacy_policy["protected_conflicts"]:raise RuntimeError("runtime_policy_unknown_or_protected_conflict")
   if unaccepted_runtime!=expected_runtime:raise RuntimeError("runtime_unaccepted_path_set_changed")
   if changed_paths!=expected_authored:raise RuntimeError("authored_changed_path_set_changed")
   preclose=snapshot(live,"preclose",3,off_sha,authored_paths,template);difference(post,preclose)
   report["operation_complete"]=True;report["status"]="audit_operation_pass_policy_unqualified";emit("operation_complete",scope="in_memory_root_session_opinion_audit_only");persist();exit_code=0
  except Exception as error:
   report["status"]="error";report["error"]=f"{type(error).__name__}: {error}";report["traceback"]=traceback.format_exc();persist()
  finally:
   try:
    timeline.stop()
    if context.get_stage() is not None:
     identifier=opened_identifier or str(context.get_stage().GetRootLayer().identifier);emit("stage_close_started",stage_identifier=identifier);await asyncio.wait_for(context.close_stage_async(),timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
     if context.get_stage() is not None:raise RuntimeError("usd_context_not_empty_after_close")
     emit("stage_close_complete",context_empty=True);report["lifecycle"]["stage_close_complete"]=True
     after_close=layer_audit.snapshot_layers_after_close(root_identifier,session_identifier);report["after_close"]=after_close;emit("after_close_opinion_check_complete",root_found=after_close["root"]["found"],session_found=after_close["session"]["found"])
    else:report["lifecycle"]["stage_close_complete"]=False
    report["shutdown_complete"]=True;report["lifecycle"]["shutdown_complete"]=True;emit("shutdown_complete",requested=True)
   except Exception as error:
    report["status"]="error";report["shutdown_error"]=f"{type(error).__name__}: {error}";report["shutdown_complete"]=False;exit_code=1
   persist();app.post_uncancellable_quit(exit_code)
 asyncio.ensure_future(run())
