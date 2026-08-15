from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from phase6hy_exact_import_fixture import run_fixture
from phase6hy_exact_kit_import import read_contract, sha256_file


class Phase6HYImportTests(unittest.TestCase):
    def test_actual_contract_and_fixture(self) -> None:
        wrapper = SCRIPTS / "probe_phase6hy_single_log_occlusion.py"
        contract = SCRIPTS / "phase6hy_exact_kit_import_contract.json"
        sidecar = SCRIPTS / "phase6hy_exact_kit_import_contract.sha256"
        policy, boundary = read_contract(wrapper, contract, sidecar)
        self.assertEqual(policy["baseline_commit"], "4d83948")
        self.assertEqual(policy["sources"]["wrapper"]["sha256"], sha256_file(wrapper))
        self.assertEqual(Path(boundary["scripts_path"]), SCRIPTS.resolve())
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
            report = run_fixture(Path(temporary) / "fixture")
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual(report["case_count"], 12)

    def test_frozen_scene_contract_identity(self) -> None:
        policy = json.loads((SCRIPTS / "phase6hy_exact_kit_import_contract.json").read_text(encoding="utf-8"))
        child = SCRIPTS / policy["frozen_probe_contract"]["path"].split("scripts/", 1)[1]
        self.assertEqual(sha256_file(child), policy["frozen_probe_contract"]["sha256"])
        self.assertFalse(policy["frozen_history"]["reclassified"])
        self.assertFalse(policy["frozen_history"]["runtime_attempt_reused"])


if __name__ == "__main__":
    unittest.main()
