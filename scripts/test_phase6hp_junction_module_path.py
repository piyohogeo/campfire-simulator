import copy
import json
import tempfile
import unittest
from pathlib import Path

from phase6hp_junction_module_path import (
    IO_REPARSE_TAG_MOUNT_POINT,
    JUNCTION_PATH,
    actual_no_kit_evidence,
    collect_module_path_evidence,
    validate_evidence_population,
    validate_module_path_evidence,
)
from phase6hp_process_tree_topology import ROOT, build_target, validate_target


class Phase6HPJunctionTests(unittest.TestCase):
    def setUp(self):
        self.actual = actual_no_kit_evidence()

    def test_actual_declared_junction_passes(self):
        self.assertEqual(validate_module_path_evidence(self.actual), (True, "pass"))
        self.assertEqual(self.actual["junction_reparse_tag"], IO_REPARSE_TAG_MOUNT_POINT)
        self.assertEqual(self.actual["junction_chain_depth"], 1)

    def test_lexical_module_spelling_passes(self):
        evidence = collect_module_path_evidence(
            extension_id="campfire.app-0.1.0",
            extension_root=JUNCTION_PATH.parent,
            module_name="campfire.app",
            package_name="campfire",
            module_file=JUNCTION_PATH / "app/__init__.py",
        )
        self.assertEqual(validate_module_path_evidence(evidence), (True, "pass"))
        self.assertTrue(evidence["module_file_under_lexical_junction"])

    def test_identity_fields_fail_closed(self):
        mutations = {
            "extension_id": "other.app-0.1.0",
            "extension_version": "0.2.0",
            "extension_root_lexical": str(ROOT / "source/extensions/campfire.app"),
            "junction_relative_path": "wrong",
            "junction_target_resolved": str(ROOT / "source/extensions/other/campfire"),
            "module_name": "other.app",
            "package_name": "other",
        }
        for key, value in mutations.items():
            row = copy.deepcopy(self.actual)
            row[key] = value
            self.assertFalse(validate_module_path_evidence(row)[0], key)

    def test_reparse_and_chain_fail_closed(self):
        mutations = {
            "junction_exists": False,
            "junction_is_reparse_point": False,
            "junction_reparse_tag": 0,
            "junction_chain_depth": 2,
            "target_reparse_point_count": 1,
            "extension_root_is_reparse_point": True,
        }
        for key, value in mutations.items():
            row = copy.deepcopy(self.actual)
            row[key] = value
            self.assertFalse(validate_module_path_evidence(row)[0], key)

    def test_module_escape_and_contradiction_fail_closed(self):
        row = copy.deepcopy(self.actual)
        row["module_file_resolved"] = r"c:\windows\__init__.py"
        self.assertEqual(validate_module_path_evidence(row), (False, "module_resolved_outside_expected_target"))
        row = copy.deepcopy(self.actual)
        row["module_file_under_resolved_target"] = False
        self.assertEqual(validate_module_path_evidence(row), (False, "module_resolved_target_membership_false"))

    def test_missing_unknown_and_duplicate_fail_closed(self):
        row = copy.deepcopy(self.actual)
        del row["module_file_resolved"]
        self.assertEqual(validate_module_path_evidence(row), (False, "evidence_missing:module_file_resolved"))
        row = copy.deepcopy(self.actual)
        row["unexpected"] = 1
        self.assertEqual(validate_module_path_evidence(row), (False, "evidence_unknown:unexpected"))
        self.assertEqual(validate_evidence_population((self.actual, self.actual)), (False, "evidence_population_duplicate"))

    def test_contract_preserves_limits_and_scope(self):
        contract = json.loads((ROOT / "scripts/phase6hp_junction_app_ready_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["baseline_commit"], "de224b3")
        self.assertEqual(contract["safety"]["kit_private_limit_bytes"], 16 * 1024**3)
        self.assertEqual(contract["safety"]["unique_tree_private_limit_bytes"], 17 * 1024**3)
        self.assertFalse(contract["production_changes"])
        self.assertFalse(contract["module_path"]["filesystem_changes"])
        self.assertEqual(contract["proxy_scope"]["readback_calls"], 0)

    def test_exact_command_preserves_phase6ho_topology(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {name: root / (name + ".json") for name in ("output", "markers", "runner_evidence", "kit_log", "kit_stdout", "kit_stderr")}
            target = build_target("smoke", paths)
            self.assertEqual(validate_target(target, "smoke"), (True, "pass"))


if __name__ == "__main__":
    unittest.main()
