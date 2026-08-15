import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6HKContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((SCRIPTS / "phase6hk_flow_proxy_boundary_contract.json").read_text(encoding="utf-8"))
        cls.probe = (SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py").read_text(encoding="utf-8")
        cls.runner = (SCRIPTS / "run_phase6hk_flow_proxy_boundary.py").read_text(encoding="utf-8")

    def test_contract_is_one_default_off_non_readback_boundary(self):
        self.assertEqual(self.contract["scope"]["readback_calls"], 0)
        self.assertEqual(self.contract["safety"]["retry_or_replacement"], 0)
        self.assertIn("default-off", self.contract["purpose"])

    def test_probe_uses_current_production_hierarchy_builder(self):
        self.assertIn("populate_phase2_scene(stage, render_hierarchy=True)", self.probe)
        self.assertEqual(self.probe.count("FlowCollisionProxy\""), 1)
        self.assertIn('CreateApproximationAttr("convexDecomposition")', self.probe)

    def test_no_readback_nanovdb_or_sampling_path(self):
        forbidden = ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "nanovdb", "_sample_grid", "np.asarray")
        for token in forbidden:
            self.assertNotIn(token, self.probe)

    def test_stopped_timeline_release_after_close_and_fail_closed(self):
        self.assertNotIn("timeline.play", self.probe)
        self.assertLess(self.probe.index("await asyncio.wait_for(context.close_stage_async()"), self.probe.index("held.clear()"))
        self.assertIn("return 0 if passed else 1", self.runner)

    def test_resource_contract_is_guarded(self):
        self.assertIn("phase6fu_resource_guard.py", self.runner)
        self.assertIn('"--kit-private-limit"', self.runner)
        self.assertIn('"--tree-private-limit"', self.runner)
        self.assertIn('"--available-memory-floor"', self.runner)
        self.assertIn('"--commit-headroom-floor"', self.runner)


if __name__ == "__main__":
    unittest.main()
