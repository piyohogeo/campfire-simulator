"""Audit the minimum production delta for a future layout representation field."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "source" / "extensions" / "campfire.app" / "campfire" / "app"
PATHS = {
    "payload": APP / "resident_point_sidecar.py",
    "session": APP / "resident_application_session.py",
    "scene": APP / "resident_point_scene.py",
    "owner": APP / "resident_point_application_owner.py",
    "exports": APP / "__init__.py",
    "wood": APP / "wood.py",
    "checkpoint_package": ROOT / "scripts" / "resident_checkpoint_package.py",
    "checkpoint_session": ROOT / "scripts" / "resident_checkpoint_session.py",
    "tests": APP / "tests" / "test_scene.py",
}
EXPECTED_PAYLOAD_FIELDS = (
    "revision",
    "tick",
    "layout_revision",
    "point_count",
    "positions",
    "fuels",
    "temperatures",
    "smokes",
    "layout_origins",
    "layout_axes",
)


def _source(path):
    return path.read_text(encoding="utf-8")


def _tree(path):
    return ast.parse(_source(path), filename=str(path))


def _class(tree, name):
    return next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method(class_node, name):
    return next(
        node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _segment(path, node):
    lines = _source(path).splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def _call_name(call):
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _call_sites(name):
    sites = []
    for base in (APP, ROOT / "scripts"):
        for path in sorted(base.rglob("*.py")):
            tree = _tree(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _call_name(node) == name:
                    sites.append(
                        {
                            "path": str(path.relative_to(ROOT)),
                            "line": node.lineno,
                            "production": APP in path.parents and "tests" not in path.parts,
                        }
                    )
    return sites


def _checkpoint_version(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "CHECKPOINT_VERSION" for target in node.targets):
                return ast.literal_eval(node.value)
    raise RuntimeError("Checkpoint version was not found")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    payload_tree = _tree(PATHS["payload"])
    payload_class = _class(payload_tree, "ImmutableSurfacePayload")
    payload_fields = tuple(
        node.target.id
        for node in payload_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    )
    digest_source = _segment(PATHS["payload"], _method(payload_class, "digest"))
    sidecar_class = _class(payload_tree, "ResidentPointSidecar")
    sidecar_status_source = _segment(PATHS["payload"], _method(sidecar_class, "status"))
    sidecar_publish_source = _segment(PATHS["payload"], _method(sidecar_class, "publish"))

    session_tree = _tree(PATHS["session"])
    session_class = _class(session_tree, "ResidentApplicationSession")
    retry_source = _segment(PATHS["session"], _method(session_class, "retry_pending"))
    replace_source = _segment(PATHS["session"], _method(session_class, "replace_consumers"))
    validation_position = replace_source.find("adapter_status = adapter.status()")
    close_position = replace_source.find("previous_adapter.close()")

    scene_source = _source(PATHS["scene"])
    owner_source = _source(PATHS["owner"])
    export_source = _source(PATHS["exports"])
    checkpoint_package_source = _source(PATHS["checkpoint_package"])
    checkpoint_session_source = _source(PATHS["checkpoint_session"])
    calls = _call_sites("ImmutableSurfacePayload")
    production_calls = [site for site in calls if site["production"]]

    checkpoint_version = _checkpoint_version(_tree(PATHS["checkpoint_package"]))
    checkpoint_point_tokens = (
        "ResidentPointSidecar",
        "layoutRepresentation",
        "layout_revision",
        "point_layout",
    )
    proposed_usd_attribute = "campfire:layoutRepresentation"
    proposed_legacy_value = "legacy_cardinal_axes_v1"
    proposed_frame_value = "rigid_frame_v1"

    checks = {
        "payload_field_shape_exact": payload_fields == EXPECTED_PAYLOAD_FIELDS,
        "payload_is_frozen_dataclass": "@dataclass(frozen=True)" in _source(PATHS["payload"]),
        "one_production_payload_constructor": len(production_calls) == 1,
        "payload_constructor_surface_is_two_sites": len(calls) == 2,
        "payload_is_publicly_exported": (
            "from .resident_point_sidecar import" in export_source
            and '"ImmutableSurfacePayload"' in export_source
        ),
        "current_digest_covers_layout_and_arrays": all(
            token in digest_source
            for token in (
                "layout_origins",
                "layout_axes",
                "positions",
                "fuels",
                "temperatures",
                "smokes",
            )
        ),
        "pending_retry_reuses_stored_sidecar_payload": (
            "sidecar_payload = self._pending_sidecar" in retry_source
            and "self._publish_pair(result, sidecar_payload)" in retry_source
        ),
        "consumer_validation_precedes_old_consumer_close": (
            validation_position >= 0 and close_position > validation_position
        ),
        "consumer_rebind_representation_check_is_missing": (
            "representation" not in replace_source
        ),
        "sidecar_status_representation_is_missing": (
            "representation" not in sidecar_status_source
        ),
        "sidecar_publish_representation_check_is_missing": (
            "representation" not in sidecar_publish_source
        ),
        "usd_representation_attribute_is_missing": proposed_usd_attribute not in scene_source,
        "point_structure_is_pre_authored": (
            "before-stage-connection" in scene_source
            and '"campfire:layoutRevision"' in scene_source
        ),
        "owner_layout_state_is_legacy_shape": all(
            token in owner_source
            for token in ('"revision": int(layout["revision"])', '"origins": layout["origins"]', '"axes": layout["axes"]')
        ) and "representation" not in owner_source,
        "checkpoint_schema_remains_v1": checkpoint_version == 1,
        "checkpoint_consumer_shape_is_logs_plus_sphere": (
            "len(consumer_revisions) != len(log_ids) + 1" in checkpoint_package_source
            and "campfire.app.FLOW_EMITTER_PATH" in checkpoint_session_source
        ),
        "checkpoint_has_no_point_layout_contract": not any(
            token in checkpoint_package_source or token in checkpoint_session_source
            for token in checkpoint_point_tokens
        ),
        "wood_json_has_no_point_layout_contract": (
            "layoutRepresentation" not in _source(PATHS["wood"])
            and "legacy_cardinal_axes_v1" not in _source(PATHS["wood"])
            and "rigid_frame_v1" not in _source(PATHS["wood"])
        ),
    }

    report = {
        "schema_version": 1,
        "phase": "phase6dm",
        "status": "ok" if all(checks.values()) else "failed",
        "audit": {
            "payload_fields": payload_fields,
            "payload_constructor_sites": calls,
            "checkpoint_version": checkpoint_version,
            "current_point_usd_attributes": [
                "pointPositions",
                "pointFuels",
                "pointTemperatures",
                "pointSmokes",
                "campfire:layoutRevision",
                "campfire:residentRevision",
            ],
            "confirmed_gaps": [
                "ImmutableSurfacePayload has no representation field",
                "ResidentPointSidecar status/publish has no representation guard",
                "ResidentApplicationSession.replace_consumers compares revisions but not representation",
                "Point stage has no immutable layout-representation token",
                "ResidentPointApplicationOwner shared layout state contains revision/origins/axes only",
            ],
        },
        "minimum_production_delta": [
            {
                "file": "resident_point_sidecar.py",
                "changes": [
                    "append a defaulted layout_representation field after all existing payload fields",
                    "include representation in payload digest",
                    "store one immutable sidecar representation and expose it through status",
                    "reject payload representation mismatch before attempt accounting, conversion, or USD writes",
                    "validate the pre-authored USD representation token during construction",
                ],
            },
            {
                "file": "resident_application_session.py",
                "changes": [
                    "compare existing and replacement sidecar representation before closing old consumers"
                ],
            },
            {
                "file": "resident_point_scene.py",
                "changes": [
                    f"pre-author one token {proposed_usd_attribute}={proposed_legacy_value} before stage connection"
                ],
            },
            {
                "file": "resident_point_application_owner.py",
                "changes": [
                    "carry representation in shared layout state and reject replace/refresh mode switches"
                ],
            },
            {
                "file": "__init__.py and tests/test_scene.py",
                "changes": [
                    "export stable representation constants and add constructor/publish/rebind/recovery compatibility tests"
                ],
            },
        ],
        "compatibility_policy": {
            "payload_constructor": "trailing default preserves existing keyword and positional call sites",
            "legacy_default": proposed_legacy_value,
            "frame_opt_in": proposed_frame_value,
            "usd_attribute_type": "Sdf.ValueTypeNames.Token",
            "usd_write_frequency": "pre-authored once; never changed during a live session",
            "legacy_stage_without_token": "fail closed once representation-aware Point mode is enabled; regenerate or upgrade offline",
            "replacement_stage": "token, shared descriptor, and sidecar status must match before old consumer close",
            "payload_digest": "changes intentionally because representation becomes part of immutable identity; no digest is currently persisted",
        },
        "explicit_non_changes": {
            "wood_json_schema": "unchanged; layout is application state, not wood authority state",
            "resident_snapshot_schema": "unchanged",
            "checkpoint_v1": "unchanged; current format has no Point sidecar and resumes Sphere only",
            "future_point_checkpoint": "requires a new checkpoint schema version and mandatory representation field",
            "stage_recovery_orchestrator": "unchanged; session/factory validation is the existing handoff boundary",
            "native_abi": "unchanged until the frame producer is integrated separately",
            "flow_attributes_and_version": "unchanged",
            "physics_and_defaults": "unchanged",
        },
        "gates": {"checks": checks},
        "decisions": {
            "minimum_diff_defined": True,
            "checkpoint_v1_change_required_now": False,
            "wood_json_change_required": False,
            "usd_static_token_required_before_frame_mode": True,
            "production_implementation_qualified": False,
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Phase 6DM audit gates failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
