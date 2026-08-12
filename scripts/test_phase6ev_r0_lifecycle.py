"""Static and fixture contracts for Phase 6EV lifecycle calibration."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path

from scripts.phase6eu_process_memory import process_memory_snapshot


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6EvLifecycleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6ev_r0_lifecycle_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6ev_r0_lifecycle.ps1").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")

    def test_contract_hash_and_frozen_sequence(self):
        actual = hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper()
        expected = (SCRIPTS / "phase6ev_r0_lifecycle_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(expected, actual)
        self.assertEqual([item["id"] for item in self.contract["conditions"]], ["L0_short", "R0_none", "R1_acquire_discard"])
        self.assertEqual(self.contract["conditions"][1]["runs"], 3)
        self.assertEqual(self.contract["conditions"][2]["readback_frames"], [60])
        self.assertFalse(self.contract["execution"]["automatic_retry"])

    def test_shutdown_marker_order_is_explicit(self):
        ordered = [
            "final_sample_complete", "measurement_complete", "timeline_stop_request_before",
            "timeline_stop_request_after", "timeline_stop_confirmed", "renderer_drain_started",
            "renderer_drain_complete", "flow_references_release_started", "flow_references_release_complete",
            "provider_readback_references_release_started", "provider_readback_references_release_complete",
            "stage_close_request_before", "stage_close_request_after", "usd_context_disconnected",
            "app_close_requested", "shutdown_complete",
        ]
        positions = [self.probe.index(f'"{marker}"') for marker in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("os_process_exit_observed", self.case_runner)

    def test_known_good_extension_is_reused(self):
        self.assertIn("phasev3tg_extension", self.case_runner)
        self.assertIn("omni.campfire.phasev3tg_shutdown", self.case_runner)
        extension = (SCRIPTS / "phasev3tg_extension/omni.campfire.phasev3tg_shutdown/omni/campfire/phasev3tg_shutdown/__init__.py").read_text(encoding="utf-8")
        self.assertIn("extension_on_shutdown_begin", extension)
        self.assertIn("os.fsync", extension)

    def test_memory_helper_returns_finite_x64_sample(self):
        sample = process_memory_snapshot()
        self.assertTrue(sample["available"], sample)
        self.assertEqual(sample["structure_bytes"], 80)
        self.assertGreater(sample["private_bytes"], 0)
        self.assertGreater(sample["working_set_bytes"], 0)

    def test_r1_is_guarded_by_three_run_plateau(self):
        first_r1 = self.runner.index('"R1_acquire_discard"')
        self.assertLess(self.runner.index("for ($run = 1; $run -le 3; $run++)"), first_r1)
        self.assertLess(self.runner.index("r0_gate_pass"), first_r1)
        self.assertIn('"acquire_discard" "60"', self.runner)

    def test_limits_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)


if __name__ == "__main__":
    unittest.main()
