from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from phase6hv_probe_source import build_probe_source
from phase6hv_stage_contract import settings_common, settings_descriptor, sha256, canonical_json
from phase6hv_visual_occlusion import evaluate
from run_phase6hv_static_flow_occlusion import frozen_contract


class Phase6HVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, cls.contract_sha, cls.schema_sha = frozen_contract()
        cls.source = build_probe_source(SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py")

    def test_contract_digest_order_and_frozen_history(self) -> None:
        expected = (SCRIPTS / "phase6hv_static_flow_occlusion_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(self.contract_sha, expected)
        self.assertEqual([item["name"] for item in self.policy["condition_order"]], ["collision_off", "collision_on"])
        self.assertEqual(self.policy["retry"], 0)
        self.assertEqual(self.policy["replacement"], 0)
        self.assertFalse(self.policy["frozen_history"]["reclassified"])
        self.assertFalse(self.policy["frozen_history"]["runtime_reused"])

    def test_probe_changes_only_collision_condition(self) -> None:
        compile(self.source, str(SCRIPTS / "probe_phase6hv_static_flow_occlusion.py"), "exec")
        self.assertIn('collision_enabled = condition == "collision_on"', self.source)
        self.assertEqual(self.source.count("known_good._define_flow(stage, collision_enabled)"), 1)
        self.assertIn("EMITTER_CENTER = (0.0, 0.0, 0.55)", self.source)
        self.assertIn("EMITTER_RADIUS_M = 0.20", self.source)
        self.assertIn("CAMERA_EYE = (2.65, -4.2, 2.35)", self.source)
        self.assertNotIn("get_latest_nanovdb_readback", self.source)
        self.assertLess(self.source.index('mark("stage_contract_complete"'), self.source.index("await context.open_stage_async"))

    def test_settings_digests_share_one_schema(self) -> None:
        authored = self.policy["stage_authoring"]
        common = settings_common(self.policy)
        self.assertEqual(sha256(canonical_json(common)), authored["settings_common_sha256"])
        for condition in ("collision_off", "collision_on"):
            self.assertEqual(sha256(canonical_json(settings_descriptor(self.policy, condition))), authored["settings_sha256"][condition])

    def test_liveness_and_safety_are_frozen(self) -> None:
        self.assertEqual(self.policy["flow_liveness"]["collision_off_active_blocks_each_sample_minimum"], 128)
        self.assertEqual(self.policy["flow_liveness"]["collision_on_active_blocks_each_sample_minimum"], 25)
        self.assertEqual(self.policy["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.policy["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertEqual(self.policy["fixed_scene"]["readback_calls"], 0)

    def test_visual_evaluator_requires_automation_and_human_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            size = tuple(self.policy["fixed_scene"]["capture_resolution"])
            for condition in ("collision_off", "collision_on"):
                captures = root / condition / "captures"
                captures.mkdir(parents=True)
                Image.new("RGB", size, "black").save(captures / "baseline.png")
                image = Image.new("RGB", size, "black")
                draw = ImageDraw.Draw(image)
                if condition == "collision_off":
                    draw.rectangle((512, 418, 831, 647), fill=(220, 130, 30))
                    draw.rectangle((560, 600, 760, 719), fill=(220, 130, 30))
                else:
                    draw.rectangle((600, 600, 720, 719), fill=(190, 110, 25))
                    draw.rectangle((330, 380, 480, 620), fill=(220, 130, 30))
                    draw.rectangle((520, 340, 650, 410), fill=(220, 130, 30))
                image.save(captures / "final.png")
            pending = evaluate(root, self.policy, "pending")
            self.assertTrue(pending["automated_pass"], pending["automated_gates"])
            self.assertEqual(pending["status"], "awaiting_human_review")
            self.assertTrue(evaluate(root, self.policy, "pass")["qualified"])
            self.assertFalse(evaluate(root, self.policy, "unclear")["qualified"])

    def test_scope_remains_static_and_diagnostic(self) -> None:
        excluded = set(self.policy["out_of_scope"])
        self.assertIn("production integration", excluded)
        self.assertIn("Point Emitter coexistence or policy", excluded)
        self.assertIn("dynamic transform", excluded)
        self.assertIn("PhysX sharing", excluded)


if __name__ == "__main__":
    unittest.main()
