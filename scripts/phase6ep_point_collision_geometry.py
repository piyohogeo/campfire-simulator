"""Offline geometry and immutable Point payload planning for Phase 6EP."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from phase6ee_velocity_distribution import build_mesh_geometry, mesh_signed_distance


LENGTH_M = 0.72
RADIUS_M = 0.105
SURFACE_POINTS_PER_LOG = 360
SIDES = 12


@dataclass(frozen=True)
class LogPose:
    name: str
    center: tuple[float, float, float]
    yaw_degrees: float = 0.0
    emits: bool = True


SCENARIOS = {
    "single": (LogPose("log0", (0.0, 0.0, 0.52)),),
    "near_two": (
        LogPose("log0", (0.0, -0.09, 0.50), 0.0),
        LogPose("log1", (0.0, 0.15, 0.59), 35.0),
    ),
    "lower_upper": (
        LogPose("lower", (0.0, 0.0, 0.45), 0.0, True),
        LogPose("upper", (0.0, 0.0, 0.78), 0.0, False),
    ),
    "production_four": (
        LogPose("lower_a", (-0.04, -0.12, 0.45), 0.0),
        LogPose("lower_b", (0.04, 0.12, 0.45), 0.0),
        LogPose("upper_a", (0.0, -0.11, 0.68), 90.0),
        LogPose("upper_b", (0.0, 0.11, 0.68), 90.0),
    ),
}


def _rotation(yaw_degrees: float) -> np.ndarray:
    value = math.radians(yaw_degrees)
    c, s = math.cos(value), math.sin(value)
    return np.asarray(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)), dtype=np.float64)


def cylinder_topology(pose: LogPose):
    local = [(-0.5 * LENGTH_M, 0.0, 0.0), (0.5 * LENGTH_M, 0.0, 0.0)]
    for x in (-0.5 * LENGTH_M, 0.5 * LENGTH_M):
        for index in range(SIDES):
            angle = 2.0 * math.pi * index / SIDES
            local.append((x, RADIUS_M * math.cos(angle), RADIUS_M * math.sin(angle)))
    rotation = _rotation(pose.yaw_degrees)
    points = np.asarray(local, dtype=np.float64) @ rotation.T + np.asarray(pose.center)
    counts, indices = [], []
    for side in range(SIDES):
        following = (side + 1) % SIDES
        counts.append(4)
        indices.extend((2 + side, 2 + following, 2 + SIDES + following, 2 + SIDES + side))
    for side in range(SIDES):
        following = (side + 1) % SIDES
        counts.append(3)
        indices.extend((0, 2 + following, 2 + side))
        counts.append(3)
        indices.extend((1, 2 + SIDES + side, 2 + SIDES + following))
    return points, np.asarray(counts, dtype=np.int32), np.asarray(indices, dtype=np.int32)


def surface_points_and_normals(pose: LogPose):
    axial_cells, circumferential_cells, radial_cells = 24, 12, 4
    dx = LENGTH_M / axial_cells
    dr = RADIUS_M / radial_cells
    points, normals, identities = [], [], []
    for axial in range(axial_cells):
        x = -0.5 * LENGTH_M + (axial + 0.5) * dx
        for circumferential in range(circumferential_cells):
            angle = 2.0 * math.pi * (circumferential + 0.5) / circumferential_cells
            for radial in range(radial_cells):
                if radial != radial_cells - 1 and axial not in (0, axial_cells - 1):
                    continue
                radius = (radial + 0.5) * dr
                local = np.asarray((x, radius * math.cos(angle), radius * math.sin(angle)))
                if radial == radial_cells - 1:
                    normal = np.asarray((0.0, math.cos(angle), math.sin(angle)))
                else:
                    normal = np.asarray((-1.0 if axial == 0 else 1.0, 0.0, 0.0))
                points.append(local)
                normals.append(normal)
                identities.append((axial, circumferential, radial))
    if len(points) != SURFACE_POINTS_PER_LOG:
        raise RuntimeError(f"unexpected Point layout: {len(points)}")
    rotation = _rotation(pose.yaw_degrees)
    return (
        np.asarray(points) @ rotation.T + np.asarray(pose.center),
        np.asarray(normals) @ rotation.T,
        identities,
    )


def plan_payload(scenario: str, offset_m: float, support_radius_m: float, filtering: bool):
    poses = SCENARIOS[scenario]
    geometries = []
    for pose in poses:
        points, counts, indices = cylinder_topology(pose)
        geometries.append((pose, points, counts, indices, build_mesh_geometry(points, counts, indices)))
    source_rows = []
    for owner_index, pose in enumerate(poses):
        if not pose.emits:
            continue
        raw_points, normals, identities = surface_points_and_normals(pose)
        moved_points = raw_points + normals * float(offset_m)
        for local_index, (raw, moved, normal, identity) in enumerate(zip(raw_points, moved_points, normals, identities)):
            source_rows.append((owner_index, pose, raw, moved, normal, identity))
    raw_array = np.asarray([row[2] for row in source_rows], dtype=np.float64)
    moved_array = np.asarray([row[3] for row in source_rows], dtype=np.float64)
    raw_distance_columns, distance_columns, face_columns = [], [], []
    for _, _, _, _, geometry in geometries:
        raw_signed, _, _ = mesh_signed_distance(raw_array, geometry)
        signed, _, face = mesh_signed_distance(moved_array, geometry)
        raw_distance_columns.append(raw_signed)
        distance_columns.append(signed)
        face_columns.append(face)
    raw_matrix = np.column_stack(raw_distance_columns)
    distance_matrix = np.column_stack(distance_columns)
    face_matrix = np.column_stack(face_columns)
    nearest_indices = np.argmin(distance_matrix, axis=1)
    records = []
    positions = []
    active = []
    for row_index, (owner_index, pose, raw, moved, normal, identity) in enumerate(source_rows):
            distances = distance_matrix[row_index]
            raw_distances = raw_matrix[row_index]
            face_types = face_matrix[row_index]
            nearest = int(np.argmin(distances))
            clearance = distances[nearest] - support_radius_m
            enabled = (clearance >= -1.0e-9) if filtering else True
            positions.append(moved if filtering else raw)
            active.append(enabled)
            records.append(
                {
                    "payload_index": len(records),
                    "owner_index": owner_index,
                    "owner": pose.name,
                    "surface_identity": list(identity),
                    "raw_position": raw.tolist(),
                    "normal": normal.tolist(),
                    "published_position": (moved if filtering else raw).tolist(),
                    "raw_self_signed_distance_m": raw_distances[owner_index],
                    "raw_inside_self": raw_distances[owner_index] < 0.0,
                    "raw_inside_other": any(value < 0.0 for index, value in enumerate(raw_distances) if index != owner_index),
                    "nearest_collider": poses[nearest].name,
                    "nearest_collider_index": nearest,
                    "nearest_face_class": face_types[nearest],
                    "signed_distance_m": distances[nearest],
                    "support_clearance_m": clearance,
                    "support_intersects": clearance < 0.0,
                    "enabled": enabled,
                }
            )
    active_array = np.asarray(active, dtype=bool)
    return {
        "scenario": scenario,
        "poses": [pose.__dict__ for pose in poses],
        "positions": np.asarray(positions, dtype=np.float32),
        "active": active_array,
        "records": records,
        "original_point_count": len(records),
        "active_point_count": int(np.count_nonzero(active_array)),
        "disabled_point_count": int(np.count_nonzero(~active_array)),
        "supply_efficiency": float(np.mean(active_array)) if active_array.size else 0.0,
        "minimum_support_clearance_m": float(min((item["support_clearance_m"] for item in records), default=0.0)),
        "minimum_active_support_clearance_m": (
            float(min(item["support_clearance_m"] for item in records if item["enabled"]))
            if any(item["enabled"] for item in records) else None
        ),
        "support_intersection_count": int(sum(bool(item["support_intersects"]) for item in records)),
        "active_support_intersection_count": int(
            sum(bool(item["enabled"] and item["support_intersects"]) for item in records)
        ),
        "self_inside_count": int(sum(bool(item["raw_inside_self"]) for item in records)),
        "other_inside_count": int(sum(bool(item["raw_inside_other"]) for item in records)),
        "geometries": geometries,
    }
