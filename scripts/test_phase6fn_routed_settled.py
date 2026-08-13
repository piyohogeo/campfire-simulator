import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_phase6fn_routed_settled import field_adjusted_pair


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6fn_routed_settled_contract.json"


class Phase6FnRoutedSettled(unittest.TestCase):
    def test_contract_freezes_explicit_marker_and_limits(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["operation_frames"], [120, 360, 540])
        self.assertEqual(contract["settling_end_frames"], [360, 540, 620])
        self.assertTrue(contract["settling"]["frame_620_is_nonoperation_sentinel"])
        self.assertEqual(contract["settling"]["minimum_wall_seconds"], 4.0)
        self.assertEqual(contract["settling"]["minimum_outer_resource_samples"], 8)
        self.assertEqual(contract["settling"]["minimum_renderer_updates"], 60)
        self.assertEqual(contract["absolute_safety"]["kit_private_limit_bytes"], 14 * 1024**3)
        self.assertEqual(contract["absolute_safety"]["unique_tree_private_limit_bytes"], 16 * 1024**3)

    def test_legacy_evaluator_is_not_formal_authority(self):
        source = (ROOT / "scripts/analyze_phase6fn_routed_settled.py").read_text(encoding="utf-8")
        self.assertNotIn("from scripts.analyze_phase6fl_three_iteration import _attempt", source)
        self.assertIn('formal_decision_authority="phase6fn_explicit_layers"', source)
        self.assertIn('legacy_evaluator_used_for_formal_decision": False', source)

    def test_paired_staircase_requires_field_adjusted_two_steps(self):
        threshold = 50
        accepted = field_adjusted_pair([100, 100, 100], [200, 320, 440], [10, 130, 250], threshold)
        rejected = field_adjusted_pair([100, 100, 100], [200, 320, 450], [10, 10, 10], threshold)
        self.assertTrue(accepted["gate_pass"])
        self.assertFalse(rejected["gate_pass"])

    def test_real_shape_e2e_preflight(self):
        with tempfile.TemporaryDirectory(prefix="phase6fn-") as directory:
            output = Path(directory) / "preflight"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/run_phase6fn_e2e_preflight.py"), "--output-root", str(output)],
                check=False, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.assertEqual(completed.returncode, 0)
            manifest = json.loads((output / "preflight_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["all_pass"])
            self.assertGreaterEqual(manifest["fixture_count"], 19)
            passed = json.loads((output / "pass_population/analyzer_report.json").read_text(encoding="utf-8"))
            self.assertTrue(passed["qualified"])
            self.assertEqual(passed["representative_processes"], 9)

    def test_runner_requires_preflight_and_stops_nonreplaceable(self):
        source = (ROOT / "scripts/run_phase6fn_routed_settled.ps1").read_text(encoding="utf-8")
        self.assertIn("[Parameter(Mandatory = $true)][string]$PreflightManifest", source)
        self.assertIn("preflight contract hash mismatch", source)
        self.assertIn("captured nonreplaceable", source)

    def test_contract_and_runtime_hashes(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for item in contract["runtime_implementation"]:
            self.assertEqual(hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest().upper(), item["sha256"])
        expected = CONTRACT.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper(), expected)


if __name__ == "__main__":
    unittest.main()
