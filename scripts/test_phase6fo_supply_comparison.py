import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prepare_phase6fo_supply_comparison import prepare


class Phase6FOSupplyComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6fo_supply_comparison_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))

    def test_contract_freezes_p3_scope(self):
        self.assertEqual(self.contract["phase"], "phase6fo")
        self.assertEqual(self.contract["sample_frames"], [60, 120, 180, 360, 540, 600])
        self.assertEqual(self.contract["readback_frames"], [180, 360, 540])
        self.assertEqual(self.contract["maximum_readbacks_per_process"], 3)
        self.assertEqual(self.contract["formal_population"]["target_representative_processes"], 6)
        self.assertEqual(self.contract["formal_population"]["startup_prerequisite_replacement_budget"], 2)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["channel_preflight"]["startup_source_sum_absolute_tolerance"], 0.0001)
        self.assertIn("fourth or per-frame readback", self.contract["excluded"])

    def test_offline_point_decisions_are_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = prepare(root / "report.json", root / "records.jsonl")
            self.assertTrue(report["all_pass"])
            rows = {row["condition"]: row for row in report["conditions"]}
            self.assertEqual(rows["S93_support_clear"]["active_points"], 1344)
            self.assertEqual(rows["S100_center_clear"]["active_points"], 1440)
            self.assertEqual(rows["S93_support_clear"]["other_center_inside_count"], 0)
            self.assertEqual(rows["S100_center_clear"]["other_center_inside_count"], 0)
            self.assertEqual(rows["S93_support_clear"]["active_other_support_sphere_intersection_count"], 0)
            self.assertEqual(rows["S100_center_clear"]["active_other_support_sphere_intersection_count"], 96)
            with (root / "records.jsonl").open(encoding="utf-8") as stream:
                self.assertEqual(sum(1 for _ in stream), 2880)

    def test_channel_path_is_direct_and_bounded(self):
        source = (SCRIPTS / "probe_phase6fo_supply_comparison.py").read_text(encoding="utf-8")
        body = source[source.index("def _p3_spatial_boundary"):source.index("async def _run")]
        self.assertIn('flow.get_latest_nanovdb_readback()', body)
        self.assertIn('handles[channel_index] = None', body)
        self.assertIn('weak_reference_alive_after_scope_count', body)
        self.assertIn('"numpy_asarray_calls": 0', body)
        self.assertNotIn("np.asarray(source)", body)
        self.assertNotIn("gc.collect()", body)
        self.assertIn("p3_spatial_release", source)

    def test_runner_is_guarded_and_fail_closed(self):
        runner = (SCRIPTS / "run_phase6fo_supply_comparison.ps1").read_text(encoding="utf-8")
        for token in (
            "phase6eg_resource_guard.py", "p3_spatial_release", "startup_prerequisite_failure",
            "maximum_formal_launches", "pair gate failed", "production app changed",
        ):
            self.assertIn(token, runner)
        self.assertNotIn("KitPrivateLimitBytes =", runner)
        self.assertIn("channel_preflight.startup_source_sum_absolute_tolerance", runner)
        self.assertIn("preflight_report_missing_or_ambiguous", runner)

    def test_channel_preflight_artifact_route_matches_runner(self):
        analyzer = (SCRIPTS / "analyze_phase6fo_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn('channel-preflight/channel_attempt*/attempt_metadata.json', analyzer)
        self.assertNotIn('channel-preflight/attempt*/attempt_metadata.json', analyzer)

    def test_visual_is_numeric_gated(self):
        source = (SCRIPTS / "run_phase6fo_supply_visual.ps1").read_text(encoding="utf-8")
        self.assertIn("numeric_qualified", source)
        self.assertIn("-ReadbackMode\",\"none", source)
        self.assertIn("no retry is permitted", source)
        media = (SCRIPTS / "build_phase6fo_supply_comparison_media.py").read_text(encoding="utf-8")
        self.assertIn('"full_decode_pass": True', media)
        self.assertIn("comparison_unique_frames", media)

    def test_hash_sidecar_matches(self):
        sidecar = self.contract_path.with_suffix(".sha256")
        if not sidecar.is_file():
            self.skipTest("sidecar is written after contract implementation is frozen")
        expected = sidecar.read_text(encoding="utf-8").split()[0].upper()
        actual = hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper()
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
