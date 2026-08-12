import hashlib
import json
import unittest
from pathlib import Path

from scripts.phase6fc_startup_contract import classify_startup


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT_PATH = SCRIPTS / "phase6fc_startup_reproduction_contract.json"


def source(enabled=True):
    return {
        "enabled": enabled,
        "revision": 1,
        "total_point_count": 1440,
        "active_point_count": 1344,
        "source_sums": {"fuel": 1075.2, "temperature": 2688.0, "smoke": 107.52},
    }


def history(active, timeline=True):
    return [
        {
            "frame": frame,
            "perf_counter_ns": frame * 100,
            "kit_update_number": frame + 500,
            "timeline_time": frame / 60.0,
            "timeline_playing": timeline,
            "active_blocks": active(frame),
        }
        for frame in range(1, 121)
    ]


class Phase6FcStartupReproduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.thresholds = cls.contract["classification"]

    def test_contract_hash_and_frozen_history(self):
        recorded = (SCRIPTS / "phase6fc_startup_reproduction_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest().upper(), recorded)
        self.assertEqual(self.contract["history"]["safe_commit"], "4e19108")
        self.assertFalse(self.contract["history"]["prior_population_reuse"])

    def test_baseline_six_and_ablation_single_variables(self):
        baseline = self.contract["baseline_conditions"]
        self.assertEqual(len(baseline), 6)
        self.assertTrue(all(item["flow_acquire_position"] == "before_updates" for item in baseline))
        self.assertTrue(all(item["pre_timeline_update_count"] == 12 for item in baseline))
        ablations = {item["id"]: item for item in self.contract["ablation_conditions"]}
        self.assertEqual(len(ablations), 4)
        self.assertEqual(ablations["A1_flow_acquire_after_updates"]["flow_acquire_position"], "after_updates")
        self.assertEqual(ablations["A2_zero_stopped_updates"]["pre_timeline_update_count"], 0)
        self.assertEqual(ablations["A3_one_extra_update_before_play"]["extra_update_before_play_count"], 1)

    def test_branching_and_scope_are_fail_closed(self):
        branching = self.contract["branching"]
        self.assertFalse(branching["automatic_retry"])
        self.assertTrue(branching["run_ablations_only_if_all_six_baselines_representative"])
        self.assertFalse(branching["public_field_probe_automatic"])
        self.assertFalse(branching["long_population_started"])
        self.assertFalse(self.contract["safety"]["production_change"])
        self.assertFalse(self.contract["safety"]["resource_ceiling_change"])

    def test_representative_small_delayed_and_indeterminate(self):
        representative = classify_startup(history(lambda frame: 24 + frame * 4), source(), self.thresholds)
        small = classify_startup(history(lambda _frame: 24), source(), self.thresholds)
        delayed = classify_startup(history(lambda frame: 24 if frame <= 60 else 24 + (frame - 60) * 3), source(), self.thresholds)
        indeterminate = classify_startup(history(lambda _frame: 64), source(), self.thresholds)
        self.assertEqual(representative["classification"], "representative_ingestion")
        self.assertEqual(small["classification"], "small_field_ingestion")
        self.assertEqual(delayed["classification"], "delayed_ingestion")
        self.assertEqual(indeterminate["classification"], "indeterminate_startup")

    def test_stale_and_no_source(self):
        stale = history(lambda frame: 200 + frame)
        stale[20]["kit_update_number"] = stale[19]["kit_update_number"]
        self.assertEqual(classify_startup(stale, source(), self.thresholds)["classification"], "stale_telemetry")
        self.assertEqual(classify_startup(history(lambda frame: 200 + frame), source(False), self.thresholds)["classification"], "no_source")

    def test_shared_probe_has_order_markers_and_no_sleep_ablation(self):
        probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6fc_startup_reproduction.ps1").read_text(encoding="utf-8")
        for marker in self.contract["required_startup_markers"]:
            self.assertIn(marker, probe)
        self.assertIn("StartupFlowAcquirePosition", runner)
        self.assertIn("StartupPreTimelineUpdateCount", runner)
        self.assertIn("StartupExtraUpdateBeforePlayCount", runner)
        self.assertNotIn("Start-Sleep", runner)

    def test_resource_ceilings_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 16 * 1024**3)


if __name__ == "__main__":
    unittest.main()
