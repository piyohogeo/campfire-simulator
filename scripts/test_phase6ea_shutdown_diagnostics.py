from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_phase6ea_stage_difference.py"
CAPTURE = ROOT / "scripts" / "capture_phase6ea_hang_diagnostics.ps1"
WCT_HELPER = ROOT / "scripts" / "phase6ea_wct_helper.ps1"
DUMP_HELPER = ROOT / "scripts" / "phase6ea_dump_helper.ps1"
MONITOR = ROOT / "scripts" / "run_phase6ea_monitored_invocation.ps1"
REPORT = ROOT / "docs" / "devlog" / "assets" / "phase6" / "kit_shutdown_residual_report.json"
WINDBG_SUMMARY = ROOT / "docs" / "devlog" / "assets" / "phase6" / "kit_shutdown_windbg_summary.json"
DEVLOG = ROOT / "docs" / "devlog" / "index.html"


class Phase6EaShutdownDiagnosticsContract(unittest.TestCase):
    def test_stage_audit_is_read_only_and_categorized(self) -> None:
        text = AUDIT.read_text(encoding="utf-8")
        self.assertIn("inputs_read_only", text)
        self.assertIn("semantic_payload_equal_except_documentation", text)
        self.assertNotIn(".Save()", text)
        self.assertNotIn(".Export(", text)

    def test_monitor_waits_after_shutdown_and_path_checks_before_stop(self) -> None:
        text = MONITOR.read_text(encoding="utf-8")
        marker = text.index('$marker -eq "shutdown_requested"')
        observation = text.index("$ShutdownObservationSeconds", marker)
        capture = text.index("capture_phase6ea_hang_diagnostics.ps1", observation)
        path_check = text.index("Test-Phase6EaProcessIdentity", observation)
        stop = text.index("Stop-Process -Id $kitPid -Force", capture)
        self.assertLess(path_check, capture)
        self.assertLess(capture, stop)
        self.assertNotIn("os._exit", text)

    def test_capture_isolates_wct_and_dump_helpers(self) -> None:
        text = CAPTURE.read_text(encoding="utf-8")
        self.assertIn("phase6ea_wct_helper.ps1", text)
        self.assertIn("Invoke-Phase6EaGuardedHelper", text)
        self.assertIn("phase6ea_dump_helper.ps1", text)
        self.assertIn("Invoke-Phase6EaDumpHelper", text)
        pre_dump = text.index("pre_dump_diagnostics.json")
        full_dump = text.index("Invoke-Phase6EaDumpHelper", pre_dump)
        self.assertLess(pre_dump, full_dump)
        self.assertNotIn("MiniDumpWriteDump", text)
        self.assertNotIn("Task.Run", WCT_HELPER.read_text(encoding="utf-8"))
        self.assertIn("MiniDumpWriteDump", DUMP_HELPER.read_text(encoding="utf-8"))

    def test_checked_in_report_is_safe_stop(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "safe_stop")
        self.assertEqual(report["matrix"]["A_phase6dy_direct"], "hang_confirmed")
        self.assertEqual(report["matrix"]["B_phase6dy_through_phase6dz_outer"], "not_run_due_to_A_hang")
        self.assertEqual(report["matrix"]["C_phase6dz_axis"], "not_run_due_to_A_hang")
        self.assertTrue(report["stage_comparison"]["semantic_payload_equal_except_documentation"])
        self.assertFalse(report["production"]["changed"])
        self.assertFalse(report["decision"]["rotation_resume_allowed"])
        self.assertTrue(report["hang_dump"]["native_stack_unwind"]["available"])
        self.assertEqual(report["hang_dump"]["handle_targets"]["target_thread_id"], "0x1A60")

    def test_windbg_summary_records_join_without_claiming_gpu_fence(self) -> None:
        summary = json.loads(WINDBG_SUMMARY.read_text(encoding="utf-8"))
        self.assertFalse(summary["dump"]["rerun_performed"])
        self.assertEqual(summary["wait_chain"]["waiter"]["handle_type"], "Thread")
        self.assertEqual(summary["wait_chain"]["target"]["thread_id"], "0x1A60")
        self.assertIn("WaitNamedPipeW", summary["wait_chain"]["target"]["state"])
        self.assertFalse(summary["related_boundaries"]["gpu_fence"]["observed_as_main_blocker"])
        self.assertFalse(summary["decision"]["rotation_resume_allowed"])

    def test_devlog_links_phase6ea_without_changing_latest_demo(self) -> None:
        html = DEVLOG.read_text(encoding="utf-8")
        self.assertIn('id="phase-6ea"', html)
        self.assertIn("kit_shutdown_residual_report.json", html)
        self.assertIn("kit_shutdown_residual_report.svg", html)
        self.assertIn("kit_shutdown_windbg_summary.json", html)
        self.assertIn('data-latest-demo-manifest="assets/latest_demo.json"', html)


if __name__ == "__main__":
    unittest.main()
