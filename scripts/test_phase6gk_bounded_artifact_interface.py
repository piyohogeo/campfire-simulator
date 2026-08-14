import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import phase6gk_bounded_artifact_interface as interface
import phase6gj_empty_rgba_alias_policy as alias_policy


class Phase6GKBoundedArtifactInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.contract_path = SCRIPTS / "phase6gk_bounded_artifact_interface_contract.json"
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))

    def assert_case(self, payload, accepted, mode):
        normalized, report = interface.normalize(payload)
        self.assertEqual(report["pass"], accepted)
        self.assertEqual(report["normalization_mode"], mode)
        if accepted:
            self.assertIsNotNone(normalized)
            self.assertIn(interface.CANONICAL, normalized)
            self.assertNotIn(interface.LEGACY, normalized)
            self.assertFalse(normalized[interface.CANONICAL])

    def test_canonical_legacy_and_dual_policies(self):
        self.assert_case({interface.CANONICAL: False}, True, "canonical_only")
        self.assert_case({interface.LEGACY: False}, True, "legacy_normalized")
        self.assert_case(
            {interface.CANONICAL: False, interface.LEGACY: False},
            True,
            "dual_equal_normalized",
        )
        self.assert_case(
            {interface.CANONICAL: False, interface.LEGACY: True},
            False,
            "invalid",
        )

    def test_missing_null_nonboolean_and_write_are_fail_closed(self):
        for payload in (
            {},
            {interface.CANONICAL: None},
            {interface.CANONICAL: "false"},
            {interface.CANONICAL: 0},
            {interface.CANONICAL: True},
        ):
            with self.subTest(payload=payload):
                _, report = interface.normalize(payload)
                self.assertFalse(report["pass"])

    def test_new_probe_emits_only_the_canonical_property(self):
        body = (SCRIPTS / "probe_phase6gk_s93_channel_preflight.py").read_text(encoding="utf-8")
        self.assertIn(f'"{interface.CANONICAL}": False', body)
        self.assertNotIn(interface.LEGACY, body)
        self.assertNotIn("np.asarray(", body)

    def test_shared_runner_has_explicit_normalization_boundary(self):
        child = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        self.assertIn("BoundedArtifactFixtureInput", child)
        self.assertIn("phase6gk_bounded_artifact_interface.py", child)
        self.assertIn("bounded_artifact_interface_normalized", child)
        self.assertIn('$metadata.PSObject.Properties[$canonicalName]', child)

    def test_contract_preserves_alias_schema_and_authorization(self):
        self.assertEqual(
            self.contract["bounded_artifact_interface"]["canonical_property"],
            interface.CANONICAL,
        )
        self.assertEqual(
            self.contract["bounded_artifact_interface"]["legacy_property"],
            interface.LEGACY,
        )
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertFalse(self.contract["authorization_boundary"]["formal_s93_s100_off_population_allowed"])
        fixture = alias_policy.run_fixtures(self.contract)
        self.assertTrue(fixture["all_pass"])


if __name__ == "__main__":
    unittest.main()
