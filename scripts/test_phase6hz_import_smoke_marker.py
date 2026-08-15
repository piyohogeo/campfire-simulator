from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from phase6hz_exact_kit_import import read_contract, sha256_file
from phase6hz_marker_contract import RESERVED_KEYS, canonical_payload
from phase6hz_marker_fixture import run_fixture


class Phase6HZMarkerTests(unittest.TestCase):
    def test_actual_contract_and_marker_fixture(self) -> None:
        wrapper = SCRIPTS / "probe_phase6hz_import_smoke.py"
        contract = SCRIPTS / "phase6hz_import_smoke_contract.json"
        sidecar = SCRIPTS / "phase6hz_import_smoke_contract.sha256"
        policy, boundary = read_contract(wrapper, contract, sidecar)
        self.assertEqual(policy["baseline_commit"], "40ff0e0")
        self.assertEqual(policy["sources"]["wrapper"]["sha256"], sha256_file(wrapper))
        self.assertEqual(Path(boundary["scripts_path"]), SCRIPTS.resolve())
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
            report = run_fixture(Path(temporary) / "fixture")
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual(report["case_count"], 11)

    def test_reserved_and_duplicate_keys_fail_closed(self) -> None:
        self.assertIn("path", RESERVED_KEYS)
        self.assertIn("marker_file", RESERVED_KEYS)
        with self.assertRaisesRegex(ValueError, "reserved_marker_key_collision:path"):
            canonical_payload("kit_app_ready", [{"attempt_id": "x", "path": "bad"}])
        with self.assertRaisesRegex(ValueError, "duplicate_marker_key:attempt_id"):
            canonical_payload("kit_app_ready", [{"attempt_id": "x"}, {"attempt_id": "x"}])


if __name__ == "__main__":
    unittest.main()
