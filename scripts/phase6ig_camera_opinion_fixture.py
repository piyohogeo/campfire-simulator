"""No-Kit fail-closed fixture for the Phase 6IG camera opinion contract."""
from __future__ import annotations
import argparse,copy,json,tempfile
from pathlib import Path
import phase6if_layer_opinion_audit as layer_audit
import phase6ig_camera_opinion_audit as audit
from phase6hu_atomic_report import atomic_write_json

def _layer_specs(root:bool,session:bool,root_id:str,session_id:str,root_properties:dict|None=None,session_properties:dict|None=None)->dict:
 def role(exists:bool,identifier:str,properties:dict|None):
  prim={"exists":exists,"path":audit.CAMERA_PATH,"spec_type":"pxr.Sdf.PrimSpec","fields":{},"fields_sha256":"0"*64} if exists else {"exists":False,"fields":{}}
  return {"prim":prim,"properties":properties or {}}
 return {"root":role(root,root_id,root_properties),"session":role(session,session_id,session_properties)}

def _prop(name:str,type_name:str,layer_id:str)->dict:
 row={"name":name,"path":audit.CAMERA_PATH+"."+name,"python_type":"pxr.Usd.Attribute","metadata":{"custom":False,"typeName":type_name,"variability":"Sdf.VariabilityVarying"},"property_stack":[layer_id],"kind":"attribute","type_name":type_name,"variability":"Sdf.VariabilityVarying","has_authored_value":True,"value":0,"connections":[]}
 row["sha256"]=layer_audit.sha256_bytes(layer_audit.canonical_bytes(row));return row

def fixture_document(boundary:str)->dict:
 base=layer_audit.fixture_snapshot(boundary, audit.BOUNDARIES.index(boundary))
 root_id=base["root_layer"]["identifier"];session_id=base["session_layer"]["identifier"]
 if boundary=="generated":camera={"path":audit.CAMERA_PATH,"exists":False,"layer_specs":_layer_specs(False,False,root_id,session_id)}
 else:
  types=dict(audit.SESSION_PROPERTIES)
  if boundary in ("post_stopped_update","preclose"):types.update(audit.ROOT_UPDATE_PROPERTIES)
  props=[_prop(name,kind,root_id if name in audit.ROOT_UPDATE_PROPERTIES else session_id) for name,kind in sorted(types.items())]
  camera={"path":audit.CAMERA_PATH,"exists":True,"type_name":"Camera","specifier":"Sdf.SpecifierDef","active":True,"applied_schemas":sorted(audit.EXPECTED_APPLIED_SCHEMAS),"metadata":{"apiSchemas":[],"customData":{},"hide_in_stage_window":True,"kind":"component","no_delete":True,"specifier":"Sdf.SpecifierDef","typeName":"Camera"},"prim_stack":[],"properties":props,"property_order":[row["name"] for row in props],"relationships":[],"children":[],"layer_specs":_layer_specs(boundary!="live_open",True,root_id,session_id)}
  camera["sha256"]=layer_audit.sha256_bytes(layer_audit.canonical_bytes(camera))
 value={"schema":audit.SCHEMA,"boundary":boundary,"sequence_index":audit.BOUNDARIES.index(boundary),"camera_path":audit.CAMERA_PATH,"camera":camera,"root_layer":base["root_layer"],"session_layer":base["session_layer"],"layer_stack":base["layer_stack"],"protected_semantics":base["protected_semantics"],"base_snapshot_sha256":base["snapshot_sha256"]}
 value["snapshot_sha256"]=layer_audit.sha256_bytes(audit.canonical_bytes(value));return value

def _rehash(value:dict)->None:
 value.pop("snapshot_sha256",None);value["snapshot_sha256"]=layer_audit.sha256_bytes(audit.canonical_bytes(value))

def run_fixture(output_root:Path)->dict:
 output_root=Path(output_root)
 if output_root.exists():raise RuntimeError("Phase 6IG fixture refuses root reuse")
 output_root.mkdir(parents=True);cases=[]
 def evaluate(name:str,docs:list[dict],accepted:bool,expected:str|None=None):
  case=output_root/name;case.mkdir();loaded=[];error=None
  try:
   for value in docs:
    path=case/(value["boundary"]+".json");audit.write_document(path,value,atomic_write_json,layer_audit);loaded.append(audit.read_document(path,layer_audit))
   result=audit.validate_sequence(loaded,layer_audit);actual=result["accepted"] is accepted;reason="pass" if actual else ";".join(result.get("reasons") or [])
   if expected and not any(expected in item for item in result.get("reasons") or []):actual=False;reason="expected_reason_missing:"+expected
  except Exception as exc:
   error=f"{type(exc).__name__}:{exc}";actual=(not accepted and (expected is None or expected in error));reason=error
  cases.append({"name":name,"passed":actual,"reason":reason,"expected_acceptance":accepted})
 base=[fixture_document(name) for name in audit.BOUNDARIES]
 evaluate("harmless_camera_runtime_augmentation",copy.deepcopy(base),True)
 docs=copy.deepcopy(base);docs[2]["protected_semantics"]["sha256"]="F"*64;_rehash(docs[2]);evaluate("protected_target_changed",docs,False,"protected_semantics_changed")
 docs=copy.deepcopy(base);docs[1]["layer_stack"].append({"identifier":"anon:unknown"});_rehash(docs[1]);evaluate("unknown_layer",docs,False,"unknown_layer")
 docs=copy.deepcopy(base);docs[1]["camera"]["properties"].pop();_rehash(docs[1]);evaluate("required_property_missing",docs,False,"camera_property_set_unknown_or_incomplete")
 docs=copy.deepcopy(base);docs[1]["camera"]["properties"].append(copy.deepcopy(docs[1]["camera"]["properties"][0]));_rehash(docs[1]);evaluate("duplicate_property",docs,False,"camera_property_duplicate_or_invalid")
 docs=copy.deepcopy(base);docs[1]["snapshot_sha256"]="0"*64;evaluate("hash_contradiction",docs,False,"camera_snapshot_hash_contradiction")
 docs=copy.deepcopy(base);docs[1]["camera"]["metadata"]["unknownRuntimeMetadata"]="x";_rehash(docs[1]);evaluate("unknown_attribute_or_metadata",docs,False,"camera_metadata_unknown")
 docs=copy.deepcopy(base);docs[1]["camera"]["metadata"]["customData"]={"oversize":"x"*(audit.MAX_DOCUMENT_BYTES+1)};_rehash(docs[1]);evaluate("oversize",docs,False,"camera_opinion_snapshot_oversize")
 passed=sum(1 for row in cases if row["passed"]);report={"schema":"campfire.phase6ig.camera-opinion-fixture.v1","phase":"phase6ig","status":"qualified" if passed==len(cases) else "failed","case_count":[passed,len(cases)],"kit_launch_count":0,"phase6if_reclassified":False,"phase6if_artifact_reused":False,"cases":cases}
 atomic_write_json(output_root/"fixture_report.json",report);return report

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--output-root",type=Path,required=True);args=parser.parse_args();report=run_fixture(args.output_root.absolute());return 0 if report["status"]=="qualified" else 1
if __name__=="__main__":raise SystemExit(main())
