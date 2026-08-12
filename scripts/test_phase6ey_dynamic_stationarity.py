import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6EyDynamicStationarity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6ey_dynamic_stationarity_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6ey_dynamic_stationarity.ps1").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.analyzer = (SCRIPTS / "analyze_phase6ey_dynamic_stationarity.py").read_text(encoding="utf-8")

    def test_contract_hash_and_history_are_frozen(self):
        expected = (SCRIPTS / "phase6ey_dynamic_stationarity_contract.sha256").read_text().split()[0]
        self.assertEqual(expected, hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper())
        self.assertIn("24.382%", self.contract["phase6ex_history"])
        self.assertIn("15%", self.contract["phase6ex_history"])
        self.assertFalse(self.contract["execution"]["prior_phase_sample_reuse"])

    def test_observation_is_finite_and_supports_four_windows(self):
        observation = self.contract["observation"]
        self.assertEqual(24.0, observation["extra_running_flow_wall_seconds"])
        self.assertEqual(0.5, observation["active_block_sample_seconds"])
        self.assertGreaterEqual(observation["target_aligned_active_resource_samples"], 48)
        self.assertGreaterEqual(observation["minimum_aligned_active_resource_samples"], 40)
        self.assertEqual(4, observation["window_count"])
        self.assertEqual(32.0, observation["maximum_observation_wall_seconds"])

    def test_old_range_gate_is_not_reused(self):
        thresholds = self.contract["dynamic_stationarity_thresholds"]
        self.assertNotIn("maximum_active_block_range_fraction", thresholds)
        for key in (
            "maximum_active_projected_drift_fraction", "maximum_private_slope_bytes_per_second",
            "maximum_private_per_block_projected_drift_fraction", "minimum_decrease_transition_fraction",
            "private_high_water_recovery_bytes",
        ):
            self.assertIn(key, thresholds)

    def test_synthetic_fixture_separates_bounded_and_divergent_series(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture"
            subprocess.run(
                [sys.executable, str(SCRIPTS / "run_phase6ey_synthetic_fixture.py"),
                 "--contract", str(self.contract_path), "--output", str(output)],
                check=True, timeout=30,
            )
            report = json.loads((output / "synthetic_fixture_report.json").read_text(encoding="utf-8"))
        self.assertEqual("pass", report["status"])
        self.assertTrue(report["cases"]["periodic"]["actual_gate_pass"])
        self.assertTrue(report["cases"]["drop_recovery"]["actual_gate_pass"])
        self.assertFalse(report["cases"]["linear_growth"]["actual_gate_pass"])
        self.assertFalse(report["cases"]["memory_only_growth"]["actual_gate_pass"])
        self.assertFalse(report["cases"]["cache_after_drop"]["actual_gate_pass"])

    def test_runner_is_fail_closed_and_r1_is_conditional(self):
        self.assertIn('"phase6ey"', self.case_runner)
        self.assertIn('"-StabilityObservationExtraSeconds"', self.runner)
        self.assertIn('if ($reason) { Stop-Safely', self.runner)
        self.assertIn('if (-not $report.r0_gate_pass)', self.runner)
        self.assertLess(
            self.runner.index('if (-not $report.r0_gate_pass)'),
            self.runner.index('Write-State "running" $completed "R1_acquire_discard"'),
        )
        self.assertNotIn("maximum_active_block_range_fraction", self.runner)
        self.assertIn('"-ReadbackChannels", "none"', self.runner)
        self.assertIn('"-SpatialCollectorsEnabled", "false"', self.runner)

    def test_resource_and_lifecycle_limits_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(14 * 1024**3, safety["kit_private_limit_bytes"])
        self.assertEqual(16 * 1024**3, safety["unique_tree_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, safety["runner_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, safety["diagnostic_private_limit_bytes"])
        self.assertEqual(8 * 1024**3, safety["physical_memory_floor_bytes"])
        self.assertEqual(8 * 1024**3, safety["commit_headroom_floor_bytes"])
        self.assertEqual(180, self.contract["lifecycle"]["stage_close_timeout_seconds"])
        self.assertFalse(self.contract["execution"]["automatic_retry"])

    def test_scope_stops_after_one_acquire(self):
        self.assertTrue(self.contract["execution"]["stop_after_r1"])
        boundary = self.contract["r1_boundary"]
        self.assertFalse(boundary["conversion"])
        self.assertFalse(boundary["spatial_sampling"])
        self.assertFalse(boundary["field_json_or_npz_persistence"])
        self.assertFalse(boundary["gc_collect"])

    def test_shared_lifecycle_compatibility_does_not_reintroduce_old_gate(self):
        self.assertIn('compatibility_contract["plateau_contract"]', self.analyzer)
        self.assertIn('row.get("marker") == "stability_observation_sample"', self.analyzer)
        self.assertIn('contract["dynamic_stationarity_thresholds"]', self.analyzer)
        self.assertNotIn('evaluate(rows, contract["plateau_contract"]', self.analyzer)

    def test_published_safe_stop_keeps_r1_blocked(self):
        report = json.loads(
            (ROOT / "docs/devlog/assets/phase6/flow_dynamic_stationarity_safe_stop.json").read_text(encoding="utf-8")
        )
        self.assertEqual("safe_stop", report["status"])
        self.assertEqual("0/3", report["safe_stop"]["formal_r0_qualification"])
        self.assertFalse(report["safe_stop"]["r0_run02_started"])
        self.assertFalse(report["safe_stop"]["r0_run03_started"])
        self.assertFalse(report["safe_stop"]["r1_started"])
        self.assertFalse(report["production"]["changed"])

    def test_fresh_publication_keeps_history_and_qualifies_only_r1(self):
        report = json.loads(
            (ROOT / "docs/devlog/assets/phase6/flow_dynamic_stationarity_qualification.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("qualified", report["status"])
        self.assertTrue(report["history"]["phase6ex_safe_stop_frozen"])
        self.assertTrue(report["history"]["phase6ey_analyzer_safe_stop_frozen"])
        self.assertFalse(report["history"]["prior_formal_population_reused"])
        self.assertEqual(3, report["r0"]["qualified_runs"])
        self.assertTrue(report["r0"]["cross_run_gate_pass"])
        self.assertEqual(1, report["r1"]["public_call_count"])
        self.assertEqual(0, report["r1"]["conversion_count"])
        self.assertGreater(report["r1"]["acquire_private_bytes"]["next_frame_residual_bytes"], 0)
        self.assertLess(report["r1"]["kit_peak_private_bytes"], 14 * 1024**3)
        self.assertTrue(report["decision"]["r2_fuel_conversion_ready_for_separate_phase"])
        self.assertFalse(report["decision"]["r2_started"])
        self.assertFalse(report["safety"]["production_changed"])


if __name__ == "__main__":
    unittest.main()
