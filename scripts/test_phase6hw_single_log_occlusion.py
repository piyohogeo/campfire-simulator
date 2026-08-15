from __future__ import annotations

import copy
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

from phase6hw_stage_builder import canonical_json, settings_common, settings_descriptor, sha256
from phase6hw_stage_fixture import run_fixture
from phase6hw_temporal_occlusion import evaluate
from run_phase6hw_single_log_occlusion import frozen_contract


def _box(bounds: list[float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    x0, y0, x1, y1 = bounds
    return round(x0 * width), round(y0 * height), round(x1 * width), round(y1 * height)


class Phase6HWTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, cls.contract_sha, cls.schema_sha = frozen_contract()

    def test_frozen_contract_and_scope(self) -> None:
        self.assertEqual(self.policy["baseline_commit"], "91f6b06")
        self.assertEqual(self.policy["frozen_history"]["phase6hv_status"], "safe_stop_visual_gate")
        self.assertFalse(self.policy["frozen_history"]["reclassified"])
        self.assertFalse(self.policy["frozen_history"]["runtime_or_images_reused"])
        self.assertEqual([item["name"] for item in self.policy["condition_order"]], ["collision_off", "collision_on"])
        self.assertEqual(self.policy["retry"], 0)
        self.assertEqual(self.policy["replacement"], 0)

    def test_stage_settings_share_one_descriptor(self) -> None:
        authored = self.policy["stage_authoring"]
        self.assertEqual(sha256(canonical_json(settings_common(self.policy))), authored["settings_common_sha256"])
        for condition in ("collision_off", "collision_on"):
            self.assertEqual(sha256(canonical_json(settings_descriptor(self.policy, condition))), authored["settings_sha256"][condition])

    def test_stage_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_fixture(Path(temporary) / "fixture", SCRIPTS / "phase6hw_single_log_occlusion_contract.json")
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual(report["kit_launch_count"], 0)

    def test_temporal_metric_requires_automation_and_human_gate(self) -> None:
        policy = copy.deepcopy(self.policy)
        size = (320, 180)
        policy["fixed_scene"]["capture_resolution"] = list(size)
        frames = policy["temporal_measurement"]["stable_window_frames"]
        rois = policy["temporal_measurement"]["rois_normalized"]
        flow = (220, 130, 30)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for condition in ("collision_off", "collision_on"):
                captures = root / condition / "captures"
                captures.mkdir(parents=True)
                for frame in frames:
                    image = Image.new("RGB", size, "black")
                    draw = ImageDraw.Draw(image)
                    draw.rectangle(_box(rois["source"], size), fill=flow)
                    if condition == "collision_off":
                        draw.rectangle(_box(rois["direct_interior"], size), fill=flow)
                    else:
                        draw.rectangle(_box(rois["left_bypass"], size), fill=flow)
                        draw.rectangle(_box(rois["right_bypass"], size), fill=flow)
                        draw.rectangle(_box(rois["upper"], size), fill=flow)
                    image.save(captures / f"flow_only_f{frame:04d}.png")
            pending, _ = evaluate(root, policy, "pending")
            passed, _ = evaluate(root, policy, "pass")
            unclear, _ = evaluate(root, policy, "unclear")
        self.assertTrue(pending["automated_pass"], pending["automated_gates"])
        self.assertEqual(pending["status"], "awaiting_human_review")
        self.assertTrue(passed["qualified"])
        self.assertFalse(unclear["qualified"])

    def test_safety_and_readback_exclusion(self) -> None:
        self.assertEqual(self.policy["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.policy["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertEqual(self.policy["fixed_scene"]["readback_calls"], 0)
        excluded = set(self.policy["out_of_scope"])
        self.assertIn("production integration", excluded)
        self.assertIn("NanoVDB readback or sampling", excluded)


if __name__ == "__main__":
    unittest.main()
