from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from phase6hx_point_policy_fixture import run_fixture as run_point_fixture
from phase6hx_point_policy_invariant import consume_report, produce_report, validate_manifest, write_report
from phase6hx_probe_source import build_probe_source
from phase6hx_stage_builder import canonical_json, settings_common, settings_descriptor, sha256
from phase6hx_stage_fixture import run_fixture as run_stage_fixture


class Phase6HXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract_path = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))
        cls.manifest = SCRIPTS / "phase6hx_point_policy_source_set.json"
        cls.manifest_sidecar = SCRIPTS / "phase6hx_point_policy_source_set.sha256"

    def test_contract_is_independent_and_phase6hw_frozen(self) -> None:
        digest = hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper()
        self.assertEqual(digest, (SCRIPTS / "phase6hx_single_log_occlusion_contract.sha256").read_text(encoding="ascii").split()[0])
        self.assertEqual(self.contract["phase"], "phase6hx")
        self.assertEqual(self.contract["baseline_commit"], "16f1e6c")
        self.assertEqual(self.contract["frozen_history"]["phase6hw_status"], "safe_stop_pre_kit_harness_failure")
        self.assertFalse(self.contract["frozen_history"]["reclassified"])
        self.assertFalse(self.contract["frozen_history"]["contract_or_root_reused"])

    def test_actual_manifest_and_round_trip(self) -> None:
        validated = validate_manifest(self.manifest, self.manifest_sidecar, ROOT)
        self.assertEqual(validated["entry_count"], 13)
        self.assertNotIn("point_emitter.py", "\n".join(entry["path"] for entry in validated["entries"]))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report.json"
            report = produce_report(self.manifest, self.manifest_sidecar, ROOT, "test-attempt")
            write_report(output, report)
            self.assertEqual(consume_report(output, self.manifest, self.manifest_sidecar, ROOT, "test-attempt"), report)

    def test_point_policy_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_point_fixture(Path(temporary) / "fixture", self.manifest, self.manifest_sidecar, ROOT)
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual(report["case_count"], 13)
        self.assertEqual(report["kit_launch_count"], 0)

    def test_stage_fixture_and_frozen_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_stage_fixture(Path(temporary) / "stage", self.contract_path)
        self.assertEqual(report["status"], "qualified", report)
        self.assertEqual([item["name"] for item in self.contract["condition_order"]], ["collision_off", "collision_on"])
        self.assertEqual(self.contract["fixed_scene"]["stable_capture_frames"], list(range(120, 241, 10)))
        self.assertEqual(self.contract["retry"], 0)
        self.assertEqual(self.contract["replacement"], 0)

    def test_settings_digests_and_probe_order(self) -> None:
        authored = self.contract["stage_authoring"]
        self.assertEqual(sha256(canonical_json(settings_common(self.contract))), authored["settings_common_sha256"])
        for condition in ("collision_off", "collision_on"):
            self.assertEqual(sha256(canonical_json(settings_descriptor(self.contract, condition))), authored["settings_sha256"][condition])
        source = build_probe_source(SCRIPTS / "probe_phase6hw_single_log_occlusion.py")
        compile(source, str(SCRIPTS / "probe_phase6hx_single_log_occlusion.py"), "exec")
        self.assertIn('"phase": "phase6hx"', source)
        self.assertNotIn("get_latest_nanovdb_readback", source)
        self.assertLess(source.index('mark("stage_contract_complete"'), source.index("await context.open_stage_async"))

    def test_safety_and_scope(self) -> None:
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertEqual(self.contract["fixed_scene"]["readback_calls"], 0)
        self.assertIn("production log placement", self.contract["out_of_scope"])
        self.assertIn("dynamic transform", self.contract["out_of_scope"])


if __name__ == "__main__":
    unittest.main()
