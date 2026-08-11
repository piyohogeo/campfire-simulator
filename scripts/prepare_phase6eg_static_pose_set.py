"""Prepare and offline-audit the predeclared Phase 6EG static pose set.

The exact Phase 6EC/6EE geometry and distance implementations are imported;
this module adds only pose construction and pre-formal pose-set checks.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
from pxr import Gf, Usd, UsdGeom


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import phase6ee_velocity_distribution as spatial  # noqa: E402
import prepare_phase6ec_static_rotated_cylinder as phase6ec  # noqa: E402


VELOCITY_VOXEL_M = 0.05
HALO_CELLS = 3.0


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _gf_matrix(rows) -> Gf.Matrix4d:
    return Gf.Matrix4d([[float(value) for value in row] for row in rows])


def _matrix_array(matrix: Gf.Matrix4d) -> np.ndarray:
    return np.asarray(phase6ec._matrix_list(matrix), dtype=np.float64)


def _quaternion_from_row_matrix(matrix: np.ndarray) -> list[float]:
    """Return [w,x,y,z] from a row-vector rotation without Euler recovery."""

    column = matrix[:3, :3].T
    trace = float(np.trace(column))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (column[2, 1] - column[1, 2]) / scale
        y = (column[0, 2] - column[2, 0]) / scale
        z = (column[1, 0] - column[0, 1]) / scale
    else:
        axis = int(np.argmax(np.diag(column)))
        if axis == 0:
            scale = math.sqrt(1.0 + column[0, 0] - column[1, 1] - column[2, 2]) * 2.0
            w = (column[2, 1] - column[1, 2]) / scale
            x, y, z = 0.25 * scale, (column[0, 1] + column[1, 0]) / scale, (column[0, 2] + column[2, 0]) / scale
        elif axis == 1:
            scale = math.sqrt(1.0 + column[1, 1] - column[0, 0] - column[2, 2]) * 2.0
            w = (column[0, 2] - column[2, 0]) / scale
            x, y, z = (column[0, 1] + column[1, 0]) / scale, 0.25 * scale, (column[1, 2] + column[2, 1]) / scale
        else:
            scale = math.sqrt(1.0 + column[2, 2] - column[0, 0] - column[1, 1]) * 2.0
            w = (column[1, 0] - column[0, 1]) / scale
            x, y, z = (column[0, 2] + column[2, 0]) / scale, (column[1, 2] + column[2, 1]) / scale, 0.25 * scale
    value = np.asarray([w, x, y, z], dtype=np.float64)
    value /= np.linalg.norm(value)
    if value[0] < 0.0:
        value *= -1.0
    return value.tolist()


def _reference_grid(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        indices = payload["index_ijk"].astype(np.float64)
        world = payload["world_xyz"].astype(np.float64)
    design = np.column_stack((np.ones(indices.shape[0]), indices))
    coefficients, residuals, _, _ = np.linalg.lstsq(design, world, rcond=None)
    predicted = design @ coefficients
    if float(np.max(np.abs(predicted - world))) > 1.0e-8:
        raise RuntimeError(f"reference NanoVDB map is not affine: {residuals}")
    return coefficients[0], coefficients[1:]


def _expected_grid_counts(geometry: dict, matrix: np.ndarray, origin: np.ndarray, basis: np.ndarray) -> dict:
    mesh_world = np.column_stack((geometry["vertices"], np.ones(len(geometry["vertices"])))) @ matrix
    mesh_world = mesh_world[:, :3]
    expansion = HALO_CELLS * VELOCITY_VOXEL_M
    corners = np.asarray(
        [
            [x, y, z]
            for x in (mesh_world[:, 0].min() - expansion, mesh_world[:, 0].max() + expansion)
            for y in (mesh_world[:, 1].min() - expansion, mesh_world[:, 1].max() + expansion)
            for z in (mesh_world[:, 2].min() - expansion, mesh_world[:, 2].max() + expansion)
        ],
        dtype=np.float64,
    )
    corner_indices = (corners - origin) @ np.linalg.inv(basis)
    minimum = np.floor(corner_indices.min(axis=0)).astype(np.int32) - 1
    maximum = np.ceil(corner_indices.max(axis=0)).astype(np.int32) + 1
    ranges = [np.arange(minimum[axis], maximum[axis] + 1, dtype=np.int32) for axis in range(3)]
    ii, jj, kk = np.meshgrid(*ranges, indexing="ij")
    indices = np.column_stack((ii.ravel(), jj.ravel(), kk.ravel()))
    world = origin + indices @ basis
    local_h = np.column_stack((world, np.ones(len(world)))) @ np.linalg.inv(matrix)
    local = local_h[:, :3]
    signed, inside, _ = spatial.mesh_signed_distance(local, geometry)
    depth = -signed / VELOCITY_VOXEL_M
    axis = int(geometry["axis"])
    radial_axes = [value for value in range(3) if value != axis]
    radial = np.linalg.norm(local[:, radial_axes] - geometry["centroid"][radial_axes], axis=1)
    deep = inside & (depth > 1.0)
    center = deep & (radial <= 0.5 * VELOCITY_VOXEL_M)
    return {
        "grid_index_minimum": minimum.tolist(),
        "grid_index_maximum": maximum.tolist(),
        "candidate_voxel_count": int(len(indices)),
        "inside_voxel_count": int(np.count_nonzero(inside)),
        "expected_deep_interior_voxel_count": int(np.count_nonzero(deep)),
        "expected_center_axis_voxel_count": int(np.count_nonzero(center)),
        "note": "offline expectation from the affine map of a Phase 6EF public velocity NanoVDB sample; formal runs verify actual samples",
    }


def _exact_emitter_clearance(stage: Usd.Stage, matrix: np.ndarray, geometry: dict) -> dict:
    emitter = stage.GetPrimAtPath(phase6ec.EMITTER_PATH)
    position = np.asarray(emitter.GetAttribute("position").Get(), dtype=np.float64)
    radius = float(emitter.GetAttribute("radius").Get())
    local = np.append(position, 1.0) @ np.linalg.inv(matrix)
    signed, inside, face_type = spatial.mesh_signed_distance(local[:3].reshape((1, 3)), geometry)
    surface_gap = float(signed[0] - radius)
    return {
        "emitter_position_world_m": position.tolist(),
        "emitter_radius_m": radius,
        "emitter_center_local_m": local[:3].tolist(),
        "emitter_center_mesh_signed_distance_m": float(signed[0]),
        "emitter_center_inside_mesh": bool(inside[0]),
        "nearest_face_class": spatial.FACE_NAMES[int(face_type[0])],
        "sphere_surface_gap_to_exact_mesh_m": surface_gap,
        "gap_velocity_voxels": surface_gap / VELOCITY_VOXEL_M,
    }


def _export_pose(source: Path, destination: Path, matrix: Gf.Matrix4d, identity: bool) -> None:
    if identity:
        shutil.copyfile(source, destination)
        return
    stage = Usd.Stage.Open(str(source))
    if stage is None or not stage.Export(str(destination)):
        raise RuntimeError(f"unable to export pose stage: {destination}")
    del stage
    stage = Usd.Stage.Open(str(destination))
    prim = stage.GetPrimAtPath(phase6ec.COLLIDER_PATH)
    xformable = UsdGeom.Xformable(prim)
    if xformable.GetOrderedXformOps():
        raise RuntimeError("qualified source unexpectedly has authored transform ops")
    xformable.AddTransformOp().Set(matrix)
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"unable to save pose stage: {destination}")


def _main() -> None:
    settings = carb.settings.get_settings()
    source = Path(settings.get_as_string("/phase6eg/source")).resolve()
    contract_path = Path(settings.get_as_string("/phase6eg/contract")).resolve()
    output_root = Path(settings.get_as_string("/phase6eg/outputRoot")).resolve()
    report_path = Path(settings.get_as_string("/phase6eg/report")).resolve()
    reference_npz = Path(settings.get_as_string("/phase6eg/referenceNpz")).resolve()
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6eg.static-pose-preflight.v1",
        "phase": "phase6eg",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": phase6ec._sha256(source) if source.is_file() else None,
        "contract_sha256": phase6ec._sha256(contract_path) if contract_path.is_file() else None,
        "reference_npz_sha256": phase6ec._sha256(reference_npz) if reference_npz.is_file() else None,
        "flow_internal_occupancy_mask_public_api_available": False,
        "poses": {},
        "gates": {},
    }
    exit_code = 1
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if report["source_sha256"] != contract["source_stage_sha256"]:
            raise RuntimeError("qualified Phase 6DY source hash mismatch")
        if not contract["declared_before_formal_runs"] or contract["phase"] != "phase6eg":
            raise RuntimeError("Phase 6EG contract is not predeclared")
        output_root.mkdir(parents=True, exist_ok=False)
        origin, basis = _reference_grid(reference_npz)
        source_stage = Usd.Stage.Open(str(source))
        if source_stage is None:
            raise RuntimeError("unable to open source stage")
        source_mesh = UsdGeom.Mesh(source_stage.GetPrimAtPath(phase6ec.COLLIDER_PATH))
        payload = phase6ec._geometry_payload(source_mesh)
        geometry = spatial.build_mesh_geometry(
            payload["points"], payload["face_vertex_counts"], payload["face_vertex_indices"]
        )
        source_geometry_hash = phase6ec._canonical_sha256(payload)
        del source_stage
        envelope = contract["fixed_environment"]["qualified_scene_envelope_m"]
        envelope_minimum = np.asarray(envelope["minimum"], dtype=np.float64)
        envelope_maximum = np.asarray(envelope["maximum"], dtype=np.float64)
        minimum_clearance = float(contract["thresholds"]["minimum_emitter_surface_clearance_m"])
        for pose_name, pose in contract["poses"].items():
            declared = np.asarray(pose["matrix"], dtype=np.float64)
            matrix = _gf_matrix(declared)
            destination = output_root / f"{pose_name}.usda"
            _export_pose(source, destination, matrix, pose_name == "P0_identity")
            stage = Usd.Stage.Open(str(destination))
            if stage is None:
                raise RuntimeError(f"unable to audit {pose_name}")
            audit = phase6ec._audit(stage)
            actual = _matrix_array(UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(phase6ec.COLLIDER_PATH)))
            rotation = actual[:3, :3]
            center = np.append(np.asarray(phase6ec.CENTER, dtype=np.float64), 1.0) @ actual
            exact_clearance = _exact_emitter_clearance(stage, actual, geometry)
            expected = _expected_grid_counts(geometry, actual, origin, basis)
            extent = np.asarray(audit["geometry"]["computed_world_extent"], dtype=np.float64)
            pose_gates = {
                "matrix_matches_contract": bool(np.allclose(actual, declared, rtol=0.0, atol=1.0e-12)),
                "rigid_orthonormal": bool(np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-10)),
                "determinant_positive_one": abs(float(np.linalg.det(rotation)) - 1.0) <= 1.0e-10,
                "center_preserved": bool(np.linalg.norm(center[:3] - np.asarray(phase6ec.CENTER)) <= 1.0e-9),
                "topology_unchanged": audit["geometry"]["vertex_count"] == 26 and audit["geometry"]["face_count"] == 36 and audit["geometry"]["index_count"] == 120,
                "geometry_hash_unchanged": audit["local_geometry_sha256"] == source_geometry_hash,
                "closed_manifold": bool(audit["geometry"]["closed_manifold"]),
                "extent_in_qualified_scene_envelope": bool(np.all(extent[0] >= envelope_minimum) and np.all(extent[1] <= envelope_maximum)),
                "emitter_outside_exact_mesh": not exact_clearance["emitter_center_inside_mesh"],
                "emitter_clearance_at_least_two_velocity_voxels": exact_clearance["sphere_surface_gap_to_exact_mesh_m"] >= minimum_clearance,
                "deep_samples_expected": expected["expected_deep_interior_voxel_count"] > 0,
                "center_axis_samples_expected": expected["expected_center_axis_voxel_count"] > 0,
                "flow_contract_preserved": abs(audit["flow"]["density_cell_size"] - 0.025) <= 1.0e-8
                and audit["flow"]["physics_collision_enabled"] is True
                and audit["flow"]["physics_convex_collision"] is True
                and abs(audit["flow"]["emitter_fuel"] - 0.8) <= 1.0e-6,
                "flow_only_no_render_surface_or_rigid_body": not audit["render_surface_present"] and not audit["rigid_body_api"],
            }
            report["poses"][pose_name] = {
                "stage": str(destination),
                "stage_sha256": phase6ec._sha256(destination),
                "declared_kind": pose["kind"],
                "declared_parameters": pose["parameters"],
                "authored_local_to_world_matrix": actual.tolist(),
                "quaternion_wxyz": _quaternion_from_row_matrix(actual),
                "audit": audit,
                "exact_mesh_emitter_clearance": exact_clearance,
                "expected_public_velocity_grid_sampling": expected,
                "gates": pose_gates,
            }
            del stage
        report["gates"] = {
            "six_predeclared_poses": len(report["poses"]) == 6,
            "all_pose_gates_pass": all(all(item["gates"].values()) for item in report["poses"].values()),
            "all_local_geometry_hashes_identical": len({item["audit"]["local_geometry_sha256"] for item in report["poses"].values()}) == 1,
            "formal_order_has_36_unique_run_condition_slots": sum(len(row) for row in contract["formal_order"]) == 36 and all(len(set(row)) == 12 for row in contract["formal_order"]),
            "thresholds_equal_phase6ef": contract["thresholds"]["existing_velocity_limit_m_s"] == 1.0e-5 and contract["thresholds"]["collision_off_positive_minimum_m_s"] == 0.1 and contract["thresholds"]["on_to_off_deep_maximum_ratio"] == 0.01,
        }
        if not all(report["gates"].values()):
            raise RuntimeError(f"Phase 6EG offline gates failed: {report['gates']}")
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
