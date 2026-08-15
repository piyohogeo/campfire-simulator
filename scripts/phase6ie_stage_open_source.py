"""App-ready Phase 6IE bounded runtime-Prim stage-open smoke."""

from __future__ import annotations

import asyncio, hashlib, json, traceback
from pathlib import Path

import omni.kit.app
import omni.timeline
import omni.usd


def _sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def start_smoke(authoring,runtime_policy,atomic_report,emit,policy:dict,audit_path:Path,prim_evidence_path:Path,authored_map_path:Path,stage_root:Path,attempt_id:str)->None:
 async def run()->None:
  from pxr import Sdf,Usd
  atomic_write_json=atomic_report.atomic_write_json;app=omni.kit.app.get_app();context=omni.usd.get_context();timeline=omni.timeline.get_timeline_interface()
  report={"schema":"campfire.phase6ie.stage-open-audit.v1","phase":"phase6ie","attempt_id":attempt_id,"status":"running","operation_complete":False,"shutdown_complete":False,"flow_interface_calls":0,"readback_calls":0,"capture_calls":0,"timeline_play_calls":0,"parser_fixture":{},"float3_evidence":[],"runtime_prim_policy":{},"lifecycle":{}}
  exit_code=1;opened_identifier=None
  def persist(): atomic_write_json(audit_path,report)
  def validate_with_evidence(stage,condition,scope):
   emit("float3_validation_started",scope=scope,attribute_path="/World/Flow/Emitter.position");captured=[]
   def capture(item): captured.append(item);report["float3_evidence"].append({"scope":scope,**item});persist()
   validation=authoring.validate_stage(stage,policy["frozen_contract"],condition,float3_evidence_callback=capture);item=captured[-1]
   emit("float3_validation_complete",scope=scope,attribute_path=item["attribute_path"],accepted=item["accepted"],maximum_ulp_distance=item["maximum_ulp_distance"]);return validation
  try:
   frozen=policy["frozen_contract"];stage_root.mkdir(parents=True,exist_ok=False);off_path=stage_root/"collision_off.usda";on_path=stage_root/"collision_on.usda"
   emit("stage_generation_started",condition="collision_off_and_collision_on_fixture");off_authored=authoring.author_stage(off_path,frozen,"collision_off");on_authored=authoring.author_stage(on_path,frozen,"collision_on");off_sha,on_sha=_sha(off_path),_sha(on_path);emit("stage_generation_complete",off_sha256=off_sha,on_sha256=on_sha)
   emit("stage_parse_started",parser="pxr.Usd.Stage.Open and pxr.Sdf.Layer.FindOrOpen");off=Usd.Stage.Open(str(off_path));on=Usd.Stage.Open(str(on_path))
   if off is None or on is None: raise RuntimeError("openusd_positive_parse_failed")
   off_validation=validate_with_evidence(off,"collision_off","parser_fixture_off");on_validation=validate_with_evidence(on,"collision_on","parser_fixture_on");difference=authoring.one_variable_diff(off,on)
   if not difference["accepted"]: raise RuntimeError("off_on_semantic_difference_invalid")
   negative=[]
   legacy=stage_root/"negative_legacy_inline.usda";legacy.write_text('#usda 1.0\ndef Xform "World"\n{\n def FlowAdvectionCombustionParams "advection"\n {\n  def FlowAdvectionChannelParams "temperature" { float secondOrderBlendFactor = 0.9 }\n }\n}\n',encoding="utf-8")
   try: layer=Sdf.Layer.FindOrOpen(str(legacy));rejected=layer is None;reason="parser_rejected" if rejected else "unexpectedly_parsed"
   except Exception as error: rejected=True;reason=f"{type(error).__name__}:{error}"
   negative.append({"name":"legacy_inline_rejected","passed":rejected,"reason":reason})
   def mutated(name,mutate):
    path=stage_root/("negative_"+name+".usda");rejected=False;reason=None
    try:
     stage=authoring.author_stage(path,frozen,"collision_off");mutate(stage)
     if not stage.GetRootLayer().Save(): raise RuntimeError("negative_stage_save_failed:"+name)
     reopened=Usd.Stage.Open(str(path))
     if reopened is None: rejected=True;reason="parser_rejected"
     else: authoring.validate_stage(reopened,frozen,"collision_off")
    except Exception as error: rejected=True;reason=f"{type(error).__name__}:{error}"
    negative.append({"name":name,"passed":rejected,"reason":reason})
   mutated("missing",lambda s:s.RemovePrim("/World/Flow/Simulate/advection/burn"));mutated("duplicate",lambda s:s.DefinePrim("/World/Flow/Simulate/advection/temperatureDuplicate","FlowAdvectionChannelParams"));mutated("type_mismatch",lambda s:s.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").SetTypeName("Xform"));mutated("nan",lambda s:s.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").GetAttribute("secondOrderBlendFactor").Set(float("nan")));mutated("unknown_schema",lambda s:s.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").SetTypeName("FutureFlowChannelParams"))
   if not all(item["passed"] for item in negative): raise RuntimeError("openusd_negative_fixture_failed")
   authored_map=runtime_policy.snapshot_authored_stage(off,off_sha);runtime_policy.write_evidence(authored_map_path,{"schema":runtime_policy.EVIDENCE_SCHEMA,"accepted":True,"kind":"authored_prim_map","authored_prim_count":authored_map["authored_prim_count"],"authored":authored_map["authored"],"root_layer_sha256":off_sha},atomic_write_json)
   report["parser_fixture"]={"positive_count":2,"negative_count":len(negative),"positive":{"off":off_validation,"on":on_validation},"negative":negative,"one_variable_difference":difference,"stage_sha256":{"collision_off":off_sha,"collision_on":on_sha}}
   emit("stage_parse_complete",positive_count=2,negative_count=len(negative));del off_authored,on_authored,off,on
   timeline.stop();opened,error=await context.open_stage_async(str(off_path))
   if not opened or error: raise RuntimeError("usd_context_stage_open_failed:"+str(error))
   live=context.get_stage()
   if live is None: raise RuntimeError("usd_context_stage_missing")
   opened_identifier=str(live.GetRootLayer().identifier);emit("stage_open_complete",stage_identifier=opened_identifier,root_layer_identifier=str(live.GetRootLayer().realPath or live.GetRootLayer().identifier))
   emit("authored_prim_validation_started",prim_count=authored_map["authored_prim_count"])
   live_projection=runtime_policy.project_live_stage(live,authored_map,_sha(off_path));runtime_evidence=runtime_policy.validate_projection(authored_map,live_projection);runtime_policy.write_evidence(prim_evidence_path,runtime_evidence,atomic_write_json);report["runtime_prim_policy"]=runtime_evidence;persist()
   emit("authored_prim_validation_complete",prim_count=runtime_evidence["authored_prim_count"],changed_count=len(runtime_evidence["authored_prim_changed"]),missing_count=len(runtime_evidence["authored_prim_missing"]))
   emit("runtime_prim_classification_started",observed_count=runtime_evidence["runtime_prim_count"]);accepted_count=sum(1 for item in runtime_evidence["runtime_prims"] if item["accepted"])
   emit("runtime_prim_classification_complete",observed_count=runtime_evidence["runtime_prim_count"],accepted_count=accepted_count,unknown_count=len(runtime_evidence["unknown_prims"]),protected_conflict_count=len(runtime_evidence["protected_conflicts"]))
   unchanged=runtime_evidence["root_layer_sha256_before"]==runtime_evidence["root_layer_sha256_after"];emit("root_layer_integrity_complete",before_sha256=runtime_evidence["root_layer_sha256_before"],after_sha256=runtime_evidence["root_layer_sha256_after"],unchanged=unchanged)
   if not runtime_evidence["accepted"]: raise RuntimeError("runtime_prim_policy_rejected:"+runtime_evidence["reasons"][0])
   emit("float3_validation_started",scope="usd_context_off",attribute_path="/World/Flow/Emitter.position");attribute=live.GetPrimAtPath("/World/Flow/Emitter").GetAttribute("position");float3=authoring.canonical_float3_evidence("/World/Flow/Emitter.position","float3",frozen["fixed_scene"]["source_center_m"],attribute.Get());report["float3_evidence"].append({"scope":"usd_context_off",**float3});persist();emit("float3_validation_complete",scope="usd_context_off",attribute_path=float3["attribute_path"],accepted=float3["accepted"],maximum_ulp_distance=float3["maximum_ulp_distance"])
   if not float3["accepted"]: raise RuntimeError("live_float3_validation_failed")
   property_count=sum(len(item["properties"]) for item in authored_map["authored"].values());report["stage"]={"identifier":opened_identifier,"root_layer_identifier":str(live.GetRootLayer().identifier),"root_layer_sha256":off_sha,"authored_prim_count":authored_map["authored_prim_count"],"authored_property_count":property_count,"runtime_prim_count":runtime_evidence["runtime_prim_count"],"validation":off_validation}
   emit("required_prims_validated",prim_count=authored_map["authored_prim_count"],flow_setting_count=property_count);report["operation_complete"]=True;report["status"]="operation_pass";emit("operation_complete",scope="bounded_runtime_prim_stage_open_only");persist();exit_code=0
  except Exception as error: report["status"]="error";report["error"]=f"{type(error).__name__}: {error}";report["traceback"]=traceback.format_exc();persist()
  finally:
   try:
    timeline.stop()
    if context.get_stage() is not None:
     identifier=opened_identifier or str(context.get_stage().GetRootLayer().identifier);emit("stage_close_started",stage_identifier=identifier);await asyncio.wait_for(context.close_stage_async(),timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
     if context.get_stage() is not None: raise RuntimeError("usd_context_not_empty_after_close")
     emit("stage_close_complete",context_empty=True);report["lifecycle"]["stage_close_complete"]=True
    else: report["lifecycle"]["stage_close_complete"]=False
    if report["status"]=="operation_pass" and report["lifecycle"]["stage_close_complete"]: report["status"]="qualified"
    report["shutdown_complete"]=True;report["lifecycle"]["shutdown_complete"]=True;emit("shutdown_complete",requested=True)
   except Exception as error: report["status"]="error";report["shutdown_error"]=f"{type(error).__name__}: {error}";report["shutdown_complete"]=False;exit_code=1
   persist();app.post_uncancellable_quit(exit_code)
 asyncio.ensure_future(run())
