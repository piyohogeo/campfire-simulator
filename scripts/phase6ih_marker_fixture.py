from __future__ import annotations
import json
from pathlib import Path
import phase6ih_marker_contract as marker
def run_fixture(root:Path)->dict:
 root=Path(root)
 if root.exists():raise RuntimeError("Phase 6IH marker fixture refuses root reuse")
 root.mkdir(parents=True);path=root/"markers.jsonl";cases=[]
 payloads={"kit_launch":{"attempt_id":"a","executable_path":"C:/kit.exe"},"kit_app_ready":{"attempt_id":"a"},"dependencies_complete":{"module_count":7},"layer_generation_started":{"condition":"collision_off_stopped_timeline"},"layer_generation_complete":{"protected_sha256":"A"*64,"container_sha256":"B"*64,"runtime_sha256":"C"*64},"isolation_snapshot_started":{"boundary":"generated","sequence_index":0},"isolation_snapshot_complete":{"boundary":"generated","sequence_index":0,"snapshot_sha256":"D"*64},"stage_open_complete":{"stage_identifier":"C:/container.usda"},"stopped_update_started":{"update_count":1},"stopped_update_complete":{"update_count":1},"isolation_sequence_validated":{"classification":"runtime_authoring_isolation_qualified","accepted":True},"operation_complete":{"scope":"runtime_authoring_isolation_only"},"stage_close_started":{"stage_identifier":"C:/container.usda"},"stage_close_complete":{"context_empty":True},"shutdown_complete":{"requested":True}}
 for event,payload in payloads.items():
  try:marker.append_marker(path,event,payload);ok=True;reason="pass"
  except Exception as exc:ok=False;reason=f"{type(exc).__name__}:{exc}"
  cases.append({"name":"positive_"+event,"passed":ok,"reason":reason})
 def reject(name,event,payload,expected):
  try:marker.append_marker(path,event,payload);ok=False;reason="unexpected_acceptance"
  except Exception as exc:reason=f"{type(exc).__name__}:{exc}";ok=expected in reason
  cases.append({"name":name,"passed":ok,"reason":reason})
 reject("reserved","kit_app_ready",{"attempt_id":"a","path":"x"},"reserved_marker_key_collision");reject("missing","kit_app_ready",{},"required_marker_key_missing");reject("unknown","kit_app_ready",{"attempt_id":"a","x":1},"unknown_marker_payload_key");reject("type","stopped_update_started",{"update_count":True},"marker_payload_type_invalid")
 rows=[json.loads(line) for line in path.read_text().splitlines()];passed=sum(row["passed"] for row in cases);report={"schema":"campfire.phase6ih.marker-fixture.v1","phase":"phase6ih","status":"qualified" if passed==len(cases) and len(rows)==len(payloads) else "failed","case_count":[passed,len(cases)],"kit_launch_count":0,"cases":cases};(root/"fixture_report.json").write_text(json.dumps(report,indent=2)+"\n");return report
