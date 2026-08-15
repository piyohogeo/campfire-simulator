import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from phase6ho_app_ready_environment import APP_LEXICAL, KIT_LEXICAL, ROOT, deployment_descriptor, lexical, validate_deployment
from phase6ho_process_tree_topology import build_target, validate_target


class Phase6HOTests(unittest.TestCase):
    def test_positive_deployment(self):
        self.assertEqual(validate_deployment(deployment_descriptor()), (True, "pass"))

    def test_reparse_points_are_not_collapsed(self):
        self.assertNotEqual(lexical(KIT_LEXICAL), lexical(KIT_LEXICAL.resolve()))
        self.assertNotEqual(lexical(APP_LEXICAL), lexical(APP_LEXICAL.resolve()))

    def test_negative_deployment_fields_fail_closed(self):
        base=deployment_descriptor()
        cases={"working_directory":"bad","kit_lexical_path":"bad","app_lexical_path":"bad","campfire_extension_lexical_path":"bad","anim_extension_resolved_path":"bad"}
        for key,value in cases.items():
            row=copy.deepcopy(base);row[key]=value
            self.assertFalse(validate_deployment(row)[0],key)
        for key in ("app_ready_marker","registry_lock_writable"):
            row=copy.deepcopy(base);row[key]=False
            self.assertFalse(validate_deployment(row)[0],key)

    def test_exact_target_preserves_lexical_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths={name:root/(name+".json") for name in ("output","markers","runner_evidence","kit_log","kit_stdout","kit_stderr")}
            target=build_target("smoke",paths)
            self.assertEqual(validate_target(target,"smoke"),(True,"pass"))
            self.assertEqual(target[target.index("-KitPath")+1],str(KIT_LEXICAL))
            self.assertEqual(target[target.index("-AppPath")+1],str(APP_LEXICAL))

    def test_resolved_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths={name:root/(name+".json") for name in ("output","markers","runner_evidence","kit_log","kit_stdout","kit_stderr")}
            target=build_target("smoke",paths);target[target.index("-KitPath")+1]=str(KIT_LEXICAL.resolve())
            self.assertEqual(validate_target(target,"smoke"),(False,"kit_path_mismatch"))

    def test_contract_has_no_retry_or_production_change(self):
        contract=json.loads((ROOT/"scripts/phase6ho_app_ready_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["frozen_history"]["retry"],0)
        self.assertFalse(contract["production_changes"])
        self.assertEqual(contract["proxy_scope"]["readback_calls"],0)

if __name__=="__main__": unittest.main()
