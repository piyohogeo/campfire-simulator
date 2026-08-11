"""Static safety contract for Phase 6DZ rotation qualification."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREPARE = (ROOT / "scripts" / "prepare_phase6dz_rotated_cylinder_cases.py").read_text(encoding="utf-8")
MATRIX = (ROOT / "scripts" / "run_phase6dz_rotated_cylinder_matrix.ps1").read_text(encoding="utf-8")
FLOW = (ROOT / "scripts" / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")


class Phase6DzRotationContract(unittest.TestCase):
    def test_qualified_geometry_and_approximation_are_immutable(self) -> None:
        self.assertIn("local_geometry_sha256_equal", PREPARE)
        self.assertIn("schema_and_approximation_equal", PREPARE)
        self.assertIn("convex_hull_absent", PREPARE)
        self.assertIn('physics_approximation"] != "convexHull"', PREPARE)

    def test_phase6dw_lifecycle_is_directly_reused(self) -> None:
        self.assertIn('run_phase6dw_gpu_renderer_case.ps1', MATRIX)
        self.assertNotIn('next_viewport_frame_async', MATRIX)
        self.assertIn('automatic_retry = $false', MATRIX)

    def test_controls_bracket_every_new_condition(self) -> None:
        start = MATRIX.index('"axis_control_start"')
        end = MATRIX.index('"axis_control_end"')
        for label in (
            '"rotate_x17"',
            '"rotate_y12"',
            '"rotate_z90_log02"',
            '"phase6dr_z37"',
            '"rotate_xyz_17_12_37"',
        ):
            self.assertLess(start, MATRIX.index(label))
            self.assertLess(MATRIX.index(label), end)

    def test_readback_uses_inverse_transformed_local_cylinder_roi(self) -> None:
        self.assertIn("world_to_local = local_to_world.GetInverse()", FLOW)
        self.assertIn("_local_roi_contains(world_to_local.Transform(point), bounds)", FLOW)
        self.assertIn('"cylinder_inside"', FLOW)
        self.assertIn('"scalar_noise_threshold": 1.0e-6', FLOW)
        self.assertIn('"velocity_noise_threshold_m_s": 1.0e-5', FLOW)

    def test_convex_hull_is_never_a_runtime_case(self) -> None:
        self.assertNotIn("convexHull", MATRIX)
        self.assertIn("phase6dz_rotated_mesh", MATRIX)


if __name__ == "__main__":
    unittest.main()
