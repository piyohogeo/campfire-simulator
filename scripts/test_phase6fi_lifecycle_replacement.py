import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import analyze_phase6fi_lifecycle_replacement as analyzer


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6fi_lifecycle_replacement_contract.json"


class Phase6FiLifecycleReplacementContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6fi_lifecycle_replacement.ps1").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")

    def test_contract_hash_and_frozen_history(self):
        expected = CONTRACT.with_suffix(".sha256").read_text(encoding="utf-8").split()[0].upper()
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)
        self.assertFalse(self.contract["history_frozen"]["historical_reclassification"])
        self.assertFalse(self.contract["history_frozen"]["artifact_overwrite"])

    def test_population_has_six_targets_two_replacements_and_eight_maximum(self):
        population = self.contract["population"]
        self.assertEqual(population["target_representative_processes"], 6)
        self.assertEqual(population["startup_prerequisite_replacement_budget"], 2)
        self.assertEqual(population["maximum_launches"], 8)
        self.assertFalse(population["automatic_retry"])
        self.assertIn('$label = "run{0:D2}" -f $attempt', self.runner)
        self.assertIn('$attemptId = "attempt{0:D2}" -f $attempt', self.runner)

    def test_only_startup_prerequisite_is_replaceable(self):
        policy = self.contract["replacement_policy"]
        self.assertEqual(policy["replaceable_classification"], "startup_prerequisite_failure")
        self.assertEqual(
            policy["nonreplaceable"],
            ["operation_failure", "native_lifecycle_failure", "absolute_safety_failure"],
        )
        self.assertIn('if ($classification -eq "startup_prerequisite_failure")', self.runner)
        self.assertIn('captured nonreplaceable $classification', self.runner)

    def test_runtime_scope_and_resource_ceilings_are_unchanged(self):
        condition = self.contract["condition"]
        self.assertEqual(condition["readback_mode"], "none")
        self.assertEqual(condition["public_readback_calls"], 0)
        self.assertEqual(condition["numpy_asarray_calls"], 0)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertFalse(self.contract["safety"]["resource_ceiling_change"])
        self.assertIn('"-ReportPhase", "phase6fi"', self.runner)
        self.assertIn('"phase6fi"', self.case_runner)

    def test_cdb_remains_native_only_and_bounded(self):
        cdb = self.contract["bounded_cdb"]
        self.assertTrue(cdb["only_after_native_lifecycle_failure"])
        self.assertEqual(
            (cdb["attach_and_module_timeout_seconds"], cdb["all_thread_stack_timeout_seconds"], cdb["detach_recovery_timeout_seconds"], cdb["worst_case_total_timeout_seconds"]),
            (30, 45, 30, 105),
        )
        self.assertFalse(cdb["full_dump_automatic"])

    def test_report_requires_six_representative_attempts(self):
        representative = {"classification": "representative_startup", "stage_close_seconds": 2.0}
        with patch.object(analyzer, "classify_attempt", side_effect=[representative] * 6 + [None, None]):
            report = analyzer.report_for(Path("unused"), self.contract, "HASH")
        self.assertEqual(report["status"], "lifecycle_qualification_pass")
        self.assertEqual(report["representative_startup_count"], 6)
        self.assertTrue(report["phase6fg_restart_candidate"])
        self.assertFalse(report["phase6fg_restart_authorized"])

    def test_report_preserves_two_startup_replacements_and_rejects_third(self):
        startup = {"classification": "startup_prerequisite_failure", "stage_close_seconds": 3.0}
        representative = {"classification": "representative_startup", "stage_close_seconds": 2.0}
        with patch.object(analyzer, "classify_attempt", side_effect=[startup, representative, startup, representative, representative, representative, representative, representative]):
            report = analyzer.report_for(Path("unused"), self.contract, "HASH")
        self.assertEqual(report["status"], "lifecycle_qualification_pass")
        self.assertEqual(report["replacement_budget_used"], 2)
        with patch.object(analyzer, "classify_attempt", side_effect=[startup, startup, startup, None, None, None, None, None]):
            report = analyzer.report_for(Path("unused"), self.contract, "HASH")
        self.assertEqual(report["status"], "prerequisite_population_incomplete")

    def test_nonreplaceable_failures_stop_report(self):
        for classification, status in (
            ("operation_failure", "operation_safe_stop"),
            ("native_lifecycle_failure", "native_lifecycle_safe_stop"),
            ("absolute_safety_failure", "absolute_safety_stop"),
        ):
            with self.subTest(classification=classification):
                item = {"classification": classification, "stage_close_seconds": None}
                with patch.object(analyzer, "classify_attempt", side_effect=[item] + [None] * 7):
                    report = analyzer.report_for(Path("unused"), self.contract, "HASH")
                self.assertEqual(report["status"], status)

    def test_published_result_preserves_replacement_and_approval_boundaries(self):
        published = json.loads((ROOT / "docs" / "devlog" / "assets" / "phase6" / "lifecycle_replacement_qualification.json").read_text(encoding="utf-8"))
        self.assertEqual(published["status"], "lifecycle_qualification_pass")
        self.assertEqual(published["population"]["total_launches"], 7)
        self.assertEqual(published["population"]["representative_startup"], 6)
        self.assertEqual(published["population"]["startup_prerequisite_failure"], 1)
        self.assertEqual(published["population"]["replacement_budget_used"], 1)
        self.assertEqual(published["startup_prerequisite_attempt"]["active_blocks_maximum"], 24)
        self.assertTrue(published["phase6fg_restart_candidate"])
        self.assertFalse(published["phase6fg_restart_authorized"])


if __name__ == "__main__":
    unittest.main()
