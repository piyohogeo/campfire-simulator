"""Bounded in-memory USD layer/opinion audit for Phase 6IF.

This module is importable without Kit. Runtime entry points accept the public
pxr objects supplied by the exact-loaded app-ready probe.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SNAPSHOT_SCHEMA = "campfire.phase6if.layer-opinion-snapshot.v1"
DIFF_SCHEMA = "campfire.phase6if.layer-opinion-diff.v1"
FIXTURE_SCHEMA = "campfire.phase6if.layer-opinion-fixture-input.v1"
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_LAYER_EXPORT_BYTES = 8 * 1024 * 1024
MAX_STRING_BYTES = 64 * 1024
MAX_SEQUENCE_ITEMS = 4096

RUNTIME_PATHS = (
    "/Render",
    "/Render/OmniverseGlobalRenderSettings",
    "/Render/OmniverseKit",
    "/Render/OmniverseKit/HydraTextures",
    "/Render/OmniverseKit/HydraTextures/omni_kit_widget_viewport_ViewportTexture_0",
    "/Render/Vars",
    "/Render/Vars/LdrColor",
    "/World/Flow/Offscreen/debugVolume",
    "/World/Flow/Render/rayMarch/cloud",
    "/World/Flow/Render/renderSettings",
)
AUTHORED_CHANGED_PATHS = (
    "/World/Flow/Simulate",
    "/World/Flow/Simulate/nanoVdbExport",
)
TARGET_PATHS = RUNTIME_PATHS + AUTHORED_CHANGED_PATHS


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def _type_name(value: object) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


def _plain(value: object, depth: int = 0):
    if depth > 12:
        raise ValueError("value_depth_unbounded")
    if value is None or type(value) in (bool, int, str):
        if isinstance(value, str) and len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise ValueError("string_value_unbounded")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite_value")
        return value
    if isinstance(value, dict):
        if len(value) > MAX_SEQUENCE_ITEMS:
            raise ValueError("mapping_value_unbounded")
        return {str(key): _plain(item, depth + 1) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if not isinstance(value, (str, bytes)) and hasattr(value, "__len__"):
        try:
            if len(value) > MAX_SEQUENCE_ITEMS:
                raise ValueError("sequence_value_unbounded")
            return [_plain(item, depth + 1) for item in value]
        except TypeError:
            pass
    text = str(value)
    if len(text.encode("utf-8")) > MAX_STRING_BYTES:
        raise ValueError("object_string_unbounded")
    return {"python_type": _type_name(value), "string": text}


def _info(spec) -> dict:
    if spec is None:
        return {"exists": False, "fields": {}}
    keys = sorted(str(item) for item in spec.ListInfoKeys())
    if len(keys) > MAX_SEQUENCE_ITEMS:
        raise ValueError("spec_field_population_unbounded")
    fields = {key: _plain(spec.GetInfo(key)) for key in keys}
    return {
        "exists": True,
        "path": str(spec.path),
        "spec_type": _type_name(spec),
        "fields": fields,
        "fields_sha256": sha256_bytes(canonical_bytes(fields)),
    }


def _layer_objects(layer) -> tuple[int, int, list[str]]:
    paths: list[str] = []
    layer.Traverse(layer.pseudoRoot.path, lambda path: paths.append(str(path)))
    if len(paths) > 10000:
        raise ValueError("layer_spec_population_unbounded")
    prim_count = sum(1 for path in paths if path == "/" or "." not in path.rsplit("/", 1)[-1]) - 1
    property_count = len(paths) - prim_count - 1
    return prim_count, property_count, sorted(paths)


def _export_layer(layer, boundary: str, role: str, export_dir: Path) -> dict:
    text = layer.ExportToString()
    data = text.encode("utf-8")
    if not data or len(data) > MAX_LAYER_EXPORT_BYTES:
        raise ValueError("layer_export_size_invalid:" + role)
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"{boundary}_{role}.usda.txt"
    if export_path.exists():
        raise RuntimeError("layer_export_path_reuse:" + str(export_path))
    export_path.write_bytes(data)
    prim_count, property_count, paths = _layer_objects(layer)
    real_path = str(layer.realPath or "")
    file_sha = sha256_file(Path(real_path)) if real_path and Path(real_path).is_file() else None
    return {
        "role": role,
        "identifier": str(layer.identifier),
        "real_path": real_path,
        "anonymous": bool(layer.anonymous),
        "dirty": bool(layer.dirty),
        "permission_to_edit": bool(layer.permissionToEdit),
        "permission_to_save": bool(layer.permissionToSave),
        "muted": bool(getattr(layer, "muted", False)),
        "file_sha256": file_sha,
        "memory_export_sha256": sha256_bytes(data),
        "memory_export_bytes": len(data),
        "memory_export_path": str(export_path),
        "prim_spec_count": prim_count,
        "property_spec_count": property_count,
        "all_spec_paths_sha256": sha256_bytes(canonical_bytes(paths)),
        "sub_layer_paths": [str(item) for item in layer.subLayerPaths],
        "root_prims": [str(item.path) for item in layer.rootPrims],
    }


def _property_record(prop) -> dict:
    row = {
        "name": prop.GetName(),
        "path": str(prop.GetPath()),
        "python_type": _type_name(prop),
        "metadata": _plain(prop.GetAllMetadata()),
        "property_stack": [str(spec.layer.identifier) for spec in prop.GetPropertyStack()],
    }
    if hasattr(prop, "GetTargets"):
        row.update({"kind": "relationship", "targets": [str(item) for item in prop.GetTargets()]})
    else:
        row.update({
            "kind": "attribute",
            "type_name": str(prop.GetTypeName()),
            "variability": str(prop.GetVariability()),
            "has_authored_value": bool(prop.HasAuthoredValueOpinion()),
            "value": _plain(prop.Get()) if prop.HasAuthoredValueOpinion() else None,
            "connections": [str(item) for item in prop.GetConnections()],
        })
    row["sha256"] = sha256_bytes(canonical_bytes(row))
    return row


def _prim_record(stage, path: str, layers: list) -> dict:
    prim = stage.GetPrimAtPath(path)
    layer_specs = {}
    for role, layer in layers:
        prim_spec = layer.GetPrimAtPath(path)
        properties = {}
        if prim_spec is not None:
            for prop in prim_spec.properties:
                properties[str(prop.path)] = _info(prop)
        layer_specs[role] = {"prim": _info(prim_spec), "properties": properties}
    if not prim:
        return {"path": path, "exists": False, "layer_specs": layer_specs}
    properties = [_property_record(item) for item in sorted(prim.GetAuthoredProperties(), key=lambda prop: prop.GetName())]
    row = {
        "path": path,
        "exists": True,
        "type_name": prim.GetTypeName(),
        "specifier": str(prim.GetSpecifier()),
        "active": bool(prim.IsActive()),
        "applied_schemas": sorted(prim.GetAppliedSchemas()),
        "metadata": _plain(prim.GetAllMetadata()),
        "prim_stack": [{"layer_identifier": str(spec.layer.identifier), "spec": _info(spec)} for spec in prim.GetPrimStack()],
        "properties": properties,
        "property_order": [item.GetName() for item in prim.GetAuthoredProperties()],
        "relationships": [item for item in properties if item["kind"] == "relationship"],
        "children": sorted(str(child.GetPath()) for child in prim.GetChildren()),
        "layer_specs": layer_specs,
    }
    row["sha256"] = sha256_bytes(canonical_bytes(row))
    return row


def _protected_record(stage, path: str, property_names: list[str]) -> dict:
    prim = stage.GetPrimAtPath(path)
    if not prim:
        return {"path": path, "exists": False, "type_name": None, "properties": []}
    properties = []
    for name in property_names:
        prop = prim.GetProperty(name)
        properties.append(_property_record(prop) if prop else {"name": name, "missing": True})
    return {"path": path, "exists": True, "type_name": prim.GetTypeName(), "properties": properties}


def snapshot_stage(stage, boundary: str, sequence_index: int, export_dir: Path, file_sha256: str, authored_paths: list[str], protected_template: dict | None = None) -> dict:
    if boundary not in ("generated", "live_open", "post_stopped_update", "preclose"):
        raise ValueError("snapshot_boundary_invalid")
    if type(sequence_index) is not int or sequence_index < 0:
        raise ValueError("snapshot_sequence_invalid")
    root = stage.GetRootLayer()
    session = stage.GetSessionLayer()
    layer_stack = list(stage.GetLayerStack(includeSessionLayers=True))
    layers = [("root", root), ("session", session)]
    targets = {path: _prim_record(stage, path, layers) for path in TARGET_PATHS}
    if protected_template is None:
        protected_template = {
            path: [item.GetName() for item in sorted(stage.GetPrimAtPath(path).GetAuthoredProperties(), key=lambda prop: prop.GetName())]
            for path in sorted(authored_paths)
        }
    if set(protected_template) != set(authored_paths):
        raise RuntimeError("protected_template_path_set_invalid")
    protected = {path: _protected_record(stage, path, list(protected_template[path])) for path in sorted(authored_paths)}
    root_projection = _export_layer(root, boundary, "root", export_dir)
    session_projection = _export_layer(session, boundary, "session", export_dir)
    if root_projection["file_sha256"] != file_sha256:
        raise RuntimeError("root_file_hash_changed_at_snapshot:" + boundary)
    value = {
        "schema": SNAPSHOT_SCHEMA,
        "boundary": boundary,
        "sequence_index": sequence_index,
        "stage_identifier": str(root.identifier),
        "root_layer": root_projection,
        "session_layer": session_projection,
        "layer_stack": [
            {"index": index, "identifier": str(layer.identifier), "real_path": str(layer.realPath or ""), "anonymous": bool(layer.anonymous)}
            for index, layer in enumerate(layer_stack)
        ],
        "target_prims": targets,
        "protected_semantics": {
            "paths": protected,
            "template": protected_template,
            "sha256": sha256_bytes(canonical_bytes(protected)),
            "path_count": len(protected),
        },
    }
    data = canonical_bytes(value)
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError("layer_opinion_snapshot_oversize")
    value["snapshot_sha256"] = sha256_bytes(data)
    return value


def _changed_paths(before: dict, after: dict) -> list[dict]:
    rows = []
    for path in TARGET_PATHS:
        left = before["target_prims"][path]
        right = after["target_prims"][path]
        if left != right:
            rows.append({
                "path": path,
                "before_sha256": sha256_bytes(canonical_bytes(left)),
                "after_sha256": sha256_bytes(canonical_bytes(right)),
                "before_exists": left.get("exists"),
                "after_exists": right.get("exists"),
                "root_spec_changed": left["layer_specs"]["root"] != right["layer_specs"]["root"],
                "session_spec_changed": left["layer_specs"]["session"] != right["layer_specs"]["session"],
                "property_names_before": [item["name"] for item in left.get("properties", [])],
                "property_names_after": [item["name"] for item in right.get("properties", [])],
            })
    return rows


def diff_snapshots(before: dict, after: dict, expected_attempt_id: str | None = None) -> dict:
    reasons = []
    for value, name in ((before, "before"), (after, "after")):
        if not isinstance(value, dict) or value.get("schema") != SNAPSHOT_SCHEMA:
            reasons.append("snapshot_schema_invalid:" + name)
    if reasons:
        return {"schema": DIFF_SCHEMA, "accepted": False, "reasons": reasons}
    if before.get("sequence_index", -1) >= after.get("sequence_index", -1):
        reasons.append("snapshot_order_invalid")
    if before["root_layer"]["identifier"] != after["root_layer"]["identifier"]:
        reasons.append("root_layer_identity_changed")
    if before["root_layer"]["file_sha256"] != after["root_layer"]["file_sha256"]:
        reasons.append("root_file_hash_changed")
    if before["protected_semantics"]["sha256"] != after["protected_semantics"]["sha256"]:
        reasons.append("protected_semantics_changed")
    if before["protected_semantics"]["path_count"] != after["protected_semantics"]["path_count"]:
        reasons.append("protected_path_count_changed")
    changed = _changed_paths(before, after)
    return {
        "schema": DIFF_SCHEMA,
        "accepted": not reasons,
        "classification": "observational_audit_only" if not reasons else "fail_closed",
        "reasons": reasons,
        "before_boundary": before["boundary"],
        "after_boundary": after["boundary"],
        "root_file_unchanged": before["root_layer"]["file_sha256"] == after["root_layer"]["file_sha256"],
        "root_memory_export_changed": before["root_layer"]["memory_export_sha256"] != after["root_layer"]["memory_export_sha256"],
        "root_dirty_before": before["root_layer"]["dirty"],
        "root_dirty_after": after["root_layer"]["dirty"],
        "session_memory_export_changed": before["session_layer"]["memory_export_sha256"] != after["session_layer"]["memory_export_sha256"],
        "protected_semantics_unchanged": before["protected_semantics"]["sha256"] == after["protected_semantics"]["sha256"],
        "changed_target_count": len(changed),
        "changed_targets": changed,
    }


def validate_snapshot_document(value: dict) -> dict:
    reasons = []
    if not isinstance(value, dict) or value.get("schema") != SNAPSHOT_SCHEMA:
        reasons.append("snapshot_schema_invalid")
        return {"accepted": False, "reasons": reasons}
    if value.get("boundary") not in ("generated", "live_open", "post_stopped_update", "preclose"):
        reasons.append("snapshot_boundary_invalid")
    targets = value.get("target_prims")
    if not isinstance(targets, dict):
        reasons.append("target_prim_mapping_invalid")
    else:
        keys = list(targets)
        if set(keys) != set(TARGET_PATHS): reasons.append("target_prim_set_invalid")
        if len(keys) != len(set(keys)): reasons.append("target_prim_duplicate")
    protected = value.get("protected_semantics") or {}
    if not isinstance(protected.get("paths"), dict) or protected.get("path_count") != len(protected.get("paths") or {}):
        reasons.append("protected_semantics_incomplete")
    else:
        template = protected.get("template")
        if not isinstance(template, dict) or set(template) != set(protected["paths"]):
            reasons.append("protected_template_invalid")
        try: expected = sha256_bytes(canonical_bytes(protected["paths"]))
        except (TypeError, ValueError): expected = None; reasons.append("protected_semantics_unbounded_or_nonfinite")
        if expected != protected.get("sha256"): reasons.append("protected_semantics_hash_contradiction")
    for role in ("root_layer", "session_layer"):
        layer = value.get(role)
        if not isinstance(layer, dict): reasons.append("layer_projection_missing:" + role); continue
        if not isinstance(layer.get("identifier"), str) or not layer["identifier"]: reasons.append("layer_identifier_invalid:" + role)
        if type(layer.get("memory_export_bytes")) is not int or not (0 < layer["memory_export_bytes"] <= MAX_LAYER_EXPORT_BYTES): reasons.append("layer_export_size_invalid:" + role)
    stack = value.get("layer_stack")
    if not isinstance(stack, list) or len(stack) != 2:
        reasons.append("layer_stack_invalid")
    else:
        identifiers = [item.get("identifier") for item in stack if isinstance(item, dict)]
        expected_identifiers = [value.get("session_layer", {}).get("identifier"), value.get("root_layer", {}).get("identifier")]
        if identifiers != expected_identifiers:
            reasons.append("layer_stack_identity_or_order_invalid")
    snapshot_hash = value.get("snapshot_sha256")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        reasons.append("snapshot_hash_invalid")
    else:
        unhashed = dict(value); unhashed.pop("snapshot_sha256", None)
        try: expected_snapshot_hash = sha256_bytes(canonical_bytes(unhashed))
        except (TypeError, ValueError): expected_snapshot_hash = None
        if snapshot_hash != expected_snapshot_hash:
            reasons.append("snapshot_hash_content_contradiction")
    return {"accepted": not reasons, "reasons": reasons}


def validate_snapshot_artifacts(value: dict, artifact_root: Path) -> dict:
    reasons = []
    root = Path(artifact_root).resolve(strict=True)
    for role in ("root_layer", "session_layer"):
        projection = value.get(role) or {}
        try:
            path = Path(projection["memory_export_path"]).resolve(strict=True)
            if path != root and root not in path.parents:
                reasons.append("layer_export_root_escape:" + role); continue
            size = path.stat().st_size
            digest = sha256_file(path)
            if size != projection.get("memory_export_bytes"):
                reasons.append("layer_export_size_contradiction:" + role)
            if digest != projection.get("memory_export_sha256"):
                reasons.append("layer_export_hash_contradiction:" + role)
        except (KeyError, OSError, RuntimeError):
            reasons.append("layer_export_missing_or_unreadable:" + role)
    return {"accepted": not reasons, "reasons": reasons}


def write_snapshot(path: Path, value: dict, atomic_write_json) -> None:
    validation = validate_snapshot_document(value)
    if not validation["accepted"]:
        raise RuntimeError(validation["reasons"][0])
    data = canonical_bytes(value)
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError("layer_opinion_snapshot_oversize")
    atomic_write_json(Path(path), value)


def read_snapshot(path: Path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    if size <= 0 or size > MAX_SNAPSHOT_BYTES:
        raise RuntimeError("layer_opinion_snapshot_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    validation = validate_snapshot_document(value)
    if not validation["accepted"]:
        raise RuntimeError(validation["reasons"][0])
    return value


def fixture_snapshot(boundary: str, sequence_index: int) -> dict:
    """Use the production consumer shape for no-Kit producer-to-consumer fixtures."""
    def layer(role: str, identifier: str, anonymous: bool) -> dict:
        return {"role": role, "identifier": identifier, "real_path": "C:/fixture/collision_off.usda" if role == "root" else "", "anonymous": anonymous, "dirty": False, "permission_to_edit": True, "permission_to_save": role == "root", "muted": False, "file_sha256": "A" * 64 if role == "root" else None, "memory_export_sha256": "B" * 64, "memory_export_bytes": 128, "memory_export_path": f"C:/fixture/{boundary}_{role}.txt", "prim_spec_count": 25, "property_spec_count": 80, "all_spec_paths_sha256": "C" * 64, "sub_layer_paths": [], "root_prims": ["/World"]}
    target_prims = {path: {"path": path, "exists": path in AUTHORED_CHANGED_PATHS, "layer_specs": {"root": {"prim": {"exists": path in AUTHORED_CHANGED_PATHS, "fields": {}}, "properties": {}}, "session": {"prim": {"exists": False, "fields": {}}, "properties": {}}}} for path in TARGET_PATHS}
    protected_paths = {path: {"path": path, "sha256": "D" * 64} for path in ("/World/PhysicsScene", "/World/Flow/Emitter", "/World/Flow/Simulate", "/World/Flow/Simulate/nanoVdbExport", "/World/DiagnosticLog/FlowCollisionProxy", "/World/Cameras/EndOn")}
    template = {path: [] for path in protected_paths}
    value = {"schema": SNAPSHOT_SCHEMA, "boundary": boundary, "sequence_index": sequence_index, "stage_identifier": "C:/fixture/collision_off.usda", "root_layer": layer("root", "C:/fixture/collision_off.usda", False), "session_layer": layer("session", "anon:fixture-session", True), "layer_stack": [{"index": 0, "identifier": "anon:fixture-session", "real_path": "", "anonymous": True}, {"index": 1, "identifier": "C:/fixture/collision_off.usda", "real_path": "C:/fixture/collision_off.usda", "anonymous": False}], "target_prims": target_prims, "protected_semantics": {"paths": protected_paths, "template": template, "sha256": sha256_bytes(canonical_bytes(protected_paths)), "path_count": len(protected_paths)}}
    value["snapshot_sha256"] = sha256_bytes(canonical_bytes(value))
    return value


def snapshot_layers_after_close(root_identifier: str, session_identifier: str) -> dict:
    from pxr import Sdf
    result = {"root_identifier": root_identifier, "session_identifier": session_identifier, "root": None, "session": None}
    for role, identifier in (("root", root_identifier), ("session", session_identifier)):
        layer = Sdf.Layer.Find(identifier)
        if layer is None:
            result[role] = {"found": False}
            continue
        data = layer.ExportToString().encode("utf-8")
        if not data or len(data) > MAX_LAYER_EXPORT_BYTES:
            raise RuntimeError("after_close_layer_export_size_invalid:" + role)
        target_specs = {}
        for path in TARGET_PATHS:
            prim = layer.GetPrimAtPath(path)
            target_specs[path] = {"prim": _info(prim), "properties": {str(prop.path): _info(prop) for prop in prim.properties} if prim is not None else {}}
        result[role] = {"found": True, "dirty": bool(layer.dirty), "memory_export_sha256": sha256_bytes(data), "memory_export_bytes": len(data), "target_specs": target_specs}
    result["sha256"] = sha256_bytes(canonical_bytes(result))
    return result
