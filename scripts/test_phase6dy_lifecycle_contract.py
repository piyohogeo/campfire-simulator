"""Static contract tests for the calibrated Phase 6DW/6DY lifecycle reuse."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "probe_phase6dw_gpu_renderer_lifecycle.py"
RUNNER = ROOT / "scripts" / "run_phase6dw_gpu_renderer_case.ps1"
MATRIX = ROOT / "scripts" / "run_phase6dy_stage_open_matrix.ps1"


class Phase6DyLifecycleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = PROBE.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.matrix = MATRIX.read_text(encoding="utf-8")
        ast.parse(cls.probe)

    def test_phase6dy_directly_invokes_phase6dw_runner(self) -> None:
        self.assertIn('"run_phase6dw_gpu_renderer_case.ps1"', self.matrix)
        self.assertIn("-Condition box_rtx", self.matrix)
        self.assertNotIn("probe_phase6dx_stage_open_boundary.py", self.matrix)

    def test_probe_marker_order_matches_calibrated_lifecycle(self) -> None:
        required = (
            'mark("pure_openusd_open_complete")',
            'mark("renderer_readiness_complete")',
            'mark("usd_context_connection_complete")',
            'mark("hydra_delegate_connection_observed")',
            'mark("first_renderer_update_started")',
            'mark("first_viewport_frame_started")',
            'mark("first_viewport_frame_complete")',
            'mark("stage_close_complete")',
            'mark("renderer_drain_started")',
            'mark("renderer_drain_complete")',
            'mark("shutdown_requested")',
        )
        offsets = [self.probe.index(marker) for marker in required]
        self.assertEqual(offsets, sorted(offsets))

    def test_no_pre_stage_viewport_frame_wait(self) -> None:
        connection = self.probe.index("await context.open_stage_async(str(stage_path))")
        frame_waits = [match.start() for match in re.finditer(r"next_viewport_frame_async\(", self.probe)]
        self.assertEqual(len(frame_waits), 1)
        self.assertGreater(frame_waits[0], connection)

    def test_context_connect_precedes_renderer_update(self) -> None:
        self.assertLess(
            self.probe.index('mark("usd_context_connection_complete")'),
            self.probe.index('mark("first_renderer_update_started")'),
        )

    def test_close_precedes_renderer_drain(self) -> None:
        self.assertLess(
            self.probe.index('mark("stage_close_complete")'),
            self.probe.index('mark("renderer_drain_started")'),
        )

    def test_matrix_order_and_fail_fast(self) -> None:
        labels = (
            "A_box_decomposition",
            "B_box_hull",
            "C_box_decomposition",
            "D_cylinder_decomposition",
            "E_box_decomposition",
        )
        offsets = [self.matrix.index(f'label="{label}"') for label in labels]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn('automatic_retry = $false', self.matrix)
        self.assertRegex(self.matrix, r"catch \{[\s\S]+?matrix_safe_stop\.json[\s\S]+?throw")


if __name__ == "__main__":
    unittest.main()
