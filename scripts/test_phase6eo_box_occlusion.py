import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6eo_box_occlusion_contract.json"


class Phase6EoBoxOcclusion(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_hash_and_phase_are_frozen(self):
        expected = (ROOT / "scripts/phase6eo_box_occlusion_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)
        self.assertEqual(self.contract["phase"], "phase6eo")
        self.assertTrue(self.contract["declared_before_formal_runs"])

    def test_phase6en_engineering_gates_are_reused(self):
        thresholds = self.contract["thresholds"]
        self.assertEqual(thresholds["collision_on_deep_maximum_m_s"], 1.0e-4)
        self.assertEqual(thresholds["collision_on_center_maximum_m_s"], 1.0e-4)
        self.assertEqual(thresholds["collision_off_deep_minimum_m_s"], 0.1)
        self.assertEqual(thresholds["collision_off_center_minimum_m_s"], 0.1)
        self.assertEqual(thresholds["on_to_off_deep_maximum_ratio"], 0.01)

    def test_on_off_difference_is_only_flow_collision_switch(self):
        conditions = self.contract["conditions"]
        self.assertEqual([item["name"] for item in conditions], ["box_off", "box_on"])
        self.assertFalse(conditions[0]["physicsCollisionEnabled"])
        self.assertTrue(conditions[1]["physicsCollisionEnabled"])
        self.assertEqual(self.contract["fixed_scene"]["mesh_vertex_count"], 8)
        self.assertTrue(self.contract["fixed_scene"]["mesh_closed"])

    def test_continuous_capture_contract(self):
        capture = self.contract["fixed_scene"]["capture_frames"]
        self.assertEqual((capture["start"], capture["end"], capture["stride"], capture["fps"]), (21, 200, 1, 15))

    def test_phase6dt_runner_exposes_only_diagnostic_modes(self):
        runner = (ROOT / "scripts/run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
        probe = (ROOT / "scripts/probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
        for token in ("phase6eo_box_mesh_collision_on", "phase6eo_box_mesh_collision_off"):
            self.assertIn(token, runner)
            self.assertIn(token, probe)
        self.assertIn("captureStartFrame", runner)
        self.assertIn("capture_end_frame", probe)

    def test_resource_and_shutdown_safety_are_reused(self):
        runner = (ROOT / "scripts/run_phase6eo_box_occlusion.ps1").read_text(encoding="utf-8")
        for token in ("phase6eg_resource_guard.py", "--cpu-telemetry", "normal_exit", "fatal_lines", "dump_inventory", "automatic_upload_attempt_lines"):
            self.assertIn(token, runner)

    def test_published_result_and_video_links(self):
        report = json.loads(
            (ROOT / "docs/devlog/assets/phase6/box_mesh_occlusion_report.json").read_text(encoding="utf-8")
        )
        self.assertTrue(report["qualified"])
        self.assertEqual(report["contract_sha256"], self.contract_hash)
        self.assertEqual(report["gates"]["worst_deep_on_off_ratio"], 0.0)
        self.assertEqual(report["gates"]["above_far_on_off_mean_ratios"]["temperature"], 0.0)
        self.assertEqual(report["gates"]["above_far_on_off_mean_ratios"]["smoke"], 0.0)
        devlog = (ROOT / "docs/devlog/index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6eo"', devlog)
        for name in (
            "phase6eo_box_collision_off.mp4",
            "phase6eo_box_collision_on.mp4",
            "phase6eo_box_collision_comparison.mp4",
        ):
            self.assertIn(name, devlog)

    @property
    def contract_hash(self):
        return hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()


if __name__ == "__main__":
    unittest.main()
