from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from phase6ep_point_collision_geometry import SCENARIOS, plan_payload
from phase6er_point_collision_geometry import (
    CORRECTED_PRODUCTION_FOUR,
    audit_pose_set,
    corrected_plan_payload,
)


class Phase6ErGeometryContract(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((SCRIPTS / "phase6er_geometry_contract.json").read_text(encoding="utf-8"))

    def test_legacy_fixture_remains_defective_and_unchanged(self):
        old = audit_pose_set(SCENARIOS["production_four"])
        self.assertEqual(old["other_log_point_centers_inside"], 480)
        upper = next(pair for pair in old["pairs"] if pair["pair"] == ["upper_a", "upper_b"])
        self.assertAlmostEqual(0.50, upper["centerline_segment_overlap_m"])
        self.assertEqual("sampled_volume_overlap", upper["classification"])

    def test_corrected_fixture_has_no_other_center_inside_or_volume_overlap(self):
        corrected = audit_pose_set(CORRECTED_PRODUCTION_FOUR)
        self.assertEqual(0, corrected["other_log_point_centers_inside"])
        self.assertEqual(0, corrected["sampled_volume_overlap_pair_count"])
        self.assertEqual(1440, corrected["point_count"])

    def test_selected_policies_forbid_active_other_support(self):
        for policy, offset in self.contract["selected_offsets_m"].items():
            if policy == "collision_off":
                continue
            plan = corrected_plan_payload("production_four", offset, 0.05, True, policy)
            self.assertEqual(0, plan["active_other_support_intersection_count"])
            self.assertGreaterEqual(plan["weighted_supply"]["fuel"]["retention"], 0.75)

    def test_legacy_planner_still_returns_frozen_phase6eq_counts(self):
        plan = plan_payload("production_four", -0.0125, 0.05, True, "allow_self_center")
        self.assertEqual(932, plan["active_point_count"])

    def test_probe_extension_is_default_preserving(self):
        probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        self.assertIn('or "legacy_phase6ep"', probe)
        self.assertIn('"phase6er_corrected"', probe)
        self.assertIn('GeometryVariant = "legacy_phase6ep"', runner)
        self.assertIn("Wait-CampfireKitProcessWithShutdownPolicy", runner)


if __name__ == "__main__":
    unittest.main()
