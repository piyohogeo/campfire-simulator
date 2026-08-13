import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT_PATH = SCRIPTS / "phase6fd_fuel_alias_lifetime_contract.json"


class Phase6FdFuelAliasLifetime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6fd_fuel_alias_lifetime.ps1").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        cls.analyzer = (SCRIPTS / "analyze_phase6fd_fuel_alias_lifetime.py").read_text(encoding="utf-8")

    def test_contract_hash_and_frozen_history(self):
        expected = (SCRIPTS / "phase6fd_fuel_alias_lifetime_contract.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest().upper(), expected)
        self.assertEqual(self.contract["history"]["safe_commit"], "5a9bc6c")
        self.assertFalse(self.contract["history"]["prior_population_reuse"])
        self.assertIn("not evidence that the issue is solved", self.contract["history"]["phase6fc"])

    def test_startup_order_and_pre_readback_gate_are_fixed(self):
        startup = self.contract["startup"]
        self.assertEqual(startup["classification_frame"], 60)
        self.assertEqual(startup["final_frame"], 120)
        self.assertEqual(startup["representative_active_blocks"], 128)
        self.assertEqual(startup["stopped_update_count"], 12)
        self.assertEqual(self.contract["readback_frame"], 120)
        self.assertTrue(startup["delayed_or_small_field_stops_before_readback"])
        self.assertFalse(startup["automatic_retry"])
        self.assertFalse(startup["automatic_recovery"])

    def test_probe_blocks_readback_until_representative_startup(self):
        self.assertIn('"startup_liveness_gate"', self.probe)
        self.assertIn('"startup_liveness_confirmed"', self.probe)
        self.assertIn('"startup_liveness_pending"', self.probe)
        self.assertIn('"startup_liveness_rejected"', self.probe)
        self.assertIn('readback blocked because startup liveness was not confirmed', self.probe)
        self.assertIn('startup liveness gate forbids readback before frame 120', self.probe)

    def test_only_c0_then_c1_and_single_alias_call(self):
        self.assertLess(self.runner.index('"C0_acquire_discard"'), self.runner.index('"C1_fuel_alias"'))
        self.assertIn('if ($reason) { Stop-Safely $completed "C0_acquire_discard" $reason }', self.runner)
        self.assertIn('"-StartupLivenessGate", "true"', self.runner)
        self.assertIn('"-ReadbackFrames", "$($contract.readback_frame)"', self.runner)
        self.assertEqual(self.probe.count("array = np.asarray(source)"), 2)  # exact and historical modes
        self.assertEqual(self.contract["conditions"][1]["conversion_calls"], 1)

    def test_forbidden_scope_and_resource_ceilings(self):
        excluded = " ".join(self.contract["excluded"])
        for phrase in ("repeated readback", "other-channel conversion", "forced GC", "production integration"):
            self.assertIn(phrase, excluded)
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(self.contract["lifecycle"]["stage_close_timeout_seconds"], 180)

    def test_analyzer_is_fail_closed_on_startup_and_lifecycle(self):
        self.assertIn('startup_not_representative', self.analyzer)
        self.assertIn('readback_before_startup_gate', self.analyzer)
        self.assertIn('channel_weak_reference_residual', self.analyzer)
        self.assertIn('fatal_dump_or_upload', self.analyzer)
        self.assertIn('shutdown_classification', self.analyzer)
        self.assertIn('repeated_readback_qualified', self.analyzer)

    def test_startup_monitoring_is_not_recovery(self):
        disposition = self.contract["startup_monitoring_disposition"]
        self.assertEqual(disposition["status"], "low-frequency monitoring issue")
        self.assertTrue(disposition["retain_detailed_markers"])
        self.assertFalse(disposition["additional_repetition_without_new_evidence"])
        self.assertFalse(disposition["automatic_recovery_implemented"])


if __name__ == "__main__":
    unittest.main()
