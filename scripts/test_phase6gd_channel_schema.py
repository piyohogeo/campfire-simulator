import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6GdChannelSchemaDiscovery(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
