import hashlib
import json
import unittest
from pathlib import Path

import phase6eg_resource_guard as legacy_guard
from phase6hm_process_tree_topology import KIT, ROOT, SCRIPTS, build_formal_target, validate_formal_target


class _Process:
    def __init__(self, pid, name):
        self.pid = pid
        self._name = name

    def name(self):
        return self._name

    def cmdline(self):
        return []


class Phase6HMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6hm_flow_proxy_process_tree_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))

    def _formal_target(self):
        base = ROOT / "artifacts/phase6hm-test-shape"
        return build_formal_target({
            "output": base / "run.json",
            "markers": base / "markers.jsonl",
            "runner_evidence": base / "runner.json",
            "kit_log": base / "kit.log",
            "kit_stdout": base / "kit.stdout.log",
            "kit_stderr": base / "kit.stderr.log",
        }, 180)

    def test_contract_hash_is_frozen(self):
        expected = (SCRIPTS / "phase6hm_flow_proxy_process_tree_contract.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper(), expected)

    def test_contract_preserves_phase6hl_and_safety(self):
        self.assertFalse(self.contract["frozen_history"]["phase6hl_reclassified"])
        self.assertFalse(self.contract["frozen_history"]["phase6hl_artifact_reused"])
        self.assertEqual(self.contract["safety"]["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)

    def test_formal_target_is_powershell_root_and_transmits_kit_child(self):
        target = self._formal_target()
        self.assertEqual(validate_formal_target(target), (True, "pass"))
        self.assertEqual(Path(target[0]).name.lower(), "powershell.exe")
        self.assertEqual(target[target.index("-KitPath") + 1], str(KIT.resolve()))

    def test_direct_kit_root_and_path_mismatch_fail_closed(self):
        self.assertEqual(validate_formal_target([str(KIT.resolve()), "--bad"]), (False, "direct_kit_guarded_root_forbidden"))
        target = self._formal_target()
        target[target.index("-KitPath") + 1] = str(ROOT / "wrong/kit.exe")
        self.assertEqual(validate_formal_target(target), (False, "kit_child_path_mismatch"))

    def test_frozen_role_classifier_assigns_root_runner_and_child_kit(self):
        self.assertEqual(legacy_guard._role(_Process(10, "kit.exe"), 10), "runner")
        self.assertEqual(legacy_guard._role(_Process(11, "kit.exe"), 10), "kit")
        self.assertEqual(legacy_guard._role(_Process(12, "cdb.exe"), 10), "diagnostic")
        self.assertEqual(legacy_guard._role(_Process(13, "unknown.exe"), 10), "child")

    def test_case_runner_preserves_child_exit_and_direct_file_streaming(self):
        source = (SCRIPTS / "run_phase6hm_flow_proxy_case.ps1").read_text(encoding="utf-8")
        self.assertIn("exit $exitCode", source)
        self.assertIn("-RedirectStandardOutput $kitStdout", source)
        self.assertIn("-RedirectStandardError $kitStderr", source)
        self.assertIn("Wait-CampfireKitProcessWithShutdownPolicy", source)

    def test_probe_wrapper_is_frozen_and_contains_no_readback_path(self):
        source = (SCRIPTS / "probe_phase6hm_flow_proxy_boundary.py").read_text(encoding="utf-8")
        self.assertIn(self.contract["scope"]["frozen_phase6hk_probe_sha256"], source)
        for token in ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "_sample_grid", "np.asarray"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
