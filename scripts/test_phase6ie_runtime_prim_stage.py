"""Focused no-Kit regression for the Phase 6IE live-stage policy boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phase6ie_marker_fixture import run_fixture as run_markers
from phase6ie_runtime_prim_fixture import run_fixture as run_runtime_policy


class Phase6IERuntimePrimStageTests(unittest.TestCase):
    def test_runtime_policy_producer_to_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            projection = Path(__file__).resolve().with_name("phase6ie_phase6id_runtime_projection.json")
            report = run_runtime_policy(Path(directory) / "runtime-policy", projection)
            self.assertEqual("qualified", report["status"])
            self.assertEqual([26, 26], report["case_count"])

    def test_marker_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run_markers(Path(directory) / "markers")
            self.assertEqual("qualified", report["status"])
            self.assertEqual([8, 8], report["case_count"])

    def test_contract_freezes_phase6id(self):
        root = Path(__file__).resolve().parents[1]
        policy = json.loads((root / "scripts/phase6ie_stage_open_contract.json").read_text(encoding="utf-8"))
        self.assertEqual("safe_stop_live_stage_prim_set_validation_failure", policy["frozen_history"]["phase6id"]["status"])
        self.assertFalse(policy["frozen_history"]["reclassified"])
        self.assertEqual(0, policy["smoke"]["timeline_play_calls"])
        self.assertEqual(0, policy["smoke"]["flow_update_calls"])


if __name__ == "__main__":
    unittest.main()
