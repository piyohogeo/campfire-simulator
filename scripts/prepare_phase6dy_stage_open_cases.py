"""Prepare and audit Phase 6DY stages without connecting them to Hydra."""

from __future__ import annotations

import hashlib
import json
import math
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
from pxr import Gf, Usd, UsdGeom


COLLIDER_PATH = "/World/ColliderReferenceMesh"
CONTROL_LABELS = ("A_box_decomposition", "C_box_decomposition", "E_box_decomposition")
ALL_LABELS = (
    "A_box_decomposition",
    "B_box_hull",
    "C_box_decomposition",
    "D_cylinder_decomposition",
    "E_box_decomposition",
)
RADIUS_M = 0.16
LENGTH_M = 1.8
SEGMENTS = 12
CYLINDER_BOTTOM_M = 0.875


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _cylinder_topology() -> tuple[list[Gf.Vec3f], list[int], list[int]]:
    center_z = CYLINDER_BOTTOM_M + RADIUS_M
    half = LENGTH_M * 0.5
    points = []
    for x in (-half, half):
        for segment in range(SEGMENTS):
            angle = 2.0 * math.pi * segment / SEGMENTS
            points.append(Gf.Vec3f(x, RADIUS_M * math.cos(angle), center_z + RADIUS_M * math.sin(angle)))
    left_center = len(points)
    points.append(Gf.Vec3f(-half, 0.0, center_z))
    right_center = len(points)
    points.append(Gf.Vec3f(half, 0.0, center_z))
    counts: list[int] = []
    indices: list[int] = []
    for segment in range(SEGMENTS):
        following = (segment + 1) % SEGMENTS
        counts.append(4)
        indices.extend((segment, following, SEGMENTS + following, SEGMENTS + segment))
    for segment in range(SEGMENTS):
        following = (segment + 1) % SEGMENTS
        counts.extend((3, 3))
        indices.extend((left_center, following, segment))
        indices.extend((right_center, SEGMENTS + segment, SEGMENTS + following))
    return points, counts, indices


def _set_cylinder(mesh: UsdGeom.Mesh) -> None:
    points, counts, indices = _cylinder_topology()
    center_z = CYLINDER_BOTTOM_M + RADIUS_M
    mesh.GetPointsAttr().Set(points)
    mesh.GetFaceVertexCountsAttr().Set(counts)
    mesh.GetFaceVertexIndicesAttr().Set(indices)
    mesh.GetExtentAttr().Set(
        [(-LENGTH_M * 0.5, -RADIUS_M, center_z - RADIUS_M), (LENGTH_M * 0.5, RADIUS_M, center_z + RADIUS_M)]
    )


def _geometry_audit(mesh: UsdGeom.Mesh) -> dict:
    points = list(mesh.GetPointsAttr().Get() or [])
    counts = [int(value) for value in (mesh.GetFaceVertexCountsAttr().Get() or [])]
    indices = [int(value) for value in (mesh.GetFaceVertexIndicesAttr().Get() or [])]
    if sum(counts) != len(indices):
        raise RuntimeError("faceVertexCounts do not sum to faceVertexIndices length")
    edges: Counter[tuple[int, int]] = Counter()
    degenerate = 0
    signed_volume = 0.0
    cursor = 0
    for count in counts:
        face = indices[cursor : cursor + count]
        cursor += count
        if count < 3 or len(set(face)) < 3:
            degenerate += 1
            continue
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            edges[tuple(sorted((first, second)))] += 1
        origin = points[face[0]]
        face_area_twice = 0.0
        for index in range(1, len(face) - 1):
            second = points[face[index]]
            third = points[face[index + 1]]
            cross = Gf.Cross(second - origin, third - origin)
            face_area_twice += float(cross.GetLength())
            signed_volume += float(Gf.Dot(origin, Gf.Cross(second, third))) / 6.0
        if face_area_twice <= 1.0e-10:
            degenerate += 1
    open_edges = sum(1 for count in edges.values() if count != 2)
    minimum = [min(float(point[axis]) for point in points) for axis in range(3)]
    maximum = [max(float(point[axis]) for point in points) for axis in range(3)]
    extent = mesh.GetExtentAttr().Get()
    authored_extent = [[float(value) for value in item] for item in extent]
    extent_matches = all(
        abs(authored_extent[bound][axis] - (minimum if bound == 0 else maximum)[axis]) <= 1.0e-6
        for bound in range(2)
        for axis in range(3)
    )
    return {
        "vertex_count": len(points),
        "face_count": len(counts),
        "index_count": len(indices),
        "closed_manifold": bool(edges) and open_edges == 0,
        "non_two_manifold_edge_count": open_edges,
        "degenerate_face_count": degenerate,
        "signed_volume": signed_volume,
        "winding": "outward" if signed_volume > 0.0 else "inward_or_zero",
        "computed_extent": [minimum, maximum],
        "authored_extent": authored_extent,
        "extent_matches": extent_matches,
    }


