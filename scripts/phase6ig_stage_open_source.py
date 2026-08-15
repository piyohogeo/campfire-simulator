"""One app-ready camera-only in-memory opinion audit for Phase 6IG."""
from __future__ import annotations
import asyncio,hashlib,traceback
from pathlib import Path
import omni.kit.app,omni.timeline,omni.usd

def _sha(path:Path)->str:return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def start_audit(authoring,runtime_policy,layer_audit,camera_audit,atomic_report,emit,policy:dict,audit_path:Path,stage_root:Path,attempt_id:str)->None:
 async def run()->None:
  from pxr import Usd
  write=atomic_report.atomic_write_json;app=omni.kit.app.get_app();context=omni.usd.get_context();timeline=omni.timeline.get_timeline_interface()
  report={"schema":"campfire.phase6ig.camera-opinion-audit.v1","phase":"phase6ig","attempt_id":attempt_id,"status":"running","operation_complete":False,"shutdown_complete":False,"timeline_play_calls":0,"stopped_kit_update_calls":0,"flow_simulation_update_calls":0,"flow_interface_calls":0,"readback_calls":0,"capture_calls":0,"snapshots":{},"sequence_validation":{},"lifecycle":{}}
  opened_identifier=None;exit_code=1
  def persist():write(audit_path,report)
  def snapshot(stage,boundary,index,disk_sha,authored_paths,template=None):
   emit("camera_snapshot_started",boundary=boundary,sequence_index=index)
   value=camera_audit.capture(stage,boundary,index,audit_path.parent/"layer-exports",disk_sha,authored_paths,layer_audit,template)
   camera_audit.write_document(audit_path.parent/(boundary+"_camera_snapshot.json"),value,write,layer_audit)
   report["snapshots"][boundary]={"snapshot_sha256":value["snapshot_sha256"],"camera":value["camera"],"root_layer":value["root_layer"],"session_layer":value["session_layer"],"protected_semantics":value["protected_semantics"]};persist()
   emit("camera_snapshot_complete",boundary=boundary,sequence_index=index,snapshot_sha256=value["snapshot_sha256"]);return value
  try:
   frozen=policy["frozen_contract"];stage_root.mkdir(parents=True,exist_ok=False);stage_path=stage_root/"collision_off.usda"
   emit("stage_generation_started",condition="collision_off");authoring.author_stage(stage_path,frozen,"collision_off");disk_sha=_sha(stage_path);emit("stage_generation_complete",stage_sha256=disk_sha)
   generated_stage=Usd.Stage.Open(str(stage_path))
   if generated_stage is None:raise RuntimeError("generated_stage_open_failed")
   authoring.validate_stage(generated_stage,frozen,"collision_off");authored_map=runtime_policy.snapshot_authored_stage(generated_stage,disk_sha);authored_paths=sorted(authored_map["authored"])
   generated=snapshot(generated_stage,"generated",0,disk_sha,authored_paths);template=generated["protected_semantics"]["template"];del generated_stage
   timeline.stop();opened,error=await context.open_stage_async(str(stage_path))
   if not opened or error:raise RuntimeError("usd_context_stage_open_failed:"+str(error))
   live=context.get_stage()
   if live is None:raise RuntimeError("usd_context_stage_missing")
   opened_identifier=str(live.GetRootLayer().identifier);emit("stage_open_complete",stage_identifier=opened_identifier)
   live_open=snapshot(live,"live_open",1,disk_sha,authored_paths,template)
   emit("stopped_update_started",update_count=1);await app.next_update_async();report["stopped_kit_update_calls"]=1;emit("stopped_update_complete",update_count=1)
   post=snapshot(live,"post_stopped_update",2,disk_sha,authored_paths,template)
   preclose=snapshot(live,"preclose",3,disk_sha,authored_paths,template)
   documents=[generated,live_open,post,preclose];sequence=camera_audit.validate_sequence(documents,layer_audit);report["sequence_validation"]=sequence;persist();emit("camera_sequence_validated",classification=sequence["classification"],accepted=sequence["accepted"])
   if not sequence["accepted"]:raise RuntimeError(sequence["reasons"][0])
   if _sha(stage_path)!=disk_sha:raise RuntimeError("root_file_hash_changed")
   emit("protected_digest_validated",sha256=sequence["protected_semantics_sha256"])
   report["operation_complete"]=True;report["status"]="camera_runtime_augmentation_audited";emit("operation_complete",scope="camera_opinion_audit_only");persist();exit_code=0
  except Exception as error:
   report["status"]="safe_stop_camera_opinion_unresolved";report["error"]=f"{type(error).__name__}: {error}";report["traceback"]=traceback.format_exc();persist()
  finally:
   try:
    timeline.stop()
    if context.get_stage() is not None:
     identifier=opened_identifier or str(context.get_stage().GetRootLayer().identifier);emit("stage_close_started",stage_identifier=identifier);await asyncio.wait_for(context.close_stage_async(),timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
     if context.get_stage() is not None:raise RuntimeError("usd_context_not_empty_after_close")
     report["lifecycle"]["stage_close_complete"]=True;emit("stage_close_complete",context_empty=True)
    else:report["lifecycle"]["stage_close_complete"]=False
    report["shutdown_complete"]=True;report["lifecycle"]["shutdown_complete"]=True;emit("shutdown_complete",requested=True)
   except Exception as error:
    report["status"]="safe_stop_camera_opinion_unresolved";report["shutdown_error"]=f"{type(error).__name__}: {error}";report["shutdown_complete"]=False;exit_code=1
   persist();app.post_uncancellable_quit(exit_code)
 asyncio.ensure_future(run())
