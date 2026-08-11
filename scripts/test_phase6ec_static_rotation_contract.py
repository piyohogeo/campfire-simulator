"""Static contracts for the production-neutral Phase 6EC safe-stop runner."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase6EcStaticRotationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = (ROOT / "scripts/run_phase6ec_static_rotated_cylinder.ps1").read_text(encoding="utf-8")
        cls.prepare = (ROOT / "scripts/prepare_phase6ec_static_rotated_cylinder.py").read_text(encoding="utf-8")
        cls.probe = (ROOT / "scripts/probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
        cls.analyze = (ROOT / "scripts/analyze_phase6ec_static_rotated_cylinder.py").read_text(encoding="utf-8")

    def test_exact_phase6dy_source_and_single_y40_transform(self) -> None:
        expected = "BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9"
        self.assertIn(expected, self.runner)
        self.assertIn(expected, self.prepare)
        self.assertIn("ROTATION_Y_DEG = 40.0", self.prepare)
        self.assertIn('"only_rotated_stage_has_one_transform_op"', self.prepare)

    def test_formal_process_order_is_axis_rotated_on_rotated_off(self) -> None:
        positions = [self.runner.index(value) for value in ("A_axis_on", "B_rotate_y40_on", "C_rotate_y40_off")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('mode = "phase6ec_rotated_mesh_collision_off"', self.runner)

    def test_fail_closed_and_no_automatic_retry(self) -> None:
        self.assertIn('automatic_retry = $false', self.runner)
        self.assertIn("two consecutive known NGX shutdown residuals", self.runner)
        self.assertIn('functional_status -ne "pass"', self.runner)
        self.assertIn('Write-SafeStop "formal_flow_readback"', self.runner)

    def test_probe_uses_transformed_and_stale_alignment_rois(self) -> None:
        self.assertIn("def _sample_alignment_grid", self.probe)
        self.assertIn('"rotated_only"', self.probe)
        self.assertIn('"axis_only"', self.probe)
        self.assertIn("local_to_world.GetInverse()", self.probe)

    def test_numeric_gate_is_independent_from_video(self) -> None:
        analysis_position = self.runner.index("& python $analyzer")
        visual_position = self.runner.index("$visualCases = @(")
        self.assertLess(analysis_position, visual_position)
        self.assertIn("debug_stages_excluded_from_numeric_gates", self.prepare)
        self.assertIn("actual renderer captures; numeric qualification remains independent", (ROOT / "scripts/build_phase6ec_static_rotation_media.py").read_text(encoding="utf-8"))

    def test_production_scope_is_unchanged(self) -> None:
        self.assertIn('if ($productionHashBefore -ne $productionHashAfter)', self.runner)
        self.assertIn('"no_render_surface_or_rigid_body"', self.prepare)
        self.assertNotRegex(self.prepare, re.compile(r"RigidBodyAPI\.Apply|DefinePrim\(.+RenderSurface"))

    def test_phase6ea_and_phase6eb_policy_are_consumed_not_redefined(self) -> None:
        case_runner = (ROOT / "scripts/run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
        self.assertIn('. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")', case_runner)
        self.assertNotIn("function Invoke-CampfireShutdownOutcomeClassification", self.runner)
        self.assertNotIn("CampfireKnownNgxSignature", self.runner)

    def test_case_runner_is_process_isolated_and_resource_bounded(self) -> None:
        self.assertIn('Invoke-Phase6EaGuardedHelper', self.runner)
        self.assertIn('$caseRunnerPrivateBytesLimit = 512MB', self.runner)
        self.assertIn('$caseRunnerTimeoutSeconds = 720', self.runner)
        self.assertIn('case-runner-logs', self.runner)
        self.assertIn('-StdoutPath $stdout', self.runner)
        self.assertIn('-StderrPath $stderr', self.runner)
        self.assertIn('private_bytes_exceeded', self.runner)
        self.assertNotIn('& $flowRunner -Mode', self.runner)

    def test_shared_case_runner_bounds_post_exit_log_readiness(self) -> None:
        case_runner = (ROOT / "scripts" / "run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
        self.assertIn('Get-CampfireWindowsExceptionEvidence -Path $log', case_runner)
        self.assertIn('maximum_wait_seconds = 5', case_runner)
        self.assertIn('Start-Sleep -Milliseconds 100', case_runner)
        self.assertIn('log_evidence_readiness = $logEvidenceReadiness', case_runner)
        self.assertIn('Invoke-CampfireShutdownOutcomeClassification', case_runner)


if __name__ == "__main__":
    unittest.main()
