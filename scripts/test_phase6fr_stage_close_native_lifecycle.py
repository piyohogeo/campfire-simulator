from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POLICY = (SCRIPTS / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
PROBE = (SCRIPTS / "probe_phase6fo_supply_comparison.py").read_text(encoding="utf-8")
FIXTURE = (SCRIPTS / "run_phase6fr_cdb_stack_first_fixtures.ps1").read_text(encoding="utf-8")
CONTRACT_PATH = SCRIPTS / "phase6fr_stage_close_native_lifecycle_contract.json"


class Phase6FrStageCloseNativeLifecycle(unittest.TestCase):
    def test_contract_is_frozen_and_does_not_restart_phase6fo(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual("phase6fr", contract["phase"])
        self.assertFalse(contract["frozen_history"]["phase6fq_reclassified"])
        self.assertFalse(contract["progression"]["phase6fo_restarted"])
        self.assertEqual(3, contract["population"]["runs_per_condition"])
        self.assertEqual(
            ["A_release_before_close", "B_release_after_close", "B_release_after_close", "A_release_before_close", "A_release_before_close", "B_release_after_close"],
            contract["population"]["order"],
        )

    def test_stack_is_before_modules_and_modules_are_auxiliary(self):
        start = POLICY.index("function Invoke-CampfireCdbStackFirstCapture")
        end = POLICY.index("function Invoke-CampfireLightweightNgxDiagnosticCore", start)
        section = POLICY[start:end]
        self.assertLess(section.index('Marker "cdb_stack_capture_started"'), section.index('Marker "cdb_module_capture_started"'))
        self.assertLess(section.index('Marker "cdb_module_capture_started"'), section.index('Marker "cdb_detach_started"'))
        self.assertIn("Module enumeration is auxiliary", section)
        self.assertIn('"~* kPn 16"', section)
        self.assertIn('"lm"', section)
        self.assertIn('"qd"', section)

    def test_cdb_is_bounded_local_cache_only_and_direct_to_files(self):
        section = POLICY[POLICY.index("function Invoke-CampfireCdbStackFirstCapture"):POLICY.index("function Wait-CampfireKitProcessWithShutdownPolicy")]
        self.assertIn('symbol_contract="local cache only', section)
        self.assertNotIn("https://msdl.microsoft.com", section)
        self.assertIn("-MaximumStdoutBytes $CampfireCdbStackLogLimitBytes", section)
        self.assertIn("-MaximumStderrBytes $CampfireCdbStderrLimitBytes", section)
        self.assertNotIn("ReadToEnd", section)
        self.assertNotIn("-iae", POLICY + FIXTURE)
        self.assertNotIn("MiniDumpWriteDump", FIXTURE)

    def test_module_timeout_does_not_gate_complete_stack(self):
        core = POLICY[POLICY.index("function Invoke-CampfireLightweightNgxDiagnosticCore"):POLICY.index("function Invoke-CampfireLightweightNgxDiagnostic {")]
        self.assertIn("$primaryCdbGuards = @($stackGuard, $detachGuard)", core)
        self.assertIn("$cdbCaptureComplete = $attachObserved -and $stackObserved -and $nativeFramesObserved -and $detachObserved", core)
        self.assertIn("module_evidence_required = $false", core)
        self.assertIn('"module-timeout-fallback"', FIXTURE)
        self.assertIn("FixtureModuleCdbSleepMilliseconds", FIXTURE)

    def test_exact_identity_and_explicit_detach_are_required(self):
        section = POLICY[POLICY.index("function Invoke-CampfireCdbStackFirstCapture"):POLICY.index("function Invoke-CampfireLightweightNgxDiagnosticCore")]
        self.assertGreaterEqual(section.count("Test-Phase6EaProcessIdentity"), 3)
        self.assertIn('Marker "cdb_detach_started"', section)
        self.assertIn('Marker "cdb_detach_complete"', section)
        self.assertIn('Marker "cdb_cleanup_complete"', section)
        self.assertIn("target_alive_after_detach", FIXTURE)
        self.assertIn("Stop-ExactTarget", FIXTURE)

    def test_release_after_close_releases_only_after_detach_and_updates(self):
        start = PROBE.index('report["lifecycle_marker"] = "stage_close_request_after"')
        section = PROBE[start:PROBE.index("else:", start)]
        self.assertLess(section.index('report["lifecycle_marker"] = "usd_context_disconnected"'), section.index('mark("references_retained_through_post_close"'))
        self.assertLess(section.rindex('mark("post_close_renderer_update_complete"'), section.index('release_owned_references(state)'))

    def test_known_ngx_remains_five_token_stack_gated(self):
        for token in (
            "gpu_foundation_shutdown",
            "ngx_d3d12_shutdown",
            "telemetry_uninitialize",
            "telemetry_named_pipe_wait",
            "telemetry_bridge_stack",
        ):
            self.assertIn(token, POLICY)
        self.assertIn("$knownSignature = $guardSucceeded -and -not ($tokens.Values -contains $false)", POLICY)

    def test_contract_hash_sidecar_matches(self):
        sidecar = CONTRACT_PATH.with_suffix(".sha256")
        if not sidecar.exists():
            self.skipTest("hash sidecar is written after the contract is frozen")
        expected = sidecar.read_text(encoding="utf-8").split()[0].upper()
        self.assertEqual(expected, hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest().upper())


if __name__ == "__main__":
    unittest.main()
