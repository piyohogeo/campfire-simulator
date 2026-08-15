"""No-Kit producer/validator and marker fixture for Phase 6IB."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import phase6ib_marker_contract as markers
import phase6ib_stage_authoring as authoring


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run_fixture(output_root: Path, contract_path: Path, sidecar_path: Path, repository_root: Path) -> dict:
    if output_root.exists(): raise RuntimeError("Phase 6IB no-Kit fixture refuses root reuse")
    output_root.mkdir(parents=True)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    frozen_path = repository_root / contract["frozen_probe_contract"]["path"]
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    cases = []
    def case(name: str, passed: bool, **evidence): cases.append({"name": name, "passed": bool(passed), **evidence})

    digest = _sha(contract_path)
    case("contract_digest", digest == sidecar_path.read_text(encoding="ascii").split()[0].upper())
    case("frozen_contract_digest", _sha(frozen_path) == contract["frozen_probe_contract"]["sha256"])
    for condition in ("collision_off", "collision_on"):
        spec = authoring.stage_spec(frozen, condition)
        result = authoring.validate_spec(spec, frozen, condition)
        case("canonical_spec_" + condition, result["accepted"], validation=result)
    off = authoring.stage_spec(frozen, "collision_off")
    on = authoring.stage_spec(frozen, "collision_on")
    changed = []
    for key in sorted(set(off) | set(on)):
        if off.get(key) != on.get(key): changed.append(key)
    case("one_variable_spec", changed == ["condition", "physics_collision_enabled"], changed=changed)
    scene = off["scene"]
    case("frozen_geometry", scene["proxy_topology"] == [26,36,120] and scene["source_surface_gap_m"] == 0.06 and scene["end_clearance_m"] == 1.6)
    case("frozen_camera_roi_gates", scene["camera_eye_m"] == [5.5,0.0,0.9] and scene["roi"] == frozen["temporal_measurement"]["rois_normalized"] and scene["numeric_gates"] == frozen["temporal_measurement"]["hard_gates"])
    for mutation, reason in (("missing","required_prim_missing:"),("duplicate","duplicate_prim_path"),("type","prim_type_mismatch:"),("nan","nonfinite_value"),("unknown_schema","schema_mismatch")):
        result = authoring.validate_spec(authoring.mutate_spec(off, mutation), frozen, "collision_off")
        case("negative_spec_" + mutation, not result["accepted"] and result["reason"].startswith(reason), reason=result["reason"])
    try:
        authoring.stage_spec(frozen, "future")
        rejected = False
    except ValueError: rejected = True
    case("unknown_condition_rejected", rejected)
    legacy = b'def FlowAdvectionChannelParams "temperature" { float secondOrderBlendFactor = 0.9 }'
    case("legacy_inline_identified", authoring.reject_legacy_inline_usda(legacy))
    authoring_source = (repository_root / contract["sources"]["authoring"]["path"]).read_text(encoding="utf-8")
    production_source = (repository_root / contract["known_good_basis"]["production_registered_schema_authoring"]["path"]).read_text(encoding="utf-8")
    known_usda = (repository_root / contract["known_good_basis"]["multiline_usda"]["path"]).read_text(encoding="utf-8")
    case("registered_schema_api_selected", "Usd.Stage.CreateNew" in authoring_source and "stage.DefinePrim" in authoring_source and "FlowAdvectionChannelParams" in authoring_source)
    case("production_api_basis_present", 'stage.DefinePrim(' in production_source and '"FlowAdvectionChannelParams"' in production_source)
    case("known_good_multiline_basis_present", 'def FlowAdvectionChannelParams "temperature"\n' in known_usda and 'float secondOrderBlendFactor = 0.9\n' in known_usda)
    positive_authoring_source = inspect.getsource(authoring.author_stage)
    case(
        "positive_authoring_has_no_inline_usda",
        'FlowAdvectionChannelParams "temperature" { float' not in positive_authoring_source
        and ".write_text(" not in positive_authoring_source
        and "Usd.Stage.CreateNew" in positive_authoring_source,
    )

    examples = [
        ("kit_launch", {"attempt_id":"phase6ib-stage-open-attempt01","executable_path":"kit.exe"}),
        ("kit_app_ready", {"attempt_id":"phase6ib-stage-open-attempt01"}),
        ("probe_import_complete", {"module_path":"probe.py","sha256":"A"*64,"callable_identity":{"start_smoke":"module.start_smoke"}}),
        ("stage_generation_started", {"condition":"collision_off_and_collision_on_fixture"}),
        ("stage_generation_complete", {"off_sha256":"A"*64,"on_sha256":"B"*64}),
        ("stage_parse_started", {"parser":"pxr.Usd.Stage.Open"}),
        ("stage_parse_complete", {"positive_count":2,"negative_count":6}),
        ("stage_open_complete", {"stage_identifier":"off.usda","root_layer_identifier":"off.usda"}),
        ("required_prims_validated", {"prim_count":24,"flow_setting_count":12}),
        ("operation_complete", {"scope":"registered_schema_stage_open_only"}),
        ("stage_close_started", {"stage_identifier":"off.usda"}),
        ("stage_close_complete", {"context_empty":True}),
        ("shutdown_complete", {"requested":True}),
    ]
    marker_path = output_root / "markers.jsonl"
    for name, payload in examples:
        event, canonical = markers.produce_marker(name, **payload); markers.append_marker(marker_path, event, canonical)
    rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
    case("actual_marker_payloads", [row["marker"] for row in rows] == [name for name,_ in examples] and len(rows) == len(examples))
    for name, payload, expected in (
        ("reserved", {"attempt_id":"a","executable_path":"kit.exe","path":"x"}, "reserved_marker_key_collision:path"),
        ("missing", {"attempt_id":"a"}, "required_marker_key_missing:executable_path"),
        ("type", {"attempt_id":"a","executable_path":1}, "marker_payload_type_invalid:executable_path"),
    ):
        try: markers.canonical_payload("kit_launch", payload); reason = None
        except Exception as error: reason = str(error)
        case("marker_negative_" + name, reason == expected, reason=reason)
    case("bounded_outputs", marker_path.stat().st_size < 1024*1024)
    report = {"schema":"campfire.phase6ib.no-kit-fixture.v1","phase":"phase6ib","status":"qualified" if all(item["passed"] for item in cases) else "failed","kit_launch_count":0,"case_count":[sum(item["passed"] for item in cases),len(cases)],"cases":cases}
    (output_root / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return report
