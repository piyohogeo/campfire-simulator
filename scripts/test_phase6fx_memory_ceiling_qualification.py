from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_phase6fx_memory_ceiling_qualification import _identity_policy_gate
from scripts.phase6fw_pid_reuse_fixtures import fixture_cases


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6fx_memory_ceiling_qualification_contract.json"
CONTRACT_SHA = ROOT / "scripts/phase6fx_memory_ceiling_qualification_contract.sha256"


class Phase6FxMemoryCeilingQualification(unittest.TestCase):
    def test_contract_hash_population_and_frozen_scope(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        expected = CONTRACT_SHA.read_text(encoding="ascii").split()[0].upper()
        actual = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
        self.assertEqual(expected, actual)
        self.assertEqual("phase6fx", contract["phase"])
        self.assertEqual(9, contract["population"]["required_representative_processes"])
        self.assertEqual(
            [
                ["M0_baseline", "M1_phase6fo_equivalent", "M2_pre_readback_frame"],
                ["M1_phase6fo_equivalent", "M2_pre_readback_frame", "M0_baseline"],
                ["M2_pre_readback_frame", "M0_baseline", "M1_phase6fo_equivalent"],
            ],
            contract["population"]["orders"],
        )
        self.assertFalse(contract["frozen_history"]["phase6fv_reclassified"])
        self.assertFalse(contract["frozen_history"]["phase6fv_artifact_reused"])
        self.assertFalse(contract["frozen_history"]["phase6fo_restarted"])

    def test_safety_limits_and_decision_margin_are_frozen(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        safety = contract["safety"]
        self.assertEqual(14 * 1024**3, safety["legacy_kit_evaluation_threshold_bytes"])
        self.assertFalse(safety["legacy_threshold_is_kill_condition"])
        self.assertEqual(16 * 1024**3, safety["kit_absolute_stop_bytes"])
        self.assertEqual(17 * 1024**3, safety["unique_tree_absolute_stop_bytes"])
        self.assertEqual(512 * 1024**2, safety["minimum_candidate_headroom_bytes"])
        self.assertEqual(int(15.5 * 1024**3), safety["candidate_peak_maximum_bytes"])

    def test_runtime_hashes_match(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        files = {
            "phase6fu_resource_guard_sha256": "phase6fu_resource_guard.py",
            "phase6fu_process_identity_sha256": "phase6fu_process_identity.py",
            "frozen_phase6eg_resource_guard_sha256": "phase6eg_resource_guard.py",
            "kit_shutdown_policy_sha256": "kit_shutdown_policy.ps1",
            "shared_case_runner_sha256": "run_phase6fo_supply_case.ps1",
            "shared_probe_sha256": "probe_phase6fo_supply_comparison.py",
            "qualification_runner_sha256": "run_phase6fv_memory_ceiling_qualification.ps1",
            "phase6fw_policy_sha256": "phase6fw_pid_reuse_policy.py",
        }
        for key, name in files.items():
            with self.subTest(key=key):
                actual = hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest().upper()
                self.assertEqual(contract["runtime_hashes"][key], actual)

    def test_phase6fw_gate_accepts_complete_reuse_and_rejects_unknown(self) -> None:
        for index, expected in ((7, True), (8, False)):
            case = fixture_cases()[index]
            with tempfile.TemporaryDirectory() as directory:
                attempt_root = Path(directory)
                log_root = attempt_root / "runner-logs"
                log_root.mkdir()
                rows = case["payload"]["cleanup_markers"]
                (log_root / "cleanup_markers.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
                )
                failures, evidence = _identity_policy_gate(
                    attempt_root, {"cleanup": case["payload"]["cleanup"]}
                )
                self.assertEqual(expected, not failures)
                self.assertEqual(expected, evidence["qualified"])
                self.assertTrue((log_root / "phase6fw_identity_policy_decision.json").exists())

    def test_runner_reuses_phase6fv_engine_and_never_starts_phase6fo(self) -> None:
        wrapper = (ROOT / "scripts/run_phase6fx_memory_ceiling_qualification.ps1").read_text(encoding="utf-8")
        engine = (ROOT / "scripts/run_phase6fv_memory_ceiling_qualification.ps1").read_text(encoding="utf-8")
        self.assertIn("run_phase6fv_memory_ceiling_qualification.ps1", wrapper)
        self.assertIn("-Phase phase6fx", wrapper)
        self.assertIn('"-ReportPhase", $CaseReportPhase', engine)
        self.assertIn("-CaseReportPhase phase6fv", wrapper)
        self.assertNotIn("run_phase6fo_supply_comparison", wrapper)

    def test_historical_phase6fv_evidence_is_unchanged(self) -> None:
        paths = {
            ROOT / "artifacts/phase6fv-memory-ceiling-1/memory_ceiling_qualification_report.json":
                "914611039770492DECE4A0ACE8EBE4F877580E75F39AF432E65380E6306AF4AA",
            ROOT / "docs/devlog/assets/phase6/memory_ceiling_qualification_safe_stop.json":
                "245A1F2CF1590E3BA65AE471324A6A2A489324A1FF1300561A5A52488C963C7A",
        }
        for path, expected in paths.items():
            with self.subTest(path=path):
                self.assertTrue(path.exists())
                self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest().upper())

    def test_published_safe_stop_never_qualifies_or_restarts(self) -> None:
        summary = json.loads(
            (ROOT / "docs/devlog/assets/phase6/memory_ceiling_phase6fx_safe_stop.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("lifecycle_safe_stop", summary["status"])
        self.assertEqual(5, summary["population"]["representative_pass"])
        self.assertEqual("attempt06", summary["lifecycle_safe_stop"]["active_attempt"])
        self.assertFalse(summary["partial_memory_evidence"]["candidate_16_gib_qualified"])
        self.assertFalse(summary["partial_memory_evidence"]["candidate_17_gib_tree_qualified"])
        self.assertFalse(summary["decision"]["phase6fo_restart_ready"])
        self.assertEqual(0, summary["identity_cleanup"]["final_kit_cdb_gpu_helper_residual"])
        html = (ROOT / "docs/devlog/index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6fx"', html)
        self.assertIn("memory_ceiling_phase6fx_safe_stop.json", html)


if __name__ == "__main__":
    unittest.main()
