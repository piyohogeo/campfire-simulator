from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CLASSIFIER_PATH = ROOT / "scripts" / "classify_kit_shutdown_outcome.py"
AGGREGATOR_PATH = ROOT / "scripts" / "aggregate_kit_shutdown_outcomes.py"
CLASSIFIER = _load("phase6eb_classifier", CLASSIFIER_PATH)
AGGREGATOR = _load("phase6eb_aggregator", AGGREGATOR_PATH)
POLICY = (ROOT / "scripts" / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
COMMON = (ROOT / "scripts" / "phase6ea_diagnostic_common.ps1").read_text(encoding="utf-8")
RUNNER = (ROOT / "scripts" / "run_phase6dw_gpu_renderer_case.ps1").read_text(encoding="utf-8")
FLOW_RUNNER = (ROOT / "scripts" / "run_phase6dt_flow_collision_case.ps1").read_text(encoding="utf-8")
PROBE = (ROOT / "scripts" / "probe_phase6dw_gpu_renderer_lifecycle.py").read_text(encoding="utf-8")
FLOW_PROBE = (ROOT / "scripts" / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")


def _base(candidate: str = "known_ngx_shutdown_residual") -> dict:
    residual = candidate == "known_ngx_shutdown_residual"
    return {
        "schema": CLASSIFIER.INPUT_SCHEMA,
        "completion": {name: True for name in CLASSIFIER.REQUIRED_COMPLETION_GATES},
        "safety": {name: True for name in CLASSIFIER.REQUIRED_SAFETY_GATES},
        "process": {
            "lifecycle_candidate": candidate,
            "exit_code": 0 if candidate == "normal_exit" else None,
            "shutdown_marker_observed": True,
            "exited_within_shutdown_grace": candidate == "normal_exit",
            "pid_and_executable_verified": True,
            "process_start_time_verified": True,
            "diagnostic_capture_succeeded": residual,
            "known_signature_matched": residual,
            "known_signature_name": CLASSIFIER.KNOWN_SIGNATURE if residual else None,
            "terminated_by_outer_runner": residual,
            "pid_absent_after_termination": True,
            "residual_process": residual,
            "windows_exception_present": False,
            "fault_module": None,
            "fault_offset": None,
            "dump_count": 0,
            "last_lifecycle_marker": "shutdown_complete" if residual else "shutdown_requested",
        },
    }


def _record(payload: dict, condition: str = "control") -> dict:
    return {
        "outcome": CLASSIFIER.classify(payload),
        "condition": condition,
        "driver_version": "580.88",
        "kit_build": "110.2",
        "native_crash": False,
        "device_lost_or_tdr": False,
    }


class Phase6EbClassifierContract(unittest.TestCase):
    def test_01_known_residual_is_functional_not_normal_or_performance(self) -> None:
        result = CLASSIFIER.classify(_base())
        self.assertEqual(result["functional_status"], "pass")
        self.assertEqual(result["lifecycle_status"], "known_ngx_shutdown_residual")
        self.assertFalse(result["performance_sample_accepted"])
        self.assertFalse(result["normal_exit_sample_accepted"])
        self.assertTrue(result["shutdown_complete_reached"])
        self.assertFalse(result["os_process_normal_exit"])

    def test_02_normal_exit_remains_performance_eligible(self) -> None:
        result = CLASSIFIER.classify(_base("normal_exit"))
        self.assertEqual(result["lifecycle_status"], "normal_exit")
        self.assertTrue(result["performance_sample_accepted"])
        self.assertEqual(result["application_shutdown_marker"], "shutdown_requested")
        self.assertTrue(result["os_process_normal_exit"])

    def test_03_shutdown_complete_or_requested_is_required(self) -> None:
        payload = _base()
        payload["completion"]["shutdown_requested"] = False
        payload["process"]["shutdown_marker_observed"] = False
        result = CLASSIFIER.classify(payload)
        self.assertEqual(result["functional_status"], "fail")
        self.assertIn("completion:shutdown_requested", result["reasons"])

    def test_04_unknown_signature_is_rejected(self) -> None:
        payload = _base()
        payload["process"]["known_signature_matched"] = False
        self.assertEqual(CLASSIFIER.classify(payload)["lifecycle_status"], "unknown_shutdown_failure")

    def test_05_unknown_module_or_fault_offset_is_rejected(self) -> None:
        payload = _base()
        payload["process"]["fault_module"] = "different.plugin.dll"
        payload["process"]["fault_offset"] = "0x1234"
        reasons = CLASSIFIER.classify(payload)["reasons"]
        self.assertIn("process:fault_module_present", reasons)
        self.assertIn("process:fault_offset_present", reasons)

    def test_06_windows_exception_is_never_known_residual(self) -> None:
        payload = _base()
        payload["safety"]["no_windows_exception"] = False
        payload["process"]["windows_exception_present"] = True
        self.assertEqual(CLASSIFIER.classify(payload)["functional_status"], "fail")

    def test_07_dump_presence_is_rejected(self) -> None:
        payload = _base()
        payload["safety"]["no_crash_dump"] = False
        payload["process"]["dump_count"] = 1
        self.assertEqual(CLASSIFIER.classify(payload)["lifecycle_status"], "unknown_shutdown_failure")

    def test_08_any_functional_gate_failure_is_rejected(self) -> None:
        payload = _base()
        payload["completion"]["renderer_drained"] = False
        result = CLASSIFIER.classify(payload)
        self.assertIn("completion:renderer_drained", result["reasons"])

    def test_09_timeout_candidate_is_rejected(self) -> None:
        payload = _base()
        payload["process"]["lifecycle_candidate"] = "unknown_shutdown_failure"
        payload["process"]["absolute_timeout"] = True
        self.assertEqual(CLASSIFIER.classify(payload)["functional_status"], "fail")

    def test_10_residual_must_be_terminated_and_absent(self) -> None:
        payload = _base()
        payload["process"]["pid_absent_after_termination"] = False
        self.assertIn("process:pid_remained_after_termination", CLASSIFIER.classify(payload)["reasons"])

    def test_11_missing_or_wrongly_typed_input_fails_closed(self) -> None:
        self.assertEqual(CLASSIFIER.classify(None)["reasons"], ["input:not_object"])
        payload = _base()
        del payload["completion"]
        self.assertEqual(CLASSIFIER.classify(payload)["reasons"], ["input:completion_not_object"])

    def test_12_corrupt_json_cli_emits_explicit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.json"
            output = Path(directory) / "out.json"
            source.write_text("{not-json", encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(CLASSIFIER_PATH), "--input", str(source), "--output", str(output)],
                timeout=15,
                check=False,
            )
            self.assertEqual(run.returncode, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(result["input_valid"])
            self.assertEqual(result["lifecycle_status"], "unknown_shutdown_failure")


class Phase6EbAggregateContract(unittest.TestCase):
    def test_13_mixed_known_normal_unknown_stays_distinct(self) -> None:
        unknown = _base()
        unknown["process"]["known_signature_matched"] = False
        report = AGGREGATOR.aggregate([_record(_base("normal_exit")), _record(_base()), _record(unknown)])
        self.assertEqual(report["counts"]["normal_exits"], 1)
        self.assertEqual(report["counts"]["known_ngx_shutdown_residuals"], 1)
        self.assertEqual(report["counts"]["unknown_shutdown_failures"], 1)

    def test_14_two_consecutive_known_residuals_trigger_reinvestigation(self) -> None:
        report = AGGREGATOR.aggregate([_record(_base()), _record(_base())])
        self.assertTrue(report["reinvestigation_triggered"]["two_consecutive_known_residuals"])

    def test_15_more_than_five_percent_at_twenty_triggers(self) -> None:
        records = [_record(_base("normal_exit")) for _ in range(18)] + [_record(_base()) for _ in range(2)]
        self.assertTrue(AGGREGATOR.aggregate(records)["reinvestigation_triggered"]["over_five_percent_at_twenty_or_more"])

    def test_16_invalid_record_and_non_list_fail_closed(self) -> None:
        invalid = AGGREGATOR.aggregate([{"outcome": {"schema": "wrong"}}])
        self.assertFalse(invalid["input_valid"])
        self.assertTrue(invalid["reinvestigation_required"])
        self.assertFalse(AGGREGATOR.aggregate({"not": "a list"})["input_valid"])

    def test_17_corrupt_aggregate_json_emits_reinvestigation_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.json"
            output = Path(directory) / "out.json"
            source.write_text("[broken", encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(AGGREGATOR_PATH), "--input", str(source), "--output", str(output)],
                timeout=15,
                check=False,
            )
            self.assertEqual(run.returncode, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(result["input_valid"])
            self.assertTrue(result["reinvestigation_required"])


class Phase6EbRunnerSafetyContract(unittest.TestCase):
    def test_18_phase6ea_guard_and_atomic_lock_are_reused(self) -> None:
        self.assertIn("phase6ea_diagnostic_common.ps1", POLICY)
        self.assertIn("Enter-Phase6EaCaptureLock", POLICY)
        self.assertIn("Invoke-Phase6EaGuardedHelper", POLICY)
        self.assertIn("512MB", POLICY)

    def test_19_cdb_output_is_streamed_and_never_read_raw(self) -> None:
        diagnostic = POLICY[POLICY.index("function Invoke-CampfireLightweightNgxDiagnostic"):POLICY.index("function Wait-CampfireKitProcessWithShutdownPolicy")]
        self.assertIn("-RedirectStandardOutput", COMMON)
        self.assertIn("Select-String -LiteralPath", POLICY)
        self.assertNotIn("Get-Content -LiteralPath $stackLog -Raw", diagnostic)

    def test_20_diagnostic_failure_does_not_stop_target_kit(self) -> None:
        guard = POLICY.index("if ($diagnosticSucceeded)")
        stop = POLICY.index("Stop-Process -Id $Process.Id -Force", guard)
        self.assertLess(guard, stop)
        self.assertIn("diagnostic_capture_succeeded = $false", POLICY)

    def test_21_pid_path_and_start_time_are_checked_before_attach_and_stop(self) -> None:
        self.assertGreaterEqual(POLICY.count("Test-Phase6EaProcessIdentity"), 3)
        self.assertIn("ExpectedStartTimeUtc", POLICY)
        self.assertIn("process_start_time_verified", POLICY)

    def test_22_lightweight_capture_has_no_dump_and_is_noninvasive(self) -> None:
        self.assertIn('"-pv"', POLICY)
        self.assertIn("full_dump_created = $false", POLICY)
        self.assertNotIn("MiniDumpWriteDump", POLICY)
        self.assertNotIn("os._exit", POLICY)

    def test_23_stage_and_flow_runners_share_policy_and_outcome(self) -> None:
        for text in (RUNNER, FLOW_RUNNER):
            self.assertIn("kit_shutdown_policy.ps1", text)
            self.assertIn("Invoke-CampfireShutdownOutcomeClassification", text)
            self.assertIn("outcome = $outcome", text)

    def test_24_probes_publish_completion_contract_before_quit(self) -> None:
        for text in (PROBE, FLOW_PROBE):
            self.assertIn('"completion_contract"', text)
            self.assertIn('"shutdown_requested"', text)
            self.assertLess(text.index('"completion_contract"'), text.rindex("post_uncancellable_quit"))


if __name__ == "__main__":
    unittest.main()
