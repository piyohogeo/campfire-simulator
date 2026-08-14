import hashlib
import json
import unittest
from pathlib import Path

import phase6gm_flow_export_state as export_state


SCRIPTS = Path(__file__).resolve().parent


class Phase6GMExportStateTests(unittest.TestCase):
    def setUp(self):
        self.contract_path = SCRIPTS / "phase6gm_supply_comparison_contract.json"
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))

    def test_descriptor_is_unique_explicit_boolean_state(self):
        descriptor = export_state.load_descriptor()
        rows = descriptor["attributes"]
        self.assertEqual(len(rows), len({row["name"] for row in rows}))
        state = {row["name"]: row["value"] for row in rows}
        self.assertTrue(state["divergenceEnabled"])
        self.assertFalse(state["rgbaEnabled"])
        self.assertFalse(state["rgbEnabled"])
        self.assertEqual(len(export_state.descriptor_digest()), 64)

    def test_phase6gm_wrapper_reuses_phase6gl_and_shared_export_helper(self):
        body = (SCRIPTS / "probe_phase6gm_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn("probe_phase6gl_supply_comparison.py", body)
        self.assertIn("phase6gm_flow_export_state.py", body)
        self.assertIn("export_state.author(stage)", body)
        self.assertIn("shared._build_stage = _build_stage_with_qualified_exports", body)

    def test_descriptor_is_phase6gk_schema_derived(self):
        descriptor = json.loads((SCRIPTS / "phase6gm_flow_export_state_descriptor.json").read_text(encoding="utf-8"))
        self.assertEqual(descriptor["derived_from"]["phase"], "phase6gk")
        self.assertEqual(descriptor["derived_from"]["schema_id"], "flow110.0.0-kit110.2-public-readback-rgba7-v1")

    def test_contract_hash_population_and_safety_are_frozen(self):
        declared = (SCRIPTS / "phase6gm_supply_comparison_contract.sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper(), declared)
        self.assertFalse(self.contract["history"]["phase6gl_reclassified"])
        self.assertEqual(self.contract["formal_population"]["required_representative_processes"], 9)
        self.assertEqual(self.contract["formal_population"]["maximum_formal_launches"], 11)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)

    def test_runtime_runner_has_prekit_offline_gate(self):
        runner = (SCRIPTS / "run_phase6fo_supply_comparison.ps1").read_text(encoding="utf-8")
        self.assertIn('if ($phase -eq "phase6gm")', runner)
        self.assertIn('run_phase6gm_export_state_fixtures.ps1', runner)
        self.assertIn('probe_phase6gm_supply_comparison.py', runner)


if __name__ == "__main__":
    unittest.main()
