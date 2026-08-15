from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6hs_operation_report import produce_report, report_digest, validate_report


ATTEMPT = "phase6hs-test-attempt"
SCHEMA_SHA = "A" * 64
CONTRACT_SHA = "B" * 64


def rows() -> list[dict]:
    return [
        {"marker":"operation_complete","attempt_id":ATTEMPT},
        {"marker":"stage_close_complete","attempt_id":ATTEMPT},
        {"marker":"shutdown_complete","attempt_id":ATTEMPT},
    ]


def data(value: list[dict]) -> bytes:
    return b"".join((json.dumps(row, sort_keys=True)+"\n").encode("utf-8") for row in value)


def raw() -> dict:
    return {"status":"qualified","last_marker":"shutdown_complete","readback_calls":0,"lifecycle":{"stage_close_complete":True,"shutdown_complete":True}}


class Phase6HSOperationReportTests(unittest.TestCase):
    def report(self):
        marker_rows = rows()
        return produce_report(raw(), marker_rows, data(marker_rows), attempt_id=ATTEMPT, kit_exit_code=0, schema_sha256=SCHEMA_SHA, contract_sha256=CONTRACT_SHA), marker_rows

    def validate(self, report, marker_rows):
        return validate_report(report, marker_rows, data(marker_rows), expected_attempt_id=ATTEMPT, expected_schema_sha256=SCHEMA_SHA, expected_contract_sha256=CONTRACT_SHA)

    def test_marker_derived_report_passes(self):
        report, marker_rows = self.report()
        self.assertTrue(self.validate(report, marker_rows)["accepted"])

    def test_missing_completion_fails_closed(self):
        report, marker_rows = self.report()
        report.pop("operation_complete")
        self.assertEqual("required_field_missing:operation_complete", self.validate(report, marker_rows)["reason"])

    def test_cross_attempt_marker_fails_closed(self):
        report, marker_rows = self.report()
        marker_rows[-1]["attempt_id"] = "other"
        self.assertEqual("marker_attempt_mismatch:shutdown_complete", self.validate(report, marker_rows)["reason"])

    def test_nested_conflict_fails_closed(self):
        report, marker_rows = self.report()
        report["lifecycle"]["shutdown_complete"] = False
        report["report_sha256"] = report_digest(report)
        self.assertEqual("nested_top_level_mismatch:shutdown_complete", self.validate(report, marker_rows)["reason"])

    def test_digest_tamper_fails_closed(self):
        report, marker_rows = self.report()
        report["functional_evidence"]["changed"] = True
        self.assertEqual("report_digest_mismatch", self.validate(report, marker_rows)["reason"])


if __name__ == "__main__":
    unittest.main()
