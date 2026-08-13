import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6FpContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((SCRIPTS / "phase6fp_pre_readback_allocation_contract.json").read_text(encoding="utf-8"))

    def test_population_is_frozen_and_balanced(self):
        conditions = [item["id"] for item in self.contract["conditions"]]
        orders = self.contract["population"]["orders"]
        self.assertEqual(3, len(orders))
        self.assertEqual(24, self.contract["population"]["required_representative_processes"])
        for order in orders:
            self.assertEqual(sorted(conditions), sorted(order))

    def test_physics_and_safety_are_unchanged(self):
        fixture = self.contract["physical_fixture"]
        self.assertEqual("production_four", fixture["scenario"])
        self.assertEqual("phase6er_corrected", fixture["geometry_variant"])
        self.assertEqual("allow_self_center", fixture["point_policy"])
        self.assertEqual(1344, fixture["expected_active_points"])
        self.assertEqual(14 * 1024**3, self.contract["safety"]["kit_private_limit_bytes"])
        self.assertFalse(self.contract["safety"]["candidate_16_gib_adopted"])

    def test_pre_readback_body_is_not_invented(self):
        boundary = self.contract["pre_readback_allocation_boundary"]
        self.assertTrue(boundary["near_mesh_body_requires_public_grid_metadata"])
        self.assertFalse(boundary["grid_metadata_available_before_readback"])
        self.assertEqual(0, boundary["buffer_body_logical_bytes_before_readback"])

    def test_probe_and_runner_expose_calibration_boundary(self):
        probe = (SCRIPTS / "probe_phase6fo_supply_comparison.py").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6fo_supply_case.ps1").read_text(encoding="utf-8")
        self.assertIn("_phase6fp_allocation_state", probe)
        self.assertIn("allocation_calibration_prepared", probe)
        self.assertIn("AllocationCalibrationLevel", runner)
        self.assertIn('"phase6fp"', runner)


if __name__ == "__main__":
    unittest.main()
