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
FILTER_POLICIES = (
    "strict_all",
    "allow_self_support",
    "allow_self_center",
)


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


def plan_payload(
    scenario: str,
    offset_m: float,
    support_radius_m: float,
    filtering: bool,
    policy: str = "strict_all",
):
    if policy not in FILTER_POLICIES:
        raise ValueError(f"unsupported Point/Collision policy: {policy}")
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
            self_signed = float(distances[owner_index])
            other_pairs = [(index, float(value)) for index, value in enumerate(distances) if index != owner_index]
            other_index, other_signed = min(other_pairs, key=lambda item: item[1]) if other_pairs else (-1, math.inf)
            self_inside = self_signed < 0.0
            other_inside = other_signed < 0.0
            self_support_intersects = self_signed - support_radius_m < 0.0
            other_support_intersects = other_signed - support_radius_m < 0.0
            if not filtering:
                enabled, reason = True, "filtering_disabled"
            elif other_support_intersects:
                enabled, reason = False, "other_support_intersection"
            elif policy == "strict_all" and self_support_intersects:
                enabled, reason = False, "self_support_intersection"
            elif policy == "allow_self_support" and self_inside:
                enabled, reason = False, "self_center_inside"
            else:
                enabled, reason = True, "enabled"
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
                    "self_signed_distance_m": self_signed,
                    "other_min_signed_distance_m": other_signed,
                    "other_nearest_collider_index": other_index,
                    "self_center_inside": self_inside,
                    "other_center_inside": other_inside,
                    "self_support_intersects": self_support_intersects,
                    "other_support_intersects": other_support_intersects,
                    "enabled_reason": reason,
                    "original_fuel": 0.8,
                    "original_temperature": 2.0,
                    "original_smoke": 0.08,
                    "enabled_fuel": 0.8 if enabled else 0.0,
                    "enabled_temperature": 2.0 if enabled else 0.0,
                    "enabled_smoke": 0.08 if enabled else 0.0,
                    "enabled": enabled,
                }
            )
    active_array = np.asarray(active, dtype=bool)
    return {
        "scenario": scenario,
        "policy": policy,
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
        "self_center_inside_count": int(sum(bool(item["self_center_inside"]) for item in records)),
        "other_center_inside_count": int(sum(bool(item["other_center_inside"]) for item in records)),
        "self_support_intersection_count": int(sum(bool(item["self_support_intersects"]) for item in records)),
        "other_support_intersection_count": int(sum(bool(item["other_support_intersects"]) for item in records)),
        "active_other_support_intersection_count": int(
            sum(bool(item["enabled"] and item["other_support_intersects"]) for item in records)
        ),
        "disable_reason_counts": {
            reason: int(sum(item["enabled_reason"] == reason for item in records))
            for reason in ("enabled", "filtering_disabled", "self_support_intersection", "self_center_inside", "other_support_intersection")
        },
        "weighted_supply": {
            channel: {
                "original": float(sum(item[f"original_{channel}"] for item in records)),
                "enabled": float(sum(item[f"enabled_{channel}"] for item in records)),
                "retention": (
                    float(sum(item[f"enabled_{channel}"] for item in records))
                    / float(sum(item[f"original_{channel}"] for item in records))
                    if records else 0.0
                ),
            }
            for channel in ("fuel", "temperature", "smoke")
        },
        "geometries": geometries,
    }
