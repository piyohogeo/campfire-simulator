import json
import tempfile
import unittest
from pathlib import Path

from phase6hl_guard_preflight import ROOT, SCRIPTS, run_preflight_suite, validate_guard_summary, validate_interpreter


class Phase6HLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((SCRIPTS / "phase6hl_flow_proxy_boundary_contract.json").read_text(encoding="utf-8"))
        cls.runner = (SCRIPTS / "run_phase6hl_flow_proxy_boundary.py").read_text(encoding="utf-8")
        cls.wrapper = (SCRIPTS / "probe_phase6hl_flow_proxy_boundary.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="phase6hl-preflight-") as directory:
            cls.preflight = run_preflight_suite(cls.contract, Path(directory) / "suite")

    def test_exact_preflight_suite_passes_without_kit(self):
        self.assertEqual(self.preflight["status"], "pass")
        self.assertTrue(all(self.preflight["cases"].values()))
        self.assertEqual(self.preflight["kit_launch_count"], 0)

    def test_interpreter_identity_and_psutil_are_exact(self):
        positive = self.preflight["positive"]
        self.assertEqual(Path(positive["sys_executable"]).resolve(), Path(r"C:\Python38\python.exe").resolve())
        self.assertEqual(positive["psutil_version"], "5.9.8")
        self.assertTrue(Path(positive["psutil_file"]).is_file())
        self.assertTrue(positive["guard_main_callable"])

    def test_packman_is_rejected_without_modification(self):
        negative = self.preflight["packman_negative"]
        self.assertEqual(negative["validation_reason"], "guard_interpreter_mismatch")
        self.assertFalse(negative["observation"]["psutil_imported"])
        self.assertFalse(self.preflight["packman_environment_modified"])

    def test_negative_reasons_are_distinct(self):
        reasons = self.preflight["negative_reasons"]
        self.assertEqual(reasons["psutil_missing"], "psutil_import_failed")
        self.assertEqual(reasons["interpreter_mismatch"], "guard_sys_executable_mismatch")
        self.assertEqual(reasons["guard_import"], "guard_import_failed")
        self.assertEqual(reasons["summary_missing"], "guard_summary_missing")
        self.assertEqual(reasons["binding_mismatch"], "guard_target_command_binding_mismatch")

    def test_exact_guard_fixture_records_identity_binding_and_residual_zero(self):
        exact = self.preflight["exact_guard_fixture"]
        self.assertEqual(exact["status"], "pass")
        self.assertTrue(all(exact["checks"].values()))
        self.assertFalse(exact["large_output_buffered_in_parent"])

    def test_summary_missing_and_command_mismatch_fail_closed(self):
        self.assertEqual(validate_guard_summary(None, ["x"]), (False, "guard_summary_missing"))
        payload = {
            "schema": "campfire.phase6eg.resource-guard.v1", "command": ["wrong"],
            "status": "ok", "exit_code": 0, "process_absent": True,
            "observed_process_cleanup": {"all_observed_absent": True},
        }
        self.assertEqual(validate_guard_summary(payload, ["right"]), (False, "guard_target_command_binding_mismatch"))

    def test_contract_has_no_fallback_and_same_frozen_boundary(self):
        self.assertFalse(self.contract["interpreter"]["implicit_fallback"])
        self.assertEqual(self.contract["scope"]["proxy_path"], "/World/Logs/Log_00/FlowCollisionProxy")
        self.assertEqual(self.contract["scope"]["geometry"]["vertices"], 26)
        self.assertEqual(self.contract["scope"]["geometry"]["faces"], 36)
        self.assertEqual(self.contract["scope"]["geometry"]["indices"], 120)
        self.assertEqual(self.contract["scope"]["readback_calls"], 0)

    def test_wrapper_hash_pins_phase6hk_implementation_without_modifying_it(self):
        self.assertIn(self.contract["scope"]["frozen_phase6hk_probe_sha256"], self.wrapper)
        self.assertIn('replace("phase6hk", "phase6hl")', self.wrapper)

    def test_formal_runner_uses_explicit_interpreter_and_streamed_files(self):
        self.assertIn('contract["interpreter"]["guard_executable"]', self.runner)
        self.assertNotIn("sys.executable, str(guard)", self.runner)
        self.assertIn('open("wb", buffering=0)', self.runner)
        self.assertIn("return 0 if passed else 1", self.runner)

    def test_no_readback_or_nanovdb_in_new_probe_wrapper(self):
        for token in ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "_sample_grid", "np.asarray"):
            self.assertNotIn(token, self.wrapper)


if __name__ == "__main__":
    unittest.main()
