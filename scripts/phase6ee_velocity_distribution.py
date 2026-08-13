"""Compact spatial sampling for the Phase 6EE Flow collision diagnostic.

This module deliberately derives geometry labels from the authored closed Mesh.
They are not, and must not be described as, Flow's internal collision occupancy.
"""

from __future__ import annotations

import gc
import hashlib
import json
import math
from collections import deque
from pathlib import Path

import numpy as np

try:
    import psutil
except ImportError:  # pragma: no cover - Kit includes psutil in the fixed app.
    psutil = None


FACE_SIDE = np.uint8(0)
FACE_END = np.uint8(1)
FACE_OTHER = np.uint8(2)
FACE_NAMES = ("side", "end", "other")
HALO_CELLS = 3.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _component(value, index: int) -> float:
    try:
        return float(value[index])
    except TypeError:
        return float((value.x, value.y, value.z)[index])


def build_mesh_geometry(points, face_counts, face_indices) -> dict:
    """Triangulate and orient a closed convex Mesh without changing its surface."""

    vertices = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    counts = np.asarray(face_counts, dtype=np.int32)
    indices = np.asarray(face_indices, dtype=np.int32)
    if vertices.shape[0] < 4 or counts.size == 0 or int(counts.sum()) != indices.size:
        raise ValueError("invalid closed Mesh topology")
    centroid = vertices.mean(axis=0)
    axis = int(np.argmax(np.ptp(vertices, axis=0)))
    triangles = []
    triangle_face_types = []
    polygon_face_types = []
    cursor = 0
    for count in counts:
        polygon = indices[cursor : cursor + int(count)]
        cursor += int(count)
        if polygon.size < 3:
            raise ValueError("degenerate polygon in collision Mesh")
        a, b, c = vertices[polygon[:3]]
        normal = np.cross(b - a, c - a)
        length = float(np.linalg.norm(normal))
        if length <= 1.0e-12:
            raise ValueError("degenerate face in collision Mesh")
        normal /= length
        face_center = vertices[polygon].mean(axis=0)
        if float(np.dot(normal, face_center - centroid)) < 0.0:
            polygon = polygon[::-1]
            a, b, c = vertices[polygon[:3]]
            normal = np.cross(b - a, c - a)
            normal /= np.linalg.norm(normal)
        axis_weight = abs(float(normal[axis]))
        face_type = FACE_END if axis_weight >= 0.75 else FACE_SIDE if axis_weight <= 0.25 else FACE_OTHER
        polygon_face_types.append(int(face_type))
        for offset in range(1, polygon.size - 1):
            triangles.append((int(polygon[0]), int(polygon[offset]), int(polygon[offset + 1])))
            triangle_face_types.append(face_type)
    triangles = np.asarray(triangles, dtype=np.int32)
    tri_vertices = vertices[triangles]
    normals = np.cross(tri_vertices[:, 1] - tri_vertices[:, 0], tri_vertices[:, 2] - tri_vertices[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    return {
        "vertices": vertices,
        "face_counts": counts,
        "face_indices": indices,
        "triangles": triangles,
        "triangle_vertices": tri_vertices,
        "triangle_normals": normals,
        "triangle_face_types": np.asarray(triangle_face_types, dtype=np.uint8),
        "polygon_face_types": np.asarray(polygon_face_types, dtype=np.uint8),
        "centroid": centroid,
        "axis": axis,
        "minimum": vertices.min(axis=0),
        "maximum": vertices.max(axis=0),
    }


def _segment_distance_squared(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    denominator = float(np.dot(ab, ab))
    if denominator <= 1.0e-24:
        return np.sum((points - a) ** 2, axis=1)
    t = np.clip(((points - a) @ ab) / denominator, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return np.sum((points - closest) ** 2, axis=1)


def mesh_signed_distance(points: np.ndarray, geometry: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return signed exact surface distance, inside flag, and nearest face class.

    The inside test uses outward oriented planes and is valid for this qualified
    convex proxy. Distance is the minimum Euclidean point-to-triangle distance.
    """

    query = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    minimum_squared = np.full(query.shape[0], np.inf, dtype=np.float64)
    nearest_type = np.full(query.shape[0], FACE_OTHER, dtype=np.uint8)
    inside = np.ones(query.shape[0], dtype=bool)
    for triangle, normal, face_type in zip(
        geometry["triangle_vertices"],
        geometry["triangle_normals"],
        geometry["triangle_face_types"],
    ):
        a, b, c = triangle
        signed_plane = (query - a) @ normal
        inside &= signed_plane <= 1.0e-9
        projection = query - signed_plane[:, None] * normal
        v0 = b - a
        v1 = c - a
        v2 = projection - a
        d00 = float(np.dot(v0, v0))
        d01 = float(np.dot(v0, v1))
        d11 = float(np.dot(v1, v1))
        denominator = d00 * d11 - d01 * d01
        if abs(denominator) <= 1.0e-24:
            plane_squared = np.full(query.shape[0], np.inf)
        else:
            d20 = v2 @ v0
            d21 = v2 @ v1
            v = (d11 * d20 - d01 * d21) / denominator
            w = (d00 * d21 - d01 * d20) / denominator
            u = 1.0 - v - w
            projection_inside = (u >= -1.0e-10) & (v >= -1.0e-10) & (w >= -1.0e-10)
            plane_squared = np.where(projection_inside, signed_plane * signed_plane, np.inf)
        squared = np.minimum.reduce(
            (
                plane_squared,
                _segment_distance_squared(query, a, b),
                _segment_distance_squared(query, b, c),
                _segment_distance_squared(query, c, a),
            )
        )
        replace = squared < minimum_squared
        minimum_squared[replace] = squared[replace]
        nearest_type[replace] = face_type
    unsigned = np.sqrt(np.maximum(minimum_squared, 0.0))
    return np.where(inside, -unsigned, unsigned), inside, nearest_type


def analytic_cylinder_signed_distance(points: np.ndarray, geometry: dict) -> np.ndarray:
    """Finite ideal-cylinder SDF used only as a secondary comparison metric."""

    query = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    axis = int(geometry["axis"])
    radial_axes = [value for value in range(3) if value != axis]
    center = (geometry["minimum"] + geometry["maximum"]) * 0.5
    half_length = (geometry["maximum"][axis] - geometry["minimum"][axis]) * 0.5
    radius = float(
        np.max(np.linalg.norm(geometry["vertices"][:, radial_axes] - center[radial_axes], axis=1))
    )
    axial = np.abs(query[:, axis] - center[axis]) - half_length
    radial = np.linalg.norm(query[:, radial_axes] - center[radial_axes], axis=1) - radius
    outside = np.sqrt(np.maximum(axial, 0.0) ** 2 + np.maximum(radial, 0.0) ** 2)
    inside = np.minimum(np.maximum(axial, radial), 0.0)
    return outside + inside


def _six_neighbor_depth(inside: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    mask = inside.reshape(shape)
    depth = np.full(shape, -1, dtype=np.int16)
    queue = deque()
    for coordinate in np.argwhere(~mask):
        key = tuple(int(value) for value in coordinate)
        depth[key] = 0
        queue.append(key)
    offsets = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    while queue:
        current = queue.popleft()
        candidate_depth = int(depth[current]) + 1
        for offset in offsets:
            candidate = tuple(current[axis] + offset[axis] for axis in range(3))
            if not all(0 <= candidate[axis] < shape[axis] for axis in range(3)):
                continue
            if depth[candidate] >= 0:
                continue
            depth[candidate] = candidate_depth
            queue.append(candidate)
    return depth.reshape(-1)


def _nearest_outside_euclidean(indices: np.ndarray, inside: np.ndarray) -> np.ndarray:
    result = np.zeros(indices.shape[0], dtype=np.float32)
    outside_indices = indices[~inside].astype(np.float32)
    inside_rows = np.flatnonzero(inside)
    if outside_indices.size == 0 or inside_rows.size == 0:
        return result
    for start in range(0, inside_rows.size, 64):
        rows = inside_rows[start : start + 64]
        delta = indices[rows, None, :].astype(np.float32) - outside_indices[None, :, :]
        result[rows] = np.sqrt(np.min(np.sum(delta * delta, axis=2), axis=1))
    return result


def _grid_mapping(grid, vec3d) -> tuple[np.ndarray, np.ndarray]:
    mapped = []
    for coordinate in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        value = grid.applyMap(vec3d(*coordinate))
        mapped.append(np.asarray([_component(value, axis) for axis in range(3)], dtype=np.float64))
    origin = mapped[0]
    basis = np.vstack([mapped[index] - origin for index in range(1, 4)])
    return origin, basis


class SpatialNeighborhoodCollector:
    """Write one compact NPZ per channel and sample without retaining frames."""

    def __init__(
        self,
        output_root: Path,
        condition: str,
        mesh_points,
        face_counts,
        face_indices,
        local_to_world,
        flow_public_members,
        forced_gc: bool = True,
    ) -> None:
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.condition = str(condition)
        self.geometry = build_mesh_geometry(mesh_points, face_counts, face_indices)
        self.local_to_world = np.asarray(local_to_world, dtype=np.float64).reshape((4, 4))
        self.world_to_local = np.linalg.inv(self.local_to_world)
        self.flow_public_members = sorted(str(value) for value in flow_public_members)
        # Historical Phase 6EE callers retain their original explicit-GC
        # behavior.  New lifetime qualifications can disable it so collection
        # cannot make an otherwise unqualified release look successful.
        self.forced_gc = bool(forced_gc)
        terms = ("collision", "mask", "occup")
        self.collision_mask_candidates = [
            name for name in self.flow_public_members if any(term in name.lower() for term in terms)
        ]
        self.files = []
        self.cache = {}
        self.process = psutil.Process() if psutil is not None else None
        self.rss_baseline = self._rss()
        self.peak_rss = self.rss_baseline

    def _rss(self) -> int | None:
        if self.process is None:
            return None
        info = self.process.memory_info()
        value = int(getattr(info, "peak_wset", info.rss))
        self.peak_rss = max(getattr(self, "peak_rss", 0) or 0, value)
        return int(info.rss)

    def _geometry_for_grid(self, grid, vec3d) -> dict:
        origin, basis = _grid_mapping(grid, vec3d)
        voxel = np.linalg.norm(basis, axis=1)
        key = tuple(np.round(np.concatenate((origin, basis.reshape(-1))), 12))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        mesh_world = np.column_stack(
            (self.geometry["vertices"], np.ones(len(self.geometry["vertices"])))
        ) @ self.local_to_world
        mesh_world = mesh_world[:, :3]
        expansion = HALO_CELLS * float(np.max(voxel))
        minimum = mesh_world.min(axis=0) - expansion
        maximum = mesh_world.max(axis=0) + expansion
        world_corners = np.asarray(
            [[x, y, z] for x in (minimum[0], maximum[0]) for y in (minimum[1], maximum[1]) for z in (minimum[2], maximum[2])],
            dtype=np.float64,
        )
        inverse_basis = np.linalg.inv(basis)
        corner_indices = (world_corners - origin) @ inverse_basis
        index_min = np.floor(corner_indices.min(axis=0)).astype(np.int32) - 1
        index_max = np.ceil(corner_indices.max(axis=0)).astype(np.int32) + 1
        ranges = [np.arange(index_min[axis], index_max[axis] + 1, dtype=np.int32) for axis in range(3)]
        ii, jj, kk = np.meshgrid(*ranges, indexing="ij")
        indices = np.column_stack((ii.reshape(-1), jj.reshape(-1), kk.reshape(-1)))
        shape = tuple(len(values) for values in ranges)
        world = origin + indices @ basis
        local_h = np.column_stack((world, np.ones(world.shape[0]))) @ self.world_to_local
        local = local_h[:, :3]
        signed, inside, face_type = mesh_signed_distance(local, self.geometry)
        analytic_signed = analytic_cylinder_signed_distance(local, self.geometry)
        analytic_inside = analytic_signed <= 0.0
        cell = float(np.mean(voxel))
        keep = inside | (signed <= HALO_CELLS * cell)
        depth_six = _six_neighbor_depth(inside, shape)
        nearest_outside = _nearest_outside_euclidean(indices, inside)
        axis = int(self.geometry["axis"])
        radial_axes = [value for value in range(3) if value != axis]
        center = self.geometry["centroid"]
        radial = np.linalg.norm(local[:, radial_axes] - center[radial_axes], axis=1)
        axis_reference_signed, axis_reference_inside, _ = mesh_signed_distance(world, self.geometry)
        cached = {
            "origin": origin,
            "basis": basis,
            "voxel": voxel,
            "cell": cell,
            "indices": indices,
            "world": world,
            "local": local,
            "signed": signed,
            "inside": inside,
            "face_type": face_type,
            "analytic_signed": analytic_signed,
            "analytic_inside": analytic_inside,
            "keep": keep,
            "depth_six": depth_six,
            "nearest_outside": nearest_outside,
            "axis_radial": radial,
            "axis_reference_signed": axis_reference_signed,
            "axis_reference_inside": axis_reference_inside,
            "shape": shape,
            "index_min": index_min,
            "index_max": index_max,
        }
        self.cache[key] = cached
        return cached

    def capture(self, grid, channel: str, frame: int, vector: bool, vec3d) -> dict:
        before_rss = self._rss()
        geometry = self._geometry_for_grid(grid, vec3d)
        accessor = grid.getAccessor()
        indices = geometry["indices"]
        if vector:
            values = np.empty((indices.shape[0], 3), dtype=np.float32)
            for row, (i, j, k) in enumerate(indices):
                value = accessor.getValue(int(i), int(j), int(k))
                values[row] = [_component(value, axis) for axis in range(3)]
            magnitude = np.linalg.norm(values, axis=1).astype(np.float32)
        else:
            values = np.empty(indices.shape[0], dtype=np.float32)
            for row, (i, j, k) in enumerate(indices):
                values[row] = float(accessor.getValue(int(i), int(j), int(k)))
            magnitude = np.abs(values).astype(np.float32)
        keep = geometry["keep"]
        selected = np.flatnonzero(keep)
        path = self.output_root / f"{self.condition}_f{int(frame):04d}_{channel}.npz"
        payload = {
            "schema": np.asarray(["campfire.phase6ee.collider-neighborhood.v1"]),
            "condition": np.asarray([self.condition]),
            "channel": np.asarray([channel]),
            "frame": np.asarray([int(frame)], dtype=np.int32),
            "voxel_size_xyz": geometry["voxel"].astype(np.float64),
            "index_ijk": indices[selected].astype(np.int32),
            "world_xyz": geometry["world"][selected].astype(np.float64),
            "local_xyz": geometry["local"][selected].astype(np.float64),
            "magnitude": magnitude[selected],
            "mesh_inside": geometry["inside"][selected],
            "mesh_signed_distance_m": geometry["signed"][selected].astype(np.float32),
            "mesh_distance_voxels": (geometry["signed"][selected] / geometry["cell"]).astype(np.float32),
            "nearest_face_class": geometry["face_type"][selected],
            "analytic_inside": geometry["analytic_inside"][selected],
            "analytic_signed_distance_m": geometry["analytic_signed"][selected].astype(np.float32),
            "analytic_mesh_classification_differs": (geometry["analytic_inside"][selected] != geometry["inside"][selected]),
            "outside_cell_distance_euclidean_voxels": geometry["nearest_outside"][selected],
            "outside_cell_distance_6_steps": geometry["depth_six"][selected],
            "axis_radial_distance_m": geometry["axis_radial"][selected].astype(np.float32),
            "axis_reference_mesh_inside": geometry["axis_reference_inside"][selected],
            "axis_reference_mesh_signed_distance_m": geometry["axis_reference_signed"][selected].astype(np.float32),
            "flow_collision_occupancy_mask_available": np.asarray([False]),
        }
        if vector:
            payload["velocity_xyz"] = values[selected]
        else:
            payload["scalar_value"] = values[selected]
        np.savez_compressed(path, **payload)
        after_rss = self._rss()
        record = {
            "condition": self.condition,
            "frame": int(frame),
            "channel": channel,
            "path": str(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "voxel_size": geometry["voxel"].tolist(),
            "stored_cell_count": int(selected.size),
            "inside_cell_count": int(np.count_nonzero(geometry["inside"][selected])),
            "halo_cell_count": int(np.count_nonzero(~geometry["inside"][selected])),
            "classification_disagreement_count": int(
                np.count_nonzero(geometry["analytic_inside"][selected] != geometry["inside"][selected])
            ),
            "maximum": float(np.max(magnitude[selected])) if selected.size else 0.0,
            "rss_before_bytes": before_rss,
            "rss_after_bytes": after_rss,
        }
        self.files.append(record)
        del payload, values, magnitude, selected
        if self.forced_gc:
            gc.collect()
        self._rss()
        return record

    def finalize(self) -> dict:
        manifest = {
            "schema": "campfire.phase6ee.spatial-capture-manifest.v1",
            "condition": self.condition,
            "flow_public_members": self.flow_public_members,
            "flow_collision_occupancy_mask_public_api_available": bool(self.collision_mask_candidates),
            "flow_collision_occupancy_mask_candidates": self.collision_mask_candidates,
            "geometry_labels_are_flow_occupancy": False,
            "geometry_label_source": (
                f"authored {self.geometry['vertices'].shape[0]}-vertex "
                f"{self.geometry['face_counts'].size}-face closed Mesh"
            ),
            "mesh": {
                "vertex_count": int(self.geometry["vertices"].shape[0]),
                "polygon_count": int(self.geometry["face_counts"].size),
                "triangle_count": int(self.geometry["triangles"].shape[0]),
                "axis": int(self.geometry["axis"]),
                "face_type_names": list(FACE_NAMES),
            },
            "halo_cells": HALO_CELLS,
            "files": self.files,
            "file_count": len(self.files),
            "total_bytes": int(sum(item["bytes"] for item in self.files)),
            "rss_baseline_bytes": self.rss_baseline,
            "peak_rss_bytes": self.peak_rss,
            "peak_rss_delta_bytes": (
                None
                if self.rss_baseline is None or self.peak_rss is None
                else int(self.peak_rss - self.rss_baseline)
            ),
            "forced_gc": self.forced_gc,
        }
        path = self.output_root / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["manifest_path"] = str(path)
        manifest["manifest_sha256"] = _sha256(path)
        return manifest
