"""Run exactly one actual-Kit Phase 6IG camera opinion audit."""
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from phase6hl_guard_preflight import _read_bounded,build_guard_command
from phase6hm_process_role_fixture import _read_jsonl
from phase6hn_process_tree_topology import validate_trace_roles
from phase6ho_app_ready_environment import ROOT,write_json
from phase6ho_process_tree_topology import APP,KIT
from phase6hr_lifecycle_classification import consume_guard_report
import phase6if_layer_opinion_audit as layer_audit
import phase6ig_camera_opinion_audit as camera_audit
from run_phase6hz_import_smoke import hashes as invariant_hashes

SCRIPTS=ROOT/"scripts";CONTRACT=SCRIPTS/"phase6ig_camera_opinion_contract.json";SIDECAR=SCRIPTS/"phase6ig_camera_opinion_contract.sha256";PYTHON=Path(r"C:\Python38\python.exe");GUARD=SCRIPTS/"phase6hr_resource_guard.py";CASE=SCRIPTS/"run_phase6ig_camera_opinion_case.ps1";PROBE=SCRIPTS/"probe_phase6ig_camera_opinion_audit.py"
def _contract():
 digest=hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
 if digest!=SIDECAR.read_text(encoding="ascii").split()[0].upper():raise RuntimeError("Phase 6IG contract digest mismatch")
 return json.loads(CONTRACT.read_text(encoding="utf-8")),digest
