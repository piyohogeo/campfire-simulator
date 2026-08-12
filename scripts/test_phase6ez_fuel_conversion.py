import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_phase6ez_fuel_conversion as analyzer


class Phase6EzFuelConversionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6ez_fuel_conversion_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.runner = (SCRIPTS / "run_phase6ez_fuel_conversion.ps1").read_text(encoding="utf-8")

    def test_contract_hash_and_frozen_phase6ey_boundary(self):
        expected = (SCRIPTS / "phase6ez_fuel_conversion_contract.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper(), expected)
        self.assertEqual(self.contract["phase6ey_history"]["safe_commit"], "6dd497c")
        self.assertFalse(self.contract["phase6ey_history"]["formal_population_reuse"])
        self.assertTrue(self.contract["declared_before_runtime"])

    def test_only_c0_then_c1_and_no_retry(self):
        self.assertEqual([item["id"] for item in self.contract["conditions"]], ["C0_acquire_discard", "C1_fuel_convert"])
        self.assertIn('Invoke-Case "C0_acquire_discard"', self.runner)
        self.assertIn('Invoke-Case "C1_fuel_convert"', self.runner)
        self.assertLess(self.runner.index('Invoke-Case "C0_acquire_discard"'), self.runner.index('Invoke-Case "C1_fuel_convert"'))
        self.assertFalse(self.contract["execution"]["automatic_retry"])
        self.assertEqual(self.contract["execution"]["maximum_kit_processes"], 2)
        self.assertIn('"phase6eg_resource_guard.py"', self.runner)
        self.assertTrue((SCRIPTS / "phase6eg_resource_guard.py").is_file())

    def test_public_boundary_and_forbidden_operations_are_fixed(self):
        boundary = self.contract["public_api_boundary"]
        self.assertEqual(boundary["fuel_channel_index"], 1)
        self.assertEqual(boundary["existing_conversion_call"], "numpy.asarray(fuel_handle)")
        self.assertFalse(boundary["public_release_api_used"])
        self.assertFalse(boundary["private_release_api_used"])
        self.assertFalse(self.contract["safety"]["large_field_persistence"])
        self.assertFalse(self.contract["safety"]["forced_gc"])
        self.assertFalse(self.contract["safety"]["resource_ceiling_change"])

    def test_exact_release_modes_and_markers_exist(self):
        for token in (
            '"acquire_discard_release"', '"fuel_convert_release"',
            '"fuel_handle_selected"', '"fuel_conversion_before"', '"fuel_conversion_after"',
            '"original_tuple_and_all_handle_aliases_released"',
            '"converted_buffer_only_held"', '"converted_buffer_released"',
        ):
            self.assertIn(token, self.probe)
        self.assertIn('"phase6ez"', self.case_runner)
        self.assertIn('"fuel_convert_release"', self.case_runner)
        self.assertIn("del value", self.probe)
        self.assertNotIn("gc.collect()", self.probe[self.probe.index("if exact_release_mode") : self.probe.index("array = None", self.probe.index("if exact_release_mode"))])

    def test_marker_order_helper_is_fail_closed(self):
        required = ["a", "b", "c"]
        self.assertTrue(analyzer._ordered([{"marker": "a"}, {"marker": "b"}, {"marker": "c"}], required))
        self.assertFalse(analyzer._ordered([{"marker": "a"}, {"marker": "c"}, {"marker": "b"}], required))
        self.assertFalse(analyzer._ordered([{"marker": "a"}, {"marker": "b"}], required))

    def test_resource_ceilings_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)


if __name__ == "__main__":
    unittest.main()
