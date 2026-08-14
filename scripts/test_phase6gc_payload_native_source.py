import tempfile
import unittest
import json
import hashlib
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

    def test_phase6gc_probe_is_isolated_from_frozen_shared_probe(self):
        root = Path(__file__).resolve().parent
        frozen = root / "probe_phase6fo_supply_comparison.py"
        self.assertEqual(
            hashlib.sha256(frozen.read_bytes()).hexdigest().upper(),
            "1FC443EFA81D10A5ECDAB1635AEE5E66E75F63A456D4C7C2A86A966B3FCBE47E",
        )
        wrapper = (root / "probe_phase6gc_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn('probe_phase6gc_shared_supply_comparison.py', wrapper)


if __name__ == "__main__":
    unittest.main()
