"""Bounded authored/runtime Prim policy for the Phase 6IE live-stage gate.

This module is importable without Kit.  Stage projection functions use only
the public object interface supplied by an actual pxr.Usd.Stage at runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

POLICY_SCHEMA = "campfire.phase6ie.runtime-prim-policy.v1"
EVIDENCE_SCHEMA = "campfire.phase6ie.runtime-prim-evidence.v1"
MAX_EVIDENCE_BYTES = 512 * 1024
MAX_RUNTIME_PRIMS = 14
MAX_PROPERTY_NAMES_PER_RUNTIME_PRIM = 256

RUNTIME_RULES = (
    {"id": "kit_camera_front", "category": "kit_camera", "path": "/OmniverseKit_Front", "type": "Camera", "parent": "/", "layer": "session", "max_depth": 1},
    {"id": "kit_camera_persp", "category": "kit_camera", "path": "/OmniverseKit_Persp", "type": "Camera", "parent": "/", "layer": "session", "max_depth": 1},
    {"id": "kit_camera_right", "category": "kit_camera", "path": "/OmniverseKit_Right", "type": "Camera", "parent": "/", "layer": "session", "max_depth": 1},
    {"id": "kit_camera_top", "category": "kit_camera", "path": "/OmniverseKit_Top", "type": "Camera", "parent": "/", "layer": "session", "max_depth": 1},
    {"id": "render_root", "category": "render_core", "path": "/Render", "type": "", "parent": "/", "layer": "session", "max_depth": 1},
    {"id": "render_settings", "category": "render_core", "path": "/Render/OmniverseGlobalRenderSettings", "type": "RenderSettings", "parent": "/Render", "layer": "session", "max_depth": 2},
    {"id": "render_kit_scope", "category": "render_core", "path": "/Render/OmniverseKit", "type": "", "parent": "/Render", "layer": "session", "max_depth": 2},
    {"id": "render_vars_scope", "category": "render_core", "path": "/Render/Vars", "type": "", "parent": "/Render", "layer": "session", "max_depth": 2},
    {"id": "render_var_ldr", "category": "render_core", "path": "/Render/Vars/LdrColor", "type": "RenderVar", "parent": "/Render/Vars", "layer": "session", "max_depth": 3},
    {"id": "hydra_texture_scope", "category": "hydra_texture", "path": "/Render/OmniverseKit/HydraTextures", "type": "", "parent": "/Render/OmniverseKit", "layer": "session", "max_depth": 3},
    {"id": "hydra_viewport_0", "category": "hydra_texture", "path": "/Render/OmniverseKit/HydraTextures/omni_kit_widget_viewport_ViewportTexture_0", "type": "RenderProduct", "parent": "/Render/OmniverseKit/HydraTextures", "layer": "session", "max_depth": 4},
    {"id": "flow_debug_volume", "category": "flow_debug", "path": "/World/Flow/Offscreen/debugVolume", "type": "FlowDebugVolumeParams", "parent": "/World/Flow/Offscreen", "layer": "session", "max_depth": 4},
    {"id": "flow_raymarch_cloud", "category": "flow_render", "path": "/World/Flow/Render/rayMarch/cloud", "type": "FlowRayMarchCloudParams", "parent": "/World/Flow/Render/rayMarch", "layer": "session", "max_depth": 5},
    {"id": "flow_render_settings", "category": "flow_render", "path": "/World/Flow/Render/renderSettings", "type": "FlowRenderSettingsParams", "parent": "/World/Flow/Render", "layer": "session", "max_depth": 4},
)

CATEGORY_MAXIMUMS = {"kit_camera": 4, "render_core": 5, "hydra_texture": 2, "flow_debug": 1, "flow_render": 2}
PROTECTED_RECURSIVE = (
    "/World/PhysicsScene",
    "/World/Cameras/EndOn",
    "/World/DiagnosticLog",
    "/World/Flow/Emitter",
    "/World/Flow/Simulate",
)
PROTECTED_EXACT = (
    "/World/Flow/Offscreen",
    "/World/Flow/Render",
    "/World/Flow/Render/rayMarch",
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _plain(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        try:
            return [_plain(item) for item in value]
        except TypeError:
            pass
    return str(value)


def _depth(path: str) -> int:
    return len([item for item in path.split("/") if item])


def _parent(path: str) -> str:
    if path.count("/") <= 1:
        return "/"
    return path.rsplit("/", 1)[0]


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def protected_classification(path: str) -> str:
    if path == "/World/PhysicsScene": return "physics_scene"
    if path == "/World/Cameras/EndOn": return "fixed_diagnostic_camera"
    if _under(path, "/World/DiagnosticLog"): return "diagnostic_log_geometry"
    if _under(path, "/World/Flow/Emitter"): return "source_fuel_temperature_smoke_input"
    if _under(path, "/World/Flow/Simulate/advection"): return "advection_channel_input"
    if _under(path, "/World/Flow/Simulate"): return "flow_simulate_input"
    if path in PROTECTED_EXACT: return "flow_render_authored_parent"
    return "authored_other"


def _layer_identifier(spec) -> str:
    layer = getattr(spec, "layer", None)
    return str(getattr(layer, "identifier", ""))


def _layer_kind(identifier: str, root_identifier: str, session_identifier: str) -> str:
    if identifier == session_identifier:
        return "session"
    if identifier == root_identifier:
        return "root"
    return "external"


def _properties(prim) -> list[dict]:
    rows = []
    for prop in sorted(prim.GetAuthoredProperties(), key=lambda item: item.GetName()):
        name = prop.GetName()
        if hasattr(prop, "GetTargets"):
            rows.append({"name": name, "kind": "relationship", "targets": [str(item) for item in prop.GetTargets()]})
        else:
            rows.append({"name": name, "kind": "attribute", "type": str(prop.GetTypeName()), "value": _plain(prop.Get())})
    return rows


def _authored_record(prim, authored_paths: set[str], root_identifier: str) -> dict:
    path = str(prim.GetPath())
    stack = list(prim.GetPrimStack())
    return {
        "path": path,
        "type": prim.GetTypeName(),
        "specifier": str(prim.GetSpecifier()),
        "defining_layer": root_identifier,
        "schema_apis": sorted(prim.GetAppliedSchemas()),
        "properties": _properties(prim),
        "relationships": [row for row in _properties(prim) if row["kind"] == "relationship"],
        "children": sorted(str(child.GetPath()) for child in prim.GetChildren() if str(child.GetPath()) in authored_paths),
        "protected_classification": protected_classification(path),
        "opinion_layers": [_layer_identifier(spec) for spec in stack],
    }


def snapshot_authored_stage(stage, root_layer_sha256: str) -> dict:
    root_identifier = str(stage.GetRootLayer().identifier)
    prims = list(stage.Traverse())
    authored_paths = {str(prim.GetPath()) for prim in prims}
    records = {path: _authored_record(stage.GetPrimAtPath(path), authored_paths, root_identifier) for path in sorted(authored_paths)}
    return {
        "schema": POLICY_SCHEMA,
        "root_layer_identifier": root_identifier,
        "root_layer_sha256": root_layer_sha256,
        "root_prim_spec_paths_sha256": sha256_bytes(canonical_bytes(sorted(records))),
        "authored_prim_count": len(records),
        "authored": records,
    }


def project_live_stage(stage, authored_map: dict, root_layer_sha256_after: str) -> dict:
    root_identifier = str(stage.GetRootLayer().identifier)
    session_identifier = str(stage.GetSessionLayer().identifier)
    authored_paths = set(authored_map["authored"])
    live_paths = {str(prim.GetPath()) for prim in stage.Traverse()}
    live_authored = {
        path: _authored_record(stage.GetPrimAtPath(path), authored_paths, root_identifier)
        for path in sorted(authored_paths & live_paths)
    }
    runtime = []
    for path in sorted(live_paths - authored_paths):
        prim = stage.GetPrimAtPath(path)
        stack = list(prim.GetPrimStack())
        layer_ids = [_layer_identifier(spec) for spec in stack]
        properties = _properties(prim)
        relationships = [row for row in properties if row["kind"] == "relationship"]
        runtime.append({
            "path": path,
            "type": prim.GetTypeName(),
            "parent": _parent(path),
            "depth": _depth(path),
            "specifier": str(prim.GetSpecifier()),
            "defining_layer_identifier": layer_ids[0] if layer_ids else "",
            "defining_layer_kind": _layer_kind(layer_ids[0], root_identifier, session_identifier) if layer_ids else "external",
            "opinion_layer_kinds": [_layer_kind(item, root_identifier, session_identifier) for item in layer_ids],
            "property_count": len(properties),
            "property_names": [item["name"] for item in properties[:MAX_PROPERTY_NAMES_PER_RUNTIME_PRIM]],
            "relationships": relationships,
        })
    return {
        "schema": POLICY_SCHEMA,
        "root_layer_identifier": root_identifier,
        "session_layer_identifier": session_identifier,
        "root_layer_sha256_before": authored_map["root_layer_sha256"],
        "root_layer_sha256_after": root_layer_sha256_after,
        "authored": live_authored,
        "runtime": runtime,
    }


def _authored_changes(expected: dict, actual: dict) -> tuple[list[str], list[dict]]:
    missing = sorted(set(expected) - set(actual))
    changed = []
    for path in sorted(set(expected) & set(actual)):
        if expected[path] != actual[path]:
            changed.append({"path": path, "expected_sha256": sha256_bytes(canonical_bytes(expected[path])), "actual_sha256": sha256_bytes(canonical_bytes(actual[path]))})
    return missing, changed


def validate_projection(authored_map: dict, live_projection: dict) -> dict:
    reasons, unknown, conflicts, runtime_evidence = [], [], [], []
    if authored_map.get("schema") != POLICY_SCHEMA or live_projection.get("schema") != POLICY_SCHEMA:
        reasons.append("schema_mismatch")
    expected_authored = authored_map.get("authored") if isinstance(authored_map.get("authored"), dict) else {}
    actual_authored = live_projection.get("authored") if isinstance(live_projection.get("authored"), dict) else {}
    missing, changed = _authored_changes(expected_authored, actual_authored)
    if missing: reasons.append("authored_prim_missing:" + missing[0])
    if changed: reasons.append("authored_prim_changed:" + changed[0]["path"])
    root_before, root_after = live_projection.get("root_layer_sha256_before"), live_projection.get("root_layer_sha256_after")
    if root_before != authored_map.get("root_layer_sha256") or root_after != root_before:
        reasons.append("root_layer_hash_changed")
    runtime = live_projection.get("runtime")
    if not isinstance(runtime, list):
        runtime = []; reasons.append("runtime_prim_list_invalid")
    if len(runtime) > MAX_RUNTIME_PRIMS:
        reasons.append("runtime_prim_population_unbounded")
    paths = [item.get("path") for item in runtime if isinstance(item, dict)]
    if len(paths) != len(runtime) or len(set(paths)) != len(paths):
        reasons.append("runtime_prim_identity_invalid")
    rules = {item["path"]: item for item in RUNTIME_RULES}
    category_counts = {name: 0 for name in CATEGORY_MAXIMUMS}
    for item in runtime:
        if not isinstance(item, dict): continue
        path = item.get("path")
        rule = rules.get(path)
        row = {"path": path, "type": item.get("type"), "parent": item.get("parent"), "defining_layer": item.get("defining_layer_identifier"), "classification": None, "matched_rule_id": None, "accepted": False, "reason": None, "protected_conflict": False}
        if rule is None:
            row["reason"] = "unknown_runtime_prim"; unknown.append(path)
        else:
            row["classification"] = rule["category"]; row["matched_rule_id"] = rule["id"]
            category_counts[rule["category"]] += 1
            if item.get("type") != rule["type"]: row["reason"] = "runtime_type_mismatch"
            elif item.get("parent") != rule["parent"]: row["reason"] = "runtime_parent_mismatch"
            elif item.get("depth") != rule["max_depth"]: row["reason"] = "runtime_depth_mismatch"
            elif item.get("defining_layer_kind") != rule["layer"] or set(item.get("opinion_layer_kinds") or []) != {rule["layer"]}: row["reason"] = "runtime_layer_mismatch"
            elif type(item.get("property_count")) is not int or item["property_count"] < 0 or item["property_count"] > MAX_PROPERTY_NAMES_PER_RUNTIME_PRIM: row["reason"] = "runtime_property_population_unbounded"
            else: row["accepted"] = True; row["reason"] = "pass"
        for root in PROTECTED_RECURSIVE:
            if _under(str(path), root):
                row["accepted"] = False; row["reason"] = "protected_subtree_intersection"; row["protected_conflict"] = True; conflicts.append(path); break
        for relationship in item.get("relationships") or []:
            for target in relationship.get("targets") or []:
                if any(_under(str(target), root) for root in PROTECTED_RECURSIVE):
                    row["accepted"] = False; row["reason"] = "runtime_relationship_targets_protected"; row["protected_conflict"] = True; conflicts.append(path); break
        if not row["accepted"]: reasons.append(row["reason"] + ":" + str(path))
        runtime_evidence.append(row)
    for category, count in category_counts.items():
        if count > CATEGORY_MAXIMUMS[category]: reasons.append("runtime_category_count_exceeded:" + category)
    accepted = not reasons
    return {
        "schema": EVIDENCE_SCHEMA,
        "status": "qualified" if accepted else "rejected",
        "accepted": accepted,
        "reasons": reasons,
        "authored_prim_count": len(expected_authored),
        "runtime_prim_count": len(runtime),
        "category_counts": category_counts,
        "runtime_prims": runtime_evidence,
        "root_layer_sha256_before": root_before,
        "root_layer_sha256_after": root_after,
        "session_layer_identifier": live_projection.get("session_layer_identifier"),
        "unknown_prims": unknown,
        "protected_conflicts": sorted(set(conflicts)),
        "authored_prim_missing": missing,
        "authored_prim_changed": changed,
        "policy_rule_count": len(RUNTIME_RULES),
    }


def write_evidence(path: Path, evidence: dict, atomic_write_json) -> None:
    data = canonical_bytes(evidence)
    if len(data) > MAX_EVIDENCE_BYTES:
        raise RuntimeError("runtime_prim_evidence_oversize")
    atomic_write_json(Path(path), evidence)


def read_evidence(path: Path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    if size <= 0 or size > MAX_EVIDENCE_BYTES:
        raise RuntimeError("runtime_prim_evidence_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != EVIDENCE_SCHEMA or type(value.get("accepted")) is not bool:
        raise RuntimeError("runtime_prim_evidence_schema_invalid")
    return value
