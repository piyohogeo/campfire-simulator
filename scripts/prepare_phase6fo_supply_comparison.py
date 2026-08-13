"""Freeze Phase 6FO S93/S100 point and geometry evidence before Kit runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from phase6er_point_collision_geometry import (
    CORRECTED_PRODUCTION_FOUR,
    SUPPORT_RADIUS_ASSUMPTION_M,
    audit_pose_set,
    corrected_plan_payload,
)


CONDITIONS = (
    ("S93_support_clear", "allow_self_center"),
    ("S100_center_clear", "allow_other_support"),
)
OFFSET_M = -0.0125


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def prepare(output: Path, records_path: Path) -> dict:
    output = output.resolve()
    records_path = records_path.resolve()
    if output.exists() or records_path.exists():
        raise FileExistsError("Phase 6FO offline artifacts are immutable and refuse reuse")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with records_path.open("x", encoding="utf-8", newline="\n") as stream:
        for condition, policy in CONDITIONS:
            plan = corrected_plan_payload(
                "production_four", OFFSET_M, SUPPORT_RADIUS_ASSUMPTION_M, True, policy
            )
            point_digest = hashlib.sha256()
            per_owner = {}
            for payload_index, record in enumerate(plan["records"]):
                owner_index = int(record["owner_index"])
                owner_log = plan["poses"][owner_index]["name"]
                enabled = bool(plan["active"][payload_index])
                per_owner.setdefault(owner_log, {"total": 0, "active": 0})
                per_owner[owner_log]["total"] += 1
                per_owner[owner_log]["active"] += int(enabled)
                row = {
                    "schema": "campfire.phase6fo.point-decision.v1",
                    "condition": condition,
                    "policy": policy,
                    "payload_index": payload_index,
                    "world_xyz_m": [float(value) for value in plan["positions"][payload_index]],
                    "owner_index": owner_index,
                    "owner_log": owner_log,
                    "enabled": enabled,
                    "disabled_reason": None if enabled else record["enabled_reason"],
                    "self_signed_distance_m": float(record["self_signed_distance_m"]),
                    "other_min_signed_distance_m": float(record["other_min_signed_distance_m"]),
                    "other_center_inside": bool(record["other_center_inside"]),
                    "other_support_sphere_intersects": bool(record["other_support_intersects"]),
                    "support_radius_assumption_m": SUPPORT_RADIUS_ASSUMPTION_M,
                    "fuel": float(record["enabled_fuel"]),
                    "temperature": float(record["enabled_temperature"]),
                    "smoke": float(record["enabled_smoke"]),
                    "original_fuel": float(record["original_fuel"]),
                    "original_temperature": float(record["original_temperature"]),
                    "original_smoke": float(record["original_smoke"]),
                }
                encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                stream.write(encoded + "\n")
                point_digest.update(encoded.encode("utf-8") + b"\n")
            rows.append({
                "condition": condition,
                "policy": policy,
                "offset_m": OFFSET_M,
                "total_points": int(plan["original_point_count"]),
                "active_points": int(plan["active_point_count"]),
                "active_fraction": float(plan["active_point_count"] / plan["original_point_count"]),
                "per_owner": per_owner,
                "other_center_inside_count": int(plan["other_center_inside_count"]),
                "other_support_sphere_intersection_count": int(plan["other_support_intersection_count"]),
                "active_other_support_sphere_intersection_count": int(plan["active_other_support_intersection_count"]),
                "weighted_supply": plan["weighted_supply"],
                "point_set_sha256": point_digest.hexdigest().upper(),
            })
    geometry = audit_pose_set(CORRECTED_PRODUCTION_FOUR)
    blueprint = {
        "geometry_variant": "phase6er_corrected",
        "poses": [pose.__dict__ for pose in CORRECTED_PRODUCTION_FOUR],
        "collision_proxy": {"vertices": 26, "faces": 36, "indices": 120},
        "flow": {"density_cell_size_m": 0.025, "velocity_voxel_size_m": 0.05},
        "point_offset_m": OFFSET_M,
        "support_radius_assumption_m": SUPPORT_RADIUS_ASSUMPTION_M,
        "point_source": {"fuel": 0.8, "temperature": 2.0, "smoke": 0.08, "revision": 1},
        "timeline_fps": 60,
    }
    report = {
        "schema": "campfire.phase6fo.offline-comparison.v1",
        "phase": "phase6fo",
        "declared_before_runtime": True,
        "production_connected": False,
        "support_radius_public_api_available": False,
        "support_radius_status": "engineering assumption equal to one velocity voxel",
        "geometry": geometry,
        "stage_blueprint": blueprint,
        "stage_blueprint_sha256": _canonical_hash(blueprint),
        "conditions": rows,
        "records": {
            "path": str(records_path),
            "format": "bounded JSONL; one immutable Point decision per line",
            "count": 2880,
            "sha256": _sha(records_path),
        },
        "gates": {
            "geometry_has_no_volume_overlap": geometry["sampled_volume_overlap_pair_count"] == 0,
            "all_point_centers_outside_other_logs": all(row["other_center_inside_count"] == 0 for row in rows),
            "S93_is_1344": rows[0]["active_points"] == 1344,
            "S93_active_other_support_is_zero": rows[0]["active_other_support_sphere_intersection_count"] == 0,
            "S100_is_1440": rows[1]["active_points"] == 1440,
            "S100_active_other_support_is_96": rows[1]["active_other_support_sphere_intersection_count"] == 96,
        },
    }
    report["all_pass"] = all(report["gates"].values())
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--records", required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.output, args.records)
    if not report["all_pass"]:
        raise SystemExit("Phase 6FO offline comparison gate failed")
    print("Phase 6FO offline comparison frozen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
