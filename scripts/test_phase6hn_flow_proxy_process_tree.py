import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from phase6hl_guard_preflight import _write
from phase6hn_process_role_projection import (
    EXPECTED_ATTEMPT_IDS,
    FZ_ROOT,
    PROJECTION_MAX_BYTES,
    ProjectionError,
    read_projection,
    validate_projection,
    write_projection,
)
from phase6hn_process_tree_topology import KIT, ROOT, SCRIPTS, build_formal_target, validate_formal_target


class Phase6HNTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_path = SCRIPTS / "phase6hn_flow_proxy_process_tree_contract.json"
        cls.contract = json.loads(cls.contract_path.read_text(encoding="utf-8"))

    def _formal_target(self):
        base = ROOT / "artifacts/phase6hn-test-shape"
        return build_formal_target({
            "output": base / "run.json",
            "markers": base / "markers.jsonl",
            "runner_evidence": base / "runner.json",
            "kit_log": base / "kit.log",
            "kit_stdout": base / "kit.stdout.log",
            "kit_stderr": base / "kit.stderr.log",
        }, 180)

    def test_contract_hash_is_frozen(self):
        sidecar = SCRIPTS / "phase6hn_flow_proxy_process_tree_contract.sha256"
        self.assertTrue(sidecar.is_file())
        expected = sidecar.read_text(encoding="ascii").split()[0]
        self.assertEqual(hashlib.sha256(self.contract_path.read_bytes()).hexdigest().upper(), expected)

    def test_contract_preserves_phase6hm_and_safety(self):
        self.assertFalse(self.contract["frozen_history"]["phase6hm_reclassified"])
        self.assertFalse(self.contract["frozen_history"]["phase6hm_artifact_reused"])
        self.assertEqual(self.contract["projection"]["maximum_bytes"], 128 * 1024)
        self.assertEqual(self.contract["projection"]["shared_bounded_reader_maximum_bytes"], 1024 * 1024)
        self.assertEqual(self.contract["safety"]["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(self.contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(self.contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)

    def test_actual_projection_producer_to_consumer(self):
        with tempfile.TemporaryDirectory(prefix="phase6hn-projection-") as directory:
            path = Path(directory) / "projection.json"
            produced = write_projection(FZ_ROOT, path)
            consumed = read_projection(path)
            self.assertEqual(produced, consumed)
            self.assertEqual(validate_projection(consumed), (True, "pass"))
            self.assertEqual([row["attempt_id"] for row in consumed["attempts"]], EXPECTED_ATTEMPT_IDS)
            self.assertLessEqual(path.stat().st_size, PROJECTION_MAX_BYTES)

    def test_projection_missing_duplicate_type_role_and_oversize_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="phase6hn-negative-") as directory:
            root = Path(directory)
            valid_path = root / "valid.json"
            write_projection(FZ_ROOT, valid_path)
            valid = read_projection(valid_path)
            cases = []
            missing = copy.deepcopy(valid)
            missing["attempts"].pop()
            missing["attempt_count"] = 8
            cases.append((missing, "projection_attempt_count_mismatch"))
            duplicate = copy.deepcopy(valid)
            duplicate["attempts"][-1] = copy.deepcopy(duplicate["attempts"][0])
            cases.append((duplicate, "projection_attempt_identity_mismatch"))
            wrong_type = copy.deepcopy(valid)
            wrong_type["attempt_count"] = "9"
            cases.append((wrong_type, "projection_attempts_type_invalid"))
            conflict = copy.deepcopy(valid)
            conflict["attempts"][0]["guarded_root"]["role"] = "kit"
            cases.append((conflict, "role_contradiction:runner"))
            for index, (payload, reason) in enumerate(cases):
                path = root / ("negative-%d.json" % index)
                _write(path, payload)
                self.assertEqual(validate_projection(read_projection(path)), (False, reason))
            oversize = root / "oversize.json"
            oversize.write_text("{\"padding\":\"" + "x" * PROJECTION_MAX_BYTES + "\"}", encoding="utf-8")
            with self.assertRaisesRegex(ProjectionError, "projection_oversize"):
                read_projection(oversize)

    def test_formal_target_is_powershell_root_and_transmits_kit_child(self):
        target = self._formal_target()
        self.assertEqual(validate_formal_target(target), (True, "pass"))
        self.assertEqual(Path(target[0]).name.lower(), "powershell.exe")
        self.assertEqual(target[target.index("-KitPath") + 1], str(KIT.resolve()))

    def test_direct_kit_root_and_path_mismatch_fail_closed(self):
        self.assertEqual(validate_formal_target([str(KIT.resolve()), "--bad"]), (False, "direct_kit_guarded_root_forbidden"))
        target = self._formal_target()
        target[target.index("-KitPath") + 1] = str(ROOT / "wrong" / "kit.exe")
        self.assertEqual(validate_formal_target(target), (False, "kit_child_path_mismatch"))

    def test_case_runner_and_probe_preserve_scope(self):
        case = (SCRIPTS / "run_phase6hn_flow_proxy_case.ps1").read_text(encoding="utf-8")
        self.assertIn("exit $exitCode", case)
        self.assertIn("-RedirectStandardOutput $kitStdout", case)
        self.assertIn("Wait-CampfireKitProcessWithShutdownPolicy", case)
        probe = (SCRIPTS / "probe_phase6hn_flow_proxy_boundary.py").read_text(encoding="utf-8")
        self.assertIn(self.contract["scope"]["frozen_phase6hk_probe_sha256"], probe)
        for token in ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "_sample_grid", "np.asarray"):
            self.assertNotIn(token, probe)

    def test_formal_runner_does_not_accept_raw_aggregate_as_bounded_input(self):
        projection = (SCRIPTS / "phase6hn_process_role_projection.py").read_text(encoding="utf-8")
        self.assertIn("historical aggregate is a read-only source", projection)
        self.assertIn("maximum_bytes=PROJECTION_MAX_BYTES", projection)
        self.assertNotIn("maximum_bytes=4 *", projection)
        self.assertNotIn("maximum_bytes=8 *", projection)


if __name__ == "__main__":
    unittest.main()
