"""Reserved-key-safe durable markers for Phase 6IF audit-only smoke."""

from __future__ import annotations

import inspect, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

AUTO_KEYS=frozenset({"marker","timestamp_utc","path"})
EVENT_FIELDS={
 "kit_launch":{"attempt_id":str,"executable_path":str},"kit_app_ready":{"attempt_id":str},
 "authoring_manifest_validation_started":{"manifest_path":str},"authoring_manifest_validation_complete":{"manifest_sha256":str,"module_count":int},
 "authoring_dependencies_load_started":{"module_count":int},"authoring_dependency_loaded":{"module_id":str,"module_path":str,"sha256":str},
 "authoring_dependencies_load_complete":{"module_count":int},"authoring_callable_validation_complete":{"callable_count":int},
 "stage_generation_started":{"condition":str},"stage_generation_complete":{"off_sha256":str,"on_sha256":str},
 "stage_parse_started":{"parser":str},"stage_parse_complete":{"positive_count":int,"negative_count":int},
 "layer_snapshot_started":{"boundary":str,"sequence_index":int},"layer_snapshot_complete":{"boundary":str,"sequence_index":int,"snapshot_sha256":str},
 "stage_open_complete":{"stage_identifier":str,"root_layer_identifier":str},
 "minimal_stopped_update_started":{"update_count":int},"minimal_stopped_update_complete":{"update_count":int,"timeline_play_calls":int},
 "layer_diff_started":{"before_boundary":str,"after_boundary":str},"layer_diff_complete":{"before_boundary":str,"after_boundary":str,"changed_target_count":int,"protected_unchanged":bool},
 "runtime_prim_audit_started":{"observed_count":int},"runtime_prim_audit_complete":{"observed_count":int,"unknown_count":int,"protected_conflict_count":int,"legacy_policy_accepted":bool},
 "authored_change_audit_started":{"path_count":int},"authored_change_audit_complete":{"path_count":int,"protected_unchanged":bool},
 "root_session_opinion_audit_complete":{"root_dirty":bool,"session_dirty":bool,"root_memory_changed":bool,"session_memory_changed":bool},
 "protected_semantics_validation_complete":{"path_count":int,"changed_count":int},
 "operation_complete":{"scope":str},
 "stage_close_started":{"stage_identifier":str},"stage_close_complete":{"context_empty":bool},
 "after_close_opinion_check_complete":{"root_found":bool,"session_found":bool},"shutdown_complete":{"requested":bool},
}

def append_marker(marker_file:Path,event_name:str,payload:Mapping[str,object])->dict:
 canonical=canonical_payload(event_name,payload);marker_file=Path(marker_file);marker_file.parent.mkdir(parents=True,exist_ok=True)
 row={"marker":event_name,"timestamp_utc":datetime.now(timezone.utc).isoformat(),**canonical}
 with marker_file.open("a",encoding="utf-8") as stream:stream.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n");stream.flush();os.fsync(stream.fileno())
 return row

RESERVED_KEYS=AUTO_KEYS|frozenset(inspect.signature(append_marker).parameters)

def canonical_payload(event_name:str,payload:Mapping[str,object])->dict:
 if event_name not in EVENT_FIELDS:raise ValueError("unknown_marker_event:"+event_name)
 if not isinstance(payload,Mapping):raise TypeError("marker_payload_type_invalid")
 collision=sorted(set(payload)&RESERVED_KEYS)
 if collision:raise ValueError("reserved_marker_key_collision:"+collision[0])
 expected=EVENT_FIELDS[event_name];missing=sorted(set(expected)-set(payload));unknown=sorted(set(payload)-set(expected))
 if missing:raise ValueError("required_marker_key_missing:"+missing[0])
 if unknown:raise ValueError("unknown_marker_payload_key:"+unknown[0])
 result=dict(payload)
 for key,expected_type in expected.items():
  value=result[key];valid=type(value)is expected_type if expected_type in(bool,int) else isinstance(value,expected_type)
  if not valid:raise TypeError("marker_payload_type_invalid:"+key)
  if expected_type is str and not value:raise ValueError("marker_payload_empty:"+key)
 return result

def produce_marker(event_name:str,**values:object)->tuple[str,dict]:return event_name,canonical_payload(event_name,values)
