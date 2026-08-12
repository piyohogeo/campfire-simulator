"""Frozen contracts for the Phase 6EX extended stability observation."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6ExStabilityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6ex_r0_stability_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6ex_r0_stability.ps1").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        cls.analyzer = (SCRIPTS / "analyze_phase6ex_r0_stability.py").read_text(encoding="utf-8")
        cls.fixture = (SCRIPTS / "run_phase6ex_sampler_fixture.py").read_text(encoding="utf-8")

    def test_contract_hash_and_prior_safe_stops_are_frozen(self):
        actual = hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper()
        expected = (SCRIPTS / "phase6ex_r0_stability_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(expected, actual)
        self.assertIn("18 of 20", self.contract["phase6ew_history"])
        self.assertFalse(self.contract["execution"]["prior_phase_sample_reuse"])
        safe_stop = json.loads(
            (ROOT / "docs/devlog/assets/phase6/r0_lifecycle_qualification_safe_stop.json").read_text(encoding="utf-8")
        )
        self.assertEqual(safe_stop["r0_run01"]["stability_resource_samples"], 18)
        self.assertFalse(safe_stop["r0_run01"]["plateau_gate_pass"])

    def test_only_observation_window_changes(self):
        plateau = self.contract["plateau_contract"]
        self.assertEqual(plateau["minimum_resource_samples_in_stability_interval"], 20)
        self.assertEqual(plateau["target_resource_samples_in_stability_interval"], 30)
        self.assertEqual(plateau["maximum_active_block_range_fraction"], 0.15)
        self.assertEqual(plateau["maximum_private_growth_bytes_per_second"], 8 * 1024**2)
        self.assertTrue(plateau["require_non_monotonic_or_flat_private_series"])
        self.assertEqual(self.contract["stability_observation"]["start_frame"], 240)
        self.assertEqual(self.contract["stability_observation"]["extra_running_flow_wall_seconds"], 8.0)
        self.assertEqual(self.contract["stability_observation"]["outer_resource_sample_seconds"], 0.20)

    def test_sampler_fixture_precedes_any_kit_run_and_requires_target(self):
        fixture = self.runner.index('Write-State "running" $completed "sampler_fixture"')
        kit_loop = self.runner.index("for ($run = 1; $run -le 3; $run++)")
        self.assertLess(fixture, kit_loop)
        self.assertIn("target_sample_count_met", self.fixture)
        self.assertIn("minimum_sample_count_met", self.fixture)
        self.assertIn("timestamps_strictly_increasing", self.fixture)
        self.assertIn("runner_identity_stable", self.fixture)
        self.assertIn("powershell_seven_digit_parser_supported", self.fixture)

    def test_flow_keeps_running_through_extra_window(self):
        start = self.probe.index('"stability_observation_started"')
        final = self.probe.index('"final_sample_complete", frame=final_frame')
        end = self.probe.index('"stability_observation_ended"')
        stop = self.probe.index('report["lifecycle_marker"] = "timeline_stop_request_before"')
        self.assertLess(start, final)
        self.assertLess(final, end)
        self.assertLess(end, stop)
        extra = self.probe[final:end]
        self.assertIn("await app.next_update_async()", extra)
        self.assertIn("timeline.is_playing()", extra)
        self.assertNotIn("get_latest_nanovdb_readback", extra)

    def test_runner_passes_frozen_window_and_stops_incrementally(self):
        self.assertIn("StabilityObservationStartFrame", self.case_runner)
        self.assertIn("StabilityObservationExtraSeconds", self.case_runner)
        self.assertIn("StabilityActiveBlockSampleSeconds", self.case_runner)
        self.assertIn('"-StabilityObservationStartFrame"', self.runner)
        self.assertIn('if ($reason) { Stop-Safely $completed $label $reason }', self.runner)
        self.assertLess(self.runner.index("r0_gate_pass"), self.runner.index('"R1_acquire_discard"'))
        self.assertFalse(self.contract["execution"]["automatic_retry"])

    def test_analyzer_uses_marker_bounded_samples_and_hard_minimum(self):
        self.assertIn('marker.get("stability_observation_started")', self.analyzer)
        self.assertIn('marker.get("stability_observation_ended")', self.analyzer)
        self.assertIn("len(stability_rows) >= minimum_samples", self.analyzer)
        self.assertIn('"stability_resource_target_met"', self.analyzer)
        self.assertIn('and item["plateau"]', self.analyzer)

    def test_resource_and_lifecycle_limits_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["physical_memory_floor_bytes"], 8 * 1024**3)
        self.assertEqual(safety["commit_headroom_floor_bytes"], 8 * 1024**3)
        self.assertEqual(self.contract["lifecycle"]["stage_close_timeout_seconds"], 180)
        self.assertEqual(self.contract["lifecycle"]["inner_absolute_timeout_seconds"], 540)
        self.assertEqual(self.contract["lifecycle"]["outer_condition_timeout_seconds"], 900)

    def test_r1_remains_metadata_only_and_conditional(self):
        boundary = self.contract["r1_boundary"]
        for name in (
            "conversion", "scalar_aggregation", "spatial_sampling", "field_json_or_npz_persistence",
            "directional_transport", "private_release_api", "gc_collect",
        ):
            self.assertFalse(boundary[name])
        self.assertIn('if mode != "acquire_discard":', self.probe)
        self.assertIn('if (-not $report.r0_gate_pass)', self.runner)
        self.assertIn('("before", "after", "references_released", "next_frame")', self.analyzer)


if __name__ == "__main__":
    unittest.main()
