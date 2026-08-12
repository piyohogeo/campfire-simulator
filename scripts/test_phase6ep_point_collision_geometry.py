import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase6ep_point_collision_geometry import SCENARIOS, cylinder_topology, plan_payload


class Phase6EpGeometry(unittest.TestCase):
    def test_frozen_controls_disable_both_filter_and_offset(self):
        contract_path = ROOT / "scripts" / "phase6ep_point_collision_contract.json"
        digest = hashlib.sha256(contract_path.read_bytes()).hexdigest().upper()
        recorded = (ROOT / "scripts" / "phase6ep_point_collision_contract.sha256").read_text(encoding="ascii").split()[0]
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        controls = contract["formal_condition_controls"]
        for name in ("lower_upper_collision_off_filter_off", "lower_upper_collision_on_filter_off"):
            self.assertFalse(controls[name]["filtering"])
            self.assertEqual(controls[name]["offset_m"], 0.0)
        self.assertTrue(controls["candidate_conditions"]["filtering"])
        self.assertEqual(controls["candidate_conditions"]["offset_m"], 0.075)
        self.assertEqual(digest, recorded)

    def test_matrix_runner_uses_the_frozen_control_offsets(self):
        runner = (ROOT / "scripts" / "run_phase6ep_point_collision_coexistence.ps1").read_text(encoding="utf-8")
        self.assertIn('lower_upper_collision_off_filter_off=@{scenario="lower_upper";offset=0.0;filtering="false";collision="false"', runner)
        self.assertIn('lower_upper_collision_on_filter_off=@{scenario="lower_upper";offset=0.0;filtering="false";collision="true"', runner)
        self.assertIn('-Offset $definition.offset', runner)
        self.assertIn('@{name="collision_on_unfiltered";offset=0.0;filtering="false";collision="true"}', runner)

    def test_scenarios_and_topology(self):
        self.assertEqual(set(SCENARIOS), {"single", "near_two", "lower_upper", "production_four"})
        for poses in SCENARIOS.values():
            for pose in poses:
                points, counts, indices = cylinder_topology(pose)
                self.assertEqual(points.shape, (26, 3))
                self.assertEqual(counts.size, 36)
                self.assertEqual(indices.size, 120)

    def test_payload_order_is_immutable_across_offsets(self):
        a = plan_payload("production_four", 0.0, 0.05, True)
        b = plan_payload("production_four", 0.075, 0.05, True)
        self.assertEqual(a["original_point_count"], 1440)
        self.assertEqual(b["original_point_count"], 1440)
        self.assertEqual(
            [(x["owner"], x["surface_identity"]) for x in a["records"]],
            [(x["owner"], x["surface_identity"]) for x in b["records"]],
        )

    def test_filter_disables_unsafe_support_without_deleting_points(self):
        result = plan_payload("single", 0.0, 0.05, True)
        self.assertEqual(result["original_point_count"], 360)
        self.assertEqual(result["active_point_count"] + result["disabled_point_count"], 360)
        self.assertGreater(result["support_intersection_count"], 0)


if __name__ == "__main__":
    unittest.main()
