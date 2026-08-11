"""Contract tests for the Phase 6EG representative static-pose qualification."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = json.loads((SCRIPTS / "phase6eg_static_pose_set_contract.json").read_text(encoding="utf-8"))
PHASE6EF = json.loads((SCRIPTS / "phase6ef_static_y40_qualification_contract.json").read_text(encoding="utf-8"))
SPEC = importlib.util.spec_from_file_location("phase6eg_analyzer", SCRIPTS / "analyze_phase6eg_static_pose_set_qualification.py")
ANALYZER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ANALYZER)


def _region(maximum: float) -> dict:
    return {
        "available": True,
        "voxel_count": 4,
        "mean": maximum / 2.0,
        "p50": maximum / 2.0,
        "p95": maximum,
        "maximum": maximum,
        "threshold_counts": {},
    }


def _sample(deep: float, center: float, identity_only: float, boundary: float = 0.5) -> dict:
    return {
        "deep_interior": _region(deep),
        "center_axis_near": _region(center),
        "axis_only": _region(identity_only),
        "boundary_0_to_1_voxel": _region(boundary),
    }


def _synthetic_samples() -> dict:
    payload = {}
    for run in range(1, 4):
        payload[str(run)] = {}
        for pose in CONTRACT["poses"]:
            identity = pose in ("P0_identity", "P2_roll_x17")
            payload[str(run)][f"{pose}_on"] = {
                str(frame): _sample(0.0, 0.0, 0.0 if identity else 0.2) for frame in ANALYZER.FRAMES
            }
            payload[str(run)][f"{pose}_off"] = {
                str(frame): _sample(0.2, 0.2, 0.0 if identity else 0.2) for frame in ANALYZER.FRAMES
            }
    return payload


class Phase6EgContractTests(unittest.TestCase):
    def test_pose_and_process_contract_is_frozen(self):
        self.assertEqual(6, len(CONTRACT["poses"]))
        self.assertEqual(
            ["P0_identity", "P1_y40", "P2_roll_x17", "P3_z33", "P4_y24_z31", "P5_axis111_53"],
            list(CONTRACT["poses"]),
        )
        self.assertEqual(36, sum(len(order) for order in CONTRACT["formal_order"]))
        for order in CONTRACT["formal_order"]:
            self.assertEqual(12, len(order))
            self.assertEqual(12, len(set(order)))

    def test_matrices_are_rigid_center_preserving(self):
        center = np.asarray([0.0, 0.0, 1.035, 1.0])
        for pose in CONTRACT["poses"].values():
            matrix = np.asarray(pose["matrix"], dtype=np.float64)
            rotation = matrix[:3, :3]
            np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-12)
            self.assertAlmostEqual(1.0, float(np.linalg.det(rotation)), places=12)
            np.testing.assert_allclose(center @ matrix, center, atol=1.0e-12)

    def test_phase6ef_thresholds_are_inherited(self):
        values = CONTRACT["thresholds"]
        reference = PHASE6EF["thresholds"]
        self.assertEqual(reference["existing_velocity_limit_m_s"], values["existing_velocity_limit_m_s"])
        self.assertEqual(reference["collision_off_positive_minimum_m_s"], values["collision_off_positive_minimum_m_s"])
        self.assertEqual(reference["rotated_on_to_off_deep_maximum_ratio"], values["on_to_off_deep_maximum_ratio"])
        self.assertEqual(reference["reported_velocity_thresholds_m_s"], values["reported_velocity_thresholds_m_s"])

    def test_phase6ef_geometry_analysis_is_imported_not_copied(self):
        source = (SCRIPTS / "analyze_phase6eg_static_pose_set_qualification.py").read_text(encoding="utf-8")
        prepare = (SCRIPTS / "prepare_phase6eg_static_pose_set.py").read_text(encoding="utf-8")
        self.assertIn("import analyze_phase6ef_static_y40_qualification as phase6ef", source)
        self.assertIn("phase6ef.sample_stats", source)
        self.assertIn("import phase6ee_velocity_distribution as spatial", prepare)
        self.assertIn("spatial.mesh_signed_distance", prepare)

    def test_guarded_runner_and_fail_closed_contract_are_reused(self):
        source = (SCRIPTS / "run_phase6eg_static_pose_set_qualification.ps1").read_text(encoding="utf-8")
        self.assertIn("phase6ea_diagnostic_common.ps1", source)
        self.assertIn("Invoke-Phase6EaGuardedHelper", source)
        self.assertIn("run_phase6dt_flow_collision_case.ps1", source)
        self.assertIn('lifecycle_status -ne "normal_exit"', source)
        self.assertIn("automatic_retry = $false", source)

    def test_synthetic_qualified_population_passes(self):
        pose_summary, checks, _ = ANALYZER.evaluate(_synthetic_samples(), CONTRACT)
        self.assertTrue(all(check["pass"] for check in checks))
        self.assertEqual(6, len(pose_summary))
        self.assertEqual(12, pose_summary["P1_y40"]["identity_only_comparable_samples"])

    def test_deep_penetration_fails_closed(self):
        samples = _synthetic_samples()
        samples["1"]["P5_axis111_53_on"]["60"]["deep_interior"]["maximum"] = 0.2
        _, checks, _ = ANALYZER.evaluate(samples, CONTRACT)
        self.assertTrue(any(not check["pass"] for check in checks))

    def test_public_occupancy_and_scope_remain_limited(self):
        self.assertFalse(CONTRACT["geometry_contract"]["flow_internal_occupancy_mask_public_api_available"])
        self.assertIn("not all SO(3)", CONTRACT["scope_if_pass"])
        self.assertIn("dynamic transform", CONTRACT["scope_if_pass"])

    def test_checked_in_result_is_an_explicit_safe_stop(self):
        report = json.loads(
            (ROOT / "docs" / "devlog" / "assets" / "phase6" / "static_pose_set_safe_stop.json").read_text(encoding="utf-8")
        )
        self.assertEqual("safe_stop", report["status"])
        self.assertFalse(report["qualified"])
        self.assertEqual(6, report["completed_normal_exit_process_count"])
        self.assertEqual(36, report["planned_process_count"])
        self.assertEqual("opening_prebuilt_stage", report["incomplete_conditions"][0]["last_lifecycle_marker"])
        self.assertFalse(report["interpretation"]["P3_failure_is_collision_failure"])
        self.assertFalse(report["production_changed"])

    def test_devlog_records_no_visual_or_archive_for_incomplete_gate(self):
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6eg"', devlog)
        self.assertIn("static_pose_set_safe_stop.json", devlog)
        section = devlog.split('id="phase-6eg"', 1)[1].split('id="phase-6ef"', 1)[0]
        self.assertNotIn("static_pose_set_qualification.svg", section)
        self.assertNotIn("static_pose_set_velocity_samples.zip", section)
        self.assertIn("latest_demo.json", devlog)


if __name__ == "__main__":
    unittest.main()
