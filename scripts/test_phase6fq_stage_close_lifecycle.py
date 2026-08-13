import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "phase6fq_stage_close_lifecycle_contract.json"
PROBE = ROOT / "probe_phase6fo_supply_comparison.py"
CASE_RUNNER = ROOT / "run_phase6fo_supply_case.ps1"
MATRIX_RUNNER = ROOT / "run_phase6fq_stage_close_lifecycle.ps1"


class Phase6FqStageCloseLifecycleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.probe = PROBE.read_text(encoding="utf-8")
        cls.case_runner = CASE_RUNNER.read_text(encoding="utf-8")
        cls.matrix_runner = MATRIX_RUNNER.read_text(encoding="utf-8")

    def test_contract_hash_and_phase6fp_history_are_frozen(self):
        expected = (ROOT / "phase6fq_stage_close_lifecycle_contract.sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)
        self.assertEqual(self.contract["frozen_history"]["phase6fp_commit"], "417cbe1")
        self.assertEqual(self.contract["frozen_history"]["phase6fp_attempt11_last_marker"], "stage_close_timeout")

    def test_no_readback_capture_or_resource_ceiling_change(self):
        fixture = self.contract["physical_fixture"]
        self.assertEqual(fixture["readback_calls"], 0)
        self.assertEqual(fixture["capture_calls"], 0)
        self.assertEqual(fixture["pixel_buffer_bytes"], 0)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)

    def test_capture_preparation_is_bounded_and_does_not_call_capture(self):
        self.assertIn('capture_preparation_mode == "provider_alias"', self.probe)
        self.assertIn('capture_provider_alias = viewport', self.probe)
        self.assertIn('"capture_calls": 0', self.probe)
        self.assertIn('"pixel_buffer_bytes": 0', self.probe)
        preparation = self.probe.split("capture_preparation_mode =", 1)[1].split("extra_update_count =", 1)[0]
        self.assertNotIn("_capture(", preparation)

    def test_release_orders_share_the_existing_lifecycle_path(self):
        self.assertIn('release_order == "before_stage_close"', self.probe)
        self.assertIn('release_order == "after_stage_close"', self.probe)
        self.assertEqual(self.probe.count("await asyncio.wait_for(context.close_stage_async()"), 1)
        self.assertIn("phase6eg_resource_guard.py", self.matrix_runner)
        self.assertIn("run_phase6fo_supply_case.ps1", self.matrix_runner)

    def test_required_markers_are_implemented(self):
        for marker in self.contract["required_markers"]:
            self.assertIn(f'"{marker}"', self.probe)
        self.assertIn("extension_lifecycle_markers.jsonl", self.case_runner)

    def test_matrix_has_single_variable_controls_and_fail_closed_stop(self):
        conditions = {row["id"]: row for row in self.contract["conditions"]}
        keys = ("allocation_level", "capture_preparation_mode", "renderer_drain_updates", "reference_release_order")

        def delta(left, right):
            return [key for key in keys if conditions[left][key] != conditions[right][key]]

        self.assertEqual(delta("L1_c5_without_capture_prep", "L2_c5_disabled_state"), ["allocation_level"])
        self.assertEqual(delta("L2_c5_disabled_state", "L3_c5_manifest"), ["capture_preparation_mode"])
        self.assertEqual(delta("L3_c5_manifest", "L4_c5_provider_alias"), ["capture_preparation_mode"])
        self.assertEqual(delta("L5_c5_no_preclose_drain", "L6_c5_normal_drain_control"), ["renderer_drain_updates"])
        self.assertEqual(delta("L7_c5_release_after_close", "L8_c5_release_before_close_control"), ["reference_release_order"])
        self.assertIn("Phase 6FQ nonreplaceable failure", self.matrix_runner)
        self.assertIn("throw", self.matrix_runner)


if __name__ == "__main__":
    unittest.main()
