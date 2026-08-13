import hashlib
import json
import unittest
from pathlib import Path

from scripts.analyze_phase6fm_settled_three_iteration import _field_adjusted_pair
from scripts.analyze_phase6fl_three_iteration import evaluate_staircase
from scripts.phase6fk_pointer_evidence import pointer_evidence_from_boundary


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6fm_settled_three_iteration_contract.json"


class Phase6FmSettledThreeIteration(unittest.TestCase):
    def test_pre_operation_growth_is_not_the_formal_gate(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(contract["accumulation_gate"]["pre_operation_is_formal"])
        self.assertEqual(contract["accumulation_gate"]["formal_baseline"], "explicit_settling_end_after_ordered_release")
        analyzer = (ROOT / "scripts/analyze_phase6fm_settled_three_iteration.py").read_text(encoding="utf-8")
        self.assertIn('"formal_gate_uses_pre_operation": False', analyzer)
        self.assertIn('"formal_gate_uses_explicit_settling_end": True', analyzer)

    def test_cache_plateau_r0_variance_and_delayed_recovery_pass(self):
        threshold = 50
        self.assertTrue(evaluate_staircase([100, 300, 305], threshold)["gate_pass"])
        self.assertTrue(_field_adjusted_pair([100, 160, 230], [200, 260, 330], [40, 40, 40], threshold)["field_adjusted_gate_pass"])
        self.assertTrue(_field_adjusted_pair([100, 160, 230], [400, 300, 350], [40, 40, 40], threshold)["field_adjusted_gate_pass"])

    def test_field_growth_explains_finite_growth(self):
        result = _field_adjusted_pair([100, 100, 100], [200, 320, 440], [40, 160, 280], 50)
        self.assertTrue(result["field_adjusted_gate_pass"])
        self.assertFalse(result["field_adjusted_staircase"])

    def test_unexplained_two_step_staircase_fails(self):
        result = _field_adjusted_pair([100, 100, 100], [200, 320, 450], [40, 45, 50], 50)
        self.assertFalse(result["field_adjusted_gate_pass"])
        self.assertTrue(result["field_adjusted_staircase"])

    def test_missing_field_context_fails_closed(self):
        result = _field_adjusted_pair([100, 100, 100], [200, 320, 450], [None, None, None], 50)
        self.assertFalse(result["field_adjusted_gate_pass"])
        self.assertIn("field_context_required", result["failures"])

    def test_exact_marker_and_non_operation_sentinel_contract(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["operation_frames"], [120, 360, 540])
        self.assertEqual(contract["settling_end_frames"], [360, 540, 620])
        self.assertTrue(contract["explicit_marker_contract"]["frame_620_is_readback_free_non_operation_sentinel"])
        probe = (ROOT / "scripts/probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        for marker in ("pre_operation", "operation_completed", "release_completed", "settling_started", "settling_end"):
            self.assertIn(f'"{marker}"', probe)
        self.assertIn('frame not in arguments["operation_frames"]', probe)

    def test_population_replacement_and_hard_limits_are_frozen(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["population"]["target_representative_processes"], 9)
        self.assertEqual(contract["population"]["startup_prerequisite_replacement_budget"], 2)
        self.assertEqual(contract["population"]["maximum_launches"], 11)
        self.assertEqual(contract["absolute_safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(contract["absolute_safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(contract["absolute_safety"]["stage_close_timeout_seconds"], 180)
        self.assertEqual(sum(contract["absolute_safety"][name] for name in (
            "cdb_module_seconds", "cdb_all_thread_stack_seconds", "cdb_detach_recovery_seconds"
        )), 105)

    def test_two_sequence_reproduction_is_required(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["accumulation_gate"]["minimum_reproducing_sequences"], 2)
        analyzer = (ROOT / "scripts/analyze_phase6fm_settled_three_iteration.py").read_text(encoding="utf-8")
        self.assertIn("len(sequences) >= contract", analyzer)

    def test_pointer_missing_or_mismatch_is_still_failure(self):
        self.assertFalse(pointer_evidence_from_boundary({})["complete"])
        boundary = {
            "fuel_source": {"python_identity": 1, "data_pointer": 100, "shape": [4], "dtype": "uint32", "strides": [4], "element_count": 4, "nbytes": 16},
            "fuel_array": {"python_identity": 1, "data_pointer": 200, "shape": [4], "dtype": "uint32", "strides": [4], "element_count": 4, "nbytes": 16, "same_identity_as_source": True, "shares_memory_with_source": True},
            "observable_copy_contract": {"source_data_pointer": 100, "converted_data_pointer": 200, "same_data_pointer": False, "same_python_identity": True, "shares_memory": True},
            "weak_reference_alive_after_scope_count": 0,
            "converted_weak_reference_alive_immediately_after_release": False,
        }
        self.assertFalse(pointer_evidence_from_boundary(boundary)["complete"])

    def test_prelaunch_regressions_are_fail_closed_not_replacements(self):
        runner = (ROOT / "scripts/run_phase6fm_settled_three_iteration.ps1").read_text(encoding="utf-8")
        self.assertIn('if (-not [string]::IsNullOrWhiteSpace($readbackCsv))', runner)
        self.assertIn('"-ReportPhase", $contract.embedded_probe_report_phase', runner)
        self.assertIn('Write-Error "Phase 6FM captured nonreplaceable', runner)
        old_analyzer = (ROOT / "scripts/analyze_phase6fl_three_iteration.py").read_text(encoding="utf-8")
        self.assertIn('item.get("name") or item.get("marker")', old_analyzer)

    def test_contract_hash_and_runtime_hashes_match(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for item in contract["runtime_implementation"]:
            self.assertEqual(hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest().upper(), item["sha256"])
        hash_path = CONTRACT.with_suffix(".sha256")
        expected = hash_path.read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)


if __name__ == "__main__":
    unittest.main()
