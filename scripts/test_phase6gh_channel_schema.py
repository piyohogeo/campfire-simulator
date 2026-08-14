import hashlib
import json
import unittest
from pathlib import Path

import phase6gh_channel_schema_policy as policy


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6GhChannelSchema(unittest.TestCase):
    def test_candidate_schema_hash(self):
        path = SCRIPTS / "phase6gh_public_channel_schema_candidate.json"
        sidecar = (SCRIPTS / "phase6gh_public_channel_schema_candidate.sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), sidecar)

    def test_candidate_maps_rgba_only(self):
        schema = policy.load_schema()
        self.assertEqual(schema["exact_order"][6], "rgba")
        self.assertEqual(schema["handles"][6]["value_type"], "17")
        self.assertFalse(schema["rgb_observation"]["shares_handle_6_with_rgba"])
        self.assertFalse(schema["compatibility"]["legacy_six_handle_schema_accepted"])

    def test_offline_fixtures(self):
        result = policy.run_fixtures(policy.load_schema())
        self.assertTrue(result["all_pass"])
        self.assertEqual(result["passed"], 12)
        self.assertEqual(result["total"], 12)

    def test_required_scalar_cannot_be_empty(self):
        schema = policy.load_schema()
        observed = policy.normal_observation(schema)
        observed["handles"][1]["empty"] = True
        self.assertFalse(policy.validate_candidate(observed, schema)["pass"])

    def test_formal_population_remains_blocked(self):
        schema = json.loads((SCRIPTS / "phase6gh_public_channel_schema_candidate.json").read_text(encoding="utf-8"))
        boundary = schema["authorization_boundary"]
        self.assertFalse(boundary["formal_s93_s100_population_started"])
        self.assertFalse(boundary["channel_preflight_qualified"])
        self.assertFalse(boundary["production_integration_allowed"])


if __name__ == "__main__":
    unittest.main()
