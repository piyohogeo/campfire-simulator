"""Apply the frozen Phase 6EP offset selection rule without Flow runtime input."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from phase6ep_point_collision_geometry import SCENARIOS, plan_payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    support = contract["fixed_environment"]["conservative_support_radius_m"]
    minimum_supply = contract["thresholds"]["minimum_supply_efficiency"]
    rows = []
    for cells, meters in zip(contract["offset_sweep"]["values"], contract["offset_sweep"]["meters"]):
        scenarios = {}
        passed = True
        for scenario in SCENARIOS:
            result = plan_payload(scenario, meters, support, True)
            item = {key: result[key] for key in (
                "original_point_count", "active_point_count", "disabled_point_count",
                "supply_efficiency", "minimum_support_clearance_m",
                "minimum_active_support_clearance_m", "support_intersection_count",
                "active_support_intersection_count", "self_inside_count", "other_inside_count",
            )}
            item["passed"] = (
                item["supply_efficiency"] >= minimum_supply
                and item["active_support_intersection_count"] == 0
                and item["minimum_active_support_clearance_m"] is not None
                and item["minimum_active_support_clearance_m"] >= -1.0e-9
            )
            passed &= item["passed"]
            scenarios[scenario] = item
        rows.append({"offset_velocity_cells": cells, "offset_m": meters, "scenarios": scenarios, "passed": passed})
    candidates = [row for row in rows if row["passed"]]
    selected = candidates[0] if candidates else None
    report = {
        "schema": "campfire.phase6ep.point-offset-selection.v1",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "selection_rule": contract["offset_sweep"]["selection"],
        "minimum_supply_efficiency": minimum_supply,
        "rows": rows,
        "selected_offset_velocity_cells": None if selected is None else selected["offset_velocity_cells"],
        "selected_offset_m": None if selected is None else selected["offset_m"],
        "status": "ok" if selected is not None else "no_candidate",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "selected_offset_m": report["selected_offset_m"]}))
    return 0 if selected is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
