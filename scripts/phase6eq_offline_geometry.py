"""Freeze and serialize Phase 6EQ self/other Collider Point classification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from phase6ep_point_collision_geometry import plan_payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    rows = []
    arrays: dict[str, np.ndarray] = {}
    failures = []
    for scenario in contract["formal_scenarios"]:
        for policy in ("strict_all", "allow_self_support", "allow_self_center"):
            for offset in contract["offline_offset_sweep_m"]:
                plan = plan_payload(scenario, float(offset), 0.05, True, policy)
                key = f"{scenario}__{policy}__{float(offset):+.4f}".replace("+", "p").replace("-", "m").replace(".", "p")
                records = plan["records"]
                arrays[f"{key}__owner_index"] = np.asarray([item["owner_index"] for item in records], dtype=np.int16)
                arrays[f"{key}__surface_identity"] = np.asarray([item["surface_identity"] for item in records], dtype=np.int16)
                arrays[f"{key}__published_position"] = np.asarray([item["published_position"] for item in records], dtype=np.float32)
                arrays[f"{key}__self_signed_distance_m"] = np.asarray([item["self_signed_distance_m"] for item in records], dtype=np.float32)
                arrays[f"{key}__other_min_signed_distance_m"] = np.asarray([item["other_min_signed_distance_m"] for item in records], dtype=np.float32)
                arrays[f"{key}__self_center_inside"] = np.asarray([item["self_center_inside"] for item in records], dtype=bool)
                arrays[f"{key}__other_center_inside"] = np.asarray([item["other_center_inside"] for item in records], dtype=bool)
                arrays[f"{key}__self_support_intersects"] = np.asarray([item["self_support_intersects"] for item in records], dtype=bool)
                arrays[f"{key}__other_support_intersects"] = np.asarray([item["other_support_intersects"] for item in records], dtype=bool)
                arrays[f"{key}__enabled"] = plan["active"]
                arrays[f"{key}__enabled_reason"] = np.asarray([item["enabled_reason"] for item in records], dtype="U32")
                arrays[f"{key}__original_supply"] = np.asarray(
                    [[item["original_fuel"], item["original_temperature"], item["original_smoke"]] for item in records], dtype=np.float32
                )
                arrays[f"{key}__enabled_supply"] = np.asarray(
                    [[item["enabled_fuel"], item["enabled_temperature"], item["enabled_smoke"]] for item in records], dtype=np.float32
                )
                rows.append({
                    "key": key,
                    "scenario": scenario,
                    "policy": policy,
                    "offset_m": float(offset),
                    "point_count": plan["original_point_count"],
                    "active_point_count": plan["active_point_count"],
                    "point_retention": plan["supply_efficiency"],
                    "weighted_supply": plan["weighted_supply"],
                    "self_center_inside_count": plan["self_center_inside_count"],
                    "other_center_inside_count": plan["other_center_inside_count"],
                    "self_support_intersection_count": plan["self_support_intersection_count"],
                    "other_support_intersection_count": plan["other_support_intersection_count"],
                    "active_other_support_intersection_count": plan["active_other_support_intersection_count"],
                    "disable_reason_counts": plan["disable_reason_counts"],
                })
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.archive, **arrays)
    for policy, definition in contract["policies"].items():
        if policy == "collision_off":
            continue
        offset = float(definition["selected_offset_m"])
        selected = [row for row in rows if row["policy"] == policy and row["offset_m"] == offset]
        if len(selected) != len(contract["formal_scenarios"]):
            failures.append(f"selected_geometry_missing:{policy}")
        for row in selected:
            if row["active_other_support_intersection_count"] != 0:
                failures.append(f"selected_other_intersection:{row['scenario']}:{policy}")
            if row["weighted_supply"]["fuel"]["retention"] < contract["thresholds"]["minimum_weighted_supply_retention"]:
                failures.append(f"selected_supply:{row['scenario']}:{policy}")
    report = {
        "schema": "campfire.phase6eq.self-collider-offline-geometry.v1",
        "phase": "phase6eq",
        "contract_sha256": _sha256(args.contract),
        "archive": {"path": str(args.archive), "sha256": _sha256(args.archive), "bytes": args.archive.stat().st_size},
        "rows": rows,
        "failed_gates": failures,
        "qualified_for_runtime": not failures,
        "notes": [
            "Signed distances use the authored 26-vertex closed Mesh, not a Flow occupancy mask.",
            "Other-Collider support intersection remains forbidden in every policy.",
            "The Phase 6EP 18-process population is not loaded or reclassified by this report."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Phase 6EQ offline rows={len(rows)} qualified={not failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
