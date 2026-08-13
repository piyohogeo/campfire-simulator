import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "phase6fj_balanced_single_readback_contract.json"
HASH = ROOT / "scripts" / "phase6fj_balanced_single_readback_contract.sha256"


class Phase6FjContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_hash_is_frozen(self):
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), HASH.read_text().split()[0])

    def test_balanced_population_and_replacement_budget(self):
        order = self.contract["balanced_order"]
        self.assertEqual(order, [["A_control", "B_readback", "C_fuel_alias"], ["B_readback", "C_fuel_alias", "A_control"], ["C_fuel_alias", "A_control", "B_readback"]])
        self.assertEqual(sum(order, []).count("A_control"), 3)
        self.assertEqual(sum(order, []).count("B_readback"), 3)
        self.assertEqual(sum(order, []).count("C_fuel_alias"), 3)
        self.assertEqual(self.contract["population"]["target_representative_processes"], 9)
        self.assertEqual(self.contract["population"]["startup_prerequisite_replacement_budget"], 2)
        self.assertEqual(self.contract["population"]["maximum_launches"], 11)

    def test_only_preoperation_startup_is_replaceable(self):
        self.assertEqual(self.contract["replaceable_only"], "startup_prerequisite_failure_before_operation")
        self.assertIn("operation_failure", self.contract["nonreplaceable"])
        self.assertIn("native_lifecycle_failure", self.contract["nonreplaceable"])
        self.assertIn("absolute_safety_failure", self.contract["nonreplaceable"])

    def test_three_layer_policy_keeps_waveform_warning_only(self):
        decision = self.contract["three_layer_decision"]
        self.assertIn("warning-only", decision["waveform_telemetry"])
        self.assertIn("adjacent synchronous markers", decision["operation_specific"])

    def test_base_contracts_and_resource_limits_are_unchanged(self):
        for key in ("base_operation_contract", "base_replacement_contract"):
            item = self.contract[key]
            path = ROOT / item["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), item["sha256"])
        limits = self.contract["unchanged_runtime"]
        self.assertEqual(limits["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(limits["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(limits["stage_close_timeout_seconds"], 180)

    def test_repeated_readback_and_production_changes_are_excluded(self):
        excluded = self.contract["excluded"]
        self.assertIn("repeated readback", excluded)
        self.assertIn("production changes", excluded)
        self.assertFalse(self.contract["qualification"]["repeated_readback_qualified"])

    def test_runner_repeats_only_the_active_balanced_slot(self):
        text = (ROOT / "scripts" / "run_phase6fj_balanced_single_readback.ps1").read_text(encoding="utf-8")
        self.assertIn("$slot = $slots[$slotIndex]", text)
        self.assertIn("$slotIndex++", text)
        self.assertIn('if ($classification -eq "startup_prerequisite_failure")', text)
        self.assertIn("$prerequisite++", text)
        self.assertNotIn("$slotIndex++\n        Write-State \"running\" $attemptId $slot.slot_id $classification \"preserved", text)

    def test_analyzer_keeps_waveform_out_of_qualification(self):
        text = (ROOT / "scripts" / "analyze_phase6fj_balanced_single_readback.py").read_text(encoding="utf-8")
        self.assertIn('"formal_gate": False', text)
        qualification = "qualified = len(representative) == 9"
        self.assertIn(qualification, text)
        self.assertNotIn("total_warnings == 0", text)


if __name__ == "__main__":
    unittest.main()
