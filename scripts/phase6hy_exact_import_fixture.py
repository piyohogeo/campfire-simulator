"""No-Kit producer/loader fixture for the exact Phase 6HY import boundary."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import phase6hy_exact_kit_import as exact


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WRAPPER = SCRIPTS / "probe_phase6hy_single_log_occlusion.py"
CONTRACT = SCRIPTS / "phase6hy_exact_kit_import_contract.json"
SIDECAR = SCRIPTS / "phase6hy_exact_kit_import_contract.sha256"


def _case(name: str, expected: str, action) -> dict:
    try:
        evidence = action()
        observed = "pass"
    except Exception as error:
        evidence = {"error": f"{type(error).__name__}: {error}"}
        observed = str(error)
    passed = observed == "pass" if expected == "pass" else expected in observed
    return {"name": name, "expected": expected, "observed": observed, "passed": passed, "evidence": evidence}


def _temporary_module(root: Path, source_text: str, name: str = "phase6hy_fixture_target.py") -> tuple[Path, Path, str]:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    source = scripts / name
    source.write_text(source_text, encoding="utf-8")
    return scripts, source, hashlib.sha256(source.read_bytes()).hexdigest().upper()


def run_fixture(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6HY import fixture refuses root reuse")
    output_root.mkdir(parents=True)
    policy, boundary = exact.read_contract(WRAPPER, CONTRACT, SIDECAR)
    probe = policy["sources"]["probe_builder"]
    cases = []
    cases.append(_case("canonical_path", "pass", lambda: exact.load_exact_module(SCRIPTS / "phase6hy_probe_source.py", SCRIPTS, probe["sha256"], "phase6hy_fixture_positive", ["build_probe_source"])[1]))
    cases.append(_case("scripts_missing", "canonical_scripts_directory_invalid", lambda: exact.load_exact_module(output_root / "missing/scripts/probe.py", output_root / "missing/scripts", "0" * 64, "phase6hy_fixture_missing_scripts", ["entry"])))
    cases.append(_case("probe_source_missing", "source_invalid", lambda: exact.load_exact_module(SCRIPTS / "missing_phase6hy_probe.py", SCRIPTS, "0" * 64, "phase6hy_fixture_missing_probe", ["entry"])))
    cases.append(_case("sha_mismatch", "sha256_mismatch", lambda: exact.load_exact_module(SCRIPTS / "phase6hy_probe_source.py", SCRIPTS, "0" * 64, "phase6hy_fixture_sha", ["build_probe_source"])))
    original_reparse = exact._is_reparse
    try:
        exact._is_reparse = lambda path: Path(path).resolve() == SCRIPTS.resolve()
        cases.append(_case("reparse_unexpected_redirection", "canonical_scripts_directory_invalid", lambda: exact.read_contract(WRAPPER, CONTRACT, SIDECAR)))
    finally:
        exact._is_reparse = original_reparse
    with tempfile.TemporaryDirectory(dir=output_root) as temporary:
        temporary_root = Path(temporary)
        scripts, source, digest = _temporary_module(temporary_root, "def entry():\n    return 1\n")
        outside = temporary_root / "outside.py"
        outside.write_text("def entry():\n    return 1\n", encoding="utf-8")
        cases.append(_case("root_outside", "source_root_escape", lambda: exact.load_exact_module(outside, scripts, exact.sha256_file(outside), "phase6hy_fixture_escape", ["entry"])))
        fake = type("Fake", (), {"__file__": str(temporary_root / "wrong.py")})()
        sys.modules["phase6hy_shadowed"] = fake
        cases.append(_case("same_name_module_shadowing", "same_name_module_shadowing", lambda: exact.load_exact_module(source, scripts, digest, "phase6hy_shadowed", ["entry"])))
        sys.modules.pop("phase6hy_shadowed", None)
        scripts2, source2, digest2 = _temporary_module(temporary_root / "file-mismatch", "__file__ = __file__ + '.wrong'\ndef entry():\n    return 1\n")
        cases.append(_case("module_file_mismatch", "loaded_module_file_mismatch", lambda: exact.load_exact_module(source2, scripts2, digest2, "phase6hy_file_mismatch", ["entry"])))
        scripts3, source3, digest3 = _temporary_module(temporary_root / "missing-callable", "value = 1\n")
        cases.append(_case("required_callable_missing", "required_callable_missing", lambda: exact.load_exact_module(source3, scripts3, digest3, "phase6hy_missing_callable", ["entry"])))
        scripts4, source4, digest4 = _temporary_module(temporary_root / "nested-missing", "import phase6hy_nested_missing\ndef entry():\n    return 1\n")
        cases.append(_case("nested_local_import_missing", "No module named", lambda: exact.load_exact_module(source4, scripts4, digest4, "phase6hy_nested_missing_parent", ["entry"])))
        sys.modules["phase6hy_preloaded_wrong"] = fake
        cases.append(_case("preloaded_wrong_same_name", "same_name_module_shadowing", lambda: exact.load_exact_module(source, scripts, digest, "phase6hy_preloaded_wrong", ["entry"])))
        sys.modules.pop("phase6hy_preloaded_wrong", None)
    cases.append(_case("actual_repository_layout", "pass", lambda: {"contract": boundary, "wrapper_sha256": exact.sha256_file(WRAPPER), "probe_sha256": exact.sha256_file(SCRIPTS / "phase6hy_probe_source.py")}))
    for name in list(sys.modules):
        if name.startswith("phase6hy_fixture_"):
            sys.modules.pop(name, None)
    report = {
        "schema": "campfire.phase6hy.exact-import-fixture.v1",
        "phase": "phase6hy",
        "status": "qualified" if all(case["passed"] for case in cases) else "failed",
        "case_count": len(cases),
        "kit_launch_count": 0,
        "cases": cases,
        "actual_boundary": boundary,
        "contract_sha256": exact.sha256_file(CONTRACT),
    }
    (output_root / "fixture_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
