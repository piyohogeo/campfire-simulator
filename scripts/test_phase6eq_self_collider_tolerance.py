from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from phase6ep_point_collision_geometry import plan_payload


class Phase6EqSelfColliderTolerance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6eq_self_collider_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))

    def test_contract_hash_and_population_are_frozen(self):
        expected = (SCRIPTS / "phase6eq_self_collider_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper(), expected)
        self.assertEqual(self.contract["formal_process_count"], 24)
        self.assertEqual(self.contract["runtime_offset_sweep_process_count"], 18)
        self.assertEqual(self.contract["sample_frames"], [30, 60, 90, 120, 150, 180, 200])

    def test_policies_distinguish_self_support_from_self_center(self):
        support = plan_payload("lower_upper", 0.0125, 0.05, True, "allow_self_support")
        center = plan_payload("lower_upper", 0.0125, 0.05, True, "allow_self_center")
        self.assertEqual(support["active_point_count"], 288)
        self.assertEqual(center["active_point_count"], 360)
        self.assertEqual(support["disable_reason_counts"]["self_center_inside"], 72)
        self.assertEqual(center["active_other_support_intersection_count"], 0)

    def test_selected_offsets_keep_other_support_intersections_zero(self):
        for scenario in self.contract["formal_scenarios"]:
            for policy in ("strict_all", "allow_self_support", "allow_self_center"):
                offset = self.contract["policies"][policy]["selected_offset_m"]
                plan = plan_payload(scenario, offset, 0.05, True, policy)
                self.assertEqual(plan["active_other_support_intersection_count"], 0)
                self.assertGreaterEqual(plan["weighted_supply"]["fuel"]["retention"], 0.5)

    def test_point_order_and_length_are_identical_across_policies(self):
        plans = [
            plan_payload("production_four", self.contract["policies"][policy]["selected_offset_m"], 0.05, True, policy)
            for policy in ("strict_all", "allow_self_support", "allow_self_center")
        ]
        identities = [np.asarray([row["surface_identity"] for row in plan["records"]]) for plan in plans]
        owners = [np.asarray([row["owner_index"] for row in plan["records"]]) for plan in plans]
        self.assertTrue(all(plan["original_point_count"] == 1440 for plan in plans))
        self.assertTrue(all(np.array_equal(identities[0], item) for item in identities[1:]))
        self.assertTrue(all(np.array_equal(owners[0], item) for item in owners[1:]))

    def test_weighted_supply_matches_enabled_channel_values(self):
        plan = plan_payload("production_four", -0.0125, 0.05, True, "allow_self_center")
        for channel in ("fuel", "temperature", "smoke"):
            enabled = sum(row[f"enabled_{channel}"] for row in plan["records"])
            self.assertAlmostEqual(enabled, plan["weighted_supply"][channel]["enabled"], places=9)
            self.assertAlmostEqual(
                plan["weighted_supply"][channel]["retention"], plan["supply_efficiency"], places=9
            )

    def test_matrix_reuses_existing_guard_and_shutdown_policy(self):
        runner = (SCRIPTS / "run_phase6eq_self_collider_matrix.ps1").read_text(encoding="utf-8")
        case = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        self.assertIn("phase6eg_resource_guard.py", runner)
        self.assertIn("run_phase6ep_point_collision_case.ps1", runner)
        self.assertIn("Wait-CampfireKitProcessWithShutdownPolicy", case)
        self.assertIn("normal_exit", runner)
        self.assertNotIn("automatic_retry", runner.lower())

    def test_production_scope_and_phase6ep_artifacts_are_read_only(self):
        runner = (SCRIPTS / "run_phase6eq_self_collider_matrix.ps1").read_text(encoding="utf-8")
        self.assertIn("productionHashBefore", runner)
        self.assertIn("productionHashAfter", runner)
        self.assertNotIn("phase6ep-point-collision-5", runner)
        self.assertNotIn("Remove-Item", runner)
        self.assertFalse(self.contract["production_connected"])
        self.assertFalse(self.contract["default_enabled"])

    def test_visual_population_is_after_numeric_aggregate(self):
        runner = (SCRIPTS / "run_phase6eq_self_collider_matrix.ps1").read_text(encoding="utf-8")
        self.assertLess(runner.index("formal aggregate failed"), runner.index("Visual conditions are outside"))
        self.assertEqual(
            self.contract["visual_conditions"],
            ["collision_off", "strict_all", "allow_self_support", "allow_self_center"],
        )

    def test_published_result_is_fail_closed_and_keeps_phase6ep_unchanged(self):
        assets = ROOT / "docs" / "devlog" / "assets" / "phase6"
        report = json.loads((assets / "point_self_collider_safe_stop.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "safe_stop")
        self.assertFalse(report["overall_qualified"])
        self.assertFalse(report["formal_population_accepted"])
        self.assertEqual(report["formal_processes_completed_as_partial_evidence"], 2)
        self.assertEqual(report["runtime_sweep_processes_completed"], 18)
        self.assertEqual(
            report["safe_stop"]["failed_condition"]["failed_gates"],
            ["other_deep_temperature", "other_deep_smoke"],
        )
        self.assertFalse(report["safe_stop"]["automatic_retry"])
        self.assertFalse(report["safe_stop"]["later_condition_started"])
        self.assertFalse(report["safe_stop"]["visual_population_started"])
        self.assertFalse(report["production_changed"])
        phase6ep = assets / "point_collision_safe_stop.json"
        self.assertEqual(
            report["phase6ep_report_sha256"], hashlib.sha256(phase6ep.read_bytes()).hexdigest().upper()
        )

    def test_devlog_records_no_video_and_no_latest_demo_change(self):
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        start = devlog.index('id="phase-6eq"')
        end = devlog.index('id="phase-6ep"')
        entry = devlog[start:end]
        self.assertIn("point_self_collider_safe_stop.svg", entry)
        self.assertIn("point_self_collider_safe_stop.json", entry)
        self.assertNotIn("video-trigger", entry)
        self.assertIn("latest demo pointerを維持", entry)
        latest = json.loads((ROOT / "docs" / "devlog" / "assets" / "latest_demo.json").read_text(encoding="utf-8"))
        self.assertNotEqual(latest["phase"], "Phase 6EQ")


if __name__ == "__main__":
    unittest.main()
