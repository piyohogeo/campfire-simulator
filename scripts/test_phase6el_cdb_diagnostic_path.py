from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POLICY = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
COMMON = (SCRIPTS / "phase6ea_diagnostic_common.ps1").read_text(encoding="utf-8")
FIXTURE = (SCRIPTS / "run_phase6el_cdb_diagnostic_fixtures.ps1").read_text(encoding="utf-8")
RUNNER = (SCRIPTS / "run_phase6el_cdb_diagnostic_validation.ps1").read_text(encoding="utf-8")


class Phase6ElCdbDiagnosticContract(unittest.TestCase):
    def test_windows_kits_cdb_is_auto_detected_without_registration(self):
        self.assertIn(r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe", POLICY)
        self.assertIn("function Get-CampfireCdbMetadata", POLICY)
        self.assertIn("[Phase6EaFileSafety]::ComputeSha256", POLICY)
        combined = POLICY + FIXTURE + RUNNER
        self.assertNotIn("cdb -iae", combined.lower())
        self.assertNotIn("-iae", combined.lower())
        self.assertNotIn("Set-ItemProperty", combined)
        self.assertNotIn("New-ItemProperty", combined)

    def test_identity_is_verified_before_attach(self):
        start = POLICY.index("function Invoke-CampfireCdbStackFirstCapture")
        identity = POLICY.index("Test-Phase6EaProcessIdentity", start)
        attach = POLICY.index('Marker "cdb_attach_started"', identity)
        self.assertLess(identity, attach)
        self.assertIn('identity = "pid+process_start_time+absolute_executable_path"', FIXTURE)

    def test_cdb_output_is_direct_bounded_and_includes_all_threads(self):
        self.assertIn('$CampfireCdbStackLogLimitBytes = 16MB', POLICY)
        self.assertIn('$CampfireCdbStderrLimitBytes = 2MB', POLICY)
        self.assertIn('"~* kPn 16"', POLICY)
        self.assertIn('"lm"', POLICY)
        self.assertIn('"qd"', POLICY)
        self.assertIn('diagnostic_order = "stack_first_then_auxiliary_modules_then_explicit_detach"', POLICY)
        self.assertIn("stage_timeouts_seconds = $cdbCapture.timeout_seconds", POLICY)
        self.assertIn("-MaximumStdoutBytes $CampfireCdbStackLogLimitBytes", POLICY)
        self.assertIn("-MaximumStderrBytes $CampfireCdbStderrLimitBytes", POLICY)
        self.assertIn("-RedirectStandardOutput $StdoutPath", COMMON)
        self.assertIn("-RedirectStandardError $StderrPath", COMMON)
        cdb_section = POLICY[POLICY.index("function Get-CampfireCdbPath"):POLICY.index("function Wait-CampfireKitProcessWithShutdownPolicy")]
        self.assertNotIn("ReadToEnd", cdb_section)

    def test_attach_stack_detach_and_cleanup_markers_are_durable(self):
        for marker in (
            "cdb_attach_started",
            "cdb_attach_complete",
            "cdb_module_capture_started",
            "cdb_module_capture_complete",
            "cdb_stack_capture_started",
            "cdb_stack_capture_complete",
            "cdb_detach_complete",
            "cdb_cleanup_complete",
        ):
            self.assertIn(f'"{marker}"', POLICY)
        self.assertIn("$stream.Flush($true)", POLICY)

    def test_guard_tracks_output_memory_and_cpu(self):
        for token in (
            "MaximumStdoutBytes",
            "MaximumStderrBytes",
            "output_bytes_exceeded",
            "peak_private_bytes",
            "user_cpu_seconds",
            "kernel_cpu_seconds",
            "total_cpu_seconds",
        ):
            self.assertIn(token, COMMON)
        self.assertIn("Stop-Phase6EaHelperTree -RootProcessId $process.Id", COMMON)
        self.assertIn("$stream.SetLength($MaximumStdoutBytes)", COMMON)
        self.assertIn("$stream.SetLength($MaximumStderrBytes)", COMMON)

    def test_fixture_covers_required_process_outcomes(self):
        for name in (
            '"wait-target"',
            '"locked-log-target"',
            '"normal-exit-target"',
            '"cdb-timeout-target"',
            '"cdb-abnormal-exit"',
        ):
            self.assertIn(name, FIXTURE)
        self.assertIn("-ExclusiveLogLock", FIXTURE)
        self.assertIn("FixtureCdbSleepMilliseconds", FIXTURE)
        self.assertIn("Stop-ExactTarget", FIXTURE)

    def test_known_ngx_remains_stack_signature_gated(self):
        self.assertIn("$knownSignature = $guardSucceeded -and -not ($tokens.Values -contains $false)", POLICY)
        self.assertIn("known_ngx_requires_accepted_stack_signature = $true", FIXTURE)
        self.assertIn("unknown_shutdown_failure", POLICY)

    def test_phase6eg_contract_and_production_are_read_only_gates(self):
        self.assertIn("phase6eg_formal_restarted = $false", RUNNER)
        self.assertNotIn("run_phase6eg_static_pose_set_qualification.ps1", RUNNER)
        contract = SCRIPTS / "phase6eg_static_pose_set_contract.json"
        self.assertEqual(
            "4BAED82160A08C061D479BCCA6B6A46866DE88F5046851D2AF140D36D8C80687",
            hashlib.sha256(contract.read_bytes()).hexdigest().upper(),
        )

    def test_published_report_preserves_safe_stop(self):
        report_path = ROOT / "docs" / "devlog" / "assets" / "phase6" / "cdb_diagnostic_path_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual("pass", report["status"])
        self.assertFalse(report["phase6eg_formal_restarted"])
        self.assertEqual("10.0.28000.2526 (WinBuild.160101.0800)", report["cdb"]["file_version"])
        self.assertEqual(
            "506D1FD7AD306F6F53D8D157375A03A8368446923DEF9457CDFB2E3214054376",
            report["cdb"]["sha256"],
        )
        self.assertFalse(report["machine_wide_configuration_changed"])
        self.assertTrue(all(case["status"] == "pass" for case in report["cases"]))
        wait_case = next(case for case in report["cases"] if case["name"] == "wait-target")
        self.assertIsNotNone(wait_case["target_resource_before"])
        self.assertIsNotNone(wait_case["target_resource_after"])


if __name__ == "__main__":
    unittest.main()
