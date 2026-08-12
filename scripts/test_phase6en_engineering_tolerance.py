"""Contract tests for the independent Phase 6EN engineering tolerance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OLD_PATH = SCRIPTS / "phase6eg_static_pose_set_contract.json"
NEW_PATH = SCRIPTS / "phase6en_static_pose_engineering_contract.json"
OLD = json.loads(OLD_PATH.read_text(encoding="utf-8"))
NEW = json.loads(NEW_PATH.read_text(encoding="utf-8"))
SPEC = importlib.util.spec_from_file_location("phase6ef", SCRIPTS / "analyze_phase6ef_static_y40_qualification.py")
PHASE6EF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PHASE6EF)


class Phase6EnEngineeringTolerance(unittest.TestCase):
    def test_contract_is_distinct_and_historical_contract_is_frozen(self):
        old_hash = hashlib.sha256(OLD_PATH.read_bytes()).hexdigest().upper()
        new_hash = hashlib.sha256(NEW_PATH.read_bytes()).hexdigest().upper()
        self.assertEqual("4BAED82160A08C061D479BCCA6B6A46866DE88F5046851D2AF140D36D8C80687", old_hash)
        self.assertEqual("C6A73B07385519160488DA07C023EC5E5104BB0A8C1BDAD70D01B15327CAE1AF", new_hash)
        self.assertEqual(old_hash, NEW["historical_contract"]["sha256"])
        self.assertEqual("formal_fail_at_1e-5_m_s_unchanged", NEW["historical_contract"]["phase6em_status"])

    def test_only_judgment_contract_changes(self):
        self.assertEqual(OLD["poses"], NEW["poses"])
        self.assertEqual(OLD["formal_order"], NEW["formal_order"])
        self.assertEqual(OLD["fixed_environment"], NEW["fixed_environment"])
        self.assertEqual(OLD["geometry_contract"]["deep_interior"], NEW["geometry_contract"]["deep_interior"])
        self.assertEqual(OLD["geometry_contract"]["center_axis_near"], NEW["geometry_contract"]["center_axis_near"])
        self.assertEqual(OLD["stale_transform_contract"], NEW["stale_transform_contract"])

    def test_engineering_thresholds_are_predeclared(self):
        thresholds = NEW["thresholds"]
        self.assertEqual(1.0e-4, thresholds["engineering_hard_maximum_m_s"])
        self.assertEqual(1.0e-4, thresholds["existing_velocity_limit_m_s"])
        self.assertEqual(5.0e-5, thresholds["warning_level_m_s"])
        self.assertEqual(0.1, thresholds["collision_off_positive_minimum_m_s"])
        self.assertEqual(0.01, thresholds["on_to_off_deep_maximum_ratio"])
        self.assertEqual([1.0e-6, 1.0e-5, 5.0e-5, 1.0e-4], thresholds["reported_velocity_thresholds_m_s"])

    def test_diagnostic_statistics_keep_hard_maximum(self):
        result = PHASE6EF.summarize(np.asarray([0.0, 1.0e-5, 5.1e-5, 9.9e-5]), tuple(NEW["thresholds"]["reported_velocity_thresholds_m_s"]))
        self.assertEqual(0.0, result["minimum"])
        self.assertIn("p99", result)
        self.assertEqual(9.9e-5, result["maximum"])
        self.assertEqual(2, result["threshold_counts"]["5e-05"])
        self.assertEqual(0, result["threshold_counts"]["0.0001"])

    def test_maximum_cell_records_geometry_and_coordinates(self):
        payload = {
            "nearest_face_class": np.asarray([0, 1], dtype=np.int8),
            "index_ijk": np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.int32),
            "world_xyz": np.asarray([[0, 0, 0], [1, 2, 3]], dtype=np.float32),
            "local_xyz": np.asarray([[0, 0, 0], [0.1, 0.2, 0.3]], dtype=np.float32),
            "velocity_xyz": np.asarray([[0, 0, 0], [0, 0, 9.0e-5]], dtype=np.float32),
            "mesh_signed_distance_m": np.asarray([-0.1, -0.2], dtype=np.float32),
            "mesh_distance_voxels": np.asarray([-2.0, -4.0], dtype=np.float32),
        }
        result = PHASE6EF.maximum_cell(payload, np.asarray([0.0, 9.0e-5]), np.asarray([True, True]))
        self.assertEqual([4, 5, 6], result["index_ijk"])
        self.assertEqual("end", result["nearest_face_class"])
        self.assertAlmostEqual(9.0e-5, result["magnitude_m_s"])

    def test_runner_reuses_phase6el_safety_and_never_rewrites_threshold(self):
        shared = (SCRIPTS / "run_phase6eg_static_pose_set_qualification.ps1").read_text(encoding="utf-8")
        wrapper = (SCRIPTS / "run_phase6en_static_pose_engineering_qualification.ps1").read_text(encoding="utf-8")
        self.assertIn("phase6eg_resource_guard.py", shared)
        self.assertIn('"--cpu-telemetry"', shared)
        self.assertIn("run_phase6dt_flow_collision_case.ps1", shared)
        self.assertIn("phase6en_static_pose_engineering_contract.json", wrapper)
        self.assertNotIn("Set-Content", wrapper)
        self.assertNotIn("ConvertTo-Json", wrapper)

    def test_published_summary_and_devlog_preserve_scope(self):
        summary = json.loads(
            (ROOT / "docs" / "devlog" / "assets" / "phase6" / "static_pose_engineering_qualification.json").read_text(encoding="utf-8")
        )
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertTrue(summary["qualified"])
        self.assertEqual(36, summary["population"]["processes"])
        self.assertEqual(144, summary["population"]["velocity_samples"])
        self.assertFalse(summary["contracts"]["production_changed"])
        self.assertEqual(0, summary["lifecycle"]["cdb_invocation_count"])
        self.assertIn('id="phase-6en"', devlog)
        self.assertIn("static_pose_engineering_qualification.svg", devlog)
        self.assertIn("内部数値試験だけで画面上の変更がない", devlog)
        self.assertNotIn("phase6en", (ROOT / "docs" / "devlog" / "assets" / "latest_demo.json").read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
