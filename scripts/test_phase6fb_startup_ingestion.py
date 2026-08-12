import hashlib
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.phase6fb_startup_contract import classify_startup


THRESHOLDS = {
    "classification_frame": 60, "final_frame": 120, "representative_active_blocks": 128,
    "small_field_minimum_blocks": 20, "small_field_maximum_blocks": 32,
    "expected_point_revision": 1, "expected_total_point_count": 1440,
    "expected_active_point_count": 1344, "minimum_fuel_sum": 1000.0,
}
SOURCE = {
    "enabled": True, "revision": 1, "total_point_count": 1440, "active_point_count": 1344,
    "source_sums": {"fuel": 1075.2},
}


def rows(active):
    return [
        {"frame": index, "perf_counter_ns": index * 10, "kit_update_number": index,
         "timeline_time": index / 60.0, "active_blocks": active(index)}
        for index in range(1, 121)
    ]


class Phase6FbStartupContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts = Path(__file__).resolve().parent
        cls.contract_path = cls.scripts / "phase6fb_startup_ingestion_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))

    def test_contract_hash_and_frozen_history(self):
        expected = (self.scripts / "phase6fb_startup_ingestion_contract.sha256").read_text(encoding="utf-8").split()[0]
        actual = hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper()
        self.assertEqual(actual, expected)
        self.assertEqual(self.contract["history"]["safe_commit"], "857ab8e")
        self.assertFalse(self.contract["history"]["prior_population_reuse"])

    def test_short_no_readback_branch_is_frozen(self):
        self.assertEqual([item["readback_mode"] for item in self.contract["conditions"]], ["none", "none"])
        self.assertEqual([item["maximum_frame"] for item in self.contract["conditions"]], [120, 120])
        self.assertTrue(self.contract["branching"]["run_second_only_after_first_representative"])
        self.assertFalse(self.contract["branching"]["public_field_check_in_this_contract"])
        self.assertFalse(self.contract["branching"]["ordering_or_cooldown_ablation_in_this_contract"])

    def test_resource_limits_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertFalse(safety["resource_ceiling_change"])

    def test_representative(self):
        result = classify_startup(rows(lambda frame: 140 if frame >= 20 else 24 + frame * 6), SOURCE, THRESHOLDS)
        self.assertEqual(result["classification"], "representative_ingestion")

    def test_small_field_is_not_accepted_as_representative(self):
        result = classify_startup(rows(lambda _frame: 24), SOURCE, THRESHOLDS)
        self.assertEqual(result["classification"], "small_field_ingestion")

    def test_stale_update_is_rejected(self):
        history = rows(lambda _frame: 140)
        for row in history:
            row["kit_update_number"] = 1
        self.assertEqual(classify_startup(history, SOURCE, THRESHOLDS)["classification"], "stale_telemetry")

    def test_no_source(self):
        source = dict(SOURCE, enabled=False)
        self.assertEqual(classify_startup(rows(lambda _frame: 140), source, THRESHOLDS)["classification"], "no_source")

    def test_incomplete_is_indeterminate(self):
        self.assertEqual(classify_startup(rows(lambda _frame: 140)[:60], SOURCE, THRESHOLDS)["classification"], "indeterminate")

    def test_published_result_and_devlog(self):
        root = self.scripts.parent
        assets = root / "docs" / "devlog" / "assets" / "phase6"
        report = json.loads((assets / "point_emitter_startup_ingestion.json").read_text(encoding="utf-8"))
        self.assertEqual(report["contract_sha256"], self.contract_path.with_suffix(".sha256").read_text(encoding="ascii").split()[0])
        self.assertTrue(report["active_history_equal_between_new_probes"])
        self.assertFalse(report["public_field_checked"])
        self.assertFalse(report["repeated_readback_started"])
        self.assertFalse(report["production_changed"])
        for result in report["new_probes"].values():
            self.assertEqual(result["classification"], "representative_ingestion")
            self.assertTrue(result["normal_os_exit"])
            self.assertEqual(result["production_app_sha256_before"], result["production_app_sha256_after"])
        ET.parse(assets / "point_emitter_startup_ingestion.svg")
        html = (root / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="phase-6fb"'), 1)
        self.assertIn("point_emitter_startup_ingestion.json", html)
        self.assertNotIn("\ufffd", html)


if __name__ == "__main__":
    unittest.main()
