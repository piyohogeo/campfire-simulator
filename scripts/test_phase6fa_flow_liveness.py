import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from phase6fa_occupancy_contract import evaluate


class Phase6FaFlowLivenessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6fa_flow_liveness_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        cls.case_runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        cls.runner = (SCRIPTS / "run_phase6fa_flow_liveness.ps1").read_text(encoding="utf-8")

    def test_contract_hash_and_history_are_frozen(self):
        expected = (SCRIPTS / "phase6fa_flow_liveness_contract.sha256").read_text().split()[0]
        self.assertEqual(expected, hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper())
        self.assertEqual("0066ab3", self.contract["history"]["safe_commit"])
        self.assertFalse(self.contract["history"]["prior_formal_population_reuse"])
        self.assertFalse(self.contract["history"]["retroactive_reclassification"])

    def test_d0_d1_d2_are_single_variable_and_fail_closed(self):
        conditions = self.contract["conditions"]
        self.assertEqual([item["id"] for item in conditions], ["D0_no_readback", "D1_readback_release", "D2_fuel_asarray"])
        self.assertEqual([item["numpy_asarray_calls"] for item in conditions], [0, 0, 1])
        self.assertFalse(self.contract["execution"]["automatic_retry"])
        self.assertIn('Invoke-Case "D0_no_readback" "none" $false', self.runner)
        self.assertIn('Invoke-Case "D1_readback_release" "acquire_discard_release" $true', self.runner)
        self.assertIn('Invoke-Case "D2_fuel_asarray" "fuel_convert_release" $true', self.runner)
        self.assertLess(self.runner.index("D0_no_readback"), self.runner.index("D1_readback_release"))
        self.assertLess(self.runner.index("D1_readback_release"), self.runner.index("D2_fuel_asarray"))

    def test_constant_branch_requires_liveness_and_representative_field(self):
        thresholds = self.contract["occupancy_stationarity_thresholds"]
        dynamic = thresholds["dynamic_thresholds"]
        rows = [
            {
                "wall_seconds": index * 0.5, "active_blocks": 24.0,
                "kit_private_bytes": 10 * 1024**3, "kit_working_set_bytes": 8 * 1024**3,
                "tree_private_bytes": 11 * 1024**3, "gpu_dedicated_memory_mib": 3000.0,
            }
            for index in range(dynamic["minimum_aligned_samples"] + 9)
        ]
        functional = {key: True for key in (
            "telemetry_fresh", "timeline_advanced", "timeline_playing", "emitter_input_positive",
            "point_revision_expected", "stage_identity_unchanged", "flow_identity_unchanged", "meaningful_flow_field",
        )}
        result = evaluate(rows, thresholds, functional)
        self.assertEqual("constant_occupancy", result["classification"])
        self.assertFalse(result["gate_pass"])
        self.assertFalse(result["checks"]["minimum_representative_occupancy"])
        rows = [dict(row, active_blocks=900.0) for row in rows]
        self.assertTrue(evaluate(rows, thresholds, functional)["gate_pass"])
        functional["telemetry_fresh"] = False
        self.assertFalse(evaluate(rows, thresholds, functional)["gate_pass"])

    def test_synthetic_fixture_covers_bounded_and_failure_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                [sys.executable, str(SCRIPTS / "run_phase6fa_synthetic_fixture.py"),
                 "--contract", str(self.contract_path), "--output", directory],
                check=True, timeout=30,
            )
            report = json.loads((Path(directory) / "synthetic_fixture_report.json").read_text(encoding="utf-8"))
        self.assertEqual("pass", report["status"])
        for name in ("constant_flat", "constant_bounded_noise", "dynamic_bounded", "drop_memory_recovery"):
            self.assertTrue(report["cases"][name]["actual_gate_pass"])
        for name in (
            "constant_linear_memory_growth", "constant_accelerating_memory_growth", "stale_active_telemetry",
            "timeline_stopped", "emitter_input_missing", "empty_flow_field", "unrepresentative_24_blocks",
            "drop_without_memory_recovery",
        ):
            self.assertFalse(report["cases"][name]["actual_gate_pass"])

    def test_public_liveness_decode_is_bounded_and_not_a_private_occupancy_claim(self):
        for token in (
            '"flow_liveness_audit"', '"fuel_liveness_decode"', '"fuel_liveness_decode_before"',
            '"fuel_liveness_decode_after"', '"flow_occupancy_mask_claimed": False',
            'path.unlink(missing_ok=True)', '"flow_liveness_history"',
        ):
            self.assertIn(token, self.probe)
        self.assertIn('"phase6fa"', self.case_runner)
        self.assertIn('"--/phase6ep/flowLivenessAudit=$FlowLivenessAudit"', self.case_runner)
        self.assertIn('"--/phase6ep/fuelLivenessDecode=$FuelLivenessDecode"', self.case_runner)

    def test_resource_ceilings_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(14 * 1024**3, safety["kit_private_limit_bytes"])
        self.assertEqual(16 * 1024**3, safety["unique_tree_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, safety["runner_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, safety["diagnostic_private_limit_bytes"])
        self.assertFalse(safety["resource_ceiling_change"])
        self.assertFalse(safety["private_api"])


if __name__ == "__main__":
    unittest.main()
