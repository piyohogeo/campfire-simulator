"""Audit the production layout-representation contract added after Phase 6DM."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "source" / "extensions" / "campfire.app" / "campfire" / "app"
FILES = {
    "payload": APP / "resident_point_sidecar.py",
    "session": APP / "resident_application_session.py",
    "scene": APP / "resident_point_scene.py",
    "owner": APP / "resident_point_application_owner.py",
    "exports": APP / "__init__.py",
    "snapshot": APP / "resident_snapshot.py",
    "wood": APP / "wood.py",
    "checkpoint": ROOT / "scripts" / "resident_checkpoint_package.py",
    "app": ROOT / "source" / "apps" / "campfire.simulator.kit",
    "benchmark_app": ROOT / "source" / "apps" / "campfire.simulator.benchmark.kit",
    "point_runner": ROOT / "scripts" / "run_phase6dq_rigid_normal_app.ps1",
}
EXPECTED_FIELDS = (
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
    "layout_representation",
    "layout_frames",
)


def _source(name):
    return FILES[name].read_text(encoding="utf-8")


def _payload_fields():
    tree = ast.parse(_source("payload"))
    payload = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ImmutableSurfacePayload"
    )
    return tuple(
        node.target.id
        for node in payload.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    )


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = _source("payload")
    session = _source("session")
    scene = _source("scene")
    owner = _source("owner")
    exports = _source("exports")
    publish = payload[payload.index("    def publish(self, payload):") :]
    representation_guard = publish.index("payload.layout_representation")
    attempt_accounting = publish.index("self.attempt_payload_ids.append")
    replacement_check = session.index("sidecar_status.get(\"layout_representation\")")
    old_close = session.index("previous_adapter.close()")
    checks = {
        "payload_field_appended": _payload_fields() == EXPECTED_FIELDS,
        "legacy_and_rigid_constants_stable": all(
            value in payload
            for value in ("legacy_cardinal_axes_v1", "rigid_frame_v1")
        ),
        "payload_digest_includes_representation": "self.layout_representation" in payload[
            payload.index("    def digest(self):") : payload.index(
                "class ResidentNativeSurfaceProducer"
            )
        ],
        "publish_rejects_before_attempt_accounting": representation_guard
        < attempt_accounting,
        "sidecar_validates_static_usd_token": all(
            value in payload
            for value in (
                "campfire:layoutRepresentation",
                "pre-authored layout representation",
                "layout representation does not match",
            )
        ),
        "sidecar_status_exposes_representation": (
            '"layout_representation": self._layout_representation' in payload
        ),
        "consumer_replacement_checks_before_close": replacement_check < old_close,
        "scene_preauthors_token": all(
            value in scene
            for value in (
                '"campfire:layoutRepresentation"',
                "Sdf.ValueTypeNames.Token",
                "layout_representation",
            )
        ),
        "owner_shared_state_carries_representation": all(
            value in owner
            for value in (
                '"representation": layout.get(',
                'layout_representation=layout_state["representation"]',
                '"layout_representation": self._layout_state["representation"]',
            )
        ),
        "constants_publicly_exported": all(
            exports.count(value) >= 2
            for value in (
                "RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY",
                "RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME",
                "RESIDENT_POINT_LAYOUT_REPRESENTATIONS",
            )
        ),
        "resident_snapshot_schema_unchanged": "layout_representation"
        not in _source("snapshot"),
        "wood_json_unchanged": "layoutRepresentation" not in _source("wood"),
        "checkpoint_v1_unchanged": all(
            value in _source("checkpoint")
            for value in ("CHECKPOINT_VERSION = 1", "len(log_ids) + 1")
        )
        and "layoutRepresentation" not in _source("checkpoint"),
        "point_default_off_and_isolation_explicit_v3_off": all(
            "residentPointApplicationEnabled = false" in _source(name)
            for name in ("app", "benchmark_app")
        )
        and 'residentPointApplicationEnabled=true' in _source("point_runner")
        and 'woodRenderHierarchyEnabled=false' in _source("point_runner")
        and 'woodVisualV3Enabled=false' in _source("point_runner"),
    }
    report = {
        "schema": "campfire.phase6dn.layout_representation_audit.v1",
        "status": "ok" if all(checks.values()) else "failed",
        "phase": "phase6dn",
        "resumes": "phase6dm minimum production delta",
        "payload_fields": _payload_fields(),
        "representations": {
            "default": "legacy_cardinal_axes_v1",
            "reserved_unconnected": "rigid_frame_v1",
        },
        "checks": checks,
        "source_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): _sha256(path)
            for path in FILES.values()
        },
        "non_changes": {
            "resident_snapshot_schema": True,
            "wood_json_schema": True,
            "checkpoint_v1": True,
            "native_abi": True,
            "flow_version": "110.0.0",
            "point_default": False,
            "production_v3_default": True,
            "point_isolation_v3_enabled": False,
            "rigid_frame_producer_connected": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] != "ok":
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Phase 6DN audit failed: {failed}")


if __name__ == "__main__":
    main()
