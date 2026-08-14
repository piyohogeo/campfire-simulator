import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "phase6gb_supply_comparison_contract.json"


class Phase6GbGeometryBinding(unittest.TestCase):
    def test_contract_hash_and_explicit_mapping(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        expected = (ROOT / "phase6gb_supply_comparison_contract.sha256").read_text(encoding="utf-8").split()[0]
        observed = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
        self.assertEqual(expected, observed)
        self.assertEqual(contract["phase"], "phase6gb")
        self.assertEqual(contract["fixture"]["geometry"]["concept"], "corrected")
        self.assertEqual(contract["fixture"]["geometry"]["runtime_token"], "phase6er_corrected")
        self.assertNotEqual(
            contract["fixture"]["geometry"]["runtime_token"],
            contract["fixture"]["geometry"]["legacy_runtime_token"],
        )

    def test_case_runner_has_fail_closed_geometry_boundary(self):
        text = (ROOT / "run_phase6fo_supply_case.ps1").read_text(encoding="utf-8")
        self.assertIn('"phase6ga", "phase6gb"', text)
        self.assertIn("ExpectedGeometryConcept", text)
        self.assertIn("must map to runtime token 'phase6er_corrected'", text)
        self.assertIn("ValidateArgumentsOnly", text)
        self.assertIn("kit_started = $false", text)
        self.assertLess(text.index("if ($ValidateArgumentsOnly.IsPresent)"), text.index("Start-Process -FilePath $kit"))

    def test_formal_runner_maps_concept_before_case_launch(self):
        text = (ROOT / "run_phase6fo_supply_comparison.ps1").read_text(encoding="utf-8")
        self.assertIn('$geometryConcept = [string]$contract.fixture.geometry.concept', text)
        self.assertIn('$geometryRuntimeToken = [string]$contract.fixture.geometry.runtime_token', text)
        self.assertIn('"-GeometryVariant", $geometryRuntimeToken', text)
        self.assertIn('"-ExpectedGeometryConcept", $geometryConcept', text)
        self.assertIn("run_phase6gb_parameter_binding_fixtures.ps1", text)

    def test_binding_fixture_exercises_positive_and_negative_runtime_paths(self):
        text = (ROOT / "run_phase6gb_parameter_binding_fixtures.ps1").read_text(encoding="utf-8")
        for name in (
            "positive_corrected_mapping",
            "negative_direct_concept_token",
            "negative_unknown_runtime_token",
            "negative_legacy_misroute",
        ):
            self.assertIn(name, text)
        self.assertIn('"phase6er_corrected" $true', text)
        self.assertIn('"legacy_phase6ep" $false', text)
        self.assertIn("Get-Process -Name kit", text)

    def test_physical_contract_is_unchanged_from_phase6ga(self):
        old = json.loads((ROOT / "phase6ga_supply_comparison_contract.json").read_text(encoding="utf-8"))
        new = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for key in ("conditions", "channel_preflight", "sample_frames", "readback_frames", "spatial", "hard_gates", "materiality", "formal_population", "artifact_commit", "safety"):
            self.assertEqual(old[key], new[key])
        for key in ("scenario", "point_offset_m", "support_radius_assumption_m", "points_total", "points_per_log", "mesh_topology", "velocity_voxel_size_m"):
            self.assertEqual(old["fixture"][key], new["fixture"][key])

    def test_probe_is_exact_path_wrapper(self):
        text = (ROOT / "probe_phase6gb_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn('SHARED_PATH = (SCRIPT_DIR / "probe_phase6fo_supply_comparison.py").resolve()', text)
        self.assertIn("load_exact_module", text)
        self.assertIn("campfire_phase6gb_shared_supply_probe", text)


if __name__ == "__main__":
    unittest.main()
