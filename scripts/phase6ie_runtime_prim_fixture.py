"""No-Kit producer-to-consumer fixture for the Phase 6IE Prim policy."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _authored_map(authoring, policy):
    root = "ROOT" * 16
    records = {}
    for path, type_name in authoring.REQUIRED_PRIMS.items():
        properties = []
        if path == "/World/Flow/Emitter":
            properties = [{"name":"position","kind":"attribute","type":"float3","value":[0.0,0.0,0.47999998927116394]}]
        elif path == "/World/Flow/Simulate":
            properties = [{"name":"physicsCollisionEnabled","kind":"attribute","type":"bool","value":False}]
        records[path] = {
            "path": path, "type": type_name, "specifier": "Sdf.SpecifierDef", "defining_layer": "<ROOT_LAYER>",
            "schema_apis": [], "properties": properties, "relationships": [], "children": [],
            "protected_classification": policy.protected_classification(path), "opinion_layers": ["<ROOT_LAYER>"],
        }
    paths = set(records)
    for path, record in records.items():
        record["children"] = sorted(item for item in paths if item.rsplit("/",1)[0] == path)
    return {"schema":policy.POLICY_SCHEMA,"root_layer_identifier":"<ROOT_LAYER>","root_layer_sha256":root,"root_prim_spec_paths_sha256":policy.sha256_bytes(policy.canonical_bytes(sorted(records))),"authored_prim_count":len(records),"authored":records}


def _projection(policy, authored, runtime):
    return {"schema":policy.POLICY_SCHEMA,"root_layer_identifier":"<ROOT_LAYER>","session_layer_identifier":"<SESSION_LAYER>","root_layer_sha256_before":authored["root_layer_sha256"],"root_layer_sha256_after":authored["root_layer_sha256"],"authored":copy.deepcopy(authored["authored"]),"runtime":copy.deepcopy(runtime)}


def run_fixture(output_root: Path, projection_path: Path) -> dict:
    output_root = Path(output_root)
    if output_root.exists(): raise RuntimeError("Phase 6IE fixture refuses root reuse")
    output_root.mkdir(parents=True)
    policy = _load("phase6ie_policy_fixture", SCRIPTS / "phase6ie_runtime_prim_policy.py")
    authoring = _load("phase6ie_authoring_fixture", SCRIPTS / "phase6ib_stage_authoring.py")
    atomic = _load("phase6ie_atomic_fixture", SCRIPTS / "phase6hu_atomic_report.py")
    replay = json.loads(Path(projection_path).read_text(encoding="utf-8"))
    authored = _authored_map(authoring, policy)
    all_runtime = replay["runtime"]
    by_category = {}
    rules = {item["path"]: item for item in policy.RUNTIME_RULES}
    for item in all_runtime: by_category.setdefault(rules[item["path"]]["category"], []).append(item)

    cases = []
    def check(name, projection, expected, expected_reason=None):
        evidence = policy.validate_projection(authored, projection)
        path = output_root / (name + ".json")
        policy.write_evidence(path, evidence, atomic.atomic_write_json)
        consumed = policy.read_evidence(path)
        passed = consumed["accepted"] is expected
        if expected_reason is not None: passed = passed and any(reason.startswith(expected_reason) for reason in consumed["reasons"])
        cases.append({"name":name,"passed":passed,"accepted":consumed["accepted"],"reasons":consumed["reasons"]})

    # Positive population: exact authored set, each SDK-confirmed category,
    # the full Phase 6ID replay projection, and zero runtime prims.
    check("authored_complete", _projection(policy, authored, []), True)
    check("runtime_camera", _projection(policy, authored, by_category["kit_camera"]), True)
    check("render_product_settings", _projection(policy, authored, by_category["render_core"]), True)
    check("hydra_texture", _projection(policy, authored, by_category["hydra_texture"]), True)
    check("flow_render_debug", _projection(policy, authored, by_category["flow_debug"] + by_category["flow_render"]), True)
    check("multiple_categories_phase6id_projection", _projection(policy, authored, all_runtime), True)
    check("session_layer_runtime_opinion", _projection(policy, authored, [all_runtime[0]]), True)
    check("runtime_zero", _projection(policy, authored, []), True)

    def negative(name, mutate, reason):
        value = _projection(policy, authored, all_runtime)
        mutate(value)
        check(name, value, False, reason)

    negative("authored_missing", lambda v: v["authored"].pop("/World/Flow/Emitter"), "authored_prim_missing")
    negative("authored_type_changed", lambda v: v["authored"]["/World/Flow/Emitter"].__setitem__("type","Xform"), "authored_prim_changed")
    negative("authored_attribute_changed", lambda v: v["authored"]["/World/Flow/Emitter"]["properties"][0].__setitem__("value",[0.0,0.0,0.481]), "authored_prim_changed")
    negative("root_hash_changed", lambda v: v.__setitem__("root_layer_sha256_after","BAD"*16), "root_layer_hash_changed")
    negative("emitter_unknown_child", lambda v: v["runtime"].append({**copy.deepcopy(all_runtime[0]),"path":"/World/Flow/Emitter/Injected","parent":"/World/Flow/Emitter","depth":4}), "protected_subtree_intersection")
    negative("proxy_unknown_child", lambda v: v["runtime"].append({**copy.deepcopy(all_runtime[0]),"path":"/World/DiagnosticLog/FlowCollisionProxy/Injected","parent":"/World/DiagnosticLog/FlowCollisionProxy","depth":5}), "protected_subtree_intersection")
    negative("flow_simulate_override", lambda v: v["authored"]["/World/Flow/Simulate"].__setitem__("opinion_layers",["<SESSION_LAYER>","<ROOT_LAYER>"]), "authored_prim_changed")
    negative("unknown_path", lambda v: v["runtime"].append({**copy.deepcopy(all_runtime[0]),"path":"/UnknownRuntime","parent":"/","depth":1}), "unknown_runtime_prim")
    negative("allowed_path_unknown_type", lambda v: v["runtime"][0].__setitem__("type","Xform"), "runtime_type_mismatch")
    negative("allowed_type_wrong_parent", lambda v: v["runtime"][0].__setitem__("parent","/World"), "runtime_parent_mismatch")
    negative("category_maximum", lambda v: v["runtime"].append(copy.deepcopy(v["runtime"][0])), "runtime_category_count_exceeded")
    negative("depth_exceeded", lambda v: v["runtime"][0].__setitem__("depth",2), "runtime_depth_mismatch")
    negative("root_layer_runtime", lambda v: (v["runtime"][0].__setitem__("defining_layer_kind","root"),v["runtime"][0].__setitem__("opinion_layer_kinds",["root"])), "runtime_layer_mismatch")
    negative("unknown_layer_runtime", lambda v: (v["runtime"][0].__setitem__("defining_layer_kind","external"),v["runtime"][0].__setitem__("opinion_layer_kinds",["external"])), "runtime_layer_mismatch")
    negative("runtime_relationship_protected", lambda v: v["runtime"][0].__setitem__("relationships",[{"name":"target","kind":"relationship","targets":["/World/Flow/Emitter"]}]), "runtime_relationship_targets_protected")
    negative("similar_prefix", lambda v: v["runtime"][0].__setitem__("path","/OmniverseKit_Perspective"), "unknown_runtime_prim")
    negative("case_namespace_spoof", lambda v: v["runtime"][0].__setitem__("path","/omniversekit_Persp"), "unknown_runtime_prim")
    negative("unbounded_population", lambda v: v.__setitem__("runtime",v["runtime"] + [copy.deepcopy(v["runtime"][0]) for _ in range(2)]), "runtime_prim_population_unbounded")

    passed = sum(1 for item in cases if item["passed"])
    report = {"schema":"campfire.phase6ie.runtime-prim-fixture.v1","phase":"phase6ie","status":"qualified" if passed==len(cases) else "failed","case_count":[passed,len(cases)],"positive_count":8,"negative_count":18,"kit_launch_count":0,"phase6id_reclassified":False,"phase6id_artifact_or_runtime_reused":False,"projection_source":replay["canonicalization"],"cases":cases}
    atomic.atomic_write_json(output_root/"fixture_report.json",report)
    return report


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("--output-root",type=Path,required=True); parser.add_argument("--projection",type=Path,default=SCRIPTS/"phase6ie_phase6id_runtime_projection.json"); args=parser.parse_args()
    raise SystemExit(0 if run_fixture(args.output_root,args.projection)["status"]=="qualified" else 1)
