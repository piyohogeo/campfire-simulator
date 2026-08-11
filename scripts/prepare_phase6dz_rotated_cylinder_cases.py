"""Prepare Phase 6DZ stages by changing only the qualified Cylinder transform."""

from __future__ import annotations

import hashlib
import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
from pxr import Gf, Usd, UsdGeom


COLLIDER_PATH = "/World/ColliderReferenceMesh"
CENTER = Gf.Vec3d(0.0, 0.0, 1.035)
CASES = (
    ("axis_control_start", (0.0, 0.0, 0.0), "qualified axis-aligned control"),
    ("rotate_x17", (17.0, 0.0, 0.0), "single-axis X rotation"),
    ("rotate_y12", (0.0, 12.0, 0.0), "single-axis Y rotation"),
    ("rotate_z90_log02", (0.0, 0.0, 90.0), "Phase 6DR four-log orientation"),
    ("phase6dr_z37", (0.0, 0.0, 37.0), "Phase 6DR Log_00 diagnostic orientation"),
    ("rotate_xyz_17_12_37", (17.0, 12.0, 37.0), "representative multi-axis orientation"),
    ("axis_control_end", (0.0, 0.0, 0.0), "qualified axis-aligned exit control"),
)


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


def _geometry_payload(mesh: UsdGeom.Mesh) -> dict:
    return {
        "points": [[float(value) for value in point] for point in mesh.GetPointsAttr().Get()],
        "face_vertex_counts": [int(value) for value in mesh.GetFaceVertexCountsAttr().Get()],
        "face_vertex_indices": [int(value) for value in mesh.GetFaceVertexIndicesAttr().Get()],
        "extent": [[float(value) for value in item] for item in mesh.GetExtentAttr().Get()],
    }


