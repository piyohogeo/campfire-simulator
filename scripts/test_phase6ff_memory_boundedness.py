import hashlib
import json
import unittest
from pathlib import Path

from scripts.calibrate_phase6ff_memory_boundedness import synthetic_rows
from scripts.phase6ff_memory_boundedness import evaluate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "scripts/phase6ff_memory_boundedness_contract.json"


class Phase6FfMemoryBoundedness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_history_and_old_slope_gate_are_frozen(self):
        self.assertEqual(self.contract["safe_commit"], "e77fb4e")
        self.assertFalse(self.contract["history_frozen"]["prior_population_reuse"])
        self.assertFalse(self.contract["history_frozen"]["old_8_mib_s_gate_reinterpreted"])

    def test_contract_hash_matches(self):
        expected = CONTRACT_PATH.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest().upper(), expected)

    def test_absolute_resource_ceilings_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertFalse(safety["resource_ceiling_change"])

    def test_required_bounded_transients_are_accepted(self):
        for name in (
            "startup_then_plateau", "brief_over_8mib_then_recovery", "bounded_allocator_cache",
            "active_following_bounded", "shader_resource_transient", "delayed_reclaim_after_disappearance",
        ):
            with self.subTest(name=name):
                self.assertTrue(evaluate(synthetic_rows(name), self.contract)["gate_pass"])

    def test_required_sustained_growth_is_rejected(self):
        for name in (
            "occupancy_independent_monotonic", "late_positive_slope", "staircase_accumulation",
            "per_block_growth", "absolute_limit",
        ):
            with self.subTest(name=name):
                self.assertFalse(evaluate(synthetic_rows(name), self.contract)["gate_pass"])

    def test_eight_mib_is_diagnostic_not_retroactive_pass(self):
        bounded = evaluate(synthetic_rows("brief_over_8mib_then_recovery"), self.contract)
        self.assertGreater(
            max(item["private_slope_bytes_per_second"] for item in bounded["metrics"]["rolling_windows"]),
            8 * 1024**2,
        )
        self.assertTrue(bounded["gate_pass"])

    def test_runtime_order_requires_controls_before_c0_before_c1(self):
        runner = (ROOT / "scripts/run_phase6ff_memory_boundedness.ps1").read_text(encoding="utf-8")
        self.assertLess(runner.index('Label="R0_none"'), runner.index('Label="C0_acquire_discard"'))
        self.assertLess(runner.index('Label="C0_acquire_discard"'), runner.index('Label="C1_fuel_alias"'))
        self.assertNotIn("Start-Sleep", runner)
        self.assertIn('if ($reason) { Stop-Safely', runner)

    def test_repeated_readback_and_field_persistence_are_excluded(self):
        excluded = " ".join(self.contract["excluded"])
        self.assertIn("repeated readback", excluded)
        self.assertIn("field-body persistence", excluded)
        self.assertIn("resource ceiling increase", excluded)

    def test_published_runtime_result_is_fail_closed(self):
        path = ROOT / "docs/devlog/assets/phase6/memory_boundedness_safe_stop.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            report["contract_sha256"],
            CONTRACT_PATH.with_suffix(".sha256").read_text(encoding="utf-8").split()[0],
        )
        runtime = report["runtime"]
        self.assertEqual(runtime["executed_conditions"], 1)
        self.assertEqual(runtime["accepted_conditions"], 0)
        self.assertTrue(runtime["normal_os_exit"])
        self.assertEqual(runtime["failed_gate"], "persistent_local_growth")
        self.assertFalse(report["qualification"]["c0_started"])
        self.assertFalse(report["qualification"]["c1_started"])
        self.assertFalse(report["qualification"]["repeated_readback_ready"])
        self.assertEqual(report["safety"]["cleanup_residual_count"], 0)


if __name__ == "__main__":
    unittest.main()
