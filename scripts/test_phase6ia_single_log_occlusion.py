from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6IASingleLogTests(unittest.TestCase):
    def test_cross_contract_and_no_kit_preflight(self) -> None:
        contract = SCRIPTS / "phase6ia_single_log_occlusion_contract.json"
        sidecar = SCRIPTS / "phase6ia_single_log_occlusion_contract.sha256"
        digest = hashlib.sha256(contract.read_bytes()).hexdigest().upper()
        self.assertEqual(digest, sidecar.read_text(encoding="ascii").split()[0].upper())
        policy = json.loads(contract.read_text(encoding="utf-8"))
        self.assertEqual(policy["execution"]["condition_order"], ["collision_off", "collision_on"])
        self.assertEqual(policy["execution"]["retry"], 0)
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
            output = Path(temporary) / "preflight"
            completed = subprocess.run([sys.executable, str(SCRIPTS / "run_phase6ia_preflight.py"), "--output-root", str(output)], cwd=ROOT, timeout=30)
            report = json.loads((output / "preflight_report.json").read_text(encoding="utf-8"))
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual(report["kit_launch_count"], 0)
        self.assertEqual(sum(report["fixture_counts"].values()), 62)


if __name__ == "__main__":
    unittest.main()

