import hashlib
import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6EuReadbackLifetimeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = SCRIPTS / "phase6eu_readback_lifetime_contract.json"
        cls.contract = json.loads(cls.path.read_text(encoding="utf-8"))
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        cls.runner = (SCRIPTS / "run_phase6eu_readback_lifetime.ps1").read_text(encoding="utf-8")
        cls.analyzer = (SCRIPTS / "analyze_phase6eu_readback_lifetime.py").read_text(encoding="utf-8")

    def test_contract_hash_and_history_are_frozen(self):
        expected = (SCRIPTS / "phase6eu_readback_lifetime_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(expected, hashlib.sha256(self.path.read_bytes()).hexdigest().upper())
        self.assertIn("frozen", self.contract["phase6es_history"])
        self.assertIn("frozen", self.contract["phase6et_history"])
        phase6et = json.loads((SCRIPTS / "phase6et_memory_calibration_contract.json").read_text(encoding="utf-8"))
        self.assertEqual("campfire.phase6et.four-log-memory-calibration-contract.v1", phase6et["schema"])

    def test_matrix_separates_acquisition_conversion_persistence(self):
        rows = {
            row["id"]: row
            for group in self.contract["condition_groups"]
            for row in group["conditions"]
        }
        self.assertEqual("none", rows["R0_none"]["readback_mode"])
        self.assertEqual([60], rows["R1_early_once"]["readback_frames"])
        self.assertEqual([180], rows["R1_late_once"]["readback_frames"])
        self.assertEqual(3, len(rows["R2_three"]["readback_frames"]))
        self.assertEqual(7, len(rows["R2_seven"]["readback_frames"]))
        self.assertEqual("fuel_convert", rows["R3_fuel_convert"]["readback_mode"])
        self.assertEqual("fuel_scalar", rows["R4_fuel_scalar"]["readback_mode"])
        self.assertEqual("fuel_jsonl", rows["R5_fuel_jsonl"]["readback_mode"])
        self.assertEqual("fuel_spatial", rows["R6_fuel_spatial"]["readback_mode"])
        self.assertEqual(27, self.contract["formal_process_count"])

    def test_readback_free_baseline_runs_first_and_three_times(self):
        first = self.contract["condition_groups"][0]
        self.assertEqual("baseline", first["id"])
        self.assertFalse(first["requires_previous_group"])
        self.assertTrue(first["requires_group_plateau"])
        self.assertEqual(3, self.contract["runs_per_condition"])
        self.assertIn("foreach ($group in $contract.condition_groups)", self.runner)
        self.assertIn("group_plateau_or_completion_gate_failed", self.runner)

    def test_limits_remain_unchanged_and_retry_is_forbidden(self):
        safety = self.contract["safety"]
        self.assertEqual(14 * 1024 ** 3, safety["kit_private_limit_bytes"])
        self.assertEqual(16 * 1024 ** 3, safety["unique_tree_private_limit_bytes"])
        self.assertEqual(512 * 1024 ** 2, safety["runner_private_limit_bytes"])
        self.assertEqual(512 * 1024 ** 2, safety["diagnostic_private_limit_bytes"])
        self.assertFalse(safety["automatic_retry"])
        self.assertIn('"--kit-private-limit"', self.runner)

    def test_probe_uses_public_acquire_without_inferred_release(self):
        self.assertIn("flow.get_latest_nanovdb_readback()", self.probe)
        self.assertIn('"public_release_method_used": False', self.probe)
        self.assertIn("No public release method is exposed", self.probe)
        self.assertNotIn("release_nanovdb_readback", self.probe)
        self.assertIn("weakref.ref", self.probe)

    def test_synchronous_markers_cover_every_boundary(self):
        for marker in self.contract["synchronous_marker_contract"]["markers"]:
            self.assertIn(marker, self.probe)
        memory_helper = (SCRIPTS / "phase6eu_process_memory.py").read_text(encoding="utf-8")
        self.assertIn("GetProcessMemoryInfo", memory_helper)
        self.assertIn("argtypes", memory_helper)
        self.assertIn("restype", memory_helper)
        self.assertIn("private_usage", memory_helper)
        self.assertIn("tracemalloc.get_traced_memory", self.probe)

    @unittest.skipUnless(os.name == "nt", "Windows process counters")
    def test_synchronous_process_memory_fixture(self):
        from scripts.phase6eu_process_memory import process_memory_snapshot

        snapshot = process_memory_snapshot()
        self.assertTrue(snapshot["available"], snapshot)
        self.assertGreater(snapshot["private_bytes"], 0)
        self.assertGreater(snapshot["working_set_bytes"], 0)
        self.assertEqual(80, snapshot["structure_bytes"])

    def test_field_data_is_not_retained_or_expanded_to_json(self):
        self.assertIn("_append_bounded_jsonl", self.probe)
        self.assertIn("16 * 1024", self.probe)
        self.assertIn("del raw", self.probe)
        self.assertNotIn("array.tolist()", self.probe)
        self.assertNotIn("raw.tolist()", self.probe)

    def test_plateau_requires_active_and_private_stability(self):
        self.assertIn("active_blocks_stable", self.analyzer)
        self.assertIn("private_memory_stable", self.analyzer)
        self.assertIn("stability_resource_sample_count", self.analyzer)
        self.assertIn("private_growth_bytes_per_second", self.analyzer)
        self.assertIn("positive tail slope alone is not called a leak", json.dumps(self.contract))

    def test_supply_comparison_is_not_part_of_this_phase(self):
        gate = self.contract["return_to_supply_comparison"]
        self.assertTrue(gate["not_part_of_this_contract"])
        self.assertIn("R0 through R4", gate["allowed_only_after"][0])


if __name__ == "__main__":
    unittest.main()
