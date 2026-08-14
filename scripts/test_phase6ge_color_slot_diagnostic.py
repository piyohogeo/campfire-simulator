import hashlib
import json
import unittest
from pathlib import Path

from phase6ge_next_condition_gate import evaluate, fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6GeColorSlotDiagnostic(unittest.TestCase):
    def test_contract_hash_and_diagnostic_limits(self):
        path = SCRIPTS / "phase6ge_color_slot_diagnostic_contract.json"
        expected = (SCRIPTS / "phase6ge_color_slot_diagnostic_contract.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), expected)
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(contract["controls"]["order"], ["C0", "C1", "C2"])
        self.assertEqual(contract["controls"]["runtime_mode"], {"C0": "baseline", "C1": "rgba", "C2": "rgb"})
        limits = contract["diagnostic_resource_limits"]
        self.assertEqual(limits["kit_private_limit_bytes"], 20 * 1024**3)
        self.assertEqual(limits["unique_tree_private_limit_bytes"], 21 * 1024**3)
        self.assertEqual(limits["physical_memory_floor_bytes"], 32 * 1024**3)
        self.assertEqual(limits["commit_headroom_floor_bytes"], 32 * 1024**3)
        self.assertFalse(limits["may_replace_phase6fz_or_formal_limits"])

    def test_existing_formal_resource_contract_is_unchanged(self):
        base = json.loads((SCRIPTS / "phase6gc_supply_comparison_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(base["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(base["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)

    def test_phase6gf_contract_freezes_prekit_safe_stop(self):
        path = SCRIPTS / "phase6gf_color_slot_diagnostic_contract.json"
        expected = (SCRIPTS / "phase6gf_color_slot_diagnostic_contract.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), expected)
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(contract["history"]["phase6ge_prekit_safe_stop_reclassified"])
        self.assertFalse(contract["history"]["phase6ge_artifact_reused"])

    def test_real_case_runner_accepts_corrected_phase_token(self):
        case_runner = (SCRIPTS / "run_phase6fo_supply_case.ps1").read_text(encoding="utf-8")
        fixture = (SCRIPTS / "run_phase6gf_parameter_binding_fixture.ps1").read_text(encoding="utf-8")
        self.assertIn('"phase6ge", "phase6gf"', case_runner)
        self.assertIn("-ReportPhase phase6gf", fixture)
        self.assertIn("-ValidateArgumentsOnly", fixture)

    def test_next_condition_fixture_matrix(self):
        report = fixtures()
        self.assertEqual(report["status"], "pass")
        self.assertEqual((report["passed"], report["total"]), (8, 8))

    def test_unknown_lifecycle_blocks_next_condition(self):
        result = evaluate(
            {
                "process_exit_code": None,
                "outcome": {"functional_status": "pass", "lifecycle_status": "unknown_shutdown_failure", "normal_exit_sample_accepted": False, "os_process_normal_exit": False},
                "shutdown_monitor": {"residual_process": True},
            },
            {"status": "ok", "exit_code": 0, "observed_process_cleanup": {"all_observed_absent": True}},
        )
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["next_condition_allowed"])

    def test_runner_requires_exact_elevated_contract_and_fast_exit(self):
        body = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        for value in ("21474836480", "22548578304", "34359738368"):
            self.assertIn(value, body)
        self.assertIn('$sampleFrames = "60,120,180"', body)
        self.assertIn('$stabilityObservationExtraSeconds = 0', body)
        self.assertIn("diagnostic/cleanup axes", body)

    def test_orchestrator_is_sequential_and_stops_on_failure(self):
        body = (SCRIPTS / "run_phase6ge_color_slot_diagnostic.ps1").read_text(encoding="utf-8")
        self.assertIn('foreach ($condition in @($contract.controls.order))', body)
        self.assertIn('if ($process.ExitCode -ne 0)', body)
        self.assertIn('if ($LASTEXITCODE -ne 0)', body)
        self.assertIn('formal_s93_s100_population_started = $false', body)


if __name__ == "__main__":
    unittest.main()
