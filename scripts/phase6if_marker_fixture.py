"""No-Kit full payload fixture for Phase 6IF markers."""

from __future__ import annotations

import json
from pathlib import Path

import phase6if_marker_contract as markers


def run_fixture(output_root: Path) -> dict:
    output_root=Path(output_root)
    if output_root.exists():raise RuntimeError("Phase 6IF marker fixture refuses root reuse")
    output_root.mkdir(parents=True);cases=[];marker_file=output_root/"markers.jsonl"
    payloads={
      "kit_launch":{"attempt_id":"attempt01","executable_path":"C:/kit.exe"},"kit_app_ready":{"attempt_id":"attempt01"},
      "authoring_manifest_validation_started":{"manifest_path":"C:/repo/scripts/manifest.json"},"authoring_manifest_validation_complete":{"manifest_sha256":"A"*64,"module_count":6},
      "authoring_dependencies_load_started":{"module_count":6},"authoring_dependency_loaded":{"module_id":"audit","module_path":"C:/repo/scripts/audit.py","sha256":"B"*64},"authoring_dependencies_load_complete":{"module_count":6},"authoring_callable_validation_complete":{"callable_count":17},
      "stage_generation_started":{"condition":"collision_off_and_collision_on_fixture"},"stage_generation_complete":{"off_sha256":"C"*64,"on_sha256":"D"*64},"stage_parse_started":{"parser":"pxr"},"stage_parse_complete":{"positive_count":2,"negative_count":6},
      "layer_snapshot_started":{"boundary":"generated","sequence_index":0},"layer_snapshot_complete":{"boundary":"generated","sequence_index":0,"snapshot_sha256":"E"*64},"stage_open_complete":{"stage_identifier":"C:/off.usda","root_layer_identifier":"C:/off.usda"},
      "minimal_stopped_update_started":{"update_count":1},"minimal_stopped_update_complete":{"update_count":1,"timeline_play_calls":0},"layer_diff_started":{"before_boundary":"generated","after_boundary":"live_open"},"layer_diff_complete":{"before_boundary":"generated","after_boundary":"live_open","changed_target_count":12,"protected_unchanged":True},
      "runtime_prim_audit_started":{"observed_count":14},"runtime_prim_audit_complete":{"observed_count":14,"unknown_count":0,"protected_conflict_count":0,"legacy_policy_accepted":False},"authored_change_audit_started":{"path_count":2},"authored_change_audit_complete":{"path_count":2,"protected_unchanged":True},
      "root_session_opinion_audit_complete":{"root_dirty":True,"session_dirty":False,"root_memory_changed":True,"session_memory_changed":True},"protected_semantics_validation_complete":{"path_count":25,"changed_count":0},"operation_complete":{"scope":"audit_only"},
      "stage_close_started":{"stage_identifier":"C:/off.usda"},"stage_close_complete":{"context_empty":True},"after_close_opinion_check_complete":{"root_found":True,"session_found":False},"shutdown_complete":{"requested":True},
    }
    for name,payload in payloads.items():
        try:markers.append_marker(marker_file,name,payload);passed=True;reason="pass"
        except Exception as error:passed=False;reason=f"{type(error).__name__}:{error}"
        cases.append({"name":"positive_"+name,"passed":passed,"reason":reason})
    def reject(name,event,payload,expected):
        try:markers.append_marker(marker_file,event,payload);passed=False;reason="unexpected_acceptance"
        except Exception as error:reason=f"{type(error).__name__}:{error}";passed=expected in reason
        cases.append({"name":name,"passed":passed,"reason":reason})
    reject("reserved_path","kit_app_ready",{"attempt_id":"attempt01","path":"x"},"reserved_marker_key_collision:path")
    reject("required_missing","kit_app_ready",{},"required_marker_key_missing:attempt_id")
    reject("unknown_key","kit_app_ready",{"attempt_id":"attempt01","extra":1},"unknown_marker_payload_key:extra")
    reject("type_invalid","minimal_stopped_update_started",{"update_count":True},"marker_payload_type_invalid:update_count")
    rows=[json.loads(line) for line in marker_file.read_text(encoding="utf-8").splitlines()]
    passed=sum(1 for item in cases if item["passed"])
    report={"schema":"campfire.phase6if.marker-fixture.v1","phase":"phase6if","status":"qualified" if passed==len(cases) and len(rows)==len(payloads) else "failed","case_count":[passed,len(cases)],"positive_event_count":len(payloads),"jsonl_row_count":len(rows),"kit_launch_count":0,"cases":cases}
    (output_root/"fixture_report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return report
