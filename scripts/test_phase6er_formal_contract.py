from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/"scripts"
SAFE_STOP=ROOT/"docs/devlog/assets/phase6/point_four_log_scalar_safe_stop.json"


class Phase6ErFormalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=SCRIPTS/"phase6er_formal_contract.json";cls.contract=json.loads(cls.path.read_text(encoding="utf-8"))

    def test_contract_hash_and_population(self):
        expected=(SCRIPTS/"phase6er_formal_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(expected,hashlib.sha256(self.path.read_bytes()).hexdigest().upper())
        self.assertEqual(24,self.contract["formal_process_count"]);self.assertEqual(3,self.contract["formal_runs_per_condition"])

    def test_scalar_gate_is_baseline_relative_and_limited_to_emitterless_blocker(self):
        self.assertEqual(0.15,self.contract["thresholds"]["collision_on_to_off_temperature_deep_sum_ratio"])
        self.assertIn("no emitter",self.contract["scalar_gate_scope"]["lower_upper"])
        self.assertIn("do not apply",self.contract["scalar_gate_scope"]["production_four"])

    def test_phase6eq_is_not_reclassified(self):
        self.assertIn("no reclassification",self.contract["phase6eq_policy"])

    def test_matrix_is_guarded_and_fail_fast(self):
        text=(SCRIPTS/"run_phase6er_formal_matrix.ps1").read_text(encoding="utf-8")
        self.assertIn("phase6eg_resource_guard.py",text);self.assertIn("normal_exit",text)
        self.assertIn("incremental gate failed",text);self.assertIn("pair gate failed",text)
        self.assertGreaterEqual(text.count("| Out-Host"),3)
        self.assertNotIn("retry",text.lower())

    def test_support_radius_remains_an_engineering_assumption(self):
        self.assertIn("not a public Flow support radius",self.contract["support_radius"]["status"])

    def test_published_safe_stop_is_partial_and_fail_closed(self):
        report=json.loads(SAFE_STOP.read_text(encoding="utf-8"))
        self.assertEqual("safe_stop",report["status"])
        self.assertFalse(report["overall_qualified"])
        self.assertEqual(4,report["formal"]["processes_completed_as_partial_evidence"])
        self.assertEqual(0,report["formal"]["accepted_complete_population"])
        self.assertEqual(
            ["temperature_opposite_ratio","temperature_far_ratio","smoke_opposite_ratio"],
            report["formal"]["failed_gates"],
        )
        self.assertFalse(report["formal"]["automatic_retry"])
        self.assertFalse(report["formal"]["later_condition_started"])
        self.assertFalse(report["formal"]["video_generated"])

    def test_phase6eq_and_latest_demo_remain_unchanged(self):
        report=json.loads(SAFE_STOP.read_text(encoding="utf-8"))
        latest=json.loads((ROOT/"docs/devlog/assets/latest_demo.json").read_text(encoding="utf-8"))
        self.assertTrue(report["phase6eq_frozen"])
        self.assertFalse(report["phase6eq_reclassified"])
        self.assertFalse(report["phase6eq_remaining_conditions_restarted"])
        self.assertFalse(report["production"]["changed"])
        self.assertNotEqual("phase6er",latest["phase"])

    def test_devlog_records_safe_stop_without_phase6er_video(self):
        html=(ROOT/"docs/devlog/index.html").read_text(encoding="utf-8")
        section=html.split('id="phase-6er"',1)[1].split('id="phase-6eq"',1)[0]
        self.assertIn("0 / 24 accepted",section)
        self.assertIn("latest demo",section)
        self.assertNotIn("data-video-src",section)


if __name__=="__main__":unittest.main()