def _stage_audit(stage: Usd.Stage) -> dict:
    prim = stage.GetPrimAtPath(COLLIDER_PATH)
    if not prim or not prim.IsValid() or prim.GetTypeName() != "Mesh":
        raise RuntimeError(f"Expected Mesh at {COLLIDER_PATH}")
    mesh = UsdGeom.Mesh(prim)
    geometry = _geometry_audit(mesh)
    if not geometry["closed_manifold"] or geometry["degenerate_face_count"] or not geometry["extent_matches"]:
        raise RuntimeError(f"Geometry gate failed: {geometry}")
    if geometry["winding"] != "outward":
        raise RuntimeError(f"Winding gate failed: {geometry['signed_volume']}")
    parent = prim.GetParent()
    applied = list(prim.GetAppliedSchemas())
    children = {child.GetName(): child.GetTypeName() for child in parent.GetChildren()}
    return {
        "collider_path": COLLIDER_PATH,
        "collider_type": prim.GetTypeName(),
        "applied_schemas": applied,
        "has_collision_api": "PhysicsCollisionAPI" in applied,
        "has_mesh_collision_api": "PhysicsMeshCollisionAPI" in applied,
        "physics_collision_enabled": prim.GetAttribute("physics:collisionEnabled").Get(),
        "physics_approximation": prim.GetAttribute("physics:approximation").Get(),
        "parent_path": str(parent.GetPath()),
        "transform_ops": [attribute.GetName() for attribute in prim.GetAttributes() if attribute.GetName().startswith("xformOp:")],
        "visibility": mesh.GetVisibilityAttr().Get(),
        "purpose": mesh.GetPurposeAttr().Get(),
        "render_surface_present": "RenderSurface" in children,
        "analytic_sibling_present": "AnalyticCollider" in children,
        "rigid_body_api": any("RigidBodyAPI" in name for name in applied),
        "geometry": geometry,
    }


def _diff(left, right, prefix: str = "") -> list[dict]:
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                result.append({"path": path, "left": left.get(key), "right": right.get(key)})
            else:
                result.extend(_diff(left[key], right[key], path))
        return result
    if left != right:
        return [{"path": prefix, "left": left, "right": right}]
    return []


def _main() -> None:
    settings = carb.settings.get_settings()
    source = Path(settings.get_as_string("/phase6dy/source")).resolve()
    output_root = Path(settings.get_as_string("/phase6dy/outputRoot")).resolve()
    report_path = Path(settings.get_as_string("/phase6dy/report")).resolve()
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6dy.prepared-stages.v1",
        "phase": "phase6dy",
        "status": "running",
        "timestamp_utc": _utc(),
        "source": str(source),
        "source_sha256": _sha256(source),
        "cases": {},
        "production_changed": False,
    }
    exit_code = 1
    try:
        if not source.is_file():
            raise RuntimeError(f"Known-good source missing: {source}")
        output_root.mkdir(parents=True, exist_ok=False)
        for label in ALL_LABELS:
            destination = output_root / f"{label}.usda"
            source_stage = Usd.Stage.Open(str(source))
            if source_stage is None or not source_stage.Export(str(destination)):
                raise RuntimeError(f"Unable to export {label}")
            del source_stage
            stage = Usd.Stage.Open(str(destination))
            if stage is None:
                raise RuntimeError(f"Unable to reopen {label}")
            prim = stage.GetPrimAtPath(COLLIDER_PATH)
            if label == "B_box_hull":
                if not prim.GetAttribute("physics:approximation").Set("convexHull"):
                    raise RuntimeError("Unable to set Box convexHull")
            elif label == "D_cylinder_decomposition":
                _set_cylinder(UsdGeom.Mesh(prim))
            if not stage.GetRootLayer().Save():
                raise RuntimeError(f"Unable to save {label}")
            audit = _stage_audit(stage)
            del stage
            report["cases"][label] = {
                "path": str(destination),
                "sha256": _sha256(destination),
                "audit": audit,
            }
        controls = [report["cases"][label] for label in CONTROL_LABELS]
        report["control_sha256_equal"] = len({item["sha256"] for item in controls}) == 1
        report["control_audit_equal"] = len({json.dumps(item["audit"], sort_keys=True) for item in controls}) == 1
        report["normalized_differences"] = {
            "A_to_B": _diff(report["cases"]["A_box_decomposition"]["audit"], report["cases"]["B_box_hull"]["audit"]),
            "A_to_D": _diff(report["cases"]["A_box_decomposition"]["audit"], report["cases"]["D_cylinder_decomposition"]["audit"]),
        }
        a_to_b_paths = {item["path"] for item in report["normalized_differences"]["A_to_B"]}
        if a_to_b_paths != {"physics_approximation"}:
            raise RuntimeError(f"A-to-B changed more than approximation: {sorted(a_to_b_paths)}")
        a_to_d_paths = {item["path"] for item in report["normalized_differences"]["A_to_D"]}
        if "physics_approximation" in a_to_d_paths:
            raise RuntimeError("A-to-D changed approximation")
        if not report["control_sha256_equal"] or not report["control_audit_equal"]:
            raise RuntimeError("A/C/E controls are not identical")
        d = report["cases"]["D_cylinder_decomposition"]["audit"]
        if d["physics_approximation"] != "convexDecomposition" or d["render_surface_present"] or d["analytic_sibling_present"] or d["rigid_body_api"]:
            raise RuntimeError(f"Cylinder isolation gate failed: {d}")
        report["status"] = "ok"
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        _write(report_path, report)
        app.post_uncancellable_quit(exit_code)


_main()
