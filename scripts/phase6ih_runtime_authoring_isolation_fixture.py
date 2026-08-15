"""No-Kit producer/writer/reader/validator fixture for Phase 6IH."""
from __future__ import annotations
import argparse,copy,json
from pathlib import Path
import phase6ih_runtime_authoring_isolation as audit
from phase6hu_atomic_report import atomic_write_json

def _layer(role:str,boundary:str)->dict:
 identifiers={"container":"C:/fixture/container.usda","runtime":"C:/fixture/runtime_opinions.usda","protected":"C:/fixture/protected_diagnostic.usda","session":"anon:fixture:container-session.usda"}
 file_hash={"container":"A"*64,"runtime":"B"*64,"protected":audit.EXPECTED_PROTECTED_SHA256,"session":None}
 memory=file_hash[role] or "C"*64
 return {"role":role,"identifier":identifiers[role],"real_path":"" if role=="session" else identifiers[role],"anonymous":role=="session","dirty":role in {"container","session"} and boundary!="generated","file_sha256":file_hash[role],"memory_export_sha256":memory,"memory_export_bytes":128,"memory_export_path":f"C:/fixture/{boundary}_{role}.txt","specs":[]}
def _runtime(path:str,kind:str,role:str="session",properties:list|None=None)->dict:
 return {"path":path,"type_name":kind,"parent":"/" if path.count("/")==1 else path.rsplit("/",1)[0],"depth":len([p for p in path.split("/") if p]),"layer_role":role,"protected_path":False,"prim_spec":{"exists":True},"properties":properties or []}
def fixture_document(boundary:str,timing:str="live")->dict:
 layers={role:_layer(role,boundary) for role in ("container","session","runtime","protected")}
 records=[]
 if boundary!="generated" and (timing=="live" or boundary!="live_open"):
  records=[_runtime("/OmniverseKit_Persp","Camera"),_runtime("/Render","",role="container")]
 protected_records={"/World/Flow/Emitter":{"path":"/World/Flow/Emitter","value":"fixed"},"/World/DiagnosticLog/FlowCollisionProxy":{"path":"/World/DiagnosticLog/FlowCollisionProxy","value":"fixed"}}
 value={"schema":audit.SCHEMA,"boundary":boundary,"sequence_index":audit.BOUNDARIES.index(boundary),"stage_identifier":layers["container"]["identifier"],"edit_target_role":"container","layer_stack":[{"index":0,"role":"session","identifier":layers["session"]["identifier"],"real_path":"","anonymous":True},{"index":1,"role":"container","identifier":layers["container"]["identifier"],"real_path":layers["container"]["real_path"],"anonymous":False},{"index":2,"role":"runtime","identifier":layers["runtime"]["identifier"],"real_path":layers["runtime"]["real_path"],"anonymous":False},{"index":3,"role":"protected","identifier":layers["protected"]["identifier"],"real_path":layers["protected"]["real_path"],"anonymous":False}],"layers":layers,"protected":{"template":{path:[] for path in protected_records},"records":protected_records,"semantic_sha256":audit.sha256_bytes(audit.canonical_bytes(protected_records)),"path_count":len(protected_records)},"runtime_records":records}
 value["snapshot_sha256"]=audit.sha256_bytes(audit.canonical_bytes(value));return value
