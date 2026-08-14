import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6GdChannelSchemaDiscovery(unittest.TestCase):
    def test_control_contract_hash(self):
        path = SCRIPTS / "phase6gd_channel_schema_control_contract.json"
        sidecar = (SCRIPTS / "phase6gd_channel_schema_control_contract.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), sidecar)

    def test_discovery_contract_hash_and_frozen_base(self):
        path = SCRIPTS / "phase6gd_channel_schema_discovery_contract.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        sidecar = (SCRIPTS / "phase6gd_channel_schema_discovery_contract.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), sidecar)
        base = SCRIPTS / "phase6gc_supply_comparison_contract.json"
        self.assertEqual(
            hashlib.sha256(base.read_bytes()).hexdigest().upper(),
            contract["base_physics_contract"]["sha256"],
        )
        self.assertFalse(contract["history"]["phase6gc_reclassified"])
        self.assertFalse(contract["history"]["phase6gc_retried"])

    def test_probe_is_bounded_and_does_not_assign_semantics(self):
        body = (SCRIPTS / "probe_phase6gd_channel_metadata.py").read_text(encoding="utf-8")
        self.assertIn('"label": f"handle[{index}]"', body)
        self.assertIn("PER_HANDLE_FILE_LIMIT = 256 * 1024 * 1024", body)
        self.assertIn("TOTAL_FILE_LIMIT = 512 * 1024 * 1024", body)
        self.assertIn('"formal_channel_names_assigned": False', body)
        self.assertIn('"unknown_handles_preserved": True', body)
        self.assertNotIn("np.asarray(", body)
        self.assertNotIn(".tobytes(", body)
        self.assertNotIn("gc.collect", body)

    def test_runner_uses_existing_guard_case_and_release_after_close(self):
        body = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        self.assertIn('"run_phase6fo_supply_case.ps1"', body)
        self.assertIn('"phase6fu_resource_guard.py"', body)
        self.assertIn('"phase6fz_preclose_committer.py"', body)
        self.assertIn('"-LifecycleReferenceReleaseOrder", "after_stage_close"', body)
        self.assertIn('"-StartupSourceContractMode", $base.source_contract.mode', body)
        self.assertIn("Phase 6GD refuses artifact root reuse", body)
        self.assertNotIn("New-Item -ItemType Directory -Path $caseDir", body)

    def test_control_probe_changes_one_public_export_attribute(self):
        probe = (SCRIPTS / "probe_phase6gd_channel_metadata.py").read_text(encoding="utf-8")
        self.assertIn('"divergence": "divergenceEnabled"', probe)
        self.assertIn('"rgba": "rgbaEnabled"', probe)
        self.assertIn('"rgb": "rgbEnabled"', probe)
        self.assertIn('"other_export_attributes_unchanged": True', probe)
        runner = (SCRIPTS / "run_phase6gd_channel_metadata_probe.ps1").read_text(encoding="utf-8")
        self.assertIn('ValidateSet("baseline", "divergence", "rgba", "rgb")', runner)
        self.assertIn('"-ChannelSchemaControl", $Control', runner)
        self.assertIn('$runnerEvidence.outcome.lifecycle_status -ne "normal_exit"', runner)
        self.assertIn('$null -eq $runnerEvidence.process_exit_code', runner)
        self.assertIn("functional/lifecycle/OS-exit axes", runner)

    def test_safe_stop_summary_is_fail_closed(self):
        body = (SCRIPTS / "summarize_phase6gd_channel_schema.py").read_text(encoding="utf-8")
        self.assertIn('"status": "safe_stop_unknown_seventh_handle"', body)
        self.assertIn('"handle[6]": "unknown"', body)
        self.assertIn('"operational_schema_id": "unavailable"', body)
        self.assertIn('runner_evidence.json', body)
        self.assertIn('normal_exit_sample_accepted', body)
        self.assertIn('"harness_correction"', body)
        self.assertIn('"formal_population_started": False', body)
        self.assertIn('"readback_called": False', body)


if __name__ == "__main__":
    unittest.main()
