from __future__ import annotations

import copy
import unittest

from phase6il_post_shutdown_boundary import CLASSIFICATIONS, REPORT_SCHEMA, classify, validate_sample


def sample() -> dict:
    return {
        "sample_offset_seconds": 0.25,
        "process_object_has_exited": True,
        "native_wait_state": "signaled",
        "native_exit_code": 0,
        "os_identity_state": "confirmed_exited",
        "same_exact_kit_alive": False,
        "private_bytes": None,
        "working_set_bytes": None,
        "thread_count": None,
        "handle_count": None,
        "tree": {"count": 0, "processes": []},
        "dump_state": {"count": 0, "files": []},
        "kit_log": {"bytes": 0, "tail": []},
    }


class Phase6IlPostShutdownTest(unittest.TestCase):
    def report(self) -> dict:
        return {
            "schema": REPORT_SCHEMA,
            "attempt_id": "a",
            "contract_valid": True,
            "operation_complete": True,
            "shutdown_complete": True,
            "samples": [sample()],
            "natural_exit_observed": True,
            "kit_exit_code": 0,
            "cdb_attempted": False,
            "crash_reporter_observed": False,
            "completed_dump_count": 0,
        }

    def test_normal_exit(self):
        self.assertFalse(validate_sample(sample()))
        self.assertEqual(classify(self.report(), fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"], CLASSIFICATIONS["qualified"])

    def test_stale_process_object(self):
        value = self.report()
        value["samples"][0]["process_object_has_exited"] = False
        self.assertEqual(classify(value, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"], CLASSIFICATIONS["stale"])

    def test_crash_reporter(self):
        value = self.report()
        value.update(kit_exit_code=0xC0000005, natural_exit_observed=False, completed_dump_count=1)
        self.assertEqual(classify(value, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"], CLASSIFICATIONS["crash_reporter"])

    def test_identity_mismatch_fails_closed(self):
        value = copy.deepcopy(self.report())
        value["samples"][0]["os_identity_state"] = "alive_identity_mismatch"
        self.assertEqual(classify(value, fixture_pass=True, resource_pass=True, cleanup_pass=True)["classification"], CLASSIFICATIONS["harness"])


if __name__ == "__main__":
    unittest.main()
