from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_phase6fv_memory_ceiling_qualification import _identity_cleanup_gate


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6fv_memory_ceiling_qualification_contract.json"
RUNNER = SCRIPTS / "run_phase6fv_memory_ceiling_qualification.ps1"
CASE_RUNNER = SCRIPTS / "run_phase6fo_supply_case.ps1"
PROBE = SCRIPTS / "probe_phase6fo_supply_comparison.py"
ANALYZER = SCRIPTS / "analyze_phase6fv_memory_ceiling_qualification.py"


class Phase6FvMemoryCeilingQualification(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.runner = RUNNER.read_text(encoding="utf-8")
        self.analyzer = ANALYZER.read_text(encoding="utf-8")

    def test_new_phase_freezes_history_and_population(self):
        self.assertEqual("phase6fv", self.contract["phase"])
        self.assertFalse(self.contract["frozen_history"]["phase6ft_reclassified"])
        self.assertFalse(self.contract["frozen_history"]["phase6ft_artifact_reused"])
        self.assertFalse(self.contract["frozen_history"]["phase6fo_restarted"])
        self.assertEqual(9, self.contract["population"]["required_representative_processes"])
        self.assertEqual(
            [
                ["M0_baseline", "M1_phase6fo_equivalent", "M2_pre_readback_frame"],
                ["M1_phase6fo_equivalent", "M2_pre_readback_frame", "M0_baseline"],
                ["M2_pre_readback_frame", "M0_baseline", "M1_phase6fo_equivalent"],
            ],
            self.contract["population"]["orders"],
        )

    def test_resource_contract_is_predeclared(self):
        safety = self.contract["safety"]
        self.assertEqual(14 * 1024**3, safety["legacy_kit_evaluation_threshold_bytes"])
        self.assertFalse(safety["legacy_threshold_is_kill_condition"])
        self.assertEqual(16 * 1024**3, safety["kit_absolute_stop_bytes"])
        self.assertEqual(17 * 1024**3, safety["unique_tree_absolute_stop_bytes"])
        self.assertEqual(512 * 1024**2, safety["minimum_candidate_headroom_bytes"])
        self.assertEqual(180, safety["stage_close_timeout_seconds"])
        self.assertFalse(self.contract["boundedness"]["slope_alone_is_gate"])

    def test_runner_reuses_shared_lifecycle_and_phase6fu_guard(self):
        self.assertIn('$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"', self.runner)
        self.assertIn('$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"', self.runner)
        self.assertIn('[ValidateSet("phase6fv")][string]$CaseReportPhase = "phase6fv"', self.runner)
        self.assertIn('"-ReportPhase", $CaseReportPhase', self.runner)
        self.assertIn('"--kit-private-limit", "$($contract.safety.kit_absolute_stop_bytes)"', self.runner)
        self.assertIn('"--tree-private-limit", "$($contract.safety.unique_tree_absolute_stop_bytes)"', self.runner)
        self.assertIn('"--cleanup-suppression-lock"', self.runner)
        self.assertIn("phase6fv", CASE_RUNNER.read_text(encoding="utf-8"))
        self.assertIn('"phase6fv"', PROBE.read_text(encoding="utf-8"))

    def test_runtime_hashes_match(self):
        mapping = {
            "phase6fu_resource_guard_sha256": "phase6fu_resource_guard.py",
            "phase6fu_process_identity_sha256": "phase6fu_process_identity.py",
            "frozen_phase6eg_resource_guard_sha256": "phase6eg_resource_guard.py",
            "shared_case_runner_sha256": "run_phase6fo_supply_case.ps1",
            "shared_probe_sha256": "probe_phase6fo_supply_comparison.py",
        }
        for key, name in mapping.items():
            if key == "shared_case_runner_sha256":
                self.assertRegex(self.contract["runtime_hashes"][key], r"^[0-9A-F]{64}$")
                continue  # historical runner hash; later phases extend the shared harness
            self.assertEqual(
                self.contract["runtime_hashes"][key],
                hashlib.sha256((SCRIPTS / name).read_bytes()).hexdigest().upper(),
            )
        # Phase 6FV is frozen evidence. Later diagnostic phases may harden the
        # shared shutdown policy without rewriting the historical contract.
        self.assertEqual(
            self.contract["runtime_hashes"]["kit_shutdown_policy_sha256"],
            "07D52B2BEB45B17D16AE768068C56E7537F02948C349231BE15843578B58216D",
        )
        self.assertNotEqual(
            self.contract["runtime_hashes"]["kit_shutdown_policy_sha256"],
            hashlib.sha256((SCRIPTS / "kit_shutdown_policy.ps1").read_bytes()).hexdigest().upper(),
        )

    def test_exact_cleanup_evidence_is_a_formal_gate(self):
        for token in (
            "phase6fu_cleanup_schema_missing",
            "exact_identity_fields_incomplete",
            "dual_source_absence_not_confirmed",
            "identity_unknown_unresolved",
            "identity_mismatch_observed",
            "cleanup_suppression_not_released",
        ):
            self.assertIn(token, self.analyzer)

    def test_identity_fixture_accepts_dual_confirmed_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "runner-logs"
            logs.mkdir()
            (logs / "cleanup_markers.jsonl").write_text(
                '{"marker":"cleanup_suppression_released"}\n{"marker":"exact_cleanup_complete"}\n',
                encoding="utf-8",
            )
            identity = {
                "pid": 42,
                "create_time_utc_epoch": 1.0,
                "path": "C:/fixture.exe",
                "parent_pid": 1,
                "observed_at_utc_epoch": 2.0,
                "role": "fixture",
                "root_attempt_id": "attempt01",
            }
            attempt = {
                "cleanup": {
                    "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
                    "before": [{"identity": identity}],
                    "absence_confirmation_sources": ["psutil", "win32"],
                    "all_matching_absent": True,
                    "all_observed_absent": True,
                    "final_unknown": [],
                    "protected_identity_mismatch": [],
                    "cleanup_suppression": {"released": True, "timed_out": False},
                }
            }
            failures, evidence = _identity_cleanup_gate(root, attempt)
            self.assertEqual([], failures)
            self.assertTrue(evidence["identity_fields_complete"])

    def test_identity_unknown_and_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "runner-logs"
            logs.mkdir()
            (logs / "cleanup_markers.jsonl").write_text(
                '{"marker":"cleanup_suppression_released"}\n{"marker":"exact_cleanup_complete"}\n',
                encoding="utf-8",
            )
            attempt = {
                "cleanup": {
                    "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
                    "before": [],
                    "absence_confirmation_sources": ["psutil"],
                    "all_matching_absent": False,
                    "all_observed_absent": False,
                    "final_unknown": [{"state": "query_failed_unknown"}],
                    "protected_identity_mismatch": [{"state": "alive_identity_mismatch"}],
                    "cleanup_suppression": {"released": False, "timed_out": True},
                }
            }
            failures, _ = _identity_cleanup_gate(root, attempt)
            self.assertIn("identity_unknown_unresolved", failures)
            self.assertIn("identity_mismatch_observed", failures)
            self.assertIn("cleanup_suppression_not_released", failures)

    def test_contract_hash_sidecar_matches(self):
        sidecar = CONTRACT.with_suffix(".sha256")
        expected = sidecar.read_text(encoding="utf-8").split()[0].upper()
        self.assertEqual(expected, hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper())

    def test_published_identity_safe_stop_does_not_qualify_or_restart(self):
        summary = json.loads(
            (ROOT / "docs" / "devlog" / "assets" / "phase6" / "memory_ceiling_post6fu_safe_stop.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("identity_safe_stop", summary["status"])
        self.assertEqual(3, summary["population"]["launched"])
        self.assertEqual(1, summary["population"]["nonreplaceable_failure"])
        self.assertFalse(summary["memory_decision"]["kit_16_gib_qualified"])
        self.assertFalse(summary["memory_decision"]["tree_17_gib_qualified"])
        self.assertFalse(summary["phase6fo_restarted"])
        identity = summary["identity_safe_stop"]
        self.assertFalse(identity["termination_attempted_for_mismatch"])
        self.assertEqual(0, identity["matching_remaining"])
        self.assertEqual(0, identity["final_unknown"])


if __name__ == "__main__":
    unittest.main()
