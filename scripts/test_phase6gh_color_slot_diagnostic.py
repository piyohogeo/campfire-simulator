import hashlib
import json
import unittest
from pathlib import Path

from phase6gh_startup_replacement_policy import fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6GhColorSlotDiagnostic(unittest.TestCase):
    def test_contract_hash_and_population(self):
        path = SCRIPTS / "phase6gh_color_slot_diagnostic_contract.json"
        expected = (SCRIPTS / "phase6gh_color_slot_diagnostic_contract.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), expected)
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(contract["controls"]["order"], ["C0", "C1", "C2"])
        self.assertEqual(contract["population"]["startup_prerequisite_replacement_budget"], 2)
        self.assertEqual(contract["population"]["maximum_total_launches"], 5)
        self.assertTrue(contract["population"]["replaceable_only_when_all_120_samples_equal_24"])

    def test_diagnostic_limits_do_not_change_formal_limits(self):
        contract = json.loads((SCRIPTS / "phase6gh_color_slot_diagnostic_contract.json").read_text())
        limits = contract["diagnostic_resource_limits"]
        self.assertEqual(limits["kit_private_limit_bytes"], 20 * 1024**3)
        self.assertEqual(limits["unique_tree_private_limit_bytes"], 21 * 1024**3)
        formal = json.loads((SCRIPTS / "phase6gc_supply_comparison_contract.json").read_text())
        self.assertEqual(formal["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(formal["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)

    def test_replacement_and_fail_closed_fixtures(self):
        report = fixtures()
        self.assertEqual(report["status"], "pass")
        self.assertEqual((report["passed"], report["total"]), (12, 12))

    def test_shared_runners_accept_phase6gh(self):
        case = (SCRIPTS / "run_phase6fo_supply_case.ps1").read_text(encoding="utf-8")
        child = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        self.assertIn('"phase6gh"', case)
        self.assertIn('"phase6gh"', child)

    def test_no_kit_preflight_uses_real_case_runner(self):
        body = (SCRIPTS / "run_phase6gh_preflight.ps1").read_text(encoding="utf-8")
        self.assertIn("run_phase6fo_supply_case.ps1", body)
        self.assertIn("-ValidateArgumentsOnly", body)
        self.assertIn("-ReportPhase phase6gh", body)


if __name__ == "__main__":
    unittest.main()
