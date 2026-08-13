import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "phase6ft_memory_ceiling_qualification_contract.json"
RUNNER = ROOT / "scripts" / "run_phase6ft_memory_ceiling_qualification.ps1"
CASE_RUNNER = ROOT / "scripts" / "run_phase6fo_supply_case.ps1"
PROBE = ROOT / "scripts" / "probe_phase6fo_supply_comparison.py"
ANALYZER = ROOT / "scripts" / "analyze_phase6ft_memory_ceiling_qualification.py"


class Phase6FtMemoryCeilingQualification(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.runner = RUNNER.read_text(encoding="utf-8")
        self.case_runner = CASE_RUNNER.read_text(encoding="utf-8")
        self.probe = PROBE.read_text(encoding="utf-8")
        self.analyzer = ANALYZER.read_text(encoding="utf-8")

    def test_population_and_frames_are_frozen(self):
        self.assertEqual(
            [
                ["M0_baseline", "M1_phase6fo_equivalent", "M2_pre_readback_frame"],
                ["M1_phase6fo_equivalent", "M2_pre_readback_frame", "M0_baseline"],
                ["M2_pre_readback_frame", "M0_baseline", "M1_phase6fo_equivalent"],
            ],
            self.contract["population"]["orders"],
        )
        self.assertEqual(9, self.contract["population"]["required_representative_processes"])
        m2 = next(row for row in self.contract["conditions"] if row["id"] == "M2_pre_readback_frame")
        self.assertEqual(179, m2["terminal_frame"])
        self.assertEqual(180, m2["planned_phase6fo_first_readback_frame"])

    def test_resource_limits_are_separated_and_margin_is_predeclared(self):
        safety = self.contract["safety"]
        self.assertEqual(14 * 1024**3, safety["legacy_kit_evaluation_threshold_bytes"])
        self.assertFalse(safety["legacy_threshold_is_kill_condition"])
        self.assertEqual(16 * 1024**3, safety["kit_provisional_hard_limit_bytes"])
        self.assertEqual(17 * 1024**3, safety["unique_tree_provisional_hard_limit_bytes"])
        self.assertEqual(512 * 1024**2, safety["minimum_candidate_headroom_bytes"])
        self.assertEqual(16 * 1024**3 - 512 * 1024**2, safety["candidate_peak_maximum_bytes"])
        self.assertIn('"--kit-private-limit", "$($contract.safety.kit_provisional_hard_limit_bytes)"', self.runner)
        self.assertIn('"--tree-private-limit", "$($contract.safety.unique_tree_provisional_hard_limit_bytes)"', self.runner)

    def test_release_after_close_and_zero_readback_are_fixed(self):
        self.assertEqual("after_stage_close", self.contract["lifecycle"]["reference_release_order"])
        self.assertIn('"-LifecycleReferenceReleaseOrder", $contract.lifecycle.reference_release_order', self.runner)
        self.assertIn('"-ReadbackChannels", "none", "-ReadbackMode", "none"', self.runner)
        self.assertIn('"-CapturePreparationMode", "none"', self.runner)
        self.assertIn('"phase6ft"', self.case_runner)
        self.assertIn('"phase6ft"', self.probe)

    def test_public_field_is_not_inferred_without_readback(self):
        recording = self.contract["recording"]
        self.assertIn("unavailable_without_readback", recording["public_field_shape_and_logical_bytes"])
        self.assertIn('"reason": "unavailable_without_readback"', self.analyzer)
        self.assertIn('"estimated": False', self.analyzer)

    def test_persistent_accumulation_is_not_a_slope_gate(self):
        self.assertFalse(self.contract["boundedness"]["slope_alone_is_gate"])
        rule = self.contract["boundedness"]["persistent_unexplained_accumulation"]
        self.assertEqual(10, rule["sample_count"])
        self.assertEqual(512 * 1024**2, rule["minimum_total_rise_bytes"])
        self.assertIn("persistent_unexplained_accumulation", self.analyzer)

    def test_contract_hash_sidecar_when_present(self):
        sidecar = CONTRACT.with_suffix(".sha256")
        if not sidecar.exists():
            self.skipTest("hash sidecar is written only after the contract is frozen")
        expected = sidecar.read_text(encoding="utf-8").split()[0].upper()
        actual = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
