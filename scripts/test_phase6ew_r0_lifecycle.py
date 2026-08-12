"""Frozen contracts for the Phase 6EW R0 lifecycle qualification."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6EwLifecycleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6ew_r0_lifecycle_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6ew_r0_lifecycle.ps1").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        cls.analyzer = (SCRIPTS / "analyze_phase6ew_r0_lifecycle.py").read_text(encoding="utf-8")

    def test_contract_hash_and_history_are_frozen(self):
        actual = hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper()
        expected = (SCRIPTS / "phase6ew_r0_lifecycle_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(expected, actual)
        self.assertIn("frozen", self.contract["phase6eu_history"])
        self.assertIn("102.595644", self.contract["phase6ev_history"])
        self.assertFalse(self.contract["execution"]["phase6eu_or_phase6ev_sample_reuse"])

    def test_sequence_is_l0_then_three_r0_then_one_r1_without_retry(self):
        self.assertEqual(
            [item["id"] for item in self.contract["conditions"]],
            ["L0_short", "R0_none", "R1_acquire_discard"],
        )
        self.assertEqual([item["runs"] for item in self.contract["conditions"]], [1, 3, 1])
        self.assertEqual(self.contract["execution"]["maximum_processes"], 5)
        self.assertFalse(self.contract["execution"]["automatic_retry"])
        loop = self.runner.index("for ($run = 1; $run -le 3; $run++)")
        r1 = self.runner.index('Write-State "running" $completed "R1_acquire_discard"')
        self.assertLess(loop, r1)
        self.assertLess(self.runner.index("r0_gate_pass"), r1)
        self.assertIn('"acquire_discard" "60"', self.runner)

    def test_stage_close_is_bounded_and_records_timeout(self):
        lifecycle = self.contract["lifecycle"]
        self.assertEqual(lifecycle["stage_close_timeout_seconds"], 180)
        self.assertEqual(lifecycle["inner_absolute_timeout_seconds"], 540)
        self.assertEqual(lifecycle["outer_condition_timeout_seconds"], 900)
        self.assertIn("102.595644", lifecycle["stage_close_timeout_rationale"])
        self.assertIn("asyncio.wait_for(context.close_stage_async(), timeout=close_timeout)", self.probe)
        self.assertIn('mark("stage_close_timeout"', self.probe)
        self.assertIn("StageCloseTimeoutSeconds", self.case_runner)

    def test_powershell_seven_digit_timestamp_is_bounded(self):
        from scripts.analyze_phase6ew_r0_lifecycle import _time

        seven_digit = _time("2026-08-12T09:26:26.7250933Z")
        six_digit = _time("2026-08-12T09:26:26.725093Z")
        self.assertEqual(seven_digit, six_digit)
        self.assertIn("ResumeAfterL0AnalysisFailure", self.runner)
        self.assertIn("without_rerunning_L0", self.runner)

    def test_common_final_marker_precedes_shutdown(self):
        common_final = self.probe.index('"final_sample_complete", frame=final_frame')
        self.assertLess(self.probe.index("for frame in range(1, final_frame + 1):"), common_final)
        self.assertLess(common_final, self.probe.index('report["spatial_manifest_collider_indices"]'))
        self.assertLess(common_final, self.probe.index('report["lifecycle_marker"] = "timeline_stopping"'))
        for marker in self.contract["required_probe_markers"]:
            self.assertIn(f'"{marker}"', self.probe)
        self.assertIn("os_process_exit_observed", self.case_runner)

    def test_plateau_and_cross_run_gates_are_predeclared(self):
        plateau = self.contract["plateau_contract"]
        self.assertEqual(plateau["stability_frames"], [240, 280, 320])
        self.assertEqual(plateau["minimum_resource_samples_in_stability_interval"], 20)
        self.assertEqual(plateau["maximum_private_growth_bytes_per_second"], 8 * 1024**2)
        self.assertTrue(plateau["require_non_monotonic_or_flat_private_series"])
        self.assertIn("three_run_reproducibility_gate_failed", self.runner)
        self.assertIn('item["plateau"]', self.analyzer)
        self.assertIn('reproducibility["gate_pass"]', self.analyzer)

    def test_r1_is_metadata_only_and_requires_all_memory_markers(self):
        boundary = self.contract["r1_boundary"]
        for name in (
            "conversion", "scalar_aggregation", "spatial_sampling",
            "field_json_or_npz_persistence", "directional_transport", "private_release_api", "gc_collect",
        ):
            self.assertFalse(boundary[name])
        self.assertEqual(boundary["release"], "natural scope end or explicit del only")
        self.assertIn('if mode != "acquire_discard":', self.probe)
        self.assertIn('"-ReferenceDisposal", "natural"', self.runner)
        self.assertIn('("before", "after", "references_released", "next_frame")', self.analyzer)

    def test_resource_limits_remain_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["physical_memory_floor_bytes"], 8 * 1024**3)
        self.assertEqual(safety["commit_headroom_floor_bytes"], 8 * 1024**3)

    def test_published_safe_stop_is_fail_closed(self):
        asset = json.loads(
            (ROOT / "docs/devlog/assets/phase6/r0_lifecycle_qualification_safe_stop.json").read_text(encoding="utf-8")
        )
        devlog = (ROOT / "docs/devlog/index.html").read_text(encoding="utf-8")
        self.assertEqual(asset["schema"], "campfire.phase6ew.r0-lifecycle-safe-stop.v1")
        self.assertEqual(asset["status"], "safe_stop")
        self.assertTrue(asset["l0"]["gate_pass"])
        self.assertEqual(asset["r0_run01"]["stability_resource_samples"], 18)
        self.assertEqual(asset["r0_run01"]["required_stability_resource_samples"], 20)
        self.assertFalse(asset["r0_run01"]["plateau_gate_pass"])
        self.assertEqual(asset["formal_population"]["accepted_complete_population"], 0)
        self.assertFalse(asset["formal_population"]["r1_started"])
        self.assertFalse(asset["production"]["changed"])
        self.assertFalse(asset["production"]["latest_demo_changed"])
        self.assertIn('id="phase-6ew"', devlog)
        self.assertIn("r0_lifecycle_qualification_safe_stop.json", devlog)
        phase_section = devlog.split('id="phase-6ew"', 1)[1].split('id="phase-6ev"', 1)[0]
        self.assertNotIn("video-trigger", phase_section)


if __name__ == "__main__":
    unittest.main()
