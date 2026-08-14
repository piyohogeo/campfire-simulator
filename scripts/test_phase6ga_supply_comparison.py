import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class Phase6GaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "phase6ga_supply_comparison_contract.json"
        cls.contract = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_contract_hash_and_population_are_frozen(self):
        expected = (ROOT / "phase6ga_supply_comparison_contract.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest().upper(), expected)
        self.assertEqual(self.contract["phase"], "phase6ga")
        self.assertEqual(sum(map(len, self.contract["formal_population"]["balanced_order"])), 9)
        self.assertEqual({*sum(self.contract["formal_population"]["balanced_order"], [])}, {"S93", "S100", "OFF"})

    def test_physical_conditions_are_explicit(self):
        self.assertEqual(self.contract["conditions"]["S93"]["expected_active_points"], 1344)
        self.assertEqual(self.contract["conditions"]["S100"]["expected_active_points"], 1440)
        self.assertTrue(self.contract["conditions"]["S100"]["collision_enabled"])
        self.assertFalse(self.contract["conditions"]["OFF"]["collision_enabled"])
        self.assertEqual(self.contract["conditions"]["S100"]["expected_other_center_inside"], 0)

    def test_numeric_gates_do_not_require_hard_zero_scalars(self):
        gates = self.contract["hard_gates"]
        self.assertEqual(gates["maximum_collision_on_deep_velocity_m_s"], 1e-4)
        self.assertEqual(gates["minimum_collision_off_deep_velocity_m_s"], 0.1)
        self.assertTrue(self.contract["materiality"]["tiny_nonzero_scalar_is_not_alone_a_failure"])
        self.assertNotIn("temperature_hard_zero", gates)

    def test_phase6fz_safety_limits_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertEqual(safety["shutdown_order"], "release_after_close")
        self.assertTrue(self.contract["artifact_commit"]["required_before_stage_close"])

    def test_probe_import_is_exact_and_shared(self):
        text = (ROOT / "probe_phase6ga_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn('"probe_phase6fo_supply_comparison.py"', text)
        self.assertIn("load_exact_module", text)
        self.assertIn("measurement_complete", text)
        self.assertIn("measurementCommitAck", text)

    def test_runner_uses_phase6fu_guard_and_preclose_committer(self):
        text = (ROOT / "run_phase6fo_supply_comparison.ps1").read_text(encoding="utf-8")
        self.assertIn('"phase6fu_resource_guard.py"', text)
        self.assertIn('"phase6fz_preclose_committer.py"', text)
        self.assertIn('"phase6ga"', text)
        self.assertIn("cleanup_markers.jsonl", text)

    def test_published_safe_stop_is_not_a_physical_result(self):
        report = json.loads((ROOT.parent / "docs/devlog/assets/phase6/supply_comparison_phase6ga_safe_stop.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "harness_operation_safe_stop")
        self.assertEqual(report["formal_launches"], 0)
        self.assertEqual(report["readback_count"], 0)
        self.assertFalse(report["production_changed"])
        devlog = (ROOT.parent / "docs/devlog/index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6ga"', devlog)
        self.assertIn("supply_comparison_phase6ga_safe_stop.json", devlog)
        self.assertIn("latest_demo.json", devlog)


if __name__ == "__main__":
    unittest.main()
