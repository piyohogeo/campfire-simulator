"""No-Kit contract and derived-probe tests for Phase 6HT."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).absolute().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6hp_process_tree_topology import ROOT
from phase6ht_probe_source import build_probe_source
from phase6ht_visual_occlusion import evaluate
from run_phase6ht_static_flow_occlusion import CONTRACT, frozen_contract, stage_difference


class Phase6HTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, cls.contract_sha, cls.schema_sha = frozen_contract()
        cls.source = build_probe_source(ROOT / "scripts/probe_phase6hk_flow_proxy_boundary.py")

    def test_frozen_contract_and_order(self) -> None:
        self.assertEqual(self.contract_sha, "AC5571BBFF59456285B745226137DE5055159A3628F46083BA47DC32C43E73A2")
        self.assertEqual([item["name"] for item in self.policy["condition_order"]], ["collision_on", "collision_off"])
        self.assertEqual(self.policy["retry"], 0)
        self.assertEqual(self.policy["replacement"], 0)

    def test_phase6hs_proxy_and_known_good_flow_are_reused(self) -> None:
        self.assertIn("known_good._define_flow(stage, collision_enabled)", self.source)
        self.assertIn("known_good._define_camera(stage, CAMERA_PATH", self.source)
        self.assertIn("known_good._capture(viewport", self.source)
        self.assertEqual(self.source.count("UsdPhysics.MeshCollisionAPI.Apply"), 1)
        self.assertNotIn("get_latest_nanovdb_readback", self.source)
        self.assertNotIn("buffer_to_volume", self.source)

    def test_one_variable_and_fixed_calls(self) -> None:
        self.assertEqual(self.source.count("timeline.play()"), 1)
        self.assertEqual(self.source.count("get_active_block_count()"), 1)
        self.assertEqual(self.source.count("report[\"capture_calls\"] += 1"), 2)
        self.assertIn("SIMULATION_UPDATES = 240", self.source)
        self.assertIn('condition = settings.get_as_string("/phase6ht/condition")', self.source)

    def test_inherited_safety_contract(self) -> None:
        safety = self.policy["safety"]
        self.assertEqual(safety["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(safety["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertEqual(safety["simultaneous_kit_processes"], 1)
        self.assertEqual(self.policy["fixed_scene"]["readback_calls"], 0)

    def test_stage_diff_accepts_only_collision_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, value in (("collision_on", "true"), ("collision_off", "false")):
                stage = root / name / "stages"
                stage.mkdir(parents=True)
                (stage / "candidate.usda").write_text(f"#usda 1.0\n bool physicsCollisionEnabled = {value}\n", encoding="utf-8")
            self.assertTrue(stage_difference(root)["passed"])
            with (root / "collision_off/stages/candidate.usda").open("a", encoding="utf-8") as stream:
                stream.write("float unexpected = 1\n")
            self.assertFalse(stage_difference(root)["passed"])

    def test_visual_evaluator_positive_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            size = tuple(self.policy["fixed_scene"]["capture_resolution"])
            for condition in ("collision_on", "collision_off"):
                captures = root / condition / "captures"
                captures.mkdir(parents=True)
                Image.new("RGB", size, "black").save(captures / "baseline.png")
                image = Image.new("RGB", size, "black")
                draw = ImageDraw.Draw(image)
                if condition == "collision_off":
                    draw.rectangle((400, 45, 560, 280), fill=(255, 100, 20))
                    draw.rectangle((150, 180, 300, 400), fill=(80, 30, 10))
                else:
                    draw.rectangle((420, 200, 540, 275), fill=(40, 18, 5))
                    draw.rectangle((170, 140, 380, 390), fill=(255, 100, 20))
                    draw.rectangle((580, 140, 790, 390), fill=(255, 100, 20))
                image.save(captures / "final.png")
            pending = evaluate(root, self.policy, "pending")
            self.assertTrue(pending["automated_pass"], pending["automated_gates"])
            self.assertEqual(pending["status"], "awaiting_human_review")
            self.assertTrue(evaluate(root, self.policy, "pass")["qualified"])
            self.assertFalse(evaluate(root, self.policy, "unclear")["qualified"])

    def test_phase6hs_is_frozen(self) -> None:
        self.assertFalse(self.policy["frozen_history"]["reclassified"])
        self.assertFalse(self.policy["frozen_history"]["runtime_reused"])
        self.assertEqual(self.policy["baseline_commit"], "fbbac6f")

    def test_no_production_or_point_scope(self) -> None:
        excluded = set(self.policy["out_of_scope"])
        self.assertIn("production integration", excluded)
        self.assertIn("Point Emitter policy", excluded)
        self.assertIn("dynamic transform", excluded)
        self.assertIn("PhysX sharing", excluded)


if __name__ == "__main__":
    unittest.main()