def run_audit(root:Path,preflight_path:Path)->dict:
 if root.exists():raise RuntimeError("Phase 6IG runtime refuses root reuse")
 policy,digest=_contract();preflight=_read_bounded(preflight_path)
 if preflight.get("status")!="qualified" or preflight.get("contract_sha256")!=digest:raise RuntimeError("Phase 6IG preflight did not qualify this contract")
 root.mkdir(parents=True);attempt=root/"attempt01";logs=attempt/"runner-logs";logs.mkdir(parents=True)
 for source,target in ((CONTRACT,"frozen_contract.json"),(SIDECAR,"frozen_contract.sha256"),(SCRIPTS/"phase6ig_authoring_dependencies.json","frozen_dependency_manifest.json"),(SCRIPTS/"phase6ig_authoring_dependencies.sha256","frozen_dependency_manifest.sha256")):shutil.copy2(source,root/target)
 before=invariant_hashes();attempt_id="phase6ig-camera-opinion-attempt01"
 paths={"output":attempt/"camera_opinion_audit.json","markers":attempt/"markers.jsonl","runner_evidence":attempt/"runner_evidence.json","kit_log":attempt/"kit.log","kit_stdout":attempt/"kit.stdout.log","kit_stderr":attempt/"kit.stderr.log","trace":logs/"resource.jsonl","summary":logs/"guard.json","child_stdout":logs/"powershell.stdout.log","child_stderr":logs/"powershell.stderr.log","cleanup":logs/"cleanup.jsonl","lifecycle":attempt/"camera_opinion_audit.json","gpu":logs/"gpu.csv"}
 powershell=Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe");target=[str(powershell),"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(CASE),"-KitPath",str(KIT),"-AppPath",str(APP),"-ProbePath",str(PROBE),"-MarkersPath",str(paths["markers"]),"-AuditPath",str(paths["output"]),"-StageRoot",str(attempt/"generated-stages"),"-RunnerEvidencePath",str(paths["runner_evidence"]),"-ContractPath",str(CONTRACT),"-KitLogPath",str(paths["kit_log"]),"-KitStdoutPath",str(paths["kit_stdout"]),"-KitStderrPath",str(paths["kit_stderr"]),"-AttemptId",attempt_id]
 write_json(attempt/"launch_contract.json",{"schema":"campfire.phase6ig.launch.v1","phase":"phase6ig","attempt_id":attempt_id,"target":target,"cwd":str(ROOT),"audit_only":True})
 command=build_guard_command(PYTHON,GUARD,paths,target,attempt_id=attempt_id,safety=policy["safety"],include_gpu=True);delimiter=command.index("--");command[delimiter:delimiter]=["--runner-evidence-path",str(paths["runner_evidence"]),"--marker-path",str(paths["markers"]),"--contract-path",str(CONTRACT),"--mode","smoke"]
 with (logs/"guard-launcher.stdout.log").open("wb",buffering=0) as stdout,(logs/"guard-launcher.stderr.log").open("wb",buffering=0) as stderr:
  process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0));guard_exit=process.wait()
 guard=_read_bounded(paths["summary"]) if paths["summary"].is_file() else {};audit=_read_bounded(paths["output"]) if paths["output"].is_file() else {};runner=_read_bounded(paths["runner_evidence"]) if paths["runner_evidence"].is_file() else {};samples=_read_jsonl(paths["trace"]) if paths["trace"].is_file() else []
 roles_ok,role_failures,roles=validate_trace_roles(samples);canonical=consume_guard_report(guard,policy,expected_attempt_id=attempt_id);after=invariant_hashes();cleanup=guard.get("observed_process_cleanup") or {};markers=runner.get("marker_names") or []
 docs=[];document_validation=[]
 for boundary in camera_audit.BOUNDARIES:
  try:value=camera_audit.read_document(attempt/(boundary+"_camera_snapshot.json"),layer_audit);docs.append(value);document_validation.append({"boundary":boundary,"accepted":True,"snapshot_sha256":value["snapshot_sha256"]})
  except Exception as error:document_validation.append({"boundary":boundary,"accepted":False,"error":f"{type(error).__name__}:{error}"})
 sequence=camera_audit.validate_sequence(docs,layer_audit) if len(docs)==4 else {"accepted":False,"classification":"safe_stop_camera_opinion_unresolved","reasons":["camera_snapshot_count_invalid"]}
 operation_complete=audit.get("operation_complete") is True and sequence.get("accepted") is True
 lifecycle_complete=bool(audit.get("shutdown_complete") is True and (audit.get("lifecycle") or {}).get("stage_close_complete") is True and runner.get("process_exit_code")==0 and canonical.get("accepted") and cleanup.get("all_observed_absent") is True)
 required=policy["runtime"]["required_markers"];markers_complete=all(name in markers for name in required)
 fully_qualified=operation_complete and lifecycle_complete and markers_complete and not (runner.get("fatal_lines") or []) and not (runner.get("dump_inventory") or []) and not (runner.get("automatic_upload_attempt_lines") or []) and roles_ok and before==after
 status="camera_runtime_augmentation_audited" if fully_qualified else "safe_stop_camera_opinion_unresolved"
 camera_projection={row["boundary"]:{"camera":row["camera"],"root_layer":row["root_layer"],"session_layer":row["session_layer"],"protected_semantics_sha256":row["protected_semantics"]["sha256"]} for row in docs}
 result={"schema":"campfire.phase6ig.camera-opinion-summary.v1","phase":"phase6ig","status":status,"attempt_id":attempt_id,"contract_sha256":digest,"kit_launch_count":1,"retry_count":0,"replacement_count":0,"guard_exit_code":guard_exit,"operation_evidence_complete":operation_complete,"lifecycle_complete":lifecycle_complete,"phase6if_reclassified":False,"phase6if_artifact_or_runtime_reused":False,"last_marker":markers[-1] if markers else None,"required_markers_complete":markers_complete,"document_validation":document_validation,"sequence_validation":sequence,"camera_boundaries":camera_projection,"canonical_lifecycle_classification":canonical.get("classification"),"canonical_consumer_reason":canonical.get("reason"),"kit_exit_code":runner.get("process_exit_code"),"resource_peaks_bytes":guard.get("peaks",{}),"resource_minima_bytes":guard.get("machine_minima",{}),"roles_pass":roles_ok,"roles":roles,"role_failures":role_failures,"exact_cleanup_all_absent":cleanup.get("all_observed_absent") is True,"residual_process_count":0 if cleanup.get("all_observed_absent") is True else None,"fatal_lines":runner.get("fatal_lines") or [],"dump_inventory":runner.get("dump_inventory") or [],"automatic_upload_attempt_lines":runner.get("automatic_upload_attempt_lines") or [],"invariants_pass":before==after,"invariant_hashes_before":before,"invariant_hashes_after":after,"production_changed":False,"defaults_changed":False,"point_policy_changed":False,"v3_changed":False,"collision_proxy_changed":False,"emitter_changed":False,"latest_demo_changed":False}
 write_json(root/"summary.json",result);return result
def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--artifact-root",type=Path,required=True);parser.add_argument("--preflight-summary",type=Path,required=True);args=parser.parse_args();result=run_audit(args.artifact_root.absolute(),args.preflight_summary.absolute());return 0 if result["status"]=="camera_runtime_augmentation_audited" else 1
if __name__=="__main__":raise SystemExit(main())
