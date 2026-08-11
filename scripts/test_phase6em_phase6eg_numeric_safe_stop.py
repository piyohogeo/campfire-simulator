import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "devlog" / "assets" / "phase6" / "static_pose_numeric_safe_stop.json"


class Phase6EmNumericSafeStopContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_safe_stop_is_numeric_and_never_accepts_partial_population(self):
        qualification = self.report["qualification"]
        self.assertEqual("safe_stop", self.report["status"])
        self.assertEqual("incremental_numeric_gate", qualification["failure_kind"])
        self.assertEqual("run_1/P4_y24_z31_on", qualification["active_condition"])
        self.assertEqual(8, qualification["completed_normal_exit_incremental_gate_processes"])
        self.assertEqual(0, qualification["accepted_complete_population"])
        self.assertFalse(qualification["automatic_retry"])
        self.assertFalse(qualification["later_processes_started"])

    def test_active_condition_exited_normally_but_failed_frozen_gate(self):
        active = self.report["active_condition"]
        numeric = active["numeric"]
        self.assertTrue(active["normal_os_exit"])
        self.assertEqual("normal_exit", active["lifecycle_status"])
        self.assertEqual(4, active["flow_velocity_sample_count"])
        self.assertFalse(numeric["pass"])
        self.assertGreater(numeric["deep_maximum_m_s"], 1e-5)
        self.assertGreater(numeric["center_maximum_m_s"], 1e-5)
        self.assertFalse(active["pair_gate_evaluated"])
        self.assertFalse(active["paired_off_condition_started"])

    def test_cdb_remains_residual_only_and_safety_is_clean(self):
        self.assertTrue(self.report["cdb"]["phase6el_path_integrated"])
        self.assertEqual(0, self.report["cdb"]["invocation_count"])
        safety = self.report["safety"]
        self.assertEqual(0, safety["fatal_count"])
        self.assertEqual(0, safety["dump_count"])
        self.assertEqual(0, safety["automatic_upload_attempt_count"])
        self.assertTrue(safety["process_absent_after_cleanup"])

    def test_contract_and_production_hashes_are_unchanged(self):
        self.assertFalse(self.report["frozen_contract"]["changed"])
        self.assertFalse(self.report["production"]["changed"])
        self.assertEqual(
            "4BAED82160A08C061D479BCCA6B6A46866DE88F5046851D2AF140D36D8C80687",
            self.report["frozen_contract"]["sha256_after"],
        )
        self.assertEqual(
            "94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A",
            self.report["production"]["app_sha256_after"],
        )

    def test_devlog_records_internal_safe_stop_without_demo_change(self):
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6em"', devlog)
        self.assertIn("static_pose_numeric_safe_stop.svg", devlog)
        self.assertIn("latest demo", devlog.lower())
        self.assertFalse(self.report["artifacts"]["latest_demo_changed"])


if __name__ == "__main__":
    unittest.main()
