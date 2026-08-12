import hashlib
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "phase6ep_point_collision_contract.json"
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"


class Phase6EpPublishedContract(unittest.TestCase):
    def test_contract_hash_and_controls(self):
        digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
        recorded = (ROOT / "scripts" / "phase6ep_point_collision_contract.sha256").read_text(encoding="ascii").split()[0]
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(digest, recorded)
        self.assertEqual(payload["schema"], "campfire.phase6ep.point-collision-coexistence-contract.v1")
        self.assertFalse(payload["production_connected"])
        self.assertFalse(payload["default_enabled"])
        self.assertEqual(payload["formal_runs_per_scenario"], 3)
        controls = payload["formal_condition_controls"]
        self.assertEqual(controls["lower_upper_collision_off_filter_off"]["offset_m"], 0.0)
        self.assertEqual(controls["lower_upper_collision_on_filter_off"]["offset_m"], 0.0)

    def test_safe_stop_is_not_promoted(self):
        report = json.loads((ASSETS / "point_collision_safe_stop.json").read_text(encoding="utf-8"))
        self.assertFalse(report["overall_qualified"])
        self.assertTrue(report["formal_numeric_qualified"])
        self.assertEqual(report["formal_processes_passed"], 18)
        self.assertFalse(report["media_gate"]["qualified"])
        failed = report["media_gate"]["collision_on_unfiltered"]
        self.assertEqual(failed["last_lifecycle_marker"], "shutdown_complete")
        self.assertEqual(failed["lifecycle_status"], "unknown_shutdown_failure")
        self.assertTrue(failed["cdb_timed_out"])
        self.assertFalse(failed["cdb_detach_observed"])
        self.assertFalse(failed["known_ngx_signature_matched"])
        self.assertFalse(report["media_gate"]["collision_on_candidate"]["started"])
        self.assertEqual(report["media_gate"]["videos_encoded_or_published"], 0)
        self.assertFalse(report["safe_stop"]["automatic_retry"])
        self.assertEqual(report["safe_stop"]["cleanup"]["remaining_count"], 0)
        self.assertFalse(report["safe_stop"]["production_changed"])

    def test_numeric_summary_preserves_gates(self):
        report = json.loads((ASSETS / "point_collision_safe_stop.json").read_text(encoding="utf-8"))
        summaries = {item["condition"]: item for item in report["numeric_report"]["formal_summary"]}
        for condition in ("single_candidate", "near_two_candidate", "lower_upper_candidate", "production_four_candidate"):
            self.assertEqual(summaries[condition]["run_count"], 3)
            self.assertEqual(summaries[condition]["worst_deep_maximum_m_s"], 0.0)
            self.assertEqual(summaries[condition]["worst_center_maximum_m_s"], 0.0)
        self.assertGreaterEqual(summaries["production_four_candidate"]["minimum_supply_efficiency"], 0.75)
        self.assertGreaterEqual(summaries["lower_upper_collision_off_filter_off"]["worst_deep_maximum_m_s"], 0.1)
        self.assertTrue(all(item["passed"] and item["deep_ratio"] <= 0.01 for item in report["numeric_report"]["pair_results"]))

    def test_published_assets_and_devlog_are_valid(self):
        for name in ("point_collision_qualification.svg", "point_collision_safe_stop.svg"):
            ET.parse(ASSETS / name)
        html = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="phase-6ep"'), 1)
        self.assertIn("point_collision_safe_stop.json", html)
        self.assertIn("point_collision_qualification.svg", html)
        self.assertNotIn("phase6ep_point_collision_comparison.mp4", html)
        self.assertNotIn("\ufffd", html)


if __name__ == "__main__":
    unittest.main()
