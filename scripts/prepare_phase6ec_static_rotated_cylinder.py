"""Prepare the Phase 6EC axis control and one Y40 static rotation."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade


COLLIDER_PATH = "/World/ColliderReferenceMesh"
VISIBLE_REFERENCE_PATH = "/World/Collider"
MATERIAL_PATH = "/World/Materials/Collider"
EMITTER_PATH = "/World/Flow/Emitter"
SIMULATE_PATH = "/World/Flow/Simulate"
CENTER = Gf.Vec3d(0.0, 0.0, 1.035)
ROTATION_Y_DEG = 40.0
HALF_LENGTH = 0.9
COLLIDER_RADIUS = 0.16
EXPECTED_SOURCE_SHA256 = "BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _canonical_sha256(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _matrix_list(matrix: Gf.Matrix4d) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _rotation_about_center_y(angle_deg: float) -> Gf.Matrix4d:
    matrix = Gf.Matrix4d(1.0)
    matrix.SetRotate(Gf.Rotation(Gf.Vec3d.YAxis(), angle_deg))
    matrix.SetTranslateOnly(CENTER - matrix.Transform(CENTER))
    if (matrix.Transform(CENTER) - CENTER).GetLength() > 1.0e-9:
        raise RuntimeError("Y rotation did not preserve the qualified Cylinder center")
    return matrix


def _geometry_payload(mesh: UsdGeom.Mesh) -> dict:
    return {
        "points": [[float(component) for component in point] for point in mesh.GetPointsAttr().Get()],
        "face_vertex_counts": [int(value) for value in mesh.GetFaceVertexCountsAttr().Get()],
        "face_vertex_indices": [int(value) for value in mesh.GetFaceVertexIndicesAttr().Get()],
        "extent": [[float(component) for component in value] for value in mesh.GetExtentAttr().Get()],
    }


def _closed_manifold(geometry: dict) -> tuple[bool, int]:
    edges: dict[tuple[int, int], int] = {}
    offset = 0
    for count in geometry["face_vertex_counts"]:
        face = geometry["face_vertex_indices"][offset : offset + count]
        offset += count
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            edge = tuple(sorted((first, second)))
            edges[edge] = edges.get(edge, 0) + 1
    invalid = sum(count != 2 for count in edges.values())
    return invalid == 0, invalid


def _emitter_gap(stage: Usd.Stage, local_to_world: Gf.Matrix4d) -> dict:
    emitter = stage.GetPrimAtPath(EMITTER_PATH)
    position = Gf.Vec3d(*emitter.GetAttribute("position").Get())
    emitter_radius = float(emitter.GetAttribute("radius").Get())
    axis = local_to_world.TransformDir(Gf.Vec3d.XAxis()).GetNormalized()
    delta = position - CENTER
    projection = max(-HALF_LENGTH, min(HALF_LENGTH, float(Gf.Dot(delta, axis))))
    closest = CENTER + axis * projection
    center_distance = (position - closest).GetLength()
    surface_gap = center_distance - COLLIDER_RADIUS - emitter_radius
    return {
        "emitter_position": list(position),
        "emitter_radius": emitter_radius,
        "cylinder_axis_world": list(axis),
        "nearest_axis_parameter": projection,
        "centerline_distance": center_distance,
        "surface_gap_m": surface_gap,
        "gap_velocity_cells": surface_gap / 0.05,
        "outside": surface_gap > 0.0,
        "minimum_two_velocity_cells": surface_gap >= 0.1,
    }


def _audit(stage: Usd.Stage) -> dict:
    prim = stage.GetPrimAtPath(COLLIDER_PATH)
    if not prim or not prim.IsValid() or prim.GetTypeName() != "Mesh":
        raise RuntimeError(f"Expected Mesh at {COLLIDER_PATH}")
    mesh = UsdGeom.Mesh(prim)
    geometry = _geometry_payload(mesh)
    closed, invalid_edges = _closed_manifold(geometry)
    local_to_world = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
    world_points = [local_to_world.Transform(Gf.Vec3d(*point)) for point in geometry["points"]]
    world_min = [min(float(point[axis]) for point in world_points) for axis in range(3)]
    world_max = [max(float(point[axis]) for point in world_points) for axis in range(3)]
    rotation = local_to_world.ExtractRotationMatrix()
    determinant = float(rotation.GetDeterminant())
    row_lengths = [float(rotation.GetRow(index).GetLength()) for index in range(3)]
    simulate = stage.GetPrimAtPath(SIMULATE_PATH)
    original = stage.GetPrimAtPath(VISIBLE_REFERENCE_PATH)
    return {
        "local_geometry_sha256": _canonical_sha256(geometry),
        "geometry": {
            "vertex_count": len(geometry["points"]),
            "face_count": len(geometry["face_vertex_counts"]),
            "index_count": len(geometry["face_vertex_indices"]),
            "closed_manifold": closed,
            "non_two_manifold_edge_count": invalid_edges,
            "authored_local_extent": geometry["extent"],
            "computed_world_extent": [world_min, world_max],
        },
        "applied_schemas": list(prim.GetAppliedSchemas()),
        "physics_collision_enabled": prim.GetAttribute("physics:collisionEnabled").Get(),
        "physics_approximation": prim.GetAttribute("physics:approximation").Get(),
        "transform_ops": [op.GetOpName() for op in UsdGeom.Xformable(prim).GetOrderedXformOps()],
        "local_to_world": _matrix_list(local_to_world),
        "center_world": list(local_to_world.Transform(CENTER)),
        "rotation_determinant": determinant,
        "rotation_row_lengths": row_lengths,
        "right_handed_unit_scale": abs(determinant - 1.0) <= 1.0e-6
        and all(abs(length - 1.0) <= 1.0e-6 for length in row_lengths),
        "emitter_clearance": _emitter_gap(stage, local_to_world),
        "flow": {
            "density_cell_size": float(simulate.GetAttribute("densityCellSize").Get()),
            "physics_collision_enabled": bool(simulate.GetAttribute("physicsCollisionEnabled").Get()),
            "physics_convex_collision": bool(simulate.GetAttribute("physicsConvexCollision").Get()),
            "emitter_fuel": float(stage.GetPrimAtPath(EMITTER_PATH).GetAttribute("fuel").Get()),
        },
        "render_surface_present": bool(stage.GetPrimAtPath("/World/RenderSurface")),
        "rigid_body_api": prim.HasAPI(UsdPhysics.RigidBodyAPI),
        "disabled_analytic_reference_present": bool(original)
        and original.GetAttribute("physics:collisionEnabled").Get() is False,
    }


def _make_debug_visible(stage: Usd.Stage) -> None:
    mesh_prim = stage.GetPrimAtPath(COLLIDER_PATH)
    source_prim = stage.GetPrimAtPath(VISIBLE_REFERENCE_PATH)
    material_prim = stage.GetPrimAtPath(MATERIAL_PATH)
    UsdGeom.Imageable(mesh_prim).GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
    UsdGeom.Imageable(source_prim).GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    binding = UsdShade.MaterialBindingAPI.Apply(mesh_prim)
    binding.Bind(UsdShade.Material(material_prim))
    mesh_prim.CreateAttribute("primvars:displayColor", Sdf.ValueTypeNames.Color3fArray).Set(
        [Gf.Vec3f(0.06, 0.22, 0.38)]
    )


def _export_transformed(source: Path, destination: Path, angle_deg: float) -> None:
    stage = Usd.Stage.Open(str(source))
    if stage is None or not stage.Export(str(destination)):
        raise RuntimeError(f"Unable to export transformed stage: {destination}")
    del stage
    stage = Usd.Stage.Open(str(destination))
    prim = stage.GetPrimAtPath(COLLIDER_PATH)
    xformable = UsdGeom.Xformable(prim)
    if xformable.GetOrderedXformOps():
        raise RuntimeError("Qualified Phase 6DY source unexpectedly has transform ops")
    xformable.AddTransformOp().Set(_rotation_about_center_y(angle_deg))
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save transformed stage: {destination}")


def _make_debug_stage(source: Path, destination: Path) -> None:
    stage = Usd.Stage.Open(str(source))
    if stage is None or not stage.Export(str(destination)):
        raise RuntimeError(f"Unable to export debug stage: {destination}")
    del stage
    stage = Usd.Stage.Open(str(destination))
    _make_debug_visible(stage)
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save debug stage: {destination}")


def _main() -> None:
    settings = carb.settings.get_settings()
    source = Path(settings.get_as_string("/phase6ec/source")).resolve()
    output_root = Path(settings.get_as_string("/phase6ec/outputRoot")).resolve()
    report_path = Path(settings.get_as_string("/phase6ec/report")).resolve()
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6ec.static-rotated-cylinder-stages.v1",
        "phase": "phase6ec",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_marker": "preparing",
        "completion_contract": {
            "results_saved": False,
            "timeline_stopped": True,
            "stage_closed": True,
            "renderer_drained": True,
            "shutdown_requested": False,
        },
        "source": str(source),
        "source_sha256": _sha256(source) if source.is_file() else None,
        "formal_change": "center-preserving Y40 xformOp:transform only",
        "debug_stages_excluded_from_numeric_gates": True,
        "cases": {},
    }
    exit_code = 1
    try:
        if not source.is_file() or report["source_sha256"] != EXPECTED_SOURCE_SHA256:
            raise RuntimeError(f"Qualified Phase 6DY source mismatch: {report['source_sha256']}")
        output_root.mkdir(parents=True, exist_ok=False)
        axis = output_root / "axis_control.usda"
        rotated = output_root / "rotate_y40.usda"
        shutil.copyfile(source, axis)
        _export_transformed(source, rotated, ROTATION_Y_DEG)
        for label, path, angle in (
            ("axis_control", axis, 0.0),
            ("rotate_y40", rotated, ROTATION_Y_DEG),
        ):
            stage = Usd.Stage.Open(str(path))
            if stage is None:
                raise RuntimeError(f"Unable to audit {label}")
            report["cases"][label] = {
                "path": str(path),
                "stage_sha256": _sha256(path),
                "rotation_y_deg": angle,
                "audit": _audit(stage),
            }
            del stage

        axis_debug = output_root / "axis_control_debug.usda"
        rotated_debug = output_root / "rotate_y40_debug.usda"
        _make_debug_stage(axis, axis_debug)
        _make_debug_stage(rotated, rotated_debug)
        report["debug_cases"] = {
            "axis_control_debug": {"path": str(axis_debug), "stage_sha256": _sha256(axis_debug)},
            "rotate_y40_debug": {"path": str(rotated_debug), "stage_sha256": _sha256(rotated_debug)},
        }

        axis_audit = report["cases"]["axis_control"]["audit"]
        rotated_audit = report["cases"]["rotate_y40"]["audit"]
        report["gates"] = {
            "axis_control_byte_identical_to_phase6dy": report["cases"]["axis_control"]["stage_sha256"] == EXPECTED_SOURCE_SHA256,
            "local_geometry_sha256_equal": axis_audit["local_geometry_sha256"] == rotated_audit["local_geometry_sha256"],
            "topology_equal": all(
                axis_audit["geometry"][key] == rotated_audit["geometry"][key]
                for key in ("vertex_count", "face_count", "index_count")
            ),
            "closed_manifold": axis_audit["geometry"]["closed_manifold"] and rotated_audit["geometry"]["closed_manifold"],
            "schema_equal": axis_audit["applied_schemas"] == rotated_audit["applied_schemas"],
            "convex_decomposition_preserved": rotated_audit["physics_approximation"] == "convexDecomposition",
            "collision_enabled_preserved": axis_audit["physics_collision_enabled"] is True and rotated_audit["physics_collision_enabled"] is True,
            "only_rotated_stage_has_one_transform_op": axis_audit["transform_ops"] == [] and rotated_audit["transform_ops"] == ["xformOp:transform"],
            "centers_equal": math.dist(axis_audit["center_world"], rotated_audit["center_world"]) <= 1.0e-8,
            "right_handed_unit_scale": axis_audit["right_handed_unit_scale"] and rotated_audit["right_handed_unit_scale"],
            "world_extent_changed": axis_audit["geometry"]["computed_world_extent"] != rotated_audit["geometry"]["computed_world_extent"],
            "emitter_outside_both": axis_audit["emitter_clearance"]["outside"] and rotated_audit["emitter_clearance"]["outside"],
            "rotated_emitter_gap_at_least_two_velocity_cells": rotated_audit["emitter_clearance"]["minimum_two_velocity_cells"],
            "flow_contract_equal": axis_audit["flow"] == rotated_audit["flow"],
            "no_render_surface_or_rigid_body": not axis_audit["render_surface_present"] and not rotated_audit["render_surface_present"] and not axis_audit["rigid_body_api"] and not rotated_audit["rigid_body_api"],
        }
        if not all(report["gates"].values()):
            raise RuntimeError(f"Phase 6EC preparation gates failed: {report['gates']}")
        report["status"] = "ok"
        report["completion_contract"]["results_saved"] = True
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        report["completion_contract"]["shutdown_requested"] = True
        report["lifecycle_marker"] = "shutdown_requested"
        _write(report_path, report)
        app.post_uncancellable_quit(exit_code)


if __name__ == "__main__":
    _main()
