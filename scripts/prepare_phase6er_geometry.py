"""Freeze Phase 6ER corrected geometry and Point-classification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from phase6ep_point_collision_geometry import SCENARIOS
from phase6er_point_collision_geometry import corrected_plan_payload, write_audit


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    audit_path = args.output.parent / "four_log_geometry_audit.json"
    audit = write_audit(audit_path, SCENARIOS["production_four"])
    arrays: dict[str, np.ndarray] = {}
    rows = []
    for policy in ("strict_all", "allow_self_support", "allow_self_center"):
        for offset in contract["offline_offset_sweep_m"]:
            plan = corrected_plan_payload("production_four", float(offset), 0.05, True, policy)
            key = f"{policy}_{offset:+.4f}".replace("+", "p").replace("-", "m").replace(".", "p")
            records = plan["records"]
            arrays[f"{key}__position"] = plan["positions"]
            arrays[f"{key}__active"] = plan["active"]
            arrays[f"{key}__self_signed_distance_m"] = np.asarray([r["self_signed_distance_m"] for r in records], np.float32)
            arrays[f"{key}__other_signed_distance_m"] = np.asarray([r["other_min_signed_distance_m"] for r in records], np.float32)
            arrays[f"{key}__self_center_inside"] = np.asarray([r["self_center_inside"] for r in records], bool)
            arrays[f"{key}__other_center_inside"] = np.asarray([r["other_center_inside"] for r in records], bool)
            arrays[f"{key}__self_support_intersects"] = np.asarray([r["self_support_intersects"] for r in records], bool)
            arrays[f"{key}__other_support_intersects"] = np.asarray([r["other_support_intersects"] for r in records], bool)
            arrays[f"{key}__enabled_reason"] = np.asarray([r["enabled_reason"] for r in records], "U32")
            rows.append({
                "policy": policy, "offset_m": float(offset),
                "point_count": plan["original_point_count"],
                "active_point_count": plan["active_point_count"],
                "point_retention": plan["supply_efficiency"],
                "weighted_supply": plan["weighted_supply"],
                "self_center_inside_count": plan["self_center_inside_count"],
                "other_center_inside_count": plan["other_center_inside_count"],
                "raw_surface_inside_other_count": plan["other_inside_count"],
                "self_support_intersection_count": plan["self_support_intersection_count"],
                "other_support_intersection_count": plan["other_support_intersection_count"],
                "active_other_support_intersection_count": plan["active_other_support_intersection_count"],
                "disable_reason_counts": plan["disable_reason_counts"],
            })
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.archive, **arrays)
    failures = []
    gates = contract["geometry_gates"]
    if not audit["qualified_for_scalar_calibration"]:
        failures.append("corrected_geometry_audit")
    for policy, offset in contract["selected_offsets_m"].items():
        if policy == "collision_off":
            continue
        row = next(item for item in rows if item["policy"] == policy and item["offset_m"] == float(offset))
        if row["raw_surface_inside_other_count"] != gates["raw_surface_point_centers_inside_other_log"]:
            failures.append(f"raw_surface_other_center:{policy}")
        if row["active_other_support_intersection_count"] != gates["active_other_support_intersections"]:
            failures.append(f"active_other_support:{policy}")
        if row["weighted_supply"]["fuel"]["retention"] < gates["minimum_selected_weighted_supply_retention"]:
            failures.append(f"retention:{policy}")
    report = {
        "schema": "campfire.phase6er.corrected-four-log-offline.v1",
        "phase": "phase6er",
        "contract_sha256": _hash(args.contract),
        "geometry_audit_sha256": _hash(audit_path),
        "classification_archive": {"path": str(args.archive), "sha256": _hash(args.archive), "bytes": args.archive.stat().st_size},
        "rows": rows,
        "failed_gates": failures,
        "qualified_for_scalar_calibration": not failures,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Phase 6ER offline rows={len(rows)} qualified={not failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
