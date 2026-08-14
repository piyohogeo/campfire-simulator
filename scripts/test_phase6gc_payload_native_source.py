import tempfile
import unittest
import json
from pathlib import Path

from scripts.run_phase6gc_source_contract_fixtures import run


class Phase6GcPayloadNativeSource(unittest.TestCase):
    def test_all_payload_native_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run(Path(directory) / "fixtures")
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_count"], 16)
        self.assertTrue(all(row["actual_pass"] == row["expected_pass"] for row in report["cases"]))

    def test_physics_and_safety_contract_remain_frozen(self):
        root = Path(__file__).resolve().parent
        old = json.loads((root / "phase6gb_supply_comparison_contract.json").read_text(encoding="utf-8"))
        new = json.loads((root / "phase6gc_supply_comparison_contract.json").read_text(encoding="utf-8"))
        for key in ("fixture", "conditions", "sample_frames", "readback_frames", "spatial", "hard_gates", "materiality", "formal_population", "artifact_commit", "safety", "gpu_contract", "visual", "out_of_scope"):
            self.assertEqual(old[key], new[key], key)


if __name__ == "__main__":
    unittest.main()
