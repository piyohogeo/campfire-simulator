import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import phase6gi_channel_preflight_policy as policy


class Phase6GIChannelPreflightTests(unittest.TestCase):
    def test_offline_fixtures(self):
        result = policy.run_fixtures(policy.load_json(policy.DEFAULT_CONTRACT))
        self.assertTrue(result["all_pass"])
        self.assertEqual(result["passed"], result["total"])

    def test_contract_normal_limits_and_scope(self):
        contract = policy.load_json(policy.DEFAULT_CONTRACT)
        self.assertEqual(contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertFalse(contract["authorization_boundary"]["formal_s93_s100_off_population_allowed"])
        self.assertEqual(contract["condition"]["public_readback_calls"], 1)

    def test_probe_is_bounded_and_ordered(self):
        body = (SCRIPTS / "probe_phase6gi_s93_channel_preflight.py").read_text(encoding="utf-8")
        self.assertIn("validate_raw_schema", body)
        self.assertIn("handles[index] = None", body)
        self.assertIn('"numpy_asarray_called": False', body)
        self.assertNotIn("np.asarray(", body)
        self.assertIn("weak_reference_alive_after_slot_clear", body)

    def test_runner_reuses_shared_lifecycle(self):
        body = (SCRIPTS / "run_phase6gi_s93_channel_preflight.ps1").read_text(encoding="utf-8")
        self.assertIn("run_phase6gd_channel_metadata_probe.ps1", body)
        child = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        self.assertIn('"after_stage_close"', child)


if __name__ == "__main__":
    unittest.main()
