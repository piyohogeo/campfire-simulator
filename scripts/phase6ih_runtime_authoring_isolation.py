"""Layer-ownership isolation contract for Phase 6IH."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path

SCHEMA="campfire.phase6ih.runtime-authoring-snapshot.v1";SEQUENCE_SCHEMA="campfire.phase6ih.runtime-authoring-sequence.v1"
BOUNDARIES=("generated","live_open","post_stopped_update","preclose");MAX_DOCUMENT_BYTES=4*1024*1024;MAX_LAYER_BYTES=8*1024*1024
PROTECTED_FILENAME="protected_diagnostic.usda";RUNTIME_FILENAME="runtime_opinions.usda";CONTAINER_FILENAME="container.usda"
RUNTIME_TEXT="#usda 1.0\n"
CONTAINER_TEXT='#usda 1.0\n(\n    subLayers = [\n        @runtime_opinions.usda@,\n        @protected_diagnostic.usda@\n    ]\n)\n'
EXPECTED_PROTECTED_SHA256="D5668572776AC0B48E9C8AF193FF517631865D9203864DBBFA1B52EFB8B8E99C"
ALLOWED_RUNTIME_PRIMS={
 "/OmniverseKit_Front":"Camera","/OmniverseKit_Persp":"Camera","/OmniverseKit_Right":"Camera","/OmniverseKit_Top":"Camera",
 "/Render":"","/Render/OmniverseGlobalRenderSettings":"RenderSettings","/Render/OmniverseKit":"","/Render/OmniverseKit/HydraTextures":"","/Render/OmniverseKit/HydraTextures/omni_kit_widget_viewport_ViewportTexture_0":"RenderProduct","/Render/Vars":"","/Render/Vars/LdrColor":"RenderVar",
 "/World/Flow/Offscreen/debugVolume":"FlowDebugVolumeParams","/World/Flow/Render/rayMarch/cloud":"FlowRayMarchCloudParams","/World/Flow/Render/renderSettings":"FlowRenderSettingsParams",
}
ALLOWED_EXISTING_OPINIONS={
 "/World":{},"/World/Flow":{},"/World/Flow/Offscreen":{},"/World/Flow/Render":{},"/World/Flow/Render/rayMarch":{},
 "/World/Flow/Simulate":{"enableHighPrecisionDensity":False,"enableHighPrecisionVelocity":False},
 "/World/Flow/Simulate/nanoVdbExport":{"interopEnabled":False},
}
CAMERA_CUSTOM_PROPERTIES={"omni:kit:centerOfInterest"}
RENDER_CUSTOM_PROPERTIES={"viewPickingId","viewportHandle","overrideClipRange"}

def canonical_bytes(value:object)->bytes:return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def sha256_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest().upper()
def sha256_file(path:Path)->str:return sha256_bytes(Path(path).read_bytes())
def _depth(path:str)->int:return len([part for part in path.split("/") if part])

def create_container_files(stage_root:Path)->dict:
 stage_root=Path(stage_root);runtime=stage_root/RUNTIME_FILENAME;container=stage_root/CONTAINER_FILENAME
 for path,data in ((runtime,RUNTIME_TEXT.encode()),(container,CONTAINER_TEXT.encode())):
  if path.exists():raise RuntimeError("isolation_layer_path_reuse:"+str(path))
  path.write_bytes(data)
 return {"runtime":runtime,"container":container,"runtime_sha256":sha256_file(runtime),"container_sha256":sha256_file(container)}

def _layer_specs(layer,layer_audit)->list[dict]:
 paths=[];layer.Traverse(layer.pseudoRoot.path,lambda path:paths.append(str(path)))
 if len(paths)>1000:raise RuntimeError("layer_spec_population_oversize")
 rows=[]
 for path in sorted(paths):
  if path=="/":continue
  spec=layer.GetObjectAtPath(path);rows.append({"path":path,"spec":layer_audit._info(spec)})
 return rows

def _layer_projection(role:str,layer,export_dir:Path,boundary:str,layer_audit)->dict:
 data=layer.ExportToString().encode("utf-8")
 if not data or len(data)>MAX_LAYER_BYTES:raise RuntimeError("layer_export_size_invalid:"+role)
 export_dir.mkdir(parents=True,exist_ok=True);path=export_dir/f"{boundary}_{role}.usda.txt"
 if path.exists():raise RuntimeError("layer_export_path_reuse:"+str(path))
 path.write_bytes(data);real=str(layer.realPath or "")
 return {"role":role,"identifier":str(layer.identifier),"real_path":real,"anonymous":bool(layer.anonymous),"dirty":bool(layer.dirty),"file_sha256":sha256_file(Path(real)) if real and Path(real).is_file() else None,"memory_export_sha256":sha256_bytes(data),"memory_export_bytes":len(data),"memory_export_path":str(path),"specs":_layer_specs(layer,layer_audit)}

def _layer_role(layer,expected:dict)->str|None:
 identifier=str(layer.identifier);real=str(layer.realPath or "")
 for role,path in expected.items():
  if role=="session":
   if bool(layer.anonymous) and identifier.endswith(":container-session.usda"):return role
  elif Path(real).resolve()==Path(path).resolve():return role
 return None

def _runtime_records(stage,roles:dict,protected_paths:set[str],layer_audit)->list[dict]:
 rows=[]
 for role in ("container","session","runtime"):
  layer=roles[role]
  paths=[];layer.Traverse(layer.pseudoRoot.path,lambda path:paths.append(str(path)))
  for path in sorted(paths):
   if path=="/" or "." in path.rsplit("/",1)[-1]:continue
   spec=layer.GetPrimAtPath(path);prim=stage.GetPrimAtPath(path);properties=[]
   for prop in spec.properties if spec is not None else []:
    name=str(prop.name);composed=prim.GetProperty(name) if prim else None;declared=False
    if prim:
     definition=prim.GetPrimDefinition();declared=bool(definition and name in definition.GetPropertyNames())
    custom=name in CAMERA_CUSTOM_PROPERTIES|RENDER_CUSTOM_PROPERTIES
    properties.append({"name":name,"schema_declared":declared,"explicit_custom_exception":custom,"spec":layer_audit._info(prop),"composed":layer_audit._property_record(composed) if composed else None})
   rows.append({"path":path,"type_name":prim.GetTypeName() if prim else "","parent":str(prim.GetParent().GetPath()) if prim and prim.GetParent() else None,"depth":_depth(path),"layer_role":role,"protected_path":path in protected_paths,"prim_spec":layer_audit._info(spec),"properties":properties})
 return rows

def capture(stage,boundary:str,index:int,export_dir:Path,expected_paths:dict,protected_template:dict|None,layer_audit)->dict:
 if boundary not in BOUNDARIES or index!=BOUNDARIES.index(boundary):raise ValueError("snapshot_boundary_invalid")
 stack=list(stage.GetLayerStack(includeSessionLayers=True));role_map={};unknown=[]
 for layer in stack:
  role=_layer_role(layer,expected_paths)
  if role is None:unknown.append(str(layer.identifier))
  elif role in role_map:raise RuntimeError("duplicate_layer_role:"+role)
  else:role_map[role]=layer
 if unknown or set(role_map)!={"session","container","runtime","protected"}:raise RuntimeError("unknown_or_missing_layer")
 protected_paths=set(expected_paths["protected_paths"])
 if protected_template is None:
  protected_template={path:[prop.GetName() for prop in sorted(stage.GetPrimAtPath(path).GetAuthoredProperties(),key=lambda item:item.GetName())] for path in sorted(protected_paths)}
 protected_records={path:layer_audit._protected_record(stage,path,protected_template[path]) for path in sorted(protected_paths)}
 layers={role:_layer_projection(role,role_map[role],Path(export_dir),boundary,layer_audit) for role in ("container","session","runtime","protected")}
 edit_role=_layer_role(stage.GetEditTarget().GetLayer(),expected_paths)
 value={"schema":SCHEMA,"boundary":boundary,"sequence_index":index,"stage_identifier":str(stage.GetRootLayer().identifier),"edit_target_role":edit_role,"layer_stack":[{"index":i,"role":_layer_role(layer,expected_paths),"identifier":str(layer.identifier),"real_path":str(layer.realPath or ""),"anonymous":bool(layer.anonymous)} for i,layer in enumerate(stack)],"layers":layers,"protected":{"template":protected_template,"records":protected_records,"semantic_sha256":sha256_bytes(canonical_bytes(protected_records)),"path_count":len(protected_records)},"runtime_records":_runtime_records(stage,role_map,protected_paths,layer_audit)}
 data=canonical_bytes(value)
 if len(data)>MAX_DOCUMENT_BYTES:raise RuntimeError("isolation_snapshot_oversize")
 value["snapshot_sha256"]=sha256_bytes(data);return value

def _validate_runtime(records:list[dict],protected_paths:set[str])->list[str]:
 reasons=[];seen=set()
 for row in records:
  key=(row.get("layer_role"),row.get("path"))
  if key in seen:reasons.append("duplicate_runtime_prim:"+str(row.get("path")));continue
  seen.add(key);path=row.get("path");kind=row.get("type_name")
  if path in ALLOWED_RUNTIME_PRIMS:
   if kind!=ALLOWED_RUNTIME_PRIMS[path]:reasons.append("unknown_runtime_type:"+str(path))
  elif path in ALLOWED_EXISTING_OPINIONS:
   allowed=ALLOWED_EXISTING_OPINIONS[path];observed={prop.get("name"):((prop.get("composed") or {}).get("value")) for prop in row.get("properties") or []}
   if observed!=allowed:reasons.append("protected_runtime_opinion_unknown:"+str(path))
  else:reasons.append("unknown_runtime_path:"+str(path))
  if _depth(str(path))>5:reasons.append("runtime_depth_exceeded:"+str(path))
  for prop in row.get("properties") or []:
   if path in ALLOWED_EXISTING_OPINIONS:continue
   if not prop.get("schema_declared") and not prop.get("explicit_custom_exception"):reasons.append("unknown_runtime_property:"+str(path)+":"+str(prop.get("name")))
 return reasons

def validate_document(value:dict)->dict:
 reasons=[]
 if not isinstance(value,dict) or value.get("schema")!=SCHEMA:return {"accepted":False,"reasons":["schema_invalid"]}
 boundary=value.get("boundary")
 if boundary not in BOUNDARIES or value.get("sequence_index")!=BOUNDARIES.index(boundary):reasons.append("boundary_invalid")
 layers=value.get("layers") or {}
 if set(layers)!={"container","session","runtime","protected"}:reasons.append("layer_role_set_invalid")
 stack=value.get("layer_stack") or []
 if [row.get("role") for row in stack]!=["session","container","runtime","protected"]:reasons.append("layer_identity_or_order_invalid")
 if value.get("edit_target_role")!="container":reasons.append("edit_target_role_invalid")
 protected=layers.get("protected") or {}
 if protected.get("dirty") is not False:reasons.append("protected_layer_dirty")
 if protected.get("file_sha256")!=EXPECTED_PROTECTED_SHA256:reasons.append("protected_disk_hash_mismatch")
 if protected.get("memory_export_sha256")!=EXPECTED_PROTECTED_SHA256:reasons.append("protected_memory_hash_mismatch")
 for role,row in layers.items():
  if type(row.get("memory_export_bytes")) is not int or not 0<row["memory_export_bytes"]<=MAX_LAYER_BYTES:reasons.append("layer_oversize:"+role)
 records=value.get("runtime_records")
 if not isinstance(records,list):reasons.append("runtime_records_missing")
 else:
  reasons.extend(_validate_runtime(records,set((value.get("protected") or {}).get("template") or {})))
  if len({row.get("path") for row in records if row.get("path") in ALLOWED_RUNTIME_PRIMS})>len(ALLOWED_RUNTIME_PRIMS):reasons.append("runtime_prim_population_exceeded")
 observed=value.get("snapshot_sha256");copy=dict(value);copy.pop("snapshot_sha256",None)
 try:expected=sha256_bytes(canonical_bytes(copy))
 except Exception:expected=None
 if observed!=expected:reasons.append("snapshot_hash_contradiction")
 return {"accepted":not reasons,"reasons":reasons}

def validate_sequence(documents:list[dict])->dict:
 reasons=[]
 if not isinstance(documents,list) or len(documents)!=4:return {"schema":SEQUENCE_SCHEMA,"accepted":False,"classification":"safe_stop_runtime_authoring_isolation_failure","reasons":["snapshot_count_invalid"]}
 if [row.get("boundary") for row in documents]!=list(BOUNDARIES):reasons.append("snapshot_order_invalid")
 for row in documents:reasons.extend(validate_document(row)["reasons"])
 for role in ("container","runtime","protected"):
  ids=[row["layers"][role]["identifier"] for row in documents];files=[row["layers"][role]["file_sha256"] for row in documents]
  if len(set(ids))!=1:reasons.append("layer_identity_changed:"+role)
  if len(set(files))!=1:reasons.append("layer_disk_hash_changed:"+role)
 protected_memory=[row["layers"]["protected"]["memory_export_sha256"] for row in documents]
 semantics=[row["protected"]["semantic_sha256"] for row in documents]
 if len(set(protected_memory))!=1:reasons.append("protected_memory_changed")
 if len(set(semantics))!=1:reasons.append("protected_semantics_changed")
 return {"schema":SEQUENCE_SCHEMA,"accepted":not reasons,"classification":"runtime_authoring_isolation_qualified" if not reasons else "safe_stop_runtime_authoring_isolation_failure","reasons":reasons,"protected_file_sha256":documents[0]["layers"]["protected"]["file_sha256"],"protected_memory_sha256":protected_memory[0],"protected_semantic_sha256":semantics[0]}

def write_document(path:Path,value:dict,atomic_write_json)->None:
 result=validate_document(value)
 if not result["accepted"]:raise RuntimeError(result["reasons"][0])
 if len(canonical_bytes(value))>MAX_DOCUMENT_BYTES:raise RuntimeError("isolation_snapshot_oversize")
 atomic_write_json(Path(path),value)
def read_document(path:Path)->dict:
 path=Path(path);size=path.stat().st_size
 if size<=0 or size>MAX_DOCUMENT_BYTES:raise RuntimeError("isolation_snapshot_size_invalid")
 value=json.loads(path.read_text(encoding="utf-8"));result=validate_document(value)
 if not result["accepted"]:raise RuntimeError(result["reasons"][0])
 return value
