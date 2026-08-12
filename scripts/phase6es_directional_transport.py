"""Direction-aware scalar transport proxy for Phase 6ES.

The metric uses public NanoVDB velocity/temperature/smoke samples.  It is a
transport proxy, not a claim about Flow's internal conservation or units.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

try:
    from phase6ep_point_collision_geometry import LENGTH_M, RADIUS_M
except ModuleNotFoundError:  # package import used by unittest
    from scripts.phase6ep_point_collision_geometry import LENGTH_M, RADIUS_M


FACE_DEFINITIONS = {
    "inlet_bottom": (2, -1.0),
    "opposite_top": (2, 1.0),
    "side_left": (1, -1.0),
    "side_right": (1, 1.0),
    "end_left": (0, -1.0),
    "end_right": (0, 1.0),
}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def world_to_log_local(world: np.ndarray, center, yaw_degrees: float) -> np.ndarray:
    angle = math.radians(float(yaw_degrees))
    rotation = np.asarray(((math.cos(angle), -math.sin(angle), 0.0), (math.sin(angle), math.cos(angle), 0.0), (0.0, 0.0, 1.0)))
    return (np.asarray(world, dtype=np.float64) - np.asarray(center, dtype=np.float64)) @ rotation


def _nearest_velocity(scalar_world: np.ndarray, velocity_world: np.ndarray, velocity_xyz: np.ndarray) -> np.ndarray:
    axes = [np.unique(np.round(velocity_world[:, axis], 9)) for axis in range(3)]
    lookup = {tuple(np.round(row, 9)): value for row, value in zip(velocity_world, velocity_xyz)}
    output = np.empty((len(scalar_world), 3), dtype=np.float64)
    for index, point in enumerate(scalar_world):
        key = tuple(float(values[np.argmin(np.abs(values - point[axis]))]) for axis, values in enumerate(axes))
        value = lookup.get(key)
        if value is None:
            distance = np.sum((velocity_world - point) ** 2, axis=1)
            value = velocity_xyz[int(np.argmin(distance))]
        output[index] = value
    return output


def face_transport(local: np.ndarray, velocity: np.ndarray, scalar: np.ndarray, voxel_xyz: np.ndarray, plane_offset_m: float) -> dict:
    half = np.asarray((0.5 * LENGTH_M + plane_offset_m, RADIUS_M + plane_offset_m, RADIUS_M + plane_offset_m))
    results = {}
    for name, (axis, sign) in FACE_DEFINITIONS.items():
        tangential = [value for value in range(3) if value != axis]
        thickness = 0.55 * float(voxel_xyz[axis])
        mask = np.abs(local[:, axis] - sign * half[axis]) <= thickness
        for tangent in tangential:
            mask &= np.abs(local[:, tangent]) <= half[tangent] + 0.5 * float(voxel_xyz[tangent])
        normal_speed = velocity[:, axis] * sign
        area = float(np.prod(voxel_xyz[tangential]))
        outward = np.maximum(normal_speed[mask], 0.0) * scalar[mask] * area
        inward = np.maximum(-normal_speed[mask], 0.0) * scalar[mask] * area
        results[name] = {
            "axis": axis,
            "normal_sign": sign,
            "plane_local_m": float(sign * half[axis]),
            "plane_thickness_m": float(2.0 * thickness),
            "sample_area_m2": area,
            "valid_voxels": int(np.count_nonzero(mask)),
            "normal_velocity_mean": float(np.mean(normal_speed[mask])) if np.any(mask) else 0.0,
            "normal_velocity_p95": float(np.percentile(normal_speed[mask], 95)) if np.any(mask) else 0.0,
            "normal_velocity_maximum": float(np.max(normal_speed[mask])) if np.any(mask) else 0.0,
            "outward_transport_proxy": float(np.sum(outward)),
            "inward_transport_proxy": float(np.sum(inward)),
            "outward_active_voxels": int(np.count_nonzero(outward > 0.0)),
            "inward_active_voxels": int(np.count_nonzero(inward > 0.0)),
        }
    return results


def _load(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as archive:
        return {key: archive[key] for key in archive.files}


def analyze_condition(condition: Path, plane_offset_m: float = 0.05) -> dict:
    raw = json.loads((condition / "raw.json").read_text(encoding="utf-8"))
    poses = raw["point_payload"]["poses"]
    manifests = raw["spatial_manifests"]
    manifest_indices = raw.get("spatial_manifest_collider_indices", list(range(len(manifests))))
    manifests_by_index = dict(zip(manifest_indices, manifests))
    frames = sorted(int(sample["frame"]) for sample in raw["samples"])
    colliders = []
    for collider_index, pose in enumerate(poses):
        manifest = manifests_by_index.get(collider_index)
        if manifest is None:
            colliders.append({"index": collider_index, "pose": pose, "scalar_transport_available": False, "reason": "no spatial collector was configured for this collider", "frames": []})
            continue
        files = {Path(item["path"]).name: Path(item["path"]) for item in manifest["files"]}
        scalar_available = any(name.endswith("_temperature.npz") for name in files)
        if not scalar_available:
            colliders.append({"index": collider_index, "pose": pose, "scalar_transport_available": False, "reason": "bounded Phase 6ES collection keeps velocity for every collider but scalar only for the predeclared representative blocker", "frames": []})
            continue
        per_frame = []
        for frame in frames:
            def find(channel: str) -> Path:
                suffix = f"_f{frame:04d}_{channel}.npz"
                return next(path for name, path in files.items() if name.endswith(suffix))
            velocity = _load(find("velocity"))
            channels = {}
            for channel in ("temperature", "smoke"):
                scalar = _load(find(channel))
                world = scalar["world_xyz"].astype(np.float64)
                local = world_to_log_local(world, pose["center"], pose["yaw_degrees"])
                mapped_velocity = _nearest_velocity(world, velocity["world_xyz"], velocity["velocity_xyz"])
                values = scalar["scalar_value"].astype(np.float64)
                signed = scalar["mesh_signed_distance_m"].astype(np.float64)
                voxel = scalar["voxel_size_xyz"].astype(np.float64)
                deep = signed < -float(np.mean(voxel))
                center = deep & (scalar["axis_radial_distance_m"] <= 0.5 * float(np.mean(voxel)))
                faces = face_transport(local, mapped_velocity, values, voxel, plane_offset_m)
                channels[channel] = {
                    "voxel_size_xyz_m": voxel.tolist(),
                    "deep_sum": float(np.sum(values[deep])),
                    "deep_mean": float(np.mean(values[deep])) if np.any(deep) else 0.0,
                    "deep_p95": float(np.percentile(values[deep], 95)) if np.any(deep) else 0.0,
                    "deep_maximum": float(np.max(values[deep])) if np.any(deep) else 0.0,
                    "center_sum": float(np.sum(values[center])),
                    "faces": faces,
                }
            per_frame.append({"frame": frame, "channels": channels})
        for channel in ("temperature", "smoke"):
            previous = None
            cumulative = {face: {"outward": 0.0, "inward": 0.0} for face in FACE_DEFINITIONS}
            for entry in per_frame:
                if previous is not None:
                    dt = (entry["frame"] - previous["frame"]) / 60.0
                    for face in FACE_DEFINITIONS:
                        before = previous["channels"][channel]["faces"][face]
                        after = entry["channels"][channel]["faces"][face]
                        cumulative[face]["outward"] += 0.5 * dt * (before["outward_transport_proxy"] + after["outward_transport_proxy"])
                        cumulative[face]["inward"] += 0.5 * dt * (before["inward_transport_proxy"] + after["inward_transport_proxy"])
                previous = entry
            for entry in per_frame:
                entry["channels"][channel]["time_integrated_transport_proxy"] = cumulative
        colliders.append({"index": collider_index, "pose": pose, "scalar_transport_available": True, "frames": per_frame})
    report = {
        "schema": "campfire.phase6es.directional-scalar-transport.v1",
        "phase": "phase6es",
        "status": "complete",
        "interpretation": "directional scalar transport proxy; physical scalar units and strict conservation are not claimed",
        "flow_occupancy_mask_available": False,
        "passive_tracer": {"available": False, "public_channels": ["temperature", "fuel", "burn", "smoke", "velocity", "divergence"], "reason": "no independent public passive source-identity channel in the fixed Flow readback"},
        "plane_offset_m": plane_offset_m,
        "condition": str(condition),
        "point_payload": raw["point_payload"],
        "colliders": colliders,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plane-offset-m", type=float, default=0.05)
    args = parser.parse_args()
    report = analyze_condition(args.condition.resolve(), args.plane_offset_m)
    _write(args.output.resolve(), report)
    print(f"Phase 6ES transport written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
