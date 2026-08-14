import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from phase6gn_exact_wrapper_contract import SHARED_CALLABLES, SHARED_MODULES, audit_module


def _module(path: Path) -> ModuleType:
    value = ModuleType("fixture")
    value.__file__ = str(path)
    for name in SHARED_CALLABLES:
        setattr(value, name, lambda: None)
    for name in SHARED_MODULES:
        setattr(value, name, ModuleType(name))
    return value


class Phase6GNExactWrapperImportTests(unittest.TestCase):
    def test_shared_module_contract_accepts_module_and_typed_attributes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "shared.py"
            path.write_text("# fixture\n", encoding="utf-8")
            audit = audit_module(_module(path), path, label="shared", required_callables=SHARED_CALLABLES, required_modules=SHARED_MODULES)
        self.assertTrue(audit["pass"] and audit["module_type_is_types_ModuleType"])

    def test_shared_module_contract_fails_closed(self):
        for mutation in ("wrong_type", "wrong_path", "missing_callable", "noncallable", "wrong_module_type"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "shared.py"
                other = Path(root) / "other.py"
                path.write_text("# fixture\n", encoding="utf-8")
                other.write_text("# fixture\n", encoding="utf-8")
                value = _module(path)
                if mutation == "wrong_type":
                    value = object()
                elif mutation == "wrong_path":
                    value.__file__ = str(other)
                elif mutation == "missing_callable":
                    delattr(value, "_run")
                elif mutation == "noncallable":
                    value._run = value
                else:
                    value.Usd = object()
                with self.assertRaises(ImportError):
                    audit_module(value, path, label="shared", required_callables=SHARED_CALLABLES, required_modules=SHARED_MODULES)

    def test_phase6gn_wrapper_does_not_declare_shared_callable(self):
        text = (Path(__file__).resolve().parent / "probe_phase6gn_supply_comparison.py").read_text(encoding="utf-8")
        self.assertIn('required_entrypoints=("_qualified_spatial_boundary",)', text)
        self.assertNotIn('required_entrypoints=("_qualified_spatial_boundary", "shared")', text)
        self.assertIn("audit_phase6gl_and_shared", text)

    def test_exact_smoke_runner_precedes_formal_population(self):
        text = (Path(__file__).resolve().parent / "run_phase6fo_supply_comparison.ps1").read_text(encoding="utf-8")
        self.assertLess(text.index("run_phase6gn_exact_wrapper_smoke.ps1"), text.index("$slots = @()"))

    def test_phase6gm_history_is_frozen_in_phase6gn_contract(self):
        contract = json.loads((Path(__file__).resolve().parent / "phase6gn_supply_comparison_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["phase"], "phase6gn")
        self.assertFalse(contract["history"]["phase6gm_reclassified"])
        self.assertFalse(contract["history"]["phase6gm_samples_reused"])


if __name__ == "__main__":
    unittest.main()
