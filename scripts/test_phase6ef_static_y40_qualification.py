"""Targeted contracts for Phase 6EF static-Y40 qualification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "scripts" / "phase6ef_static_y40_qualification_contract.json"


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(result)
    return result


ANALYZE = module(
    "phase6ef_analyze_test",
    ROOT / "scripts" / "analyze_phase6ef_static_y40_qualification.py",
)


def region(maximum: float, available: bool = True) -> dict:
    return {
        "available": available,
        "voxel_count": 4 if available else 0,
        "mean": maximum / 2.0 if available else 0.0,
        "p50": maximum / 2.0 if available else 0.0,
        "p95": maximum if available else 0.0,
        "maximum": maximum,
        "threshold_counts": {},
    }


def sample(deep: float, center: float, axis_only: float) -> dict:
    return {
        "outside_halo": region(1.0),
        "boundary_0_to_1_voxel": region(4.0),
        "deep_interior": region(deep),
        "center_axis_near": region(center),
        "axis_reference_deep": region(axis_only),
        "rotated_only": region(deep),
        "axis_only": region(axis_only),
        "overlap": region(deep),
    }


def matrix(a=(0.0, 0.0, 0.5), b=(8e-6, 7e-6, 1.0), c=(2.0, 1.0, 1.0)) -> dict:
    result = {}
    for run in range(1, 4):
        result[str(run)] = {}
        for condition, values in zip(ANALYZE.CONDITIONS, (a, b, c)):
            result[str(run)][condition] = {
                str(frame): sample(*values) for frame in ANALYZE.FRAMES
            }
    return result


class Phase6EfContract(unittest.TestCase):
    def test_thresholds_and_rotated_orders_are_predeclared(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertTrue(contract["declared_before_formal_runs"])
        self.assertEqual(contract["thresholds"]["existing_velocity_limit_m_s"], 1e-5)
        self.assertEqual(contract["thresholds"]["collision_off_positive_minimum_m_s"], 0.1)
        self.assertEqual(contract["thresholds"]["rotated_on_to_off_deep_maximum_ratio"], 0.01)
        self.assertEqual(
            contract["run_order"],
            [
                ["A_axis_on", "B_rotate_y40_on", "C_rotate_y40_off"],
                ["B_rotate_y40_on", "C_rotate_y40_off", "A_axis_on"],
                ["C_rotate_y40_off", "A_axis_on", "B_rotate_y40_on"],
            ],
        )
        self.assertFalse(contract["history_contract"]["phase6ec_gate_changed"])
        self.assertFalse(contract["geometry_contract"]["flow_internal_occupancy_mask_public_api_available"])

    def test_runner_reuses_guarded_lifecycle_and_velocity_only_capture(self):
        runner = (ROOT / "scripts" / "run_phase6ef_static_y40_qualification.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-Phase6EaGuardedHelper", runner)
        self.assertIn("run_phase6dt_flow_collision_case.ps1", runner)
        self.assertIn("-SpatialVelocityOnly", runner)
        self.assertIn("-TimeoutSeconds 720", runner)
        self.assertIn("-PrivateBytesLimit 512MB", runner)
        self.assertIn('lifecycle_status -ne "normal_exit"', runner)
        self.assertIn("refuses artifact root reuse", runner)
        self.assertIn("for ($runIndex = 1; $runIndex -le 3; $runIndex++)", runner)
        analyzer = (ROOT / "scripts" / "analyze_phase6ef_static_y40_qualification.py").read_text(encoding="utf-8")
        self.assertIn('condition != "C_rotate_y40_off"', analyzer)
        self.assertIn('b_input["collider"] == c_input["collider"]', analyzer)
        self.assertIn('a_input["emitter"] == b_input["emitter"] == c_input["emitter"]', analyzer)

    def test_shared_capture_defaults_to_all_channels(self):
        runner = (ROOT / "scripts" / "run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
        probe = (ROOT / "scripts" / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
        self.assertIn("[switch]$SpatialVelocityOnly", runner)
        self.assertIn("velocity-only capture requires spatial output", runner)
        self.assertIn("phase6ee_spatial_velocity_only", probe)
        self.assertIn('not spatial_velocity_only or channel == "velocity"', probe)


class Phase6EfGates(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_boundary_velocity_is_reported_but_not_a_zero_gate(self):
        samples = matrix()
        for run in samples.values():
            for condition in run.values():
                for frame in condition.values():
                    frame["boundary_0_to_1_voxel"] = region(9.0)
        _, checks = ANALYZE.evaluate_samples(samples, self.contract)
        self.assertTrue(all(item["pass"] for item in checks))

    def test_deep_velocity_over_existing_limit_fails(self):
        _, checks = ANALYZE.evaluate_samples(matrix(b=(1.1e-5, 7e-6, 1.0)), self.contract)
        self.assertFalse(all(item["pass"] for item in checks))
        self.assertFalse(checks[0]["predicates"]["B_deep_at_or_below_limit"])

    def test_collision_off_must_be_a_positive_control(self):
        _, checks = ANALYZE.evaluate_samples(matrix(c=(0.09, 1.0, 1.0)), self.contract)
        self.assertFalse(checks[0]["predicates"]["C_deep_positive"])

    def test_axis_only_cannot_be_marked_pass_when_not_comparable(self):
        _, checks = ANALYZE.evaluate_samples(matrix(b=(8e-6, 7e-6, 0.0), c=(2.0, 1.0, 0.0)), self.contract)
        self.assertFalse(checks[0]["predicates"]["axis_only_C_comparable"])
        self.assertFalse(checks[0]["pass"])


if __name__ == "__main__":
    unittest.main()
