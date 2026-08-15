from __future__ import annotations
import json
from pathlib import Path
import phase6ig_marker_contract as markers

def run_fixture(output_root:Path)->dict:
 output_root=Path(output_root)
 if output_root.exists():raise RuntimeError("Phase 6IG marker fixture refuses root reuse")
 output_root.mkdir(parents=True);path=output_root/"markers.jsonl";cases=[]
 payloads={"kit_launch":{"attempt_id":"a","executable_path":"C:/kit.exe"},"kit_app_ready":{"attempt_id":"a"},"dependencies_complete":{"module_count":5},"stage_generation_started":{"condition":"collision_off"},"stage_generation_complete":{"stage_sha256":"A"*64},"camera_snapshot_started":{"boundary":"generated","sequence_index":0},"camera_snapshot_complete":{"boundary":"generated","sequence_index":0,"snapshot_sha256":"B"*64},"stage_open_complete":{"stage_identifier":"C:/off.usda"},"stopped_update_started":{"update_count":1},"stopped_update_complete":{"update_count":1},"camera_sequence_validated":{"classification":"camera_runtime_augmentation_audited","accepted":True},"protected_digest_validated":{"sha256":"C"*64},"operation_complete":{"scope":"camera_audit_only"},"stage_close_started":{"stage_identifier":"C:/off.usda"},"stage_close_complete":{"context_empty":True},"shutdown_complete":{"requested":True}}
 for event,payload in payloads.items():
  try:markers.append_marker(path,event,payload);passed=True;reason="pass"
  except Exception as exc:passed=False;reason=f"{type(exc).__name__}:{exc}"
  cases.append({"name":"positive_"+event,"passed":passed,"reason":reason})
 def reject(name,event,payload,expected):
  try:markers.append_marker(path,event,payload);passed=False;reason="unexpected_acceptance"
  except Exception as exc:reason=f"{type(exc).__name__}:{exc}";passed=expected in reason
  cases.append({"name":name,"passed":passed,"reason":reason})
 reject("reserved_path","kit_app_ready",{"attempt_id":"a","path":"x"},"reserved_marker_key_collision:path")
 reject("missing","kit_app_ready",{},"required_marker_key_missing:attempt_id")
 reject("unknown","kit_app_ready",{"attempt_id":"a","extra":1},"unknown_marker_payload_key:extra")
 reject("type","stopped_update_started",{"update_count":True},"marker_payload_type_invalid:update_count")
 rows=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
 passed=sum(1 for row in cases if row["passed"]);report={"schema":"campfire.phase6ig.marker-fixture.v1","phase":"phase6ig","status":"qualified" if passed==len(cases) and len(rows)==len(payloads) else "failed","case_count":[passed,len(cases)],"kit_launch_count":0,"cases":cases};(output_root/"fixture_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8");return report
