from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import phase6fy_preclose_committer as committer
from phase6fy_three_axis_policy import classify_attempt, evaluate_population


CONTRACT = SCRIPTS / "phase6fy_three_axis_memory_qualification_contract.json"
HASH = CONTRACT.with_suffix(".sha256")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


class Phase6FyThreeAxisMemoryQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_hash_and_scope(self):
        self.assertEqual(HASH.read_text(encoding="utf-8").split()[0], sha256(CONTRACT))
        self.assertEqual(self.contract["phase"], "phase6fy")
        self.assertFalse(self.contract["frozen_history"]["phase6ft_reclassified"])
        self.assertFalse(self.contract["frozen_history"]["phase6fv_reclassified"])
        self.assertFalse(self.contract["frozen_history"]["phase6fx_reclassified"])
        self.assertFalse(self.contract["decision"]["phase6fo_execution_authorized"])
        self.assertEqual(self.contract["physical_fixture"]["readback_calls"], 0)
        self.assertEqual(self.contract["physical_fixture"]["capture_calls"], 0)

    def test_runtime_hashes_are_frozen(self):
        names = {
            "phase6fu_resource_guard_sha256": "phase6fu_resource_guard.py",
            "phase6fu_process_identity_sha256": "phase6fu_process_identity.py",
            "frozen_phase6eg_resource_guard_sha256": "phase6eg_resource_guard.py",
            "shared_case_runner_sha256": "run_phase6fo_supply_case.ps1",
            "shared_probe_sha256": "probe_phase6fo_supply_comparison.py",
            "phase6fw_policy_sha256": "phase6fw_pid_reuse_policy.py",
            "three_axis_policy_sha256": "phase6fy_three_axis_policy.py",
            "preclose_committer_sha256": "phase6fy_preclose_committer.py",
            "analyzer_sha256": "analyze_phase6fy_three_axis_memory_qualification.py",
            "qualification_runner_sha256": "run_phase6fy_three_axis_memory_qualification.ps1",
            "synchronized_probe_sha256": "probe_phase6fy_three_axis_memory.py",
            "phase6fy_case_runner_sha256": "run_phase6fy_memory_case.ps1",
            "fixture_runner_sha256": "run_phase6fy_three_axis_fixtures.py",
        }
        for key, filename in names.items():
            with self.subTest(key=key):
                self.assertEqual(self.contract["runtime_hashes"][key], sha256(SCRIPTS / filename))
        # The historical contract records the policy used by the frozen 6FY
        # run. Later phases may harden the shared diagnostic policy without
        # rewriting that historical hash or reclassifying the old artifact.
        self.assertEqual(
            self.contract["runtime_hashes"]["kit_shutdown_policy_sha256"],
            "07D52B2BEB45B17D16AE768068C56E7537F02948C349231BE15843578B58216D",
        )
        self.assertNotEqual(
            self.contract["runtime_hashes"]["kit_shutdown_policy_sha256"],
            sha256(SCRIPTS / "kit_shutdown_policy.ps1"),
        )

    def test_three_axes_and_replacement_limits_are_explicit(self):
        self.assertIn("memory_valid_lifecycle_normal", self.contract["classification"]["attempt_classes"])
        self.assertIn("memory_valid_lifecycle_timeout", self.contract["classification"]["attempt_classes"])
        self.assertTrue(self.contract["classification"]["timeout_memory_peak_included_in_formal_distribution"])
        self.assertEqual(self.contract["population"]["required_basic_processes"], 9)
        self.assertEqual(self.contract["population"]["maximum_timeout_replacements"], 2)
        self.assertEqual(self.contract["population"]["maximum_total_launches"], 11)
        self.assertTrue(self.contract["population"]["original_timeout_artifact_remains_formal"])
        self.assertTrue(self.contract["population"]["second_timeout_same_condition_stops_population"])

    def test_safety_and_memory_decision_are_unchanged(self):
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_absolute_stop_bytes"], 16 * 1024**3)
        self.assertEqual(safety["unique_tree_absolute_stop_bytes"], 17 * 1024**3)
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["physical_memory_floor_bytes"], 8 * 1024**3)
        self.assertEqual(safety["commit_headroom_floor_bytes"], 8 * 1024**3)
        self.assertEqual(safety["stage_close_timeout_seconds"], 180)
        self.assertEqual(safety["candidate_peak_maximum_bytes"], int(15.5 * 1024**3))
        self.assertEqual(safety["minimum_candidate_headroom_bytes"], 512 * 1024**2)

    def test_all_twenty_fixtures_pass_and_leave_no_child(self):
        with tempfile.TemporaryDirectory(prefix="phase6fy-fixtures-") as directory:
            output = Path(directory) / "root"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_phase6fy_three_axis_fixtures.py"),
                    "--contract", str(CONTRACT),
                    "--output-root", str(output),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((output / "fixture_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual(report["passed_count"], 20)
            self.assertEqual(report["total_count"], 20)
            self.assertEqual(report["short_lived_process_evidence"]["final_residual_count"], 0)
            self.assertFalse(report["real_kit_started"])

    def test_preclose_committer_streams_and_hashes_before_close(self):
        with tempfile.TemporaryDirectory(prefix="phase6fy-commit-") as directory:
            root = Path(directory)
            raw = root / "raw.json"
            resource = root / "resource.jsonl"
            gpu = root / "gpu.csv"
            markers = root / "markers.jsonl"
            metadata = root / "attempt.json"
            raw.write_text(json.dumps({"status": "ok", "lifecycle_marker": "measurement_complete", "completion_contract": {"results_saved": True}}), encoding="utf-8")
            resource.write_text(json.dumps({
                "sample_index": 1,
                "timestamp_utc_epoch": 1.0,
                "tree_private_bytes": 30,
                "processes": [
                    {"role": "kit", "private_bytes": 10},
                    {"role": "runner", "private_bytes": 10},
                    {"role": "diagnostic", "private_bytes": 10},
                ],
                "machine": {"available_physical_bytes": 100, "estimated_commit_headroom_bytes": 100},
            }) + "\n", encoding="utf-8")
            gpu.write_text("gpu\n", encoding="utf-8")
            markers.write_text(json.dumps({"marker": "measurement_complete", "timestamp_utc": "2026-01-01T00:00:00+00:00"}) + "\n", encoding="utf-8")
            metadata.write_text(json.dumps({"attempt_id": "attempt01", "condition": "M0_baseline", "slot_id": "s1", "slot_kind": "basic", "replacement_for": None}), encoding="utf-8")
            arguments = type("Arguments", (), {
                "raw_path": raw,
                "resource_path": resource,
                "gpu_path": gpu,
                "marker_path": markers,
                "attempt_metadata": metadata,
                "contract": CONTRACT,
                "output_dir": root / "output",
                "private_limit_bytes": 128 * 1024**2,
            })()
            result = committer.commit(arguments)
            self.assertEqual(result["status"], "committed_before_stage_close")
            self.assertFalse(result["stage_close_observed_during_commit"])
            self.assertGreater(result["telemetry"]["resource_sample_count"], 0)
            for details in result["files"].values():
                self.assertEqual(details["sha256"], sha256(Path(details["path"])))

    def test_timeout_remains_in_population_and_cannot_be_overwritten(self):
        rows = [
            {"attempt_id": "a1", "condition": "M0_baseline", "slot_kind": "basic", "classification": "memory_valid_lifecycle_timeout"},
            {"attempt_id": "a2", "condition": "M1_phase6fo_equivalent", "slot_kind": "basic", "classification": "memory_valid_lifecycle_normal"},
            {"attempt_id": "a3", "condition": "M2_pre_readback_frame", "slot_kind": "basic", "classification": "memory_valid_lifecycle_normal"},
        ]
        decision = evaluate_population(rows, self.contract)
        self.assertEqual(decision["memory_valid"], 3)
        self.assertEqual(decision["stage_close_timeout"], 1)
        self.assertIn("a1", decision["pending_replacement_origins"])
        overwritten = [*rows, {"attempt_id": "a1", "condition": "M0_baseline", "slot_kind": "replacement", "replacement_for": "a1", "classification": "memory_valid_lifecycle_normal"}]
        self.assertTrue(evaluate_population(overwritten, self.contract)["population_stopping_failure"])

    def test_diagnostic_degradation_is_separate_but_detach_is_fatal(self):
        report = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_phase6fy_three_axis_fixtures.py"), "--help"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(report.returncode, 0)
        text = (SCRIPTS / "phase6fy_three_axis_policy.py").read_text(encoding="utf-8")
        self.assertIn("diagnostic_attach_unavailable", text)
        self.assertIn("diagnostic_detach_failure", self.contract["diagnostic"]["classifications"])

    def test_runner_never_starts_phase6fo_or_readback(self):
        runner = (SCRIPTS / "run_phase6fy_three_axis_memory_qualification.ps1").read_text(encoding="utf-8")
        case = (SCRIPTS / "run_phase6fy_memory_case.ps1").read_text(encoding="utf-8")
        self.assertIn("Phase 6FO remains stopped", runner)
        self.assertIn("--/phase6ep/readbackChannels=none", case)
        self.assertIn("--/phase6ep/readbackMode=none", case)
        self.assertIn("--/phase6ep/capture=false", case)
        self.assertNotIn("run_phase6fo_supply_comparison.ps1", runner)

    def test_published_safe_stop_excludes_the_pre_operation_sample(self):
        published = json.loads(
            (
                ROOT
                / "docs"
                / "devlog"
                / "assets"
                / "phase6"
                / "three_axis_memory_phase6fy_safe_stop.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(published["status"], "operation_harness_safe_stop")
        self.assertEqual(published["population"]["memory_valid"], 0)
        self.assertEqual(published["population"]["memory_invalid"], 1)
        self.assertFalse(published["confirmed_boundary"]["preclose_commit"])
        self.assertIn("ModuleNotFoundError", published["confirmed_boundary"]["exception"])
        self.assertFalse(published["decision"]["phase6fo_restart_ready"])
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6fy"', devlog)
        self.assertIn("three_axis_memory_phase6fy_safe_stop.json", devlog)


if __name__ == "__main__":
    unittest.main()
