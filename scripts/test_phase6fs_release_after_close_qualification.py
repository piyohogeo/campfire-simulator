from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT_PATH = SCRIPTS / "phase6fs_release_after_close_contract.json"
PROBE = (SCRIPTS / "probe_phase6fo_supply_comparison.py").read_text(encoding="utf-8")
RUNNER = (SCRIPTS / "run_phase6fs_release_after_close_qualification.ps1").read_text(encoding="utf-8")
ANALYZER = (SCRIPTS / "analyze_phase6fs_release_after_close_qualification.py").read_text(encoding="utf-8")
FIXTURE = (SCRIPTS / "run_phase6fr_cdb_stack_first_fixtures.ps1").read_text(encoding="utf-8")


class Phase6FsReleaseAfterCloseQualification(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_is_b_only_three_processes_and_keeps_limits(self):
        self.assertEqual("phase6fs", self.contract["phase"])
        self.assertEqual(["B_release_after_close"] * 3, self.contract["population"]["order"])
        self.assertEqual(3, self.contract["population"]["independent_processes"])
        self.assertEqual(14 * 1024**3, self.contract["safety"]["kit_private_limit_bytes"])
        self.assertEqual(16 * 1024**3, self.contract["safety"]["unique_tree_private_limit_bytes"])
        self.assertFalse(self.contract["qualification"]["phase6fo_restarted"])
        self.assertFalse(self.contract["qualification"]["production_shutdown_order_changed"])

    def test_probe_retains_explicit_container_until_after_detach_and_updates(self):
        retain = PROBE.index("retain_owned_references(state)", PROBE.index('release_order = arguments["lifecycle_reference_release_order"]'))
        close = PROBE.index('mark("stage_close_request_before"', retain)
        detach = PROBE.index('mark("usd_context_disconnected"', close)
        post = PROBE.rindex('mark("post_close_renderer_update_complete"', detach)
        retained = PROBE.index('mark("references_retained_through_post_close"', post)
        release = PROBE.index("release_owned_references(state)", retained)
        self.assertLess(retain, close)
        self.assertLess(close, detach)
        self.assertLess(detach, post)
        self.assertLess(post, retained)
        self.assertLess(retained, release)
        for slot in self.contract["ownership"]["required_slots"]:
            self.assertIn(f'"{slot}"', PROBE)

    def test_release_clears_python_owned_slots_without_forced_gc(self):
        start = PROBE.index("def release_owned_references(state):")
        end = PROBE.index("    try:", start)
        section = PROBE[start:end]
        self.assertIn('"python_owned_slots_clear"', section)
        self.assertIn('mark(\n            "ownership_container_released"', section)
        self.assertNotIn("gc.collect", section)
        self.assertTrue(self.contract["ownership"]["weak_reference_liveness_is_diagnostic_only"])

    def test_runner_uses_existing_case_and_stack_first_smoke(self):
        self.assertIn('"-SmokeOnly"', RUNNER)
        self.assertIn('"-LifecycleReferenceReleaseOrder", "after_stage_close"', RUNNER)
        self.assertIn('$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"', RUNNER)
        self.assertNotIn('"-LifecycleReferenceReleaseOrder", "before_stage_close"', RUNNER)
        self.assertIn("[switch]$SmokeOnly", FIXTURE)

    def test_analyzer_fail_closes_marker_ownership_extension_and_exit(self):
        for token in (
            "resource_marker_order_integrity",
            "renderer_drain_update_count",
            "post_close_renderer_update_count",
            "extension_marker_order_integrity",
            "runner_exit_marker_missing",
            "python_owned_slots_not_clear",
            "ownership_container_not_empty",
            "unexpected_cdb_invocation",
        ):
            self.assertIn(token, ANALYZER)

    def test_contract_hash_sidecar_matches(self):
        sidecar = CONTRACT_PATH.with_suffix(".sha256")
        if not sidecar.exists():
            self.skipTest("hash sidecar is written after the contract is frozen")
        expected = sidecar.read_text(encoding="utf-8").split()[0].upper()
        self.assertEqual(expected, hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest().upper())


if __name__ == "__main__":
    unittest.main()
