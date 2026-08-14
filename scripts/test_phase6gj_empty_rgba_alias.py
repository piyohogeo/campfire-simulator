import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import phase6gj_empty_rgba_alias_policy as policy


class Phase6GJEmptyRgbaAliasTests(unittest.TestCase):
    def setUp(self):
        self.contract = policy.load_json(policy.DEFAULT_CONTRACT)

    def test_offline_fixtures(self):
        result = policy.run_fixtures(self.contract)
        self.assertTrue(result["all_pass"])
        self.assertTrue(result["raw_artifact_end_to_end_pass"])
        self.assertEqual(result["passed"], result["total"])

    def test_empty_same_object_zero_byte_does_not_require_sharing(self):
        observed = policy.normal_observation(self.contract)
        self.assertFalse(observed["handles"][6]["alias_contract"]["shares_memory"])
        self.assertTrue(policy.validate_preflight(observed, self.contract)["pass"])

    def test_nonempty_still_requires_sharing(self):
        observed = policy.normal_observation(self.contract)
        observed["handles"][0]["alias_contract"]["shares_memory"] = False
        result = policy.validate_preflight(observed, self.contract)
        self.assertFalse(result["pass"])
        self.assertIn("nonempty_shared_memory_required", result["reasons"])

    def test_raw_artifact_round_trip(self):
        observed = policy.normal_observation(self.contract)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded_handle_metadata.json"
            path.write_text(json.dumps(observed), encoding="utf-8")
            self.assertTrue(policy.validate_preflight(policy.load_json(path), self.contract)["pass"])

    def test_contract_keeps_normal_limits_and_authorization_boundary(self):
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertFalse(self.contract["authorization_boundary"]["formal_s93_s100_off_population_allowed"])
        self.assertFalse(self.contract["alias_gate"]["empty"]["numpy_shares_memory_required"])

    def test_probe_does_not_convert_or_persist_field_body(self):
        body = (SCRIPTS / "probe_phase6gj_s93_channel_preflight.py").read_text(encoding="utf-8")
        self.assertNotIn("np.asarray(", body)
        self.assertIn('"numpy_asarray_called": False', body)
        self.assertIn("handles[index] = None", body)
        self.assertIn('"shares_memory_required": bool(source.size > 0)', body)

    def test_runner_reuses_shared_lifecycle(self):
        body = (SCRIPTS / "run_phase6gj_s93_channel_preflight.ps1").read_text(encoding="utf-8")
        self.assertIn("run_phase6gd_channel_metadata_probe.ps1", body)
        child = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        self.assertIn('"after_stage_close"', child)


if __name__ == "__main__":
    unittest.main()
