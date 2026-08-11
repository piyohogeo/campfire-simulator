"""Contract tests for the Phase 6EG representative static-pose qualification."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from unittest import mock
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
        self.assertIn("phase6eg_resource_guard.py", source)
        self.assertIn("runner_private_bytes = 536870912", source)
        self.assertIn("kit_private_bytes = 15032385536", source)
        self.assertIn("tree_private_bytes = 17179869184", source)
        self.assertIn("run_phase6dt_flow_collision_case.ps1", source)
        self.assertIn('lifecycle_status -ne "normal_exit"', source)
        self.assertIn("automatic_retry = $false", source)

    def test_resource_guard_separates_runner_kit_diagnostic_and_tree_budgets(self):
        source = (SCRIPTS / "phase6eg_resource_guard.py").read_text(encoding="utf-8")
        calibration = (SCRIPTS / "run_phase6eg_resource_calibration.ps1").read_text(encoding="utf-8")
        self.assertIn('"runner_private_limit"', source)
        self.assertIn('"kit_private_limit"', source)
        self.assertIn('"diagnostic_private_limit"', source)
        self.assertIn('"tree_private_limit"', source)
        self.assertIn('identity = (row["pid"], row["create_time_utc_epoch"])', source)
        self.assertIn('trace.write(json.dumps(record', source)
        self.assertIn('"nvidia-smi.exe"', source)
        self.assertIn('current.create_time() != root_identity["create_time_utc_epoch"]', source)
        self.assertIn('"machine_minima": machine_minima', source)
        self.assertIn('"536870912"', calibration)
        self.assertIn('"12884901888"', calibration)

    def test_stage_open_calibration_reuses_the_existing_probe_lifecycle(self):
        probe = (SCRIPTS / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
        calibration = (SCRIPTS / "run_phase6eg_resource_calibration.ps1").read_text(encoding="utf-8")
        self.assertIn('settings.get_as_bool("/phase6egResourceProbe/stageOpenOnly")', probe)
        self.assertIn('"stage_open_probe_complete"', probe)
        self.assertIn("await context.close_stage_async()", probe)
        self.assertIn("-StageOpenOnly", calibration)
        self.assertIn("run_phase6dt_flow_collision_case.ps1", calibration)
        self.assertIn("phase6egResourceProbe/stageOpenOnly", runner)

    def test_shutdown_gpu_inventory_is_isolated_from_the_runner(self):
        policy = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-CampfireGpuInventory -OutputDir $output", policy)
        self.assertIn("Invoke-Phase6EaGuardedHelper -FilePath $executable", policy)
        self.assertIn("-TimeoutSeconds 15 -PrivateBytesLimit 128MB", policy)
        self.assertIn("[IO.File]::ReadLines($stdout", policy)
        self.assertNotIn("$lines = & nvidia-smi", policy)
        self.assertIn("diagnostic_capture_succeeded = $diagnosticCaptureSucceeded", policy)
        fixture = (SCRIPTS / "phase6eg_resource_guard_fixture.ps1").read_text(encoding="utf-8")
        self.assertIn('"gpu_inventory_capture.json"', fixture)

    def test_each_completed_process_runs_incremental_numeric_gate(self):
        runner = (SCRIPTS / "run_phase6eg_static_pose_set_qualification.ps1").read_text(encoding="utf-8")
        analyzer = (SCRIPTS / "analyze_phase6eg_static_pose_set_qualification.py").read_text(encoding="utf-8")
        self.assertIn("--check-run $RunIndex --check-condition $Condition", runner)
        self.assertIn("incremental numeric gate failed", runner)
        self.assertIn("def evaluate_incremental", analyzer)
        self.assertIn('"pair_available": pair_available', analyzer)

    def test_incremental_numeric_gate_checks_condition_and_completed_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pair = root / "spatial" / "run_1" / "P1_y40_off"
            pair.mkdir(parents=True)
            for frame in ANALYZER.FRAMES:
                (pair / f"P1_y40_off_f{frame:04d}_velocity.npz").touch()
            on = {str(frame): _sample(0.0, 0.0, 0.2) for frame in ANALYZER.FRAMES}
            off = {str(frame): _sample(0.2, 0.2, 0.2) for frame in ANALYZER.FRAMES}
            with mock.patch.object(
                ANALYZER,
                "collect_condition",
                side_effect=[(on, {str(frame): {} for frame in ANALYZER.FRAMES}), (off, {})],
            ):
                result = ANALYZER.evaluate_incremental(root, CONTRACT, 1, "P1_y40_on")
            self.assertTrue(result["pass"])
            self.assertTrue(result["pair_available"])
            self.assertEqual(4, result["sample_count"])

            failed_on = {str(frame): _sample(0.2, 0.2, 0.2) for frame in ANALYZER.FRAMES}
            with mock.patch.object(
                ANALYZER,
                "collect_condition",
                side_effect=[(failed_on, {}), (off, {})],
            ):
                failed = ANALYZER.evaluate_incremental(root, CONTRACT, 1, "P1_y40_on")
            self.assertFalse(failed["pass"])

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

    def test_phase6eh_records_the_second_safe_stop_and_pending_point_work(self):
        report = json.loads(
            (ROOT / "docs" / "devlog" / "assets" / "phase6" / "static_pose_resource_diagnosis.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("safe_stop", report["status"])
        self.assertEqual("12/36", report["qualification"]["completed_fraction"])
        self.assertFalse(report["qualification"]["phase6eg_qualified"])
        self.assertEqual("runner_private_limit", report["observed_facts"]["formal_failed_guard_reason"])
        self.assertFalse(report["observed_facts"]["cdb_process_observed"])
        self.assertEqual(536870912, report["correction"]["runner_limit_unchanged_bytes"])
        self.assertFalse(report["pending_after_phase6eg"]["implemented_in_phase6eh"])
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6eh"', devlog)
        self.assertIn("static_pose_resource_diagnosis.svg", devlog)
        self.assertIn("PointEmitter–CollisionProxy", devlog)

    def test_phase6ei_records_approved_restart_safe_stop(self):
        report = json.loads(
            (ROOT / "docs" / "devlog" / "assets" / "phase6" / "static_pose_restart_safe_stop.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("safe_stop", report["status"])
        self.assertFalse(report["qualification"]["phase6eg_qualified"])
        self.assertEqual(0, report["qualification"]["accepted_processes"])
        self.assertEqual("run_1/P0_identity_on", report["qualification"]["active_failed_condition"])
        self.assertEqual("shutdown_complete", report["functional_evidence_before_rejection"]["last_durable_marker"])
        self.assertEqual("runner_private_limit", report["resource_guard"]["stop_reason"])
        self.assertFalse(report["pending_after_phase6eg"]["implemented"])


if __name__ == "__main__":
    unittest.main()
