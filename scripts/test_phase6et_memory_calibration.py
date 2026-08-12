import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6EtMemoryCalibrationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = SCRIPTS / "phase6et_memory_calibration_contract.json"
        cls.contract = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_contract_hash_and_phase6es_history_are_frozen(self):
        expected = (SCRIPTS / "phase6et_memory_calibration_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(expected, hashlib.sha256(self.path.read_bytes()).hexdigest().upper())
        self.assertIn("frozen", self.contract["phase6es_history"])
        self.assertFalse(self.contract["return_to_phase6es_comparison"]["not_part_of_this_contract"] is False)

    def test_matrix_is_three_counterbalanced_runs_of_seven_conditions(self):
        ids = [row["id"] for row in self.contract["conditions"]]
        self.assertEqual(7, len(ids))
        self.assertEqual(21, self.contract["formal_process_count"])
        self.assertEqual(3, len(self.contract["run_orders"]))
        for order in self.contract["run_orders"]:
            self.assertEqual(set(ids), set(order))
            self.assertEqual(len(ids), len(order))

    def test_one_variable_channel_boundaries_are_explicit(self):
        rows = {row["id"]: row for row in self.contract["conditions"]}
        self.assertEqual([], rows["A_flow_only"]["readback_channels"])
        self.assertEqual(["fuel"], rows["B_minimal_fuel"]["readback_channels"])
        self.assertEqual(["velocity"], rows["C_velocity"]["readback_channels"])
        self.assertEqual(["temperature"], rows["D_temperature"]["readback_channels"])
        self.assertEqual(["smoke"], rows["E_smoke"]["readback_channels"])
        self.assertFalse(rows["F_velocity_temperature_smoke"]["offline_transport"])
        self.assertTrue(rows["G_directional_transport"]["offline_transport"])

    def test_original_resource_limits_are_not_relaxed(self):
        limits = self.contract["safety"]
        self.assertEqual(14 * 1024**3, limits["kit_private_limit_bytes"])
        self.assertEqual(16 * 1024**3, limits["unique_tree_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, limits["runner_private_limit_bytes"])
        self.assertFalse(limits["automatic_retry"])

    def test_probe_has_bounded_channel_and_marker_switches(self):
        probe = (SCRIPTS / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
        for token in ("readbackChannels", "spatialCollectorsEnabled", "spatialColliderIndices", "resourceMarkerPath"):
            self.assertIn(token, probe + runner)
        for marker in ("readback_started", "channel_started", "channel_complete", "sample_persist_started", "sample_persisted"):
            self.assertIn(marker, probe)
        self.assertNotIn("Get-Content -Raw", (SCRIPTS / "phase6eg_resource_guard.py").read_text(encoding="utf-8"))

    def test_gpu_telemetry_is_direct_to_file_and_shared_is_unavailable(self):
        guard = (SCRIPTS / "phase6eg_resource_guard.py").read_text(encoding="utf-8")
        self.assertIn('"--gpu-csv"', guard)
        self.assertIn("stdout=gpu_stdout", guard)
        self.assertIn('"shared_memory": "unavailable', guard)
        self.assertNotIn("subprocess.PIPE", guard)

    def test_directional_transport_uses_actual_manifest_indices(self):
        transport = (SCRIPTS / "phase6es_directional_transport.py").read_text(encoding="utf-8")
        self.assertIn("spatial_manifest_collider_indices", transport)
        self.assertIn("manifests_by_index", transport)

    def test_analyzer_supports_bundled_python_and_persists_marker_boundaries(self):
        analyzer = (SCRIPTS / "analyze_phase6et_memory_calibration.py").read_text(encoding="utf-8")
        runner = (SCRIPTS / "run_phase6et_memory_calibration.ps1").read_text(encoding="utf-8")
        self.assertNotIn("removesuffix", analyzer)
        self.assertIn("marker_memory", analyzer)
        self.assertIn("if ($LASTEXITCODE -ne 0)", runner)


if __name__ == "__main__":
    unittest.main()
