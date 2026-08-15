"""One stopped-timeline Layer-ownership isolation audit for Phase 6IH."""
from __future__ import annotations
import asyncio,hashlib,traceback
from pathlib import Path
import omni.kit.app,omni.timeline,omni.usd
def _sha(path:Path)->str:return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()
def start_audit(authoring,runtime_policy,layer_audit,isolation,atomic_report,emit,policy,audit_path:Path,stage_root:Path,attempt_id:str)->None:
 async def run():
  from pxr import Usd
  app=omni.kit.app.get_app();context=omni.usd.get_context();timeline=omni.timeline.get_timeline_interface();write=atomic_report.atomic_write_json
  report={"schema":"campfire.phase6ih.runtime-authoring-isolation-audit.v1","phase":"phase6ih","attempt_id":attempt_id,"status":"running","operation_complete":False,"shutdown_complete":False,"timeline_play_calls":0,"stopped_kit_update_calls":0,"flow_simulation_update_calls":0,"flow_interface_calls":0,"readback_calls":0,"capture_calls":0,"snapshots":{},"sequence_validation":{},"lifecycle":{}};opened_identifier=None;exit_code=1
  def persist():write(audit_path,report)
  def snapshot(stage,boundary,index,expected,template=None):
   emit("isolation_snapshot_started",boundary=boundary,sequence_index=index);value=isolation.capture(stage,boundary,index,audit_path.parent/"layer-exports",expected,template,layer_audit);isolation.write_document(audit_path.parent/(boundary+"_isolation_snapshot.json"),value,write);report["snapshots"][boundary]={"snapshot_sha256":value["snapshot_sha256"],"layer_stack":value["layer_stack"],"edit_target_role":value["edit_target_role"],"layers":{role:{key:row.get(key) for key in ("identifier","real_path","dirty","file_sha256","memory_export_sha256","memory_export_bytes")} for role,row in value["layers"].items()},"protected_semantic_sha256":value["protected"]["semantic_sha256"],"runtime_record_count":len(value["runtime_records"])};persist();emit("isolation_snapshot_complete",boundary=boundary,sequence_index=index,snapshot_sha256=value["snapshot_sha256"]);return value
  try:
   frozen=policy["frozen_contract"];stage_root.mkdir(parents=True,exist_ok=False);protected_path=stage_root/isolation.PROTECTED_FILENAME
   emit("layer_generation_started",condition="collision_off_stopped_timeline");protected_stage=authoring.author_stage(protected_path,frozen,"collision_off");protected_sha=_sha(protected_path)
   if protected_sha!=policy["layer_contract"]["protected_file_sha256"]:raise RuntimeError("protected_generated_hash_mismatch")
   authored=runtime_policy.snapshot_authored_stage(protected_stage,protected_sha);files=isolation.create_container_files(stage_root)
   if files["container_sha256"]!=policy["layer_contract"]["container_file_sha256"] or files["runtime_sha256"]!=policy["layer_contract"]["runtime_file_sha256"]:raise RuntimeError("container_or_runtime_hash_mismatch")
   emit("layer_generation_complete",protected_sha256=protected_sha,container_sha256=files["container_sha256"],runtime_sha256=files["runtime_sha256"])
   generated=Usd.Stage.Open(str(files["container"]));
   if generated is None:raise RuntimeError("generated_container_open_failed")
   authoring.validate_stage(generated,frozen,"collision_off");expected={"container":str(files["container"]),"runtime":str(files["runtime"]),"protected":str(protected_path),"session":None,"protected_paths":sorted(authored["authored"])}
   report["layer_contract"]={"identifiers":expected,"file_sha256":{"protected":protected_sha,"container":files["container_sha256"],"runtime":files["runtime_sha256"]}};first=snapshot(generated,"generated",0,expected);template=first["protected"]["template"];del generated,protected_stage
   timeline.stop();opened,error=await context.open_stage_async(str(files["container"]))
   if not opened or error:raise RuntimeError("usd_context_stage_open_failed:"+str(error))
   live=context.get_stage();opened_identifier=str(live.GetRootLayer().identifier);emit("stage_open_complete",stage_identifier=opened_identifier)
   second=snapshot(live,"live_open",1,expected,template);emit("stopped_update_started",update_count=1);await app.next_update_async();report["stopped_kit_update_calls"]=1;emit("stopped_update_complete",update_count=1)
   third=snapshot(live,"post_stopped_update",2,expected,template);fourth=snapshot(live,"preclose",3,expected,template);sequence=isolation.validate_sequence([first,second,third,fourth]);report["sequence_validation"]=sequence;persist();emit("isolation_sequence_validated",classification=sequence["classification"],accepted=sequence["accepted"])
   if not sequence["accepted"]:raise RuntimeError(sequence["reasons"][0])
   report["operation_complete"]=True;report["status"]="runtime_authoring_isolation_qualified";emit("operation_complete",scope="runtime_authoring_isolation_only");persist();exit_code=0
  except Exception as error:
   report["status"]="safe_stop_runtime_authoring_isolation_failure";report["error"]=f"{type(error).__name__}: {error}";report["traceback"]=traceback.format_exc();persist()
  finally:
   try:
    timeline.stop()
    if context.get_stage() is not None:
     identifier=opened_identifier or str(context.get_stage().GetRootLayer().identifier);emit("stage_close_started",stage_identifier=identifier);await asyncio.wait_for(context.close_stage_async(),timeout=float(policy["safety"]["stage_close_timeout_seconds"]));
     if context.get_stage() is not None:raise RuntimeError("usd_context_not_empty_after_close")
     report["lifecycle"]["stage_close_complete"]=True;emit("stage_close_complete",context_empty=True)
    else:report["lifecycle"]["stage_close_complete"]=False
    report["shutdown_complete"]=True;report["lifecycle"]["shutdown_complete"]=True;emit("shutdown_complete",requested=True)
   except Exception as error:report["status"]="safe_stop_runtime_authoring_isolation_failure";report["shutdown_error"]=f"{type(error).__name__}: {error}";report["shutdown_complete"]=False;exit_code=1
   persist();app.post_uncancellable_quit(exit_code)
 asyncio.ensure_future(run())
