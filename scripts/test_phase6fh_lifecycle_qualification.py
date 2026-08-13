import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6fh_lifecycle_qualification_contract.json"


class Phase6FhLifecycleQualificationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6fh_lifecycle_qualification.ps1").read_text(encoding="utf-8")
        cls.policy = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")

    def test_contract_hash_is_frozen(self):
        expected = CONTRACT.with_suffix(".sha256").read_text(encoding="utf-8").split()[0].upper()
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)

    def test_phase6fg_is_frozen_and_population_is_bounded(self):
        self.assertFalse(self.contract["history_frozen"]["historical_reclassification"])
        self.assertEqual(6, self.contract["population"]["planned_processes"])
        self.assertTrue(self.contract["population"]["stop_after_first_lifecycle_failure"])
        self.assertIn('if ($guardExit -ne 0 -or $case.status -ne "pass")', self.runner)

    def test_condition_has_no_readback_or_memory_contract_change(self):
        condition = self.contract["condition"]
        self.assertEqual("none", condition["readback_mode"])
        self.assertEqual(0, condition["public_readback_calls"])
        self.assertEqual(0, condition["numpy_asarray_calls"])
        self.assertFalse(self.contract["safety"]["resource_ceiling_change"])
        self.assertIn('"-ReadbackMode", "none"', self.runner)

    def test_cdb_is_split_bounded_and_full_dump_is_disabled(self):
        cdb = self.contract["bounded_cdb"]
        self.assertEqual((30, 45, 30, 105), (cdb["attach_and_module_timeout_seconds"], cdb["all_thread_stack_timeout_seconds"], cdb["detach_recovery_timeout_seconds"], cdb["worst_case_total_timeout_seconds"]))
        self.assertFalse(cdb["full_dump_automatic"])
        for marker in ("cdb_module_capture_started", "cdb_module_capture_complete", "cdb_stack_capture_started", "cdb_stack_capture_complete", "cdb_detach_complete"):
            self.assertIn(f'"{marker}"', self.policy)

    def test_two_axis_policy_never_promotes_lifecycle_failure(self):
        proposal = self.contract["two_axis_policy_proposal"]
        self.assertIn("both axes must pass", proposal["overall_production_qualification"])
        self.assertIn("normal OS exit", proposal["lifecycle_axis"])


if __name__ == "__main__":
    unittest.main()
