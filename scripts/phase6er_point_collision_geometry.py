"""Corrected four-log diagnostic geometry for Phase 6ER.

This module does not modify the frozen Phase 6EP/6EQ fixture.  It supplies a
separate pose set to the existing immutable Point planner.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from phase6ee_velocity_distribution import build_mesh_geometry, mesh_signed_distance
from phase6ep_point_collision_geometry import (
    LENGTH_M,
    RADIUS_M,
    SURFACE_POINTS_PER_LOG,
    LogPose,
    cylinder_topology,
    plan_payload as _legacy_plan_payload,
    surface_points_and_normals,
)


GEOMETRY_TOLERANCE_M = 1.0e-6
SUPPORT_RADIUS_ASSUMPTION_M = 0.05
PRODUCTION_RADIUS_M = 0.16
PRODUCTION_PAIR_HALF_SEPARATION_M = 0.34

# Preserve the production Phase-2 arrangement: lower axes are world X and are
# separated in Y; upper axes are world Y and are separated in X.  The lateral
# offset is radius-scaled from production, while the vertical center spacing is
# exactly two diagnostic radii so the crossed layers touch without volume
# penetration in the authored closed Mesh.
PAIR_HALF_SEPARATION_M = (
    PRODUCTION_PAIR_HALF_SEPARATION_M * RADIUS_M / PRODUCTION_RADIUS_M
)
LOWER_Z_M = 0.45
UPPER_Z_M = LOWER_Z_M + 2.0 * RADIUS_M

CORRECTED_PRODUCTION_FOUR = (
    LogPose("lower_a", (0.0, -PAIR_HALF_SEPARATION_M, LOWER_Z_M), 0.0),
    LogPose("lower_b", (0.0, PAIR_HALF_SEPARATION_M, LOWER_Z_M), 0.0),
    LogPose("upper_a", (-PAIR_HALF_SEPARATION_M, 0.0, UPPER_Z_M), 90.0),
    LogPose("upper_b", (PAIR_HALF_SEPARATION_M, 0.0, UPPER_Z_M), 90.0),
)


def corrected_plan_payload(
    scenario: str,
    offset_m: float,
    support_radius_m: float,
    filtering: bool,
    policy: str = "strict_all",
):
    if scenario == "production_four":
        return _legacy_plan_payload(
            scenario,
            offset_m,
            support_radius_m,
            filtering,
            policy,
            poses_override=CORRECTED_PRODUCTION_FOUR,
        )
    return _legacy_plan_payload(
        scenario, offset_m, support_radius_m, filtering, policy
    )


def _axis(pose: LogPose) -> np.ndarray:
    angle = math.radians(pose.yaw_degrees)
    return np.asarray((math.cos(angle), math.sin(angle), 0.0), dtype=np.float64)


def _mesh_vertex_signed_distance(first: LogPose, second: LogPose) -> tuple[float, int]:
    first_points, _, _ = cylinder_topology(first)
    second_points, counts, indices = cylinder_topology(second)
    signed, _, _ = mesh_signed_distance(
        first_points, build_mesh_geometry(second_points, counts, indices)
    )
    return float(np.min(signed)), int(np.count_nonzero(signed < -GEOMETRY_TOLERANCE_M))


def _dense_surface_distance(first: LogPose, second: LogPose) -> tuple[float, int]:
    points, _, _ = surface_points_and_normals(first)
    second_points, counts, indices = cylinder_topology(second)
    signed, _, _ = mesh_signed_distance(
        points, build_mesh_geometry(second_points, counts, indices)
    )
    return float(np.min(signed)), int(np.count_nonzero(signed < -GEOMETRY_TOLERANCE_M))


def _triangles(pose: LogPose) -> list[np.ndarray]:
    points, counts, indices = cylinder_topology(pose)
    triangles = []
    cursor = 0
    for count in counts:
        face = indices[cursor : cursor + int(count)]
        cursor += int(count)
        for offset in range(1, len(face) - 1):
            triangles.append(points[[face[0], face[offset], face[offset + 1]]])
    return triangles


def _point_triangle_distance(point: np.ndarray, triangle: np.ndarray) -> float:
    # Real-Time Collision Detection, Christer Ericson, closest point on triangle.
    a, b, c = triangle
    ab, ac, ap = b - a, c - a, point - a
    d1, d2 = float(np.dot(ab, ap)), float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return float(np.linalg.norm(ap))
    bp = point - b
    d3, d4 = float(np.dot(ab, bp)), float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return float(np.linalg.norm(bp))
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return float(np.linalg.norm(point - (a + v * ab)))
    cp = point - c
    d5, d6 = float(np.dot(ab, cp)), float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return float(np.linalg.norm(cp))
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return float(np.linalg.norm(point - (a + w * ac)))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return float(np.linalg.norm(point - (b + w * (c - b))))
    normal = np.cross(ab, ac)
    return abs(float(np.dot(point - a, normal))) / float(np.linalg.norm(normal))


def _segment_segment_distance(p1, q1, p2, q2) -> float:
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = float(np.dot(d1, d1)), float(np.dot(d2, d2)), float(np.dot(d2, r))
    eps = 1.0e-18
    if a <= eps and e <= eps:
        return float(np.linalg.norm(p1 - p2))
    if a <= eps:
        s, t = 0.0, min(1.0, max(0.0, f / e))
    else:
        c = float(np.dot(d1, r))
        if e <= eps:
            t, s = 0.0, min(1.0, max(0.0, -c / a))
        else:
            b = float(np.dot(d1, d2))
            denominator = a * e - b * b
            s = min(1.0, max(0.0, (b * f - c * e) / denominator)) if denominator else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(1.0, max(0.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, min(1.0, max(0.0, (b - c) / a))
    return float(np.linalg.norm((p1 + d1 * s) - (p2 + d2 * t)))


def _triangle_distance(first: np.ndarray, second: np.ndarray) -> float:
    best = min(
        *(_point_triangle_distance(point, second) for point in first),
        *(_point_triangle_distance(point, first) for point in second),
    )
    for left in range(3):
        for right in range(3):
            best = min(
                best,
                _segment_segment_distance(
                    first[left], first[(left + 1) % 3],
                    second[right], second[(right + 1) % 3],
                ),
            )
    return best


def _closed_mesh_surface_distance(first: LogPose, second: LogPose) -> float:
    return min(
        _triangle_distance(left, right)
        for left in _triangles(first)
        for right in _triangles(second)
    )


def _pair_audit(first: LogPose, second: LogPose) -> dict:
    axis = _axis(first)
    delta = np.asarray(second.center, dtype=np.float64) - np.asarray(first.center, dtype=np.float64)
    along = float(abs(np.dot(delta, axis)))
    perpendicular = float(np.linalg.norm(delta - np.dot(delta, axis) * axis))
    parallel = float(abs(np.dot(axis, _axis(second)))) >= 1.0 - 1.0e-12
    segment_overlap = max(0.0, LENGTH_M - along) if parallel else None
    forward_min, forward_inside = _mesh_vertex_signed_distance(first, second)
    reverse_min, reverse_inside = _mesh_vertex_signed_distance(second, first)
    dense_forward, dense_inside_forward = _dense_surface_distance(first, second)
    dense_reverse, dense_inside_reverse = _dense_surface_distance(second, first)
    surface_distance = _closed_mesh_surface_distance(first, second)
    # For the convex diagnostic proxies, negative vertex/dense samples prove
    # volume overlap.  Zero within tolerance records intended contact.  A fully
    # general polyhedron intersection is deliberately not claimed here.
    sampled_min = min(forward_min, reverse_min, dense_forward, dense_reverse)
    inside_count = sum((forward_inside, reverse_inside, dense_inside_forward, dense_inside_reverse))
    signed_distance = sampled_min if inside_count else surface_distance
    classification = (
        "sampled_volume_overlap"
        if inside_count
        else ("contact_within_tolerance" if surface_distance <= GEOMETRY_TOLERANCE_M else "separated")
    )
    return {
        "pair": [first.name, second.name],
        "first_world_long_axis": _axis(first).tolist(),
        "second_world_long_axis": _axis(second).tolist(),
        "center_delta_m": delta.tolist(),
        "first_axis_component_m": along,
        "first_axis_perpendicular_component_m": perpendicular,
        "parallel_axes": parallel,
        "centerline_segment_overlap_m": segment_overlap,
        "closed_mesh_surface_distance_m": surface_distance,
        "minimum_signed_distance_m": signed_distance,
        "signed_distance_method": "negative sampled authored-Mesh penetration; otherwise exact triangle-pair surface distance",
        "first_vertices_inside_second": forward_inside,
        "second_vertices_inside_first": reverse_inside,
        "first_surface_points_inside_second": dense_inside_forward,
        "second_surface_points_inside_first": dense_inside_reverse,
        "classification": classification,
    }


def audit_pose_set(poses: tuple[LogPose, ...]) -> dict:
    pairs = [
        _pair_audit(poses[left], poses[right])
        for left in range(len(poses))
        for right in range(left + 1, len(poses))
    ]
    point_plan = _legacy_plan_payload(
        "production_four", 0.0, SUPPORT_RADIUS_ASSUMPTION_M, False,
        poses_override=poses,
    )
    topology_digest = hashlib.sha256()
    for pose in poses:
        points, counts, indices = cylinder_topology(pose)
        topology_digest.update(points.astype("<f8", copy=False).tobytes())
        topology_digest.update(counts.astype("<i4", copy=False).tobytes())
        topology_digest.update(indices.astype("<i4", copy=False).tobytes())
    return {
        "poses": [pose.__dict__ for pose in poses],
        "geometry_sha256": topology_digest.hexdigest().upper(),
        "point_count": point_plan["original_point_count"],
        "points_per_log": SURFACE_POINTS_PER_LOG,
        "other_log_point_centers_inside": point_plan["other_inside_count"],
        "pairs": pairs,
        "minimum_signed_distance_m": min(
            pair["minimum_signed_distance_m"] for pair in pairs
        ),
        "sampled_volume_overlap_pair_count": sum(
            pair["classification"] == "sampled_volume_overlap" for pair in pairs
        ),
    }


def write_audit(path: Path, legacy_poses: tuple[LogPose, ...]) -> dict:
    report = {
        "schema": "campfire.phase6er.four-log-geometry-audit.v1",
        "phase": "phase6er",
        "geometry_tolerance_m": GEOMETRY_TOLERANCE_M,
        "support_radius": {
            "value_m": SUPPORT_RADIUS_ASSUMPTION_M,
            "status": "engineering_assumption_equal_to_one_velocity_voxel",
            "public_flow_support_radius_available": False,
        },
        "legacy_fixture": audit_pose_set(legacy_poses),
        "corrected_fixture": audit_pose_set(CORRECTED_PRODUCTION_FOUR),
        "production_reference": {
            "source": "source/extensions/campfire.app/campfire/app/phase2_scene.py",
            "lower_centers_m": [[0.0, -0.34, 0.18], [0.0, 0.34, 0.18]],
            "upper_centers_m": [[-0.34, 0.0, 0.50], [0.34, 0.0, 0.50]],
            "radius_m": PRODUCTION_RADIUS_M,
            "length_m": 1.80,
            "same_axis_overlap_defect": False,
            "correction_basis": "production lateral pattern radius-scaled; vertical crossed-layer tangency preserved",
        },
        "gates": {},
    }
    corrected = report["corrected_fixture"]
    report["gates"] = {
        "point_count_1440": corrected["point_count"] == 1440,
        "other_log_point_centers_inside_zero": corrected["other_log_point_centers_inside"] == 0,
        "no_sampled_volume_overlap": corrected["sampled_volume_overlap_pair_count"] == 0,
        "top_axes_world_y": all(
            np.allclose(_axis(pose), (0.0, 1.0, 0.0), atol=1.0e-12)
            for pose in CORRECTED_PRODUCTION_FOUR[2:]
        ),
        "top_separation_perpendicular_to_long_axis": abs(
            CORRECTED_PRODUCTION_FOUR[3].center[0] - CORRECTED_PRODUCTION_FOUR[2].center[0]
        ) > 0.0 and CORRECTED_PRODUCTION_FOUR[3].center[1] == CORRECTED_PRODUCTION_FOUR[2].center[1],
    }
    report["qualified_for_scalar_calibration"] = all(report["gates"].values())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
