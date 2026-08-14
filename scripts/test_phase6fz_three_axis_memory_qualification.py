from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6fz_three_axis_memory_qualification_contract.json"
HASH = CONTRACT.with_suffix(".sha256")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


class Phase6FzThreeAxisQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_hash_scope_and_preflight(self) -> None:
        self.assertEqual(HASH.read_text(encoding="utf-8").split()[0], sha256(CONTRACT))
        self.assertEqual(self.contract["phase"], "phase6fz")
        self.assertFalse(self.contract["frozen_history"]["phase6fy_reclassified"])
        self.assertFalse(self.contract["frozen_history"]["phase6fy_artifact_reused"])
        self.assertFalse(self.contract["decision"]["phase6fo_execution_authorized"])
        self.assertTrue(self.contract["import_preflight"]["app_ready_kit_exec_required"])
        self.assertEqual(self.contract["diagnostic"]["timeout_contract"]["no_progress_timeout_seconds"], 20)
        self.assertEqual(self.contract["diagnostic"]["timeout_contract"]["overall_absolute_timeout_seconds"], 120)

    def test_runtime_hashes_are_frozen(self) -> None:
        names = {
            "phase6fu_resource_guard_sha256": "phase6fu_resource_guard.py",
            "phase6fu_process_identity_sha256": "phase6fu_process_identity.py",
            "frozen_phase6eg_resource_guard_sha256": "phase6eg_resource_guard.py",
            "kit_shutdown_policy_sha256": "kit_shutdown_policy.ps1",
            "shared_case_runner_sha256": "run_phase6fo_supply_case.ps1",
            "shared_probe_sha256": "probe_phase6fo_supply_comparison.py",
            "phase6fw_policy_sha256": "phase6fw_pid_reuse_policy.py",
            "three_axis_policy_sha256": "phase6fz_three_axis_policy.py",
            "preclose_committer_sha256": "phase6fz_preclose_committer.py",
            "analyzer_sha256": "analyze_phase6fz_three_axis_memory_qualification.py",
            "qualification_runner_sha256": "run_phase6fz_three_axis_memory_qualification.ps1",
            "synchronized_probe_sha256": "probe_phase6fz_three_axis_memory.py",
            "phase6fz_case_runner_sha256": "run_phase6fz_memory_case.ps1",
            "fixture_runner_sha256": "run_phase6fz_three_axis_fixtures.py",
            "import_contract_sha256": "phase6fz_import_contract.py",
            "import_smoke_probe_sha256": "probe_phase6fz_import_smoke.py",
            "import_smoke_runner_sha256": "run_phase6fz_import_smoke.ps1",
            "cdb_progress_fixture_sha256": "run_phase6fz_cdb_progress_fixtures.ps1",
            "cdb_progress_helper_sha256": "phase6fz_progress_fixture.ps1",
            "phase6ea_common_sha256": "phase6ea_diagnostic_common.ps1",
        }
        for key, filename in names.items():
            with self.subTest(key=key):
                self.assertEqual(self.contract["runtime_hashes"][key], sha256(SCRIPTS / filename))

    def test_physical_and_safety_contract_is_unchanged(self) -> None:
        physical = self.contract["physical_fixture"]
        self.assertEqual((physical["active_points"], physical["total_points"]), (1344, 1440))
        self.assertEqual(physical["readback_calls"], 0)
        self.assertEqual(physical["capture_calls"], 0)
        safety = self.contract["safety"]
        self.assertEqual(safety["kit_absolute_stop_bytes"], 16 * 1024**3)
        self.assertEqual(safety["unique_tree_absolute_stop_bytes"], 17 * 1024**3)
        self.assertEqual(safety["runner_private_limit_bytes"], 512 * 1024**2)
        self.assertEqual(safety["diagnostic_private_limit_bytes"], 512 * 1024**2)

    def test_synthetic_population_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase6fz-fixture-") as directory:
            output = Path(directory) / "root"
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_phase6fz_three_axis_fixtures.py"), "--contract", str(CONTRACT), "--output-root", str(output)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((output / "fixture_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual((report["passed_count"], report["total_count"]), (20, 20))

    def test_formal_runner_orders_preflight_before_attempts(self) -> None:
        runner = (SCRIPTS / "run_phase6fz_three_axis_memory_qualification.ps1").read_text(encoding="utf-8")
        self.assertLess(runner.index("run_phase6fz_import_smoke.ps1"), runner.index("$basicSlots"))
        self.assertLess(runner.index("run_phase6fz_cdb_progress_fixtures.ps1"), runner.index("$basicSlots"))
        self.assertIn("Phase 6FO remains stopped", runner)
        case = (SCRIPTS / "run_phase6fz_memory_case.ps1").read_text(encoding="utf-8")
        self.assertIn("--/phase6ep/readbackChannels=none", case)
        self.assertIn("--/phase6fz/importAuditPath=", case)


if __name__ == "__main__":
    unittest.main()
