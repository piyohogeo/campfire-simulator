import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.calibrate_phase6fe_lagged_memory_response import _synthetic_rows, synthetic_evaluation
from scripts.phase6fe_lagged_memory_response import evaluate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "scripts" / "phase6fe_lagged_memory_response_contract.json"


class Phase6FeLaggedMemoryResponse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_is_new_and_history_is_frozen(self):
        self.assertEqual(self.contract["schema"], "campfire.phase6fe.lagged-memory-response-contract.v1")
        self.assertEqual(self.contract["safe_commit"], "e692915")
        self.assertFalse(self.contract["history_frozen"]["prior_population_reuse"])
        self.assertTrue(self.contract["same_sample_response_is_not_required"])

    def test_lag_window_and_resource_ceilings_are_frozen(self):
        response = self.contract["lagged_occupancy_response"]
        self.assertEqual(response["lag_samples"], 4)
        self.assertEqual(response["maximum_lag_window_seconds"], 3.0)
        self.assertEqual(response["minimum_active_block_drop"], 16)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertFalse(self.contract["safety"]["resource_ceiling_change"])

    def test_normal_and_delayed_reclaim_are_recognized(self):
        immediate = evaluate(_synthetic_rows("immediate_reclaim"), self.contract)
        delayed = evaluate(_synthetic_rows("delayed_reclaim"), self.contract)
        self.assertTrue(immediate["gate_pass"])
        self.assertGreater(immediate["lagged_response"]["classification_counts"]["immediate_reclaim"], 0)
        self.assertTrue(delayed["gate_pass"])
        self.assertGreater(delayed["lagged_response"]["classification_counts"]["delayed_reclaim"], 0)

    def test_bounded_cache_is_allowed_without_same_sample_reclaim(self):
        result = evaluate(_synthetic_rows("bounded_cache_retention"), self.contract)
        self.assertTrue(result["gate_pass"])
        self.assertGreater(result["lagged_response"]["classification_counts"]["bounded_cache_retention"], 0)

    def test_other_required_bounded_series_are_accepted(self):
        for name in (
            "periodic_bounded", "drop_cancelled_by_rebound", "constant_occupancy_bounded_noise",
        ):
            with self.subTest(name=name):
                result = synthetic_evaluation(name, self.contract)
                self.assertTrue(result["full_contract_gate_pass"])
                if name == "drop_cancelled_by_rebound":
                    self.assertGreater(result["lagged_response"]["classification_counts"]["active_rebound_overlap"], 0)

    def test_leaks_are_rejected(self):
        for name in (
            "occupancy_independent_monotonic_growth",
            "constant_accelerating_growth",
            "post_drop_continued_growth",
            "repeated_accumulation",
            "short_plateau_long_divergence",
            "stale_telemetry",
            "resource_ceiling",
            "shutdown_incomplete",
        ):
            with self.subTest(name=name):
                self.assertFalse(synthetic_evaluation(name, self.contract)["full_contract_gate_pass"])

    def test_contract_hash_file_matches(self):
        hash_path = CONTRACT_PATH.with_suffix(".sha256")
        self.assertTrue(hash_path.is_file())
        expected = hash_path.read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest().upper(), expected)

    def test_runner_is_sequential_fail_closed_and_does_not_retry(self):
        runner = (ROOT / "scripts/run_phase6fe_lagged_memory_response.ps1").read_text(encoding="utf-8")
        shared_runner = (ROOT / "scripts/run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        self.assertIn('foreach ($runIndex in 1..3)', runner)
        self.assertLess(runner.index('Label="C0_acquire_discard"'), runner.index('Label="C1_fuel_alias"'))
        self.assertIn('if ($reason) { Stop-Safely $completed $active $reason }', runner)
        self.assertNotIn("Start-Sleep", runner)
        self.assertIn('"-StartupLivenessGate", "true"', runner)
        self.assertIn('"-StabilityObservationExtraSeconds", "$($window.extra_running_flow_wall_seconds)"', runner)
        self.assertIn('"phase6fd", "phase6fe"', shared_runner)

    def test_analyzer_replaces_only_the_legacy_same_sample_gate(self):
        analyzer = (ROOT / "scripts/analyze_phase6fe_lagged_memory_response.py").read_text(encoding="utf-8")
        self.assertIn('legacy_failures.discard("dynamic_stationarity")', analyzer)
        self.assertIn('failures.append("lagged_memory_response")', analyzer)
        self.assertIn('not_same_object_zero_copy_alias', analyzer)
        self.assertIn('repeated_readback_qualified', analyzer)


if __name__ == "__main__":
    unittest.main()
