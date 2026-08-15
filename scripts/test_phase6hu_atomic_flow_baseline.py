from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from phase6hu_atomic_fixture import run_fixture
from phase6hu_probe_source import build_probe_source


class Phase6HuAtomicFlowBaselineTests(unittest.TestCase):
    def test_atomic_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = run_fixture(
                Path(directory) / "fixture",
                SCRIPTS / "phase6hu_atomic_flow_baseline_contract.json",
                SCRIPTS / "phase6hs_operation_report_schema.json",
            )
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual(report["kit_launch_count"], 0)

    def test_probe_is_collision_off_and_cleanup_safe(self) -> None:
        source = build_probe_source(SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py")
        compile(source, str(SCRIPTS / "probe_phase6hu_flow_baseline.py"), "exec")
        self.assertIn('condition = "collision_off"', source)
        self.assertIn("collision_enabled = False", source)
        self.assertIn("known_good.EMITTER_RADIUS_M = EMITTER_RADIUS_M", source)
        self.assertIn("EMITTER_RADIUS_M = 0.20", source)
        self.assertIn("reporter.enter_cleanup()", source)
        self.assertNotIn("get_latest_nanovdb_readback", source)

    def test_contract_freezes_single_baseline(self) -> None:
        contract_path = SCRIPTS / "phase6hu_atomic_flow_baseline_contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(contract["baseline_commit"], "89ae109")
        self.assertEqual(contract["runtime"]["condition"], "collision_off")
        self.assertEqual(contract["runtime"]["launches"], 1)
        self.assertEqual(contract["runtime"]["active_blocks_each_sample_minimum"], 128)
        self.assertEqual(contract["runtime"]["retry"], 0)
        self.assertNotIn("Collision ON", contract["scope_if_pass"])
        expected = (SCRIPTS / "phase6hu_atomic_flow_baseline_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(hashlib.sha256(contract_path.read_bytes()).hexdigest().upper(), expected)

    def test_exact_runtime_is_single_off_process(self) -> None:
        case = (SCRIPTS / "run_phase6hu_kit_case.ps1").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6hu_flow_baseline.py").read_text(encoding="utf-8")
        self.assertIn('condition="collision_off"', case)
        self.assertNotIn("[ValidateSet(\"collision_on\"", case)
        self.assertIn('"collision_on_started": False', runner)
        self.assertIn('"occlusion_comparison_started": False', runner)
        self.assertNotIn("get_latest_nanovdb_readback", case + runner)


if __name__ == "__main__":
    unittest.main()
