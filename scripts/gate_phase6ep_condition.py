"""Fail-fast numeric gate for one completed Phase 6EP process and optional pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def maxima(directory):
    deep_values, center_values = [], []
    for path in directory.glob("spatial/collider_*/*.npz"):
        with np.load(path) as data:
            magnitude = data["magnitude"]
            depth = data["mesh_distance_voxels"]
            radial = data["axis_radial_distance_m"]
            voxel = float(np.mean(data["voxel_size_xyz"]))
            deep = depth < -1.0
            center = deep & (radial <= 0.5 * voxel)
            deep_values.append(float(magnitude[deep].max(initial=0.0)))
            center_values.append(float(magnitude[center].max(initial=0.0)))
    return max(deep_values, default=0.0), max(center_values, default=0.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=("candidate", "collision_off", "filter_off"))
    parser.add_argument("--pair-positive", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    thresholds = contract["thresholds"]
    raw = json.loads((args.condition / "raw.json").read_text(encoding="utf-8"))
    deep, center = maxima(args.condition)
    checks = {
        "status": raw["status"] == "ok" and raw["lifecycle_marker"] == "shutdown_complete",
        "samples": len(raw["samples"]) == 4,
        "active_blocks": int(raw["active_blocks_final"]) > 0,
        "revision": int(raw["revision"]) == 1,
    }
    if args.kind == "candidate":
        checks.update({
            "supply": raw["point_payload"]["supply_efficiency"] >= thresholds["minimum_supply_efficiency"],
            "support_clear": raw["point_payload"]["active_support_intersection_count"] == 0,
            "deep": deep <= thresholds["collision_on_deep_maximum_m_s"],
            "center": center <= thresholds["collision_on_center_maximum_m_s"],
        })
    elif args.kind == "collision_off":
        checks.update({
            "deep_positive": deep >= thresholds["collision_off_deep_minimum_m_s"],
            "center_positive": center >= thresholds["collision_off_center_minimum_m_s"],
        })
    pair = None
    if args.pair_positive:
        positive_deep, _ = maxima(args.pair_positive)
        ratio = deep / max(positive_deep, 1e-30)
        pair = {"positive_deep": positive_deep, "ratio": ratio, "passed": ratio <= thresholds["on_to_off_deep_maximum_ratio"]}
        checks["pair_ratio"] = pair["passed"]
    report = {"schema": "campfire.phase6ep.incremental-gate.v1", "kind": args.kind, "deep_maximum_m_s": deep, "center_maximum_m_s": center, "checks": checks, "pair": pair, "passed": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "deep": deep, "center": center}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
