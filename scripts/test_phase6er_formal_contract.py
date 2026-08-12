from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/"scripts"


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


if __name__=="__main__":unittest.main()