def _canonical_sha256(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _matrix_list(matrix: Gf.Matrix4d) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _rotation_about_center(angles_deg: tuple[float, float, float]) -> Gf.Matrix4d:
    rotation = Gf.Matrix4d(1.0)
    for axis, angle in zip(
        (Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis()), angles_deg
    ):
        if abs(angle) <= 1.0e-12:
            continue
        step = Gf.Matrix4d(1.0)
        step.SetRotate(Gf.Rotation(axis, angle))
        rotation = rotation * step
    moved_center = rotation.Transform(CENTER)
    rotation.SetTranslateOnly(CENTER - moved_center)
    if (rotation.Transform(CENTER) - CENTER).GetLength() > 1.0e-9:
        raise RuntimeError("Unable to preserve the Cylinder center")
    return rotation


def _audit(stage: Usd.Stage) -> dict:
    prim = stage.GetPrimAtPath(COLLIDER_PATH)
    if not prim or not prim.IsValid() or prim.GetTypeName() != "Mesh":
        raise RuntimeError(f"Expected Mesh at {COLLIDER_PATH}")
    mesh = UsdGeom.Mesh(prim)
    geometry = _geometry_payload(mesh)
    matrix = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
    rotation = matrix.ExtractRotationMatrix()
    determinant = float(rotation.GetDeterminant())
    row_lengths = [float(rotation.GetRow(index).GetLength()) for index in range(3)]
    applied = list(prim.GetAppliedSchemas())
    return {
        "local_geometry_sha256": _canonical_sha256(geometry),
        "geometry": {
            "vertex_count": len(geometry["points"]),
            "face_count": len(geometry["face_vertex_counts"]),
            "index_count": len(geometry["face_vertex_indices"]),
            "extent": geometry["extent"],
        },
        "applied_schemas": applied,
        "physics_collision_enabled": prim.GetAttribute("physics:collisionEnabled").Get(),
        "physics_approximation": prim.GetAttribute("physics:approximation").Get(),
        "transform_ops": [
            attribute.GetName()
            for attribute in prim.GetAttributes()
            if attribute.GetName().startswith("xformOp:")
        ],
        "local_to_world": _matrix_list(matrix),
        "center_world": list(matrix.Transform(CENTER)),
        "rotation_determinant": determinant,
        "rotation_row_lengths": row_lengths,
        "right_handed_unit_scale": (
            abs(determinant - 1.0) <= 1.0e-6
            and all(abs(length - 1.0) <= 1.0e-6 for length in row_lengths)
        ),
    }


def _main() -> None:
    settings = carb.settings.get_settings()
    source = Path(settings.get_as_string("/phase6dz/source")).resolve()
    output_root = Path(settings.get_as_string("/phase6dz/outputRoot")).resolve()
    report_path = Path(settings.get_as_string("/phase6dz/report")).resolve()
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6dz.rotated-cylinder-stages.v1",
        "phase": "phase6dz",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_sha256": _sha256(source) if source.is_file() else None,
        "transform_order": "local X then Y then Z; single xformOp:transform about local center",
        "cases": {},
    }
    exit_code = 1
    try:
        if not source.is_file():
            raise RuntimeError(f"Qualified Phase 6DY Cylinder source missing: {source}")
        output_root.mkdir(parents=True, exist_ok=False)
        source_stage = Usd.Stage.Open(str(source))
        if source_stage is None:
            raise RuntimeError("Unable to open qualified Phase 6DY Cylinder source")
        source_audit = _audit(source_stage)
        del source_stage
        if source_audit["physics_approximation"] != "convexDecomposition":
            raise RuntimeError("Source is not the qualified convexDecomposition Cylinder")
        if source_audit["geometry"] != {
            "vertex_count": 26,
            "face_count": 36,
            "index_count": 120,
            "extent": [[-0.8999999761581421, -0.1599999964237213, 0.875], [0.8999999761581421, 0.1599999964237213, 1.1950000524520874]],
        }:
            raise RuntimeError(f"Unexpected source topology: {source_audit['geometry']}")

        for label, angles, purpose in CASES:
            destination = output_root / f"{label}.usda"
            source_stage = Usd.Stage.Open(str(source))
            if source_stage is None or not source_stage.Export(str(destination)):
                raise RuntimeError(f"Unable to export {label}")
            del source_stage
            stage = Usd.Stage.Open(str(destination))
            prim = stage.GetPrimAtPath(COLLIDER_PATH)
            xformable = UsdGeom.Xformable(prim)
            if any(abs(angle) > 1.0e-12 for angle in angles):
                if xformable.GetOrderedXformOps():
                    raise RuntimeError("Qualified source unexpectedly has transform ops")
                xformable.AddTransformOp().Set(_rotation_about_center(angles))
            if not stage.GetRootLayer().Save():
                raise RuntimeError(f"Unable to save {label}")
            audit = _audit(stage)
            del stage
            report["cases"][label] = {
                "path": str(destination),
                "stage_sha256": _sha256(destination),
                "rotation_xyz_deg": list(angles),
                "purpose": purpose,
                "audit": audit,
            }

        local_hashes = {
            case["audit"]["local_geometry_sha256"] for case in report["cases"].values()
        }
        schema_contracts = {
            json.dumps(
                {
                    "schemas": case["audit"]["applied_schemas"],
                    "enabled": case["audit"]["physics_collision_enabled"],
                    "approximation": case["audit"]["physics_approximation"],
                },
                sort_keys=True,
            )
            for case in report["cases"].values()
        }
        start = report["cases"]["axis_control_start"]
        end = report["cases"]["axis_control_end"]
        report["gates"] = {
            "local_geometry_sha256_equal": len(local_hashes) == 1,
            "schema_and_approximation_equal": len(schema_contracts) == 1,
            "controls_byte_identical": start["stage_sha256"] == end["stage_sha256"],
            "controls_audit_identical": start["audit"] == end["audit"],
            "all_transforms_right_handed_unit_scale": all(
                case["audit"]["right_handed_unit_scale"] for case in report["cases"].values()
            ),
            "all_centers_preserved": all(
                math.dist(case["audit"]["center_world"], list(CENTER)) <= 1.0e-8
                for case in report["cases"].values()
            ),
            "convex_hull_absent": all(
                case["audit"]["physics_approximation"] != "convexHull"
                for case in report["cases"].values()
            ),
        }
        if not all(report["gates"].values()):
            raise RuntimeError(f"Offline rotation gates failed: {report['gates']}")
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
