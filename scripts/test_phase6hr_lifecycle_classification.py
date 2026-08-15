from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_phase6hr_preflight import ROOT, _base, _produce


class Phase6HRLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / "scripts/phase6hr_ngx_cleanup_proxy_contract.json").read_text(encoding="utf-8"))

    def classify(self, kinds=()):
        temporary = tempfile.TemporaryDirectory(prefix="phase6hr-test-")
        self.addCleanup(temporary.cleanup)
        _, guard, parent = _produce(Path(temporary.name), self.policy, _base(self.policy, kinds))
        self.assertEqual(guard, parent)
        return parent

    def test_natural(self):
        self.assertEqual("natural_clean_exit", self.classify()["classification"])

    def test_telemetry(self):
        self.assertEqual("cleanup_assisted_telemetry_exit", self.classify(("telemetry",))["classification"])

    def test_ngx_tree(self):
        result = self.classify(("ngx", "conhost"))
        self.assertEqual("cleanup_assisted_ngx_exit", result["classification"])
        self.assertEqual([400, 401], result["killed_pid_set"])

    def test_incomplete_tree_fails_closed(self):
        self.assertEqual("cleanup_failure", self.classify(("ngx",))["classification"])

    def test_safety_limits_unchanged(self):
        self.assertEqual(16 * 1024**3, self.policy["safety"]["kit_private_limit_bytes"])
        self.assertEqual(17 * 1024**3, self.policy["safety"]["unique_tree_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, self.policy["safety"]["runner_private_limit_bytes"])


if __name__ == "__main__":
    unittest.main()
