from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6hq_lifecycle_classification import consume_guard_report
from run_phase6hq_preflight import ROOT, _base, _produce_consume


class Phase6HQLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / "scripts/phase6hq_cleanup_assisted_proxy_contract.json").read_text(encoding="utf-8"))

    def produce(self, assisted: bool):
        temporary = tempfile.TemporaryDirectory(prefix="phase6hq-test-")
        self.addCleanup(temporary.cleanup)
        return _produce_consume(Path(temporary.name), self.policy, *_base(self.policy, assisted))

    def test_natural_clean_exit(self):
        guard, parent = self.produce(False)
        self.assertEqual("natural_clean_exit", guard["canonical_lifecycle_classification"])
        self.assertEqual("natural_clean_exit", parent["classification"])
        self.assertTrue(parent["accepted"])

    def test_single_exact_telemetry_cleanup_assisted(self):
        guard, parent = self.produce(True)
        self.assertEqual("cleanup_assisted_exit", guard["canonical_lifecycle_classification"])
        self.assertEqual("cleanup_assisted_exit", parent["classification"])
        self.assertTrue(parent["accepted"])
        self.assertEqual([300], guard["observed_process_cleanup"]["killed_pids"])

    def test_parent_cannot_override_guard_contradiction(self):
        guard, _ = self.produce(True)
        guard = copy.deepcopy(guard)
        guard["status"] = "failed"
        parent = consume_guard_report(guard, self.policy, expected_attempt_id="phase6hq-fixture")
        self.assertFalse(parent["accepted"])
        self.assertEqual("cleanup_failure", parent["classification"])

    def test_safety_and_base_contract_remain_frozen(self):
        self.assertEqual(16 * 1024**3, self.policy["safety"]["kit_private_limit_bytes"])
        self.assertEqual(17 * 1024**3, self.policy["safety"]["unique_tree_private_limit_bytes"])
        self.assertEqual(512 * 1024**2, self.policy["safety"]["runner_private_limit_bytes"])
        self.assertEqual("BEE59EA12B8AAA074D863F2ABB8AA28FA21718682637734E89A8CFEF0A8E15B0", self.policy["base_module_contract_sha256"])


if __name__ == "__main__":
    unittest.main()
