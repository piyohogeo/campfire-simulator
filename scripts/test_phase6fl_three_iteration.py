import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_phase6fl_three_iteration import evaluate_staircase
from scripts.phase6fk_pointer_evidence import pointer_evidence_from_boundary


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "phase6fl_three_iteration_contract.json"


class Phase6FlThreeIterationContract(unittest.TestCase):
    def test_first_cache_then_plateau_is_accepted(self):
        self.assertTrue(evaluate_staircase([100, 300, 305], 50)["gate_pass"])

    def test_r0_like_variance_is_accepted(self):
        self.assertTrue(evaluate_staircase([300, 240, 290], 50)["gate_pass"])

    def test_two_material_steps_are_rejected(self):
        result = evaluate_staircase([100, 160, 230], 50)
        self.assertFalse(result["gate_pass"])
        self.assertIn("material_two_step_staircase", result["failures"])

    def test_incomplete_baseline_fails_closed(self):
        self.assertFalse(evaluate_staircase([100, 120], 50)["gate_pass"])

    def test_contract_is_exactly_three_iterations_and_balanced(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["operation_frames"], [120, 360, 600])
        self.assertEqual(contract["population"]["target_representative_processes"], 9)
        self.assertEqual(contract["population"]["startup_prerequisite_replacement_budget"], 2)
        self.assertEqual(contract["population"]["maximum_launches"], 11)
        self.assertEqual(contract["balanced_order"], [
            ["R0_control", "R1_readback", "R2_fuel_alias"],
            ["R1_readback", "R2_fuel_alias", "R0_control"],
            ["R2_fuel_alias", "R0_control", "R1_readback"],
        ])

    def test_contract_keeps_hard_limits_and_no_slope_gate(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["absolute_safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(contract["absolute_safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertFalse(contract["waveform_telemetry"]["slope_is_formal_gate"])
        self.assertFalse(contract["qualification"]["more_than_three_iterations_qualified"])

    def test_settling_is_finite_and_sample_bounded(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        settling = contract["settling"]
        self.assertGreaterEqual(settling["minimum_wall_seconds"], 4.0)
        self.assertGreaterEqual(settling["minimum_outer_resource_samples"], 8)
        self.assertGreaterEqual(settling["minimum_renderer_updates"], 60)
        self.assertGreater(settling["final_extra_running_flow_seconds"], settling["minimum_wall_seconds"])

    def test_pointer_missing_and_mismatch_are_rejected(self):
        missing = pointer_evidence_from_boundary({})
        self.assertFalse(missing["complete"])
        mismatch = pointer_evidence_from_boundary({
            "fuel_source": {
                "python_identity": 10, "data_pointer": 100, "shape": [4], "dtype": "uint32",
                "strides": [4], "element_count": 4, "nbytes": 16,
            },
            "fuel_array": {
                "python_identity": 10, "data_pointer": 200, "shape": [4], "dtype": "uint32",
                "strides": [4], "element_count": 4, "nbytes": 16,
                "same_identity_as_source": True, "shares_memory_with_source": True,
            },
            "observable_copy_contract": {
                "source_data_pointer": 100, "converted_data_pointer": 200,
                "same_data_pointer": False, "same_python_identity": True, "shares_memory": True,
            },
            "weak_reference_alive_after_scope_count": 0,
            "converted_weak_reference_alive_immediately_after_release": False,
        })
        self.assertFalse(mismatch["complete"])
        self.assertTrue(any("pointer" in item for item in mismatch["failures"]))

    def test_contract_fails_closed_for_calls_weak_lifecycle_and_absolute_limits(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertIn("operation failure", contract["nonreplaceable"])
        self.assertIn("weak reference residual", contract["nonreplaceable"])
        self.assertIn("native lifecycle failure", contract["nonreplaceable"])
        self.assertIn("resource or headroom failure", contract["nonreplaceable"])
        runner = (ROOT / "scripts" / "run_phase6fl_three_iteration.ps1").read_text(encoding="utf-8")
        self.assertIn('Write-Error "Phase 6FL captured nonreplaceable', runner)
        self.assertIn("exit 2", runner)


if __name__ == "__main__":
    unittest.main()
