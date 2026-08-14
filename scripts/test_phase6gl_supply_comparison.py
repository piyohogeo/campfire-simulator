import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class Phase6GLContractTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "phase6gl_supply_comparison_contract.json"
        self.contract = json.loads(self.path.read_text(encoding="utf-8"))

    def test_frozen_contract_hash_and_population(self):
        declared = (ROOT / "phase6gl_supply_comparison_contract.sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest().upper(), declared)
        self.assertEqual(self.contract["formal_population"]["required_representative_processes"], 9)
        self.assertEqual(self.contract["formal_population"]["maximum_formal_launches"], 11)
        self.assertEqual(self.contract["formal_population"]["startup_prerequisite_replacement_budget"], 2)

    def test_schema_and_artifact_boundary(self):
        schema = self.contract["public_channel_schema"]
        self.assertEqual(schema["expected_handle_count"], 7)
        self.assertEqual(schema["exact_order"], [
            "temperature", "fuel", "burn", "smoke", "velocity", "divergence", "rgba"])
        self.assertEqual(schema["canonical_artifact_property"], "field_body_json_npz_or_openvdb_written")
        self.assertFalse(schema["runtime_legacy_property_allowed"])
        probe = (ROOT / "probe_phase6gl_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn('"field_body_json_npz_or_openvdb_written": False', probe)
        self.assertNotIn('"full_field_json_or_npz_written"', probe)

    def test_physics_and_safety_are_frozen(self):
        gates = self.contract["hard_gates"]
        self.assertEqual(gates["maximum_collision_on_deep_velocity_m_s"], 1e-4)
        self.assertEqual(gates["minimum_collision_off_deep_velocity_m_s"], 0.1)
        self.assertEqual(gates["maximum_s100_to_off_deep_velocity_ratio"], 0.01)
        self.assertEqual(gates["minimum_s100_to_s93_weighted_supply_ratio"], 1.07)
        self.assertEqual(gates["maximum_s100_to_s93_deep_scalar_excess_ratio"], 1.25)
        self.assertEqual(gates["maximum_s100_to_s93_opposite_transport_ratio"], 1.25)
        self.assertEqual(gates["maximum_run_relative_range"], 0.35)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertEqual(self.contract["safety"]["shutdown_order"], "release_after_close")


if __name__ == "__main__":
    unittest.main()
