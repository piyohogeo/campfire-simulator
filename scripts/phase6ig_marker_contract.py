"""Reserved-key-safe durable marker contract for Phase 6IG."""
from __future__ import annotations
import inspect,json,os
from datetime import datetime,timezone
from pathlib import Path
from typing import Mapping

AUTO_KEYS=frozenset({"marker","timestamp_utc","path"})
EVENT_FIELDS={
 "kit_launch":{"attempt_id":str,"executable_path":str},"kit_app_ready":{"attempt_id":str},
 "dependencies_complete":{"module_count":int},"stage_generation_started":{"condition":str},"stage_generation_complete":{"stage_sha256":str},
 "camera_snapshot_started":{"boundary":str,"sequence_index":int},"camera_snapshot_complete":{"boundary":str,"sequence_index":int,"snapshot_sha256":str},
 "stage_open_complete":{"stage_identifier":str},"stopped_update_started":{"update_count":int},"stopped_update_complete":{"update_count":int},
 "camera_sequence_validated":{"classification":str,"accepted":bool},"protected_digest_validated":{"sha256":str},"operation_complete":{"scope":str},
 "stage_close_started":{"stage_identifier":str},"stage_close_complete":{"context_empty":bool},"shutdown_complete":{"requested":bool},
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
 for key,kind in expected.items():
  value=result[key];valid=type(value)is kind if kind in(bool,int) else isinstance(value,kind)
  if not valid:raise TypeError("marker_payload_type_invalid:"+key)
  if kind is str and not value:raise ValueError("marker_payload_empty:"+key)
 return result
def produce_marker(event_name:str,**values:object)->tuple[str,dict]:return event_name,canonical_payload(event_name,values)
