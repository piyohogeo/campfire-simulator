"""No-Kit producer-to-consumer fixture for Phase 6IF layer evidence."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import phase6if_layer_opinion_audit as audit
from phase6hu_atomic_report import atomic_write_json


def _rehash(value: dict) -> None:
    value.pop("snapshot_sha256", None)
    value["snapshot_sha256"] = audit.sha256_bytes(audit.canonical_bytes(value))


def _materialize(value: dict, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for role in ("root_layer", "session_layer"):
        projection = value[role]
        path = root / f"{value['boundary']}_{role}.usda.txt"
        data = (f"#usda 1.0\n# {value['boundary']} {role}\n").encode("utf-8")
        path.write_bytes(data)
        projection["memory_export_path"] = str(path)
        projection["memory_export_bytes"] = len(data)
        projection["memory_export_sha256"] = audit.sha256_bytes(data)
    _rehash(value)


def _round_trip(value: dict, root: Path, name: str) -> dict:
    case_root = root / name
    _materialize(value, case_root / "exports")
    path = case_root / "snapshot.json"
    audit.write_snapshot(path, value, atomic_write_json)
    loaded = audit.read_snapshot(path)
    artifacts = audit.validate_snapshot_artifacts(loaded, case_root / "exports")
    if not artifacts["accepted"]:
        raise RuntimeError(artifacts["reasons"][0])
    return loaded


def run_fixture(output_root: Path) -> dict:
    output_root = Path(output_root)
    if output_root.exists():
        raise RuntimeError("Phase 6IF fixture refuses root reuse")
    output_root.mkdir(parents=True)
    cases = []

    def positive(name: str, mutate=None) -> None:
        before = audit.fixture_snapshot("generated", 0)
        after = audit.fixture_snapshot("live_open", 1)
        if mutate: mutate(before, after)
        try:
            left = _round_trip(before, output_root / "cases", name + "_before")
            right = _round_trip(after, output_root / "cases", name + "_after")
            result = audit.diff_snapshots(left, right)
            passed = result.get("accepted") is True and result.get("classification") == "observational_audit_only"
            reason = "pass" if passed else ";".join(result.get("reasons") or ["unexpected_rejection"])
        except Exception as error:
            passed = False; reason = f"{type(error).__name__}:{error}"
        cases.append({"name": name, "kind": "positive_observation", "passed": passed, "reason": reason})

    def negative(name: str, mutate, expected: str, post_materialize_mutate=None) -> None:
        before = audit.fixture_snapshot("generated", 0)
        after = audit.fixture_snapshot("live_open", 1)
        mutate(before, after)
        try:
            left = _round_trip(before, output_root / "cases", name + "_before")
            if post_materialize_mutate is None:
                right = _round_trip(after, output_root / "cases", name + "_after")
            else:
                case_root = output_root / "cases" / (name + "_after")
                _materialize(after, case_root / "exports")
                post_materialize_mutate(after)
                path = case_root / "snapshot.json"
                audit.write_snapshot(path, after, atomic_write_json)
                right = audit.read_snapshot(path)
            result = audit.diff_snapshots(left, right)
            reasons = result.get("reasons") or []
            passed = result.get("accepted") is False and any(expected in item for item in reasons)
            reason = ";".join(reasons) if reasons else "unexpected_acceptance"
        except Exception as error:
            text = f"{type(error).__name__}:{error}"
            passed = expected in text; reason = text
        cases.append({"name": name, "kind": "negative_fail_closed", "passed": passed, "reason": reason, "expected": expected})

    positive("root_file_unchanged_memory_differs", lambda b, a: a["root_layer"].__setitem__("memory_export_sha256", "E" * 64))
    positive("dirty_only", lambda b, a: a["root_layer"].__setitem__("dirty", True))
    positive("runtime_property_added", lambda b, a: a["target_prims"][audit.RUNTIME_PATHS[0]].update({"exists": True, "properties": [{"name": "runtime:value", "kind": "attribute"}]}))
    positive("debug_relationship_added", lambda b, a: a["target_prims"]["/World/Flow/Offscreen/debugVolume"].update({"exists": True, "relationships": [{"name": "debug", "targets": ["/Render"]}]}))
    positive("property_order_changed", lambda b, a: a["target_prims"][audit.AUTHORED_CHANGED_PATHS[0]].update({"property_order": ["b", "a"]}))
    positive("schema_application_added", lambda b, a: a["target_prims"][audit.AUTHORED_CHANGED_PATHS[0]].update({"applied_schemas": ["RuntimeAPI"]}))
    positive("session_opinion_added", lambda b, a: a["target_prims"][audit.RUNTIME_PATHS[0]]["layer_specs"]["session"].update({"prim": {"exists": True, "fields": {"specifier": "over"}}}))
    positive("root_opinion_added", lambda b, a: a["target_prims"][audit.RUNTIME_PATHS[0]]["layer_specs"]["root"].update({"prim": {"exists": True, "fields": {"specifier": "over"}}}))
    positive("authored_record_changed_protected_semantics_unchanged", lambda b, a: a["target_prims"][audit.AUTHORED_CHANGED_PATHS[1]].update({"property_order": ["enabled"]}))

    negative("root_file_hash_changed", lambda b, a: a["root_layer"].__setitem__("file_sha256", "F" * 64), "root_file_hash_changed")
    for name, protected_path in (
        ("protected_collision_value_changed", "/World/Flow/Simulate"),
        ("protected_emitter_value_changed", "/World/Flow/Emitter"),
        ("protected_geometry_changed", "/World/DiagnosticLog/FlowCollisionProxy"),
        ("protected_type_changed", "/World/PhysicsScene"),
        ("protected_relationship_changed", "/World/Flow/Emitter"),
    ):
        def mutate_protected(b, a, path=protected_path, label=name):
            a["protected_semantics"]["paths"][path]["mutation"] = label
            a["protected_semantics"]["sha256"] = audit.sha256_bytes(audit.canonical_bytes(a["protected_semantics"]["paths"]))
        negative(name, mutate_protected, "protected_semantics_changed")
    negative("unknown_layer", lambda b, a: a["layer_stack"].append({"index": 2, "identifier": "anon:unknown", "real_path": "", "anonymous": True}), "layer_stack_invalid")
    negative("unbounded_export", lambda b, a: None, "layer_export_size_invalid", lambda a: (a["root_layer"].__setitem__("memory_export_bytes", audit.MAX_LAYER_EXPORT_BYTES + 1), _rehash(a)))
    negative("nonfinite", lambda b, a: a["target_prims"][audit.AUTHORED_CHANGED_PATHS[0]].update({"value": float("nan")}), "ValueError")
    negative("missing_target", lambda b, a: a["target_prims"].pop(audit.RUNTIME_PATHS[0]), "target_prim_set_invalid")
    negative("duplicate_target_shape", lambda b, a: a.__setitem__("target_prims", list(a["target_prims"].items()) + [(audit.RUNTIME_PATHS[0], {})]), "target_prim_mapping_invalid")
    negative("swapped_target", lambda b, a: a["target_prims"].update({audit.RUNTIME_PATHS[0] + "X": a["target_prims"].pop(audit.RUNTIME_PATHS[0])}), "target_prim_set_invalid")
    negative("snapshot_hash_content_contradiction", lambda b, a: None, "snapshot_hash_content_contradiction", lambda a: a.__setitem__("snapshot_sha256", "0" * 64))
    negative("layer_identity_mismatch", lambda b, a: a["root_layer"].__setitem__("identifier", "C:/fixture/other.usda"), "layer_stack_identity_or_order_invalid")
    negative("protected_hash_content_contradiction", lambda b, a: None, "protected_semantics_hash_contradiction", lambda a: (a["protected_semantics"].__setitem__("sha256", "0" * 64), _rehash(a)))

    passed = sum(1 for item in cases if item["passed"])
    report = {"schema": "campfire.phase6if.layer-opinion-fixture.v1", "phase": "phase6if", "status": "qualified" if passed == len(cases) else "failed", "case_count": [passed, len(cases)], "positive_observational_count": 9, "negative_fail_closed_count": len(cases) - 9, "kit_launch_count": 0, "phase6ie_reclassified": False, "phase6ie_artifact_reused": False, "cases": cases}
    atomic_write_json(output_root / "fixture_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True); args = parser.parse_args()
    report = run_fixture(args.output_root.absolute())
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
