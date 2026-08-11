from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GUARD_SPEC = importlib.util.spec_from_file_location("phase6eg_resource_guard", SCRIPTS / "phase6eg_resource_guard.py")
GUARD = importlib.util.module_from_spec(GUARD_SPEC)
assert GUARD_SPEC.loader is not None
GUARD_SPEC.loader.exec_module(GUARD)


class Phase6EjIsolationContract(unittest.TestCase):
    def test_whole_diagnostic_is_a_bounded_child_process(self):
        policy = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
        helper = (SCRIPTS / "run_lightweight_shutdown_diagnostic_helper.ps1").read_text(encoding="utf-8")
        self.assertIn("function Invoke-CampfireLightweightNgxDiagnosticCore", policy)
        self.assertIn('"run_lightweight_shutdown_diagnostic_helper.ps1"', policy)
        self.assertIn("$CampfireShutdownDiagnosticTimeoutSeconds = 90", policy)
        self.assertIn("$CampfireShutdownDiagnosticJsonLimitBytes = 2MB", policy)
        self.assertIn("-PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit", policy)
        self.assertIn("Invoke-CampfireLightweightNgxDiagnosticCore", helper)
        self.assertNotIn("nvidia-smi", helper)

    def test_durable_boundaries_are_complete(self):
        policy = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
        helper = (SCRIPTS / "run_lightweight_shutdown_diagnostic_helper.ps1").read_text(encoding="utf-8")
        for marker in (
            "diagnostic_child_process_started",
            "process_identity_complete",
            "capture_lock_acquired",
            "gpu_inventory_started",
            "gpu_inventory_complete",
            "kit_log_parse_started",
            "kit_log_parse_complete",
            "dump_cdb_decision",
            "diagnostic_json_write_started",
            "diagnostic_json_write_complete",
            "cleanup_started",
            "cleanup_complete",
            "diagnostic_child_process_normal_exit",
            "parent_process_returned",
        ):
            self.assertIn(f'"{marker}"', policy + helper)
        self.assertIn("$stream.Flush($true)", policy)

    def test_large_inputs_are_bounded_or_streamed(self):
        policy = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
        core_start = policy.index("function Invoke-CampfireLightweightNgxDiagnosticCore")
        wrapper_start = policy.index("function Invoke-CampfireLightweightNgxDiagnostic {", core_start)
        core = policy[core_start:wrapper_start]
        self.assertNotIn("Get-Content -LiteralPath $LogPath -Raw", core)
        self.assertNotIn("ReadAllBytes", core)
        self.assertIn("[IO.File]::ReadLines", policy)
        self.assertIn("MaximumCharactersPerLine = 8192", policy)
        self.assertIn("MaximumLines = 120", policy)
        self.assertIn("JSON output exceeds fixed bound", policy)
        self.assertIn("Log tailing is auxiliary evidence", policy)
        self.assertIn("log_capture_error = $logCaptureError", policy)

    def test_cpu_delta_is_normalized_to_all_logical_cpus(self):
        previous = {(10, 1.0): (1.0, 2.0)}
        rows = [{
            "pid": 10,
            "create_time_utc_epoch": 1.0,
            "role": "kit",
            "cpu_total_seconds": 3.0,
        }]
        GUARD._append_cpu_deltas(rows, previous, 2.0, 4, 99.0)
        self.assertAlmostEqual(25.0, rows[0]["cpu_percent_of_logical_total"])
        self.assertEqual(1.0, rows[0]["cpu_sample_interval_seconds"])
        self.assertIsNone(rows[0]["top_cpu_thread"])

    def test_formal_runner_enables_cpu_and_marker_telemetry_without_contract_change(self):
        runner = (SCRIPTS / "run_phase6eg_static_pose_set_qualification.ps1").read_text(encoding="utf-8")
        self.assertIn('"--cpu-telemetry"', runner)
        self.assertIn('"--lifecycle-path"', runner)
        self.assertIn('"--diagnostic-marker-path"', runner)
        contract = SCRIPTS / "phase6eg_static_pose_set_contract.json"
        self.assertEqual(
            "4BAED82160A08C061D479BCCA6B6A46866DE88F5046851D2AF140D36D8C80687",
            __import__("hashlib").sha256(contract.read_bytes()).hexdigest().upper(),
        )

    def test_resource_guard_tracks_and_cleans_exact_observed_descendants(self):
        source = (SCRIPTS / "phase6eg_resource_guard.py").read_text(encoding="utf-8")
        self.assertIn("def _cleanup_observed_processes", source)
        self.assertIn("process.create_time()", source)
        self.assertIn("os.path.normcase(process.exe())", source)
        self.assertIn('stop_reason = "observed_descendant_residual"', source)
        self.assertIn('"observed_process_cleanup": observed_cleanup', source)
        fixture = (SCRIPTS / "phase6eg_resource_guard_fixture.ps1").read_text(encoding="utf-8")
        self.assertIn('"orphan_child"', fixture)
        self.assertIn('"orphan_child_pid_$($child.Id)"', fixture)

    def test_phase6ej_never_restarts_the_formal_matrix(self):
        runner = (SCRIPTS / "run_phase6ej_lightweight_shutdown_isolation.ps1").read_text(encoding="utf-8")
        self.assertIn("phase6eg_formal_restarted = $false", runner)
        self.assertNotIn("run_phase6eg_static_pose_set_qualification.ps1", runner)
        self.assertIn('"p0_equivalent_probe"', runner)
        self.assertIn("foreach ($run in 1..3)", runner)

    def test_public_report_and_devlog_preserve_safe_stop(self):
        report_path = ROOT / "docs" / "devlog" / "assets" / "phase6" / "lightweight_shutdown_isolation_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual("pass", report["status"])
        self.assertFalse(report["phase6eg_formal_restarted"])
        self.assertEqual("normal_exit", report["p0_equivalent"]["lifecycle_status"])
        self.assertFalse(report["p0_equivalent"]["diagnostic_invoked"])
        self.assertFalse(report["isolation_fixture"]["cdb_available"])
        devlog = (ROOT / "docs" / "devlog" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="phase-6ej"', devlog)
        self.assertIn("assets/phase6/lightweight_shutdown_isolation_report.svg", devlog)
        self.assertIn("36条件は未再開", devlog)


if __name__ == "__main__":
    unittest.main()
