import hashlib
import json
import unittest
from pathlib import Path

from scripts.phase6fg_paired_readback_policy import evaluate_hard_gate, evaluate_repetition_candidate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "phase6fg_paired_readback_contract.json"


class Phase6FgContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_hash_is_frozen(self):
        expected = (CONTRACT.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]).upper()
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)

    def test_balanced_order_and_scope(self):
        order = self.contract["balanced_order"]
        self.assertEqual(order, [["A_control", "B_readback", "C_fuel_alias"], ["B_readback", "C_fuel_alias", "A_control"], ["C_fuel_alias", "A_control", "B_readback"]])
        for position in range(3):
            self.assertEqual(set(row[position] for row in order), set(self.contract["conditions"]))
        self.assertFalse(self.contract["repetition_candidate"]["runtime_in_this_phase"])

    def test_waveforms_are_warning_only(self):
        self.assertFalse(self.contract["waveform_telemetry"]["formal_gate"])
        self.assertFalse(self.contract["paired_comparison"]["waveform_metrics_are_formal_gate"])

    def _evidence(self):
        return {"guard_status": "ok", "guard_exit_code": 0, "process_absent": True, "cleanup_residual_count": 0,
                "runner_peak_bytes": 1, "diagnostic_peak_bytes": 1, "kit_peak_bytes": 1, "tree_peak_bytes": 1,
                "minimum_available_physical_bytes": 2**40, "minimum_commit_headroom_bytes": 2**40,
                "fatal_count": 0, "access_violation_count": 0, "dump_count": 0, "upload_attempt_count": 0,
                "lifecycle_complete": True, "normal_os_exit": True}

    def test_absolute_and_lifecycle_fail_closed(self):
        evidence = self._evidence()
        self.assertTrue(evaluate_hard_gate(evidence, self.contract["safety"])["gate_pass"])
        evidence["kit_peak_bytes"] = self.contract["safety"]["kit_private_limit_bytes"] + 1
        self.assertFalse(evaluate_hard_gate(evidence, self.contract["safety"])["gate_pass"])
        evidence = self._evidence()
        evidence["normal_os_exit"] = False
        self.assertFalse(evaluate_hard_gate(evidence, self.contract["safety"])["gate_pass"])

    def test_repetition_candidate_distinguishes_plateau_and_staircase(self):
        gib = 2**30
        mib = 2**20
        plateau = [10*gib, 10*gib+128*mib, 10*gib+132*mib, 10*gib+129*mib, 10*gib+134*mib, 10*gib+131*mib]
        staircase = [10*gib + index*64*mib for index in range(6)]
        self.assertTrue(evaluate_repetition_candidate(plateau, self.contract)["gate_pass"])
        self.assertFalse(evaluate_repetition_candidate(staircase, self.contract)["gate_pass"])

    def test_runner_has_no_repeated_readback(self):
        runner = (ROOT / "scripts" / "run_phase6fg_paired_readback.ps1").read_text(encoding="utf-8")
        self.assertIn('"A_control" { "none" }', runner)
        self.assertIn('"B_readback" { "acquire_discard_release" }', runner)
        self.assertIn('"C_fuel_alias" { "fuel_convert_release" }', runner)
        self.assertNotIn("fuel_scalar", runner)
        self.assertIn('"phase6fg"', (ROOT / "scripts" / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
