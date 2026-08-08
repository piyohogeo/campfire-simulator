"""Frame-aligned diagnostics for the unresolved Resident Point continuity gap."""

from __future__ import annotations

import math

from .wood import get_log_world_position


def resident_point_group_centroids(points, points_per_log: int) -> tuple:
    """Return one SI-unit centroid for each contiguous per-log point group."""

    if isinstance(points_per_log, bool) or not isinstance(points_per_log, int):
        raise TypeError("points_per_log must be an integer")
    if points_per_log <= 0:
        raise ValueError("points_per_log must be positive")
    converted = tuple(tuple(float(component) for component in point) for point in points)
    if not converted or len(converted) % points_per_log:
        raise ValueError("Point count must contain complete per-log groups")
    if any(len(point) != 3 or not all(math.isfinite(value) for value in point) for point in converted):
        raise ValueError("Resident Point positions must be finite 3D values")

    centroids = []
    for start in range(0, len(converted), points_per_log):
        group = converted[start : start + points_per_log]
        centroids.append(
            tuple(sum(point[axis] for point in group) / points_per_log for axis in range(3))
        )
    return tuple(centroids)


def measure_resident_point_log_alignment(
    stage, log_ids, points, *, points_per_log: int
) -> dict:
    """Measure Point group-centroid drift from authoritative PhysX log poses."""

    log_ids = tuple(log_ids)
    centroids = resident_point_group_centroids(points, points_per_log)
    if len(centroids) != len(log_ids):
        raise ValueError("Point group count must match the log count")
    origins = tuple(
        tuple(float(component) for component in get_log_world_position(stage, log_id))
        for log_id in log_ids
    )
    error_m = tuple(
        math.sqrt(sum((centroid[axis] - origin[axis]) ** 2 for axis in range(3)))
        for centroid, origin in zip(centroids, origins)
    )
    return {
        "log_origins_m": origins,
        "point_centroids_m": centroids,
        "error_m": error_m,
        "max_error_m": max(error_m, default=0.0),
        "points_per_log": points_per_log,
        "point_count": len(centroids) * points_per_log,
    }
