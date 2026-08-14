"""Offline saved/reloaded USD fixtures for Phase 6GM Flow export authoring."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, Vt

from phase6ep_point_collision_geometry import cylinder_topology
from phase6er_point_collision_geometry import corrected_plan_payload
from phase6gm_flow_export_state import author, descriptor_digest, load_descriptor, validate


CONDITIONS = {
    "S93": {"policy": "allow_self_center", "collision": True, "active": 1344},
    "S100": {"policy": "allow_other_support", "collision": True, "active": 1440},
    "OFF": {"policy": "allow_other_support", "collision": False, "active": 1440},
}


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _array_hash(*arrays) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        value = np.ascontiguousarray(array)
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(json.dumps(list(value.shape)).encode("ascii"))
        digest.update(value.tobytes(order="C"))
    return digest.hexdigest().upper()


def _author_condition(path: Path, condition: str, spec: dict) -> dict:
    plan = corrected_plan_payload("production_four", -0.0125, 0.05, True, spec["policy"])
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/Flow")
    simulate = stage.DefinePrim("/World/Flow/Simulate", "FlowSimulate")
    simulate.CreateAttribute("physicsCollisionEnabled", Sdf.ValueTypeNames.Bool, custom=True).Set(spec["collision"])
    export = stage.DefinePrim("/World/Flow/Simulate/nanoVdbExport", "FlowSparseNanoVdbExportParams")
    del export
    export_report = author(stage)
    meshes = []
    UsdGeom.Xform.Define(stage, "/World/CollisionProxies")
    for pose, points, counts, indices, _geometry in plan["geometries"]:
        mesh = UsdGeom.Mesh.Define(stage, f"/World/CollisionProxies/{pose.name}")
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*(float(v) for v in row)) for row in points]))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray(counts.tolist()))
        mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(indices.tolist()))
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        meshes.append((points.astype(np.float32), counts, indices))
    point_source = UsdGeom.Points.Define(stage, "/World/PointSource")
    positions = np.ascontiguousarray(plan["positions"], dtype=np.float32)
    active = np.ascontiguousarray(plan["active"], dtype=np.float32)
    point_source.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*(float(v) for v in row)) for row in positions]))
    emitter = stage.DefinePrim("/World/PointEmitter", "FlowEmitterPoint")
    emitter.CreateAttribute("pointFuels", Sdf.ValueTypeNames.FloatArray, custom=True).Set(Vt.FloatArray((active * np.float32(0.8)).tolist()))
    emitter.CreateAttribute("pointTemperatures", Sdf.ValueTypeNames.FloatArray, custom=True).Set(Vt.FloatArray((active * np.float32(2.0)).tolist()))
    emitter.CreateAttribute("pointSmokes", Sdf.ValueTypeNames.FloatArray, custom=True).Set(Vt.FloatArray((active * np.float32(0.08)).tolist()))
    emitter.CreateAttribute("campfire:residentRevision", Sdf.ValueTypeNames.Int, custom=True).Set(1)
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"failed to save {condition} fixture stage")
    reopened = Usd.Stage.Open(str(path))
    validation = validate(reopened)
    mesh_digest = _array_hash(*[array for triple in meshes for array in triple])
    payload_digest = _array_hash(positions, active * np.float32(0.8), active * np.float32(2.0), active * np.float32(0.08))
    return {
        "condition": condition, "path": str(path), "file_bytes": path.stat().st_size,
        "file_sha256": _sha_bytes(path.read_bytes()), "export": validation,
        "active_points": int(np.count_nonzero(active)), "expected_active_points": spec["active"],
        "collision_enabled": spec["collision"], "policy": spec["policy"],
        "geometry_digest": mesh_digest, "payload_digest": payload_digest,
        "source_sums": {"fuel": float(np.sum(active * np.float32(0.8), dtype=np.float64)),
                        "temperature": float(np.sum(active * np.float32(2.0), dtype=np.float64)),
                        "smoke": float(np.sum(active * np.float32(0.08), dtype=np.float64))},
        "pass": bool(export_report["pass"] and validation["pass"] and int(np.count_nonzero(active)) == spec["active"]),
    }


def _negative_stage(path: Path, mode: str) -> dict:
    descriptor = load_descriptor()
    if mode == "duplicate_descriptor":
        modified = json.loads(json.dumps(descriptor))
        modified["attributes"].append(dict(modified["attributes"][0]))
        try:
            names = [row["name"] for row in modified["attributes"]]
            if len(names) != len(set(names)):
                raise ValueError("duplicate")
        except ValueError:
            return {"name": mode, "rejected": True, "failures": ["duplicate_descriptor_attribute"]}
    if mode == "inherited_only":
        base_path = path.with_name(path.stem + "_base.usda")
        base = Usd.Stage.CreateNew(str(base_path))
        UsdGeom.Xform.Define(base, "/World")
        UsdGeom.Xform.Define(base, "/World/Flow")
        base.DefinePrim("/World/Flow/Simulate", "FlowSimulate")
        base.DefinePrim(descriptor["prim"]["path"], descriptor["prim"]["type_name"])
        author(base)
        base.GetRootLayer().Save()
        stage = Usd.Stage.CreateNew(str(path))
        stage.GetRootLayer().subLayerPaths.append(str(base_path))
        stage.GetRootLayer().Save()
        result = validate(Usd.Stage.Open(str(path)))
        return {"name": mode, "rejected": not result["pass"], "failures": result["failures"]}
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/Flow")
    stage.DefinePrim("/World/Flow/Simulate", "FlowSimulate")
    if mode == "wrong_prim":
        stage.DefinePrim("/World/Flow/Wrong/nanoVdbExport", "FlowSparseNanoVdbExportParams")
    else:
        stage.DefinePrim(descriptor["prim"]["path"], descriptor["prim"]["type_name"])
        author(stage)
        prim = stage.GetPrimAtPath(descriptor["prim"]["path"])
        if mode == "missing":
            prim.RemoveProperty("divergenceEnabled")
        elif mode == "wrong_type":
            prim.RemoveProperty("divergenceEnabled")
            prim.CreateAttribute("divergenceEnabled", Sdf.ValueTypeNames.Int, custom=True).Set(1)
    stage.GetRootLayer().Save()
    result = validate(Usd.Stage.Open(str(path)))
    return {"name": mode, "rejected": not result["pass"], "failures": result["failures"]}


def run(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Phase 6GM fixture refuses output reuse: {output}")
    output.mkdir(parents=True)
    rows = [_author_condition(output / f"{name}.usda", name, spec) for name, spec in CONDITIONS.items()]
    negative = [_negative_stage(output / f"negative_{mode}.usda", mode)
                for mode in ("missing", "wrong_prim", "wrong_type", "duplicate_descriptor", "inherited_only")]
    geometry_equal = len({row["geometry_digest"] for row in rows}) == 1
    export_equal = len({row["export"]["descriptor_digest"] for row in rows}) == 1
    s100_off_payload_equal = rows[1]["payload_digest"] == rows[2]["payload_digest"]
    payloads_expected = rows[0]["payload_digest"] != rows[1]["payload_digest"] and s100_off_payload_equal
    passed = bool(all(row["pass"] for row in rows) and geometry_equal and export_equal and payloads_expected
                  and all(row["rejected"] for row in negative))
    report = {
        "schema": "campfire.phase6gm.offline-export-state-fixture.v1", "phase": "phase6gm",
        "passed": passed, "kit_process_launched": False, "descriptor_path": str(Path(__file__).parent / "phase6gm_flow_export_state_descriptor.json"),
        "descriptor_digest": descriptor_digest(), "conditions": rows, "negative_fixtures": negative,
        "cross_condition": {"geometry_identical": geometry_equal, "export_state_identical": export_equal,
                            "s93_payload_differs_as_expected": payloads_expected,
                            "s100_off_payload_identical": s100_off_payload_equal,
                            "only_allowed_differences": ["Point payload S93 versus S100", "Collision ON versus OFF"]},
    }
    encoded = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise RuntimeError("Phase 6GM fixture report exceeded 1 MiB")
    (output / "report.json").write_text(encoded, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return 0 if run(args.output.resolve())["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
