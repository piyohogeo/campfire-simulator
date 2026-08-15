from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phase6ib_no_kit_fixture import run_fixture
from phase6ib_stage_authoring import stage_spec, validate_spec


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6ib_stage_open_contract.json"
SIDECAR = ROOT / "scripts/phase6ib_stage_open_contract.sha256"
FROZEN = json.loads((ROOT / "scripts/phase6hx_single_log_occlusion_contract.json").read_text(encoding="utf-8"))


class Phase6IBTests(unittest.TestCase):
    def test_actual_no_kit_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = run_fixture(Path(temporary) / "fixture", CONTRACT, SIDECAR, ROOT)
        self.assertEqual(report["status"], "qualified")
        self.assertEqual(report["case_count"], [23, 23])

    def test_frozen_spec_is_exact(self):
        off = stage_spec(FROZEN, "collision_off")
        on = stage_spec(FROZEN, "collision_on")
        self.assertTrue(validate_spec(off, FROZEN, "collision_off")["accepted"])
        self.assertTrue(validate_spec(on, FROZEN, "collision_on")["accepted"])
        self.assertFalse(off["physics_collision_enabled"])
        self.assertTrue(on["physics_collision_enabled"])

    def test_runtime_source_forbids_simulation_and_readback(self):
        source = (ROOT / "scripts/phase6ib_stage_open_source.py").read_text(encoding="utf-8")
        for token in ("timeline.play", "get_latest_nanovdb_readback", "buffer_to_volume", "_flowusd", "_capture("):
            self.assertNotIn(token, source)


if __name__ == "__main__": unittest.main()
