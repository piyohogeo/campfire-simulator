"""No-Kit fixture for every Phase 6IE durable marker payload."""

from __future__ import annotations

import json
from pathlib import Path

import phase6ie_marker_contract as markers


def _events() -> list[tuple[str, dict]]:
    return [
        ("kit_launch", {"attempt_id": "fixture", "executable_path": "kit.exe"}),
        ("kit_app_ready", {"attempt_id": "fixture"}),
        ("authoring_manifest_validation_started", {"manifest_path": "manifest.json"}),
        ("authoring_manifest_validation_complete", {"manifest_sha256": "A" * 64, "module_count": 5}),
        ("authoring_dependencies_load_started", {"module_count": 5}),
        ("authoring_dependency_loaded", {"module_id": "stage_builder", "module_path": "stage_builder.py", "sha256": "B" * 64}),
        ("authoring_dependencies_load_complete", {"module_count": 5}),
        ("authoring_callable_validation_complete", {"callable_count": 18}),
        ("stage_generation_started", {"condition": "collision_off_and_collision_on_fixture"}),
        ("stage_generation_complete", {"off_sha256": "C" * 64, "on_sha256": "D" * 64}),
        ("stage_parse_started", {"parser": "pxr.Usd.Stage.Open and pxr.Sdf.Layer.FindOrOpen"}),
        ("float3_validation_started", {"scope": "parser_fixture_off", "attribute_path": "/World/Flow/Emitter.position"}),
        ("float3_validation_complete", {"scope": "parser_fixture_off", "attribute_path": "/World/Flow/Emitter.position", "accepted": True, "maximum_ulp_distance": 0}),
        ("stage_parse_complete", {"positive_count": 2, "negative_count": 6}),
        ("stage_open_complete", {"stage_identifier": "off.usda", "root_layer_identifier": "off.usda"}),
        ("authored_prim_validation_started", {"prim_count": 25}),
        ("authored_prim_validation_complete", {"prim_count": 25, "changed_count": 0, "missing_count": 0}),
        ("runtime_prim_classification_started", {"observed_count": 14}),
        ("runtime_prim_classification_complete", {"observed_count": 14, "accepted_count": 14, "unknown_count": 0, "protected_conflict_count": 0}),
        ("root_layer_integrity_complete", {"before_sha256": "C" * 64, "after_sha256": "C" * 64, "unchanged": True}),
        ("required_prims_validated", {"prim_count": 25, "flow_setting_count": 40}),
        ("operation_complete", {"scope": "bounded_runtime_prim_stage_open_only"}),
        ("stage_close_started", {"stage_identifier": "off.usda"}),
        ("stage_close_complete", {"context_empty": True}),
        ("shutdown_complete", {"requested": True}),
    ]


def run_fixture(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6IE marker fixture refuses root reuse")
    output_root.mkdir(parents=True)
    cases = []
    marker_path = output_root / "markers.jsonl"
    events = _events()
    for name, payload in events:
        event, canonical = markers.produce_marker(name, **payload)
        markers.append_marker(marker_path, event, canonical)
    rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
    cases.append({"name": "actual_complete_payload_set", "passed": [row["marker"] for row in rows] == [name for name, _ in events]})

    def reject(name: str, action, prefix: str) -> None:
        try:
            action(); reason = None
        except Exception as error:
            reason = str(error)
        cases.append({"name": name, "passed": isinstance(reason, str) and reason.startswith(prefix), "reason": reason})

    reject("reserved_path", lambda: markers.canonical_payload("kit_app_ready", {"attempt_id": "x", "path": "bad"}), "reserved_marker_key_collision:path")
    reject("reserved_event_name", lambda: markers.canonical_payload("kit_app_ready", {"attempt_id": "x", "event_name": "bad"}), "reserved_marker_key_collision:event_name")
    reject("missing_required", lambda: markers.canonical_payload("kit_app_ready", {}), "required_marker_key_missing:attempt_id")
    reject("unknown_key", lambda: markers.canonical_payload("kit_app_ready", {"attempt_id": "x", "extra": 1}), "unknown_marker_payload_key:extra")
    reject("wrong_type", lambda: markers.canonical_payload("runtime_prim_classification_started", {"observed_count": True}), "marker_payload_type_invalid:observed_count")
    reject("unknown_event", lambda: markers.canonical_payload("future_event", {}), "unknown_marker_event:future_event")
    cases.append({"name": "one_jsonl_row_per_event", "passed": len(rows) == len(events) and marker_path.stat().st_size < 65536})
    report = {
        "schema": "campfire.phase6ie.marker-fixture.v1",
        "phase": "phase6ie",
        "status": "qualified" if all(item["passed"] for item in cases) else "failed",
        "kit_launch_count": 0,
        "case_count": [sum(item["passed"] for item in cases), len(cases)],
        "event_count": len(events),
        "cases": cases,
    }
    (output_root / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(); raise SystemExit(0 if run_fixture(args.output_root.absolute())["status"] == "qualified" else 1)
