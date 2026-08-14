from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("phase6fz_import_contract_test", HERE / "phase6fz_import_contract.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Phase6FzImportContract(unittest.TestCase):
    def test_exact_file_and_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.py"
            target.write_text("def _run(): pass\ndef _append_resource_marker(): pass\n", encoding="utf-8")
            module, audit = MODULE.load_exact_module(target, target, module_name="phase6fz_fixture_ok", required_entrypoints=("_run", "_append_resource_marker"))
            self.assertEqual(Path(module.__file__).resolve(), target.resolve())
            self.assertEqual(audit["resolved_file"], str(target.resolve()))

    def test_missing_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.py"
            with self.assertRaises(FileNotFoundError):
                MODULE.load_exact_module(missing, missing, module_name="phase6fz_fixture_missing")

    def test_wrong_path_fails_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.py"
            expected = root / "expected.py"
            target.write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
            expected.write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(ImportError, "origin mismatch"):
                MODULE.load_exact_module(target, expected, module_name="phase6fz_fixture_wrong")


class Phase6FzStaticCdbContract(unittest.TestCase):
    def test_progress_timeout_contract_is_wired(self) -> None:
        common = (HERE / "phase6ea_diagnostic_common.ps1").read_text(encoding="utf-8")
        policy = (HERE / "kit_shutdown_policy.ps1").read_text(encoding="utf-8")
        self.assertIn("NoProgressTimeoutSeconds", common)
        self.assertIn('timeout_reason = if ($noProgressTimedOut)', common)
        self.assertIn("-NoProgressTimeoutSeconds $NoProgressTimeoutSeconds", policy)
        self.assertIn('stack_evidence=if ($stackObserved', policy)
        self.assertIn("stack_absolute", policy)


if __name__ == "__main__":
    unittest.main()