def _rehash(value:dict)->None:value.pop("snapshot_sha256",None);value["snapshot_sha256"]=audit.sha256_bytes(audit.canonical_bytes(value))
def run_fixture(output_root:Path)->dict:
 output_root=Path(output_root)
 if output_root.exists():raise RuntimeError("Phase 6IH fixture refuses root reuse")
 output_root.mkdir(parents=True);cases=[]
 def evaluate(name,docs,accepted,expected=None):
  root=output_root/name;root.mkdir();loaded=[]
  try:
   for doc in docs:
    path=root/(doc["boundary"]+".json");audit.write_document(path,doc,atomic_write_json);loaded.append(audit.read_document(path))
   result=audit.validate_sequence(loaded);ok=result["accepted"] is accepted
   if expected and not any(expected in reason for reason in result.get("reasons") or []):ok=False
   reason="pass" if ok else ";".join(result.get("reasons") or ["unexpected_result"])
  except Exception as exc:
   reason=f"{type(exc).__name__}:{exc}";ok=(not accepted and (expected is None or expected in reason))
  cases.append({"name":name,"passed":ok,"reason":reason,"expected_acceptance":accepted})
 base=[fixture_document(b) for b in audit.BOUNDARIES];delayed=[fixture_document(b,"post") for b in audit.BOUNDARIES]
 evaluate("runtime_camera_render_only",copy.deepcopy(base),True);evaluate("runtime_generation_timing_varies",delayed,True)
 docs=copy.deepcopy(base);docs[1]["layers"]["protected"]["dirty"]=True;_rehash(docs[1]);evaluate("camera_opinion_in_protected_layer",docs,False,"protected_layer_dirty")
 docs=copy.deepcopy(base);docs[2]["protected"]["records"]["/World/Flow/Emitter"]["value"]="changed";docs[2]["protected"]["semantic_sha256"]=audit.sha256_bytes(audit.canonical_bytes(docs[2]["protected"]["records"]));_rehash(docs[2]);evaluate("protected_flow_emitter_collision_changed",docs,False,"protected_semantics_changed")
 docs=copy.deepcopy(base);docs[1]["layer_stack"].append({"role":None});_rehash(docs[1]);evaluate("unknown_layer",docs,False,"layer_identity_or_order_invalid")
 docs=copy.deepcopy(base);docs[1]["runtime_records"].append(_runtime("/Unknown","Xform"));_rehash(docs[1]);evaluate("unknown_path",docs,False,"unknown_runtime_path")
 docs=copy.deepcopy(base);docs[1]["runtime_records"][0]["type_name"]="Xform";_rehash(docs[1]);evaluate("unknown_type",docs,False,"unknown_runtime_type")
 docs=copy.deepcopy(base);docs[1]["runtime_records"][0]["properties"]=[{"name":"unknown","schema_declared":False,"explicit_custom_exception":False}];_rehash(docs[1]);evaluate("unknown_property",docs,False,"unknown_runtime_property")
 docs=copy.deepcopy(base);docs[1]["layer_stack"][1]["role"],docs[1]["layer_stack"][2]["role"]="runtime","container";_rehash(docs[1]);evaluate("layer_identity_swapped",docs,False,"layer_identity_or_order_invalid")
 docs=copy.deepcopy(base);docs[2]["layers"]["protected"]["file_sha256"]="0"*64;_rehash(docs[2]);evaluate("disk_hash_mismatch",docs,False,"protected_disk_hash_mismatch")
 docs=copy.deepcopy(base);docs[1]["runtime_records"].append(copy.deepcopy(docs[1]["runtime_records"][0]));_rehash(docs[1]);evaluate("duplicate",docs,False,"duplicate_runtime_prim")
 docs=copy.deepcopy(base);docs[1]["layers"].pop("runtime");_rehash(docs[1]);evaluate("missing",docs,False,"layer_role_set_invalid")
 docs=copy.deepcopy(base);docs[1]["layers"]["session"]["memory_export_bytes"]=audit.MAX_LAYER_BYTES+1;_rehash(docs[1]);evaluate("oversize",docs,False,"layer_oversize")
 docs=copy.deepcopy(base);docs[1]["snapshot_sha256"]="0"*64;evaluate("hash_content_contradiction",docs,False,"snapshot_hash_contradiction")
 passed=sum(1 for row in cases if row["passed"]);report={"schema":"campfire.phase6ih.runtime-authoring-isolation-fixture.v1","phase":"phase6ih","status":"qualified" if passed==len(cases) else "failed","case_count":[passed,len(cases)],"kit_launch_count":0,"phase6ig_reclassified":False,"phase6ig_artifact_reused":False,"cases":cases};atomic_write_json(output_root/"fixture_report.json",report);return report
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--output-root",type=Path,required=True);args=p.parse_args();return 0 if run_fixture(args.output_root.absolute())["status"]=="qualified" else 1
if __name__=="__main__":raise SystemExit(main())
