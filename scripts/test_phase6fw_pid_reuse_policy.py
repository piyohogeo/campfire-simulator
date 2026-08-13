from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from scripts.phase6fw_pid_reuse_fixtures import fixture_cases
from scripts.phase6fw_pid_reuse_policy import classify, compare_creation_times, compare_windows_paths


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6fw_pid_reuse_policy_contract.json"
CONTRACT_SHA = ROOT / "scripts/phase6fw_pid_reuse_policy_contract.sha256"


class Phase6FwPidReusePolicy(unittest.TestCase):
    def test_contract_sha_and_frozen_scope(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        expected = CONTRACT_SHA.read_text(encoding="ascii").split()[0].upper()
        actual = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
        self.assertEqual(expected, actual)
        self.assertEqual("phase6fw", contract["phase"])
        self.assertFalse(contract["frozen_history"]["phase6fv_reclassified"])
        self.assertFalse(contract["next_phase_boundary"]["memory_population_started_here"])

    def test_all_fifteen_frozen_cases(self) -> None:
        cases = fixture_cases()
        self.assertEqual(15, len(cases))
        for case in cases:
            with self.subTest(case=case["name"]):
                decision = classify(case["payload"])
                classifications = [row["classification"] for row in decision["identities"]]
                self.assertEqual(case["expected_qualified"], decision["qualified"])
                self.assertIn(case["expected_classification"], classifications)

    def test_access_denied_alone_is_not_reuse_evidence(self) -> None:
        case = fixture_cases()[7]
        case["payload"]["cleanup"]["final"][0]["queries"] = [
            {"state": "access_denied_unknown", "source": "win32", "win32_error": 5}
        ]
        decision = classify(case["payload"])
        self.assertFalse(decision["qualified"])
        self.assertIn("trusted_complete_current_identity_missing", decision["global_failures"])

    def test_time_tolerance_is_explicit(self) -> None:
        self.assertEqual("same", compare_creation_times(1000.0, 1001.0)["result"])
        self.assertEqual("different", compare_creation_times(1000.0, 1001.000001)["result"])
        self.assertEqual("unknown", compare_creation_times(None, 1001.0)["result"])

    def test_namespace_and_case_normalization(self) -> None:
        comparison = compare_windows_paths(
            r"\\?\C:\Windows\System32\CONHOST.EXE",
            r"c:\windows\system32\conhost.exe",
        )
        self.assertEqual("same", comparison["result"])

    def test_unresolved_same_basename_alias_fails_closed(self) -> None:
        comparison = compare_windows_paths(
            r"C:\missing-one\same.exe",
            r"C:\missing-two\same.exe",
        )
        self.assertEqual("unknown", comparison["result"])

    def test_marker_order_and_suppression_are_required(self) -> None:
        case = fixture_cases()[0]
        case["payload"]["cleanup_markers"].reverse()
        case["payload"]["cleanup"]["cleanup_suppression"]["released"] = False
        decision = classify(case["payload"])
        self.assertFalse(decision["qualified"])
        self.assertIn("cleanup_marker_integrity", decision["global_failures"])
        self.assertIn("cleanup_suppression_not_released", decision["global_failures"])


if __name__ == "__main__":
    unittest.main()
