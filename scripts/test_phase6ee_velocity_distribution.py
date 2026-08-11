"""Targeted contracts for the production-neutral Phase 6EE diagnostic."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SPATIAL = _module("phase6ee_spatial_test", ROOT / "scripts" / "phase6ee_velocity_distribution.py")
ANALYZE = _module("phase6ee_analyze_test", ROOT / "scripts" / "analyze_phase6ee_velocity_distribution.py")


def _cylinder12():
    points = []
    for x in (-0.9, 0.9):
        points.append((x, 0.0, 1.035))
        for segment in range(12):
            angle = 2.0 * np.pi * segment / 12.0
            points.append((x, 0.16 * np.cos(angle), 1.035 + 0.16 * np.sin(angle)))
    counts = [4] * 12 + [3] * 24
    indices = []
    for segment in range(12):
        following = (segment + 1) % 12
        indices.extend((1 + segment, 1 + following, 14 + following, 14 + segment))
    for segment in range(12):
        following = (segment + 1) % 12
        indices.extend((0, 1 + following, 1 + segment))
        indices.extend((13, 14 + segment, 14 + following))
    return points, counts, indices


class Phase6EeGeometry(unittest.TestCase):
    def test_exact_mesh_distance_and_face_classes(self):
        geometry = SPATIAL.build_mesh_geometry(*_cylinder12())
        query = np.asarray(((0.0, 0.0, 1.035), (0.0, 0.3, 1.035), (1.0, 0.0, 1.035)))
        signed, inside, nearest = SPATIAL.mesh_signed_distance(query, geometry)
        self.assertEqual(inside.tolist(), [True, False, False])
        self.assertLess(signed[0], 0.0)
        self.assertEqual(int(nearest[1]), int(SPATIAL.FACE_SIDE))
        self.assertEqual(int(nearest[2]), int(SPATIAL.FACE_END))

    def test_low_poly_and_analytic_cylinder_can_disagree(self):
        geometry = SPATIAL.build_mesh_geometry(*_cylinder12())
        angle = np.deg2rad(15.0)
        radius = 0.157
        query = np.asarray(((0.0, radius * np.cos(angle), 1.035 + radius * np.sin(angle)),))
        _, mesh_inside, _ = SPATIAL.mesh_signed_distance(query, geometry)
        analytic = SPATIAL.analytic_cylinder_signed_distance(query, geometry)
        self.assertFalse(bool(mesh_inside[0]))
        self.assertLess(float(analytic[0]), 0.0)

    def test_six_neighbor_depth_counts_cells_from_geometric_outside(self):
        inside = np.zeros((5, 5, 5), dtype=bool)
        inside[1:4, 1:4, 1:4] = True
        depth = SPATIAL._six_neighbor_depth(inside.reshape(-1), inside.shape).reshape(inside.shape)
        self.assertEqual(int(depth[1, 2, 2]), 1)
        self.assertEqual(int(depth[2, 2, 2]), 2)

    def test_primary_connectivity_is_six_neighbor_only(self):
        payload = {
            "index_ijk": np.asarray(((0, 0, 0), (1, 1, 0), (2, 1, 0)), dtype=np.int32),
            "magnitude": np.ones(3, dtype=np.float32),
            "mesh_inside": np.asarray((False, True, True)),
            "mesh_distance_voxels": np.asarray((1.0, -1.0, -2.5), dtype=np.float32),
            "local_xyz": np.asarray(((0, 0, 0), (1, 1, 0), (2, 1, 0)), dtype=np.float64),
        }
        six = ANALYZE.connectivity(payload, 1.0e-5, 6)
        eighteen = ANALYZE.connectivity(payload, 1.0e-5, 18)
        self.assertEqual(six["reachable_inside_count"], 0)
        self.assertEqual(eighteen["reachable_inside_count"], 2)


class Phase6EeContracts(unittest.TestCase):
    def test_runner_reuses_guarded_phase6ec_path_and_exact_order(self):
        text = (ROOT / "scripts" / "run_phase6ee_velocity_distribution.ps1").read_text(encoding="utf-8")
        self.assertIn("run_phase6dt_flow_collision_case.ps1", text)
        self.assertIn("Invoke-Phase6EaGuardedHelper", text)
        self.assertIn("512MB", text)
        self.assertIn("720", text)
        self.assertIn("BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9", text)
        self.assertLess(text.index('label = "A_axis_on"'), text.index('label = "B_rotate_y40_on"'))
        self.assertLess(text.index('label = "B_rotate_y40_on"'), text.index('label = "C_rotate_y40_off"'))
        self.assertIn("refuses artifact root reuse", text)

    def test_optional_probe_records_public_api_and_compact_npz(self):
        probe = (ROOT / "scripts" / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
        spatial = (ROOT / "scripts" / "phase6ee_velocity_distribution.py").read_text(encoding="utf-8")
        self.assertIn("get_latest_nanovdb_readback", probe)
        self.assertIn("phase6ee_spatial_enabled", probe)
        self.assertIn("np.savez_compressed", spatial)
        for field in (
            "index_ijk", "world_xyz", "local_xyz", "velocity_xyz", "mesh_inside",
            "mesh_signed_distance_m", "mesh_distance_voxels", "nearest_face_class",
            "analytic_inside", "outside_cell_distance_6_steps",
        ):
            self.assertIn(f'"{field}"', spatial)
        self.assertIn('"geometry_labels_are_flow_occupancy": False', spatial)

    def test_shared_case_runner_defaults_phase6ee_off(self):
        text = (ROOT / "scripts" / "run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$SpatialOutputRoot", text)
        self.assertIn('"--/phase6ee/spatialEnabled=$($spatialEnabled.ToString().ToLowerInvariant())"', text)
        self.assertIn("SpatialCondition", text)


if __name__ == "__main__":
    unittest.main()
