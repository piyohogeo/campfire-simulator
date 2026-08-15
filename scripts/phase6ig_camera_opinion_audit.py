"""Bounded `/OmniverseKit_Persp` layer/opinion audit for Phase 6IG.

The runtime producer deliberately reuses the frozen Phase 6IF layer exporter
and protected-semantic projection.  This module adds only the camera-specific
projection and the fail-closed transition contract derived from the preserved
Phase 6IF evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "campfire.phase6ig.camera-opinion-snapshot.v1"
SEQUENCE_SCHEMA = "campfire.phase6ig.camera-opinion-sequence.v1"
MAX_DOCUMENT_BYTES = 3 * 1024 * 1024
CAMERA_PATH = "/OmniverseKit_Persp"
BOUNDARIES = ("generated", "live_open", "post_stopped_update", "preclose")

SESSION_PROPERTIES = {
    "clippingRange": "float2",
    "focalLength": "float",
    "focusDistance": "float",
    "omni:kit:centerOfInterest": "vector3d",
    "xformOp:rotateXYZ": "float3",
    "xformOp:scale": "float3",
    "xformOp:translate": "double3",
    "xformOpOrder": "token[]",
}
ROOT_UPDATE_PROPERTIES = {
    "exposure:fStop": "float",
    "exposure:responsivity": "float",
    "exposure:time": "float",
}
EXPECTED_APPLIED_SCHEMAS = {
    "OmniRtxCameraAutoExposureAPI_1",
    "OmniRtxCameraExposureAPI_1",
}
ALLOWED_PRIM_METADATA = {
    "apiSchemas", "customData", "hide_in_stage_window", "kind", "no_delete",
    "specifier", "typeName",
}
ALLOWED_PROPERTY_METADATA = {
    "connectionPaths", "custom", "displayGroup", "displayName", "documentation",
    "hidden", "typeName", "variability",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _property_map(camera: dict) -> dict[str, dict]:
    rows = camera.get("properties") or []
    if not isinstance(rows, list):
        raise RuntimeError("camera_properties_invalid")
    names = [row.get("name") for row in rows if isinstance(row, dict)]
    if len(names) != len(rows) or len(names) != len(set(names)):
        raise RuntimeError("camera_property_duplicate_or_invalid")
    return {row["name"]: row for row in rows}


def capture(stage, boundary: str, sequence_index: int, export_dir: Path,
            disk_sha256: str, authored_paths: list[str], layer_audit,
            protected_template: dict | None = None) -> dict:
    if boundary not in BOUNDARIES or sequence_index != BOUNDARIES.index(boundary):
        raise ValueError("camera_snapshot_boundary_or_sequence_invalid")
    base = layer_audit.snapshot_stage(
        stage, boundary, sequence_index, export_dir, disk_sha256,
        authored_paths, protected_template,
    )
    root = stage.GetRootLayer(); session = stage.GetSessionLayer()
    camera = layer_audit._prim_record(stage, CAMERA_PATH, [("root", root), ("session", session)])
    value = {
        "schema": SCHEMA,
        "boundary": boundary,
        "sequence_index": sequence_index,
        "camera_path": CAMERA_PATH,
        "camera": camera,
        "root_layer": base["root_layer"],
        "session_layer": base["session_layer"],
        "layer_stack": base["layer_stack"],
        "protected_semantics": base["protected_semantics"],
        "base_snapshot_sha256": base["snapshot_sha256"],
    }
    data = canonical_bytes(value)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise RuntimeError("camera_opinion_snapshot_oversize")
    value["snapshot_sha256"] = layer_audit.sha256_bytes(data)
    return value


def validate_document(value: dict, layer_audit) -> dict:
    reasons: list[str] = []
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return {"accepted": False, "reasons": ["camera_snapshot_schema_invalid"]}
    boundary = value.get("boundary")
    if boundary not in BOUNDARIES or value.get("sequence_index") != BOUNDARIES.index(boundary):
        reasons.append("camera_snapshot_boundary_or_sequence_invalid")
    if value.get("camera_path") != CAMERA_PATH:
        reasons.append("camera_path_invalid")
    stack = value.get("layer_stack")
    if not isinstance(stack, list) or len(stack) != 2:
        reasons.append("unknown_layer")
    else:
        expected = [value.get("session_layer", {}).get("identifier"), value.get("root_layer", {}).get("identifier")]
        if [row.get("identifier") for row in stack if isinstance(row, dict)] != expected:
            reasons.append("unknown_layer_or_order")
    unhashed = dict(value); observed_hash = unhashed.pop("snapshot_sha256", None)
    try: expected_hash = layer_audit.sha256_bytes(canonical_bytes(unhashed))
    except (TypeError, ValueError): expected_hash = None
    if observed_hash != expected_hash:
        reasons.append("camera_snapshot_hash_contradiction")
    camera = value.get("camera")
    if not isinstance(camera, dict):
        reasons.append("camera_record_missing")
    elif boundary == "generated":
        if camera.get("exists") is not False:
            reasons.append("generated_camera_unexpected")
    else:
        if camera.get("exists") is not True: reasons.append("camera_missing")
        if camera.get("type_name") != "Camera": reasons.append("camera_type_invalid")
        if camera.get("children") != []: reasons.append("camera_children_unexpected")
        if camera.get("relationships") != []: reasons.append("camera_relationship_unexpected")
        if set(camera.get("applied_schemas") or []) != EXPECTED_APPLIED_SCHEMAS:
            reasons.append("camera_applied_schema_invalid")
        metadata = camera.get("metadata") or {}
        if not isinstance(metadata, dict) or set(metadata) - ALLOWED_PRIM_METADATA:
            reasons.append("camera_metadata_unknown")
        try: props = _property_map(camera)
        except RuntimeError as error: props = {}; reasons.append(str(error))
        expected_types = dict(SESSION_PROPERTIES)
        if boundary in ("post_stopped_update", "preclose"):
            expected_types.update(ROOT_UPDATE_PROPERTIES)
        if set(props) != set(expected_types):
            reasons.append("camera_property_set_unknown_or_incomplete")
        for name, expected_type in expected_types.items():
            row = props.get(name) or {}
            if row.get("kind") != "attribute" or row.get("type_name") != expected_type:
                reasons.append("camera_property_type_invalid:" + name)
            prop_metadata = row.get("metadata") or {}
            if not isinstance(prop_metadata, dict) or set(prop_metadata) - ALLOWED_PROPERTY_METADATA:
                reasons.append("camera_property_metadata_unknown:" + name)
            expected_role = "root" if name in ROOT_UPDATE_PROPERTIES else "session"
            expected_identifier = value.get(expected_role + "_layer", {}).get("identifier")
            if row.get("property_stack") != [expected_identifier]:
                reasons.append("camera_property_layer_invalid:" + name)
        layer_specs = camera.get("layer_specs") or {}
        root_exists = ((layer_specs.get("root") or {}).get("prim") or {}).get("exists") is True
        session_exists = ((layer_specs.get("session") or {}).get("prim") or {}).get("exists") is True
        if not session_exists: reasons.append("camera_session_spec_missing")
        if boundary == "live_open" and root_exists: reasons.append("camera_root_spec_too_early")
        if boundary in ("post_stopped_update", "preclose") and not root_exists:
            reasons.append("camera_root_update_spec_missing")
    return {"accepted": not reasons, "reasons": reasons}


def validate_sequence(documents: list[dict], layer_audit) -> dict:
    reasons: list[str] = []
    if not isinstance(documents, list) or len(documents) != 4:
        return {"schema": SEQUENCE_SCHEMA, "accepted": False, "reasons": ["camera_snapshot_count_invalid"]}
    if [item.get("boundary") for item in documents if isinstance(item, dict)] != list(BOUNDARIES):
        reasons.append("camera_snapshot_order_invalid")
    validations = []
    for value in documents:
        result = validate_document(value, layer_audit); validations.append(result); reasons.extend(result["reasons"])
    first = documents[0]
    disk_hashes = [row.get("root_layer", {}).get("file_sha256") for row in documents]
    if len(set(disk_hashes)) != 1 or not disk_hashes[0]: reasons.append("root_file_hash_changed")
    protected = [row.get("protected_semantics", {}).get("sha256") for row in documents]
    if len(set(protected)) != 1 or not protected[0]: reasons.append("protected_semantics_changed")
    if documents[2].get("camera") != documents[3].get("camera"):
        reasons.append("camera_changed_after_single_stopped_update")
    return {
        "schema": SEQUENCE_SCHEMA,
        "accepted": not reasons,
        "classification": "camera_runtime_augmentation_audited" if not reasons else "safe_stop_camera_opinion_unresolved",
        "reasons": reasons,
        "document_validations": validations,
        "root_file_sha256": disk_hashes[0] if disk_hashes else None,
        "protected_semantics_sha256": protected[0] if protected else None,
        "inference": {
            "subsystem": "Kit viewport/camera runtime augmentation",
            "confidence": "bounded inference",
            "basis": ["exact /OmniverseKit_Persp path", "UsdGeom Camera type", "session camera spec at live open", "root exposure opinions after one stopped Kit update"],
        },
    }


def write_document(path: Path, value: dict, atomic_write_json, layer_audit) -> None:
    result = validate_document(value, layer_audit)
    if not result["accepted"]: raise RuntimeError(result["reasons"][0])
    if len(canonical_bytes(value)) > MAX_DOCUMENT_BYTES: raise RuntimeError("camera_opinion_snapshot_oversize")
    atomic_write_json(Path(path), value)


def read_document(path: Path, layer_audit) -> dict:
    path = Path(path); size = path.stat().st_size
    if size <= 0 or size > MAX_DOCUMENT_BYTES: raise RuntimeError("camera_opinion_snapshot_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    result = validate_document(value, layer_audit)
    if not result["accepted"]: raise RuntimeError(result["reasons"][0])
    return value

