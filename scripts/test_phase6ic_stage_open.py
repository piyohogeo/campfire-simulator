"""Focused no-Kit tests for Phase 6IC."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase6ic_no_kit_fixture import run_fixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class Phase6ICTest(unittest.TestCase):
    def test_exact_dependency_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_fixture(
                Path(temporary) / "fixture",
                SCRIPTS / "phase6ic_authoring_dependencies.json",
                SCRIPTS / "phase6ic_authoring_dependencies.sha256",
                ROOT,
                SCRIPTS / "phase6hx_single_log_occlusion_contract.json",
            )
        self.assertEqual(report["status"], "qualified")
        self.assertEqual(report["case_count"], [18, 18])

    def test_contract_and_manifest_sidecars(self) -> None:
        import hashlib

        for stem in ("phase6ic_stage_open_contract", "phase6ic_authoring_dependencies"):
            source = SCRIPTS / (stem + ".json")
            sidecar = SCRIPTS / (stem + ".sha256")
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest().upper(), sidecar.read_text(encoding="ascii").split()[0].upper())


if __name__ == "__main__":
    unittest.main()
