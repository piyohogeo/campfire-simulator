from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.phase6fu_process_identity import (
    ACCESS_DENIED_UNKNOWN,
    ALIVE_IDENTITY_MATCH,
    ALIVE_IDENTITY_MISMATCH,
    CONFIRMED_EXITED,
    QUERY_FAILED_UNKNOWN,
    combine_query_results,
    exact_cleanup,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GUARD = (SCRIPTS / "phase6fu_resource_guard.py").read_text(encoding="utf-8")
POLICY = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
COMMON = (SCRIPTS / "phase6ea_diagnostic_common.ps1").read_text(encoding="utf-8")
CONTRACT = SCRIPTS / "phase6fu_diagnostic_cleanup_contract.json"
PUBLISHED = ROOT / "docs" / "devlog" / "assets" / "phase6" / "diagnostic_identity_cleanup_qualification.json"
DEVLOG = ROOT / "docs" / "devlog" / "index.html"


class Phase6FuDiagnosticCleanup(unittest.TestCase):
    def test_state_combination_is_fail_closed(self):
        self.assertEqual(CONFIRMED_EXITED, combine_query_results({"state": CONFIRMED_EXITED}, {"state": CONFIRMED_EXITED}))
        self.assertEqual(ALIVE_IDENTITY_MATCH, combine_query_results({"state": QUERY_FAILED_UNKNOWN}, {"state": ALIVE_IDENTITY_MATCH}))
        self.assertEqual(ALIVE_IDENTITY_MISMATCH, combine_query_results({"state": ALIVE_IDENTITY_MISMATCH}, {"state": ALIVE_IDENTITY_MATCH}))
        self.assertEqual(ACCESS_DENIED_UNKNOWN, combine_query_results({"state": ACCESS_DENIED_UNKNOWN}, {"state": QUERY_FAILED_UNKNOWN}))

    def test_unknown_and_mismatch_are_never_killed(self):
        identity = {"pid": 42, "create_time_utc_epoch": 1.0, "path": "C:/fixture.exe", "parent_pid": 1, "role": "fixture", "root_attempt_id": "test", "observed_at_utc_epoch": 1.0}
        killed: list[int] = []
        mismatch = lambda _: {"state": ALIVE_IDENTITY_MISMATCH, "source": "fixture"}
        summary = exact_cleanup([identity], kill=killed.append, primary_query=mismatch, independent_query=mismatch, retry_count=1)
        self.assertEqual([], killed)
        self.assertTrue(summary["protected_identity_mismatch"])

        unknown = lambda _: {"state": QUERY_FAILED_UNKNOWN, "source": "fixture"}
        summary = exact_cleanup([identity], kill=killed.append, primary_query=unknown, independent_query=unknown, retry_count=1)
        self.assertEqual([], killed)
        self.assertFalse(summary["all_matching_absent"])
        self.assertTrue(summary["final_unknown"])

    def test_guard_has_suppression_and_exact_cleanup(self):
        self.assertIn("--cleanup-suppression-lock", GUARD)
        self.assertIn("wait_for_cleanup_suppression", GUARD)
        self.assertIn("exact_cleanup", GUARD)
        self.assertIn("legacy._cleanup_observed_processes = cleanup_observed_exact", GUARD)

    def test_powershell_state_model_and_dual_query(self):
        for state in (
            "alive_identity_match", "alive_identity_mismatch", "confirmed_exited",
            "query_failed_unknown", "access_denied_unknown",
            "creation_time_unavailable_unknown", "path_unavailable_unknown",
        ):
            self.assertIn(state, COMMON)
        self.assertIn("Get-CimInstance Win32_Process -Filter", COMMON)
        self.assertIn("Get-Phase6EaProcessIdentityState", POLICY)

    def test_diagnostic_ownership_and_partial_artifact(self):
        self.assertIn("diagnostic_ownership_acquired", POLICY)
        self.assertIn("diagnostic_ownership_released", POLICY)
        self.assertIn("partial-diagnostic.json", POLICY)
        self.assertIn("[IO.FileMode]::CreateNew", POLICY)

    def test_contract_hash(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual("phase6fu", contract["phase"])
        self.assertFalse(contract["progression"]["phase6fo_restarted"])
        self.assertFalse(contract["progression"]["memory_population_restarted"])
        sidecar = CONTRACT.with_suffix(".sha256")
        expected = sidecar.read_text(encoding="utf-8").split()[0].upper()
        self.assertEqual(expected, hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper())

    def test_published_result_preserves_progression_boundary(self):
        report = json.loads(PUBLISHED.read_text(encoding="utf-8"))
        self.assertEqual("qualified", report["status"])
        self.assertFalse(report["history"]["phase6fo_restarted"])
        self.assertFalse(report["history"]["memory_population_restarted"])
        self.assertFalse(report["next"]["kit_16_gib_qualified"])
        self.assertEqual(0, report["residual_process_count"])
        devlog = DEVLOG.read_text(encoding="utf-8")
        self.assertIn('id="phase-6fu"', devlog)
        self.assertIn("Phase 6FOはblocked", devlog)


if __name__ == "__main__":
    unittest.main()
