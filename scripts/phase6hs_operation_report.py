"""Canonical proxy operation-report producer, bounded reader, and validator."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import time
from pathlib import Path

from phase6hu_atomic_report import BACKOFF_SECONDS, atomic_write_json as bounded_atomic_write_json


REPORT_SCHEMA = "campfire.phase6hs.proxy-operation-report.v1"
PRODUCER_VERSION = "phase6hs-operation-report-producer-v1"
MAX_REPORT_BYTES = 1024 * 1024
MAX_MARKER_BYTES = 1024 * 1024
COMPLETION_FIELDS = ("operation_complete", "stage_close_complete", "shutdown_complete")
COMPLETION_MARKERS = COMPLETION_FIELDS


class ReportError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def canonical_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def report_digest(report: dict) -> str:
    value = copy.deepcopy(report)
    value.pop("report_sha256", None)
    return sha256_bytes(canonical_bytes(value))


def read_bounded_json(path: Path, maximum_bytes: int = MAX_REPORT_BYTES) -> dict:
    if not path.is_file():
        raise ReportError("report_missing")
    lease = path.with_name(path.name + ".writer.lock")
    data = None
    last_error = None
    for attempt in range(1 + len(BACKOFF_SECONDS)):
        if lease.exists():
            if attempt < len(BACKOFF_SECONDS):
                time.sleep(BACKOFF_SECONDS[attempt])
                continue
            raise ReportError("report_writer_busy")
        try:
            with path.open("rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                if size > maximum_bytes:
                    raise ReportError("report_oversize")
                if size <= 0:
                    raise ReportError("report_json_invalid")
                candidate = stream.read(maximum_bytes + 1)
            if lease.exists():
                if attempt < len(BACKOFF_SECONDS):
                    time.sleep(BACKOFF_SECONDS[attempt])
                    continue
                raise ReportError("report_writer_busy")
            data = candidate
            break
        except ReportError:
            raise
        except OSError as error:
            last_error = error
            if attempt < len(BACKOFF_SECONDS):
                time.sleep(BACKOFF_SECONDS[attempt])
                continue
    if data is None:
        raise ReportError("report_json_invalid") from last_error
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReportError("report_json_invalid") from error
    if not isinstance(value, dict):
        raise ReportError("report_type_invalid")
    return value


def read_bounded_markers(path: Path, maximum_bytes: int = MAX_MARKER_BYTES) -> tuple[list[dict], bytes]:
    if not path.is_file():
        raise ReportError("marker_file_missing")
    data = path.read_bytes()
    if len(data) > maximum_bytes:
        raise ReportError("marker_file_oversize")
    rows = []
    try:
        for line in data.splitlines():
            if line.strip():
                value = json.loads(line.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ReportError("marker_row_type_invalid")
                rows.append(value)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReportError("marker_json_invalid") from error
    return rows, data


def marker_name(row: dict) -> object:
    return row.get("marker", row.get("name"))


def validate_marker_sequence(rows: list[dict], expected_attempt_id: str | None = None) -> tuple[bool, str, dict]:
    names = [marker_name(row) for row in rows]
    positions = {}
    for required in COMPLETION_MARKERS:
        found = [index for index, name in enumerate(names) if name == required]
        if not found:
            return False, "marker_missing:" + required, {}
        if len(found) != 1:
            return False, "marker_duplicate:" + required, {}
        positions[required] = found[0]
        if expected_attempt_id is not None:
            marker_attempt = rows[found[0]].get("attempt_id")
            if marker_attempt is None:
                return False, "marker_attempt_missing:" + required, positions
            if marker_attempt != expected_attempt_id:
                return False, "marker_attempt_mismatch:" + required, positions
    if not (positions["operation_complete"] < positions["stage_close_complete"] < positions["shutdown_complete"]):
        return False, "marker_order_invalid", positions
    if positions["shutdown_complete"] != len(names) - 1:
        return False, "marker_after_shutdown_complete", positions
    return True, "pass", positions


def atomic_write_json(path: Path, payload: dict) -> None:
    bounded_atomic_write_json(path, payload)


def produce_report(
    raw_report: dict,
    marker_rows: list[dict],
    marker_data: bytes,
    *,
    attempt_id: str,
    kit_exit_code: int,
    schema_sha256: str,
    contract_sha256: str,
    include_nested_lifecycle: bool = True,
) -> dict:
    marker_ok, marker_reason, _ = validate_marker_sequence(marker_rows, attempt_id)
    if not marker_ok:
        raise ReportError(marker_reason)
    if raw_report.get("status") != "qualified":
        raise ReportError("raw_operation_status_not_qualified")
    if raw_report.get("last_marker") != "shutdown_complete":
        raise ReportError("raw_last_marker_mismatch")
    if raw_report.get("readback_calls") != 0 or isinstance(raw_report.get("readback_calls"), bool):
        raise ReportError("raw_readback_calls_invalid")
    nested = raw_report.get("lifecycle")
    if nested is not None:
        if not isinstance(nested, dict):
            raise ReportError("raw_nested_lifecycle_type_invalid")
        if nested.get("stage_close_complete") is not True:
            raise ReportError("raw_nested_stage_close_incomplete")
        if nested.get("shutdown_complete") is not True:
            raise ReportError("raw_nested_shutdown_incomplete")
    if not isinstance(kit_exit_code, int) or isinstance(kit_exit_code, bool) or kit_exit_code != 0:
        raise ReportError("kit_exit_code_invalid")
    report = {
        "schema": REPORT_SCHEMA,
        "schema_sha256": schema_sha256,
        "producer_version": PRODUCER_VERSION,
        "phase": "phase6hs",
        "attempt_id": attempt_id,
        "status": "qualified",
        "operation_complete": True,
        "stage_close_complete": True,
        "shutdown_complete": True,
        "last_marker": "shutdown_complete",
        "kit_exit_code": kit_exit_code,
        "readback_calls": 0,
        "marker_sha256": sha256_bytes(marker_data),
        "contract_sha256": contract_sha256,
        "functional_evidence": raw_report,
    }
    if include_nested_lifecycle:
        report["lifecycle"] = {
            "operation_complete": True,
            "stage_close_complete": True,
            "shutdown_complete": True,
        }
    report["report_sha256"] = report_digest(report)
    return report


def validate_report(
    report: dict,
    marker_rows: list[dict],
    marker_data: bytes,
    *,
    expected_attempt_id: str,
    expected_schema_sha256: str,
    expected_contract_sha256: str,
) -> dict:
    def failed(reason: str) -> dict:
        return {"schema":"campfire.phase6hs.operation-validation.v1","accepted":False,"reason":reason}

    for field in ("schema", "schema_sha256", "producer_version", "phase", "attempt_id", "status", *COMPLETION_FIELDS, "last_marker", "kit_exit_code", "readback_calls", "marker_sha256", "contract_sha256", "report_sha256"):
        if field not in report:
            return failed("required_field_missing:" + field)
    if report.get("schema") != REPORT_SCHEMA:
        return failed("schema_mismatch")
    if report.get("schema_sha256") != expected_schema_sha256:
        return failed("schema_digest_mismatch")
    if report.get("producer_version") != PRODUCER_VERSION:
        return failed("producer_version_mismatch")
    if report.get("phase") != "phase6hs":
        return failed("phase_mismatch")
    if report.get("attempt_id") != expected_attempt_id:
        return failed("attempt_identity_mismatch")
    if report.get("contract_sha256") != expected_contract_sha256:
        return failed("contract_digest_mismatch")
    for field in COMPLETION_FIELDS:
        value = report.get(field)
        if not isinstance(value, bool):
            return failed("completion_type_invalid:" + field)
    nested = report.get("lifecycle")
    if nested is not None:
        if not isinstance(nested, dict):
            return failed("nested_lifecycle_type_invalid")
        for field in COMPLETION_FIELDS:
            if field not in nested:
                return failed("nested_field_missing:" + field)
            if not isinstance(nested[field], bool):
                return failed("nested_completion_type_invalid:" + field)
            if nested[field] != report[field]:
                return failed("nested_top_level_mismatch:" + field)
    for field in COMPLETION_FIELDS:
        if report[field] is not True:
            return failed("completion_false:" + field)
    if report.get("status") != "qualified":
        return failed("status_not_qualified")
    if report.get("last_marker") != "shutdown_complete":
        return failed("last_marker_mismatch")
    if not isinstance(report.get("kit_exit_code"), int) or isinstance(report.get("kit_exit_code"), bool) or report.get("kit_exit_code") != 0:
        return failed("kit_exit_code_invalid")
    if not isinstance(report.get("readback_calls"), int) or isinstance(report.get("readback_calls"), bool) or report.get("readback_calls") != 0:
        return failed("readback_calls_invalid")
    marker_ok, marker_reason, _ = validate_marker_sequence(marker_rows, expected_attempt_id)
    if not marker_ok:
        return failed(marker_reason)
    if report.get("marker_sha256") != sha256_bytes(marker_data):
        return failed("marker_digest_mismatch")
    if report.get("report_sha256") != report_digest(report):
        return failed("report_digest_mismatch")
    return {
        "schema":"campfire.phase6hs.operation-validation.v1",
        "accepted":True,
        "reason":"pass",
        "attempt_id":expected_attempt_id,
        "marker_sha256":report["marker_sha256"],
        "report_sha256":report["report_sha256"],
        "completion":{"operation_complete":True,"stage_close_complete":True,"shutdown_complete":True},
    }


def validate_paths(report_path: Path, marker_path: Path, **expected) -> tuple[dict, dict, list[dict], bytes]:
    report = read_bounded_json(report_path)
    rows, data = read_bounded_markers(marker_path)
    return validate_report(report, rows, data, **expected), report, rows, data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("produce", "validate"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--markers", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--schema-path", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--raw-report", type=Path)
    parser.add_argument("--kit-exit-code", type=int)
    parser.add_argument("--validation-output", type=Path)
    parser.add_argument("--without-nested-lifecycle", action="store_true")
    args = parser.parse_args()
    schema_sha = sha256_bytes(args.schema_path.read_bytes())
    if args.command == "produce":
        if args.raw_report is None or args.kit_exit_code is None:
            raise ReportError("producer_argument_missing")
        raw = read_bounded_json(args.raw_report)
        rows, data = read_bounded_markers(args.markers)
        report = produce_report(raw, rows, data, attempt_id=args.attempt_id, kit_exit_code=args.kit_exit_code, schema_sha256=schema_sha, contract_sha256=args.contract_sha256, include_nested_lifecycle=not args.without_nested_lifecycle)
        atomic_write_json(args.report, report)
        return 0
    validation, _, _, _ = validate_paths(args.report, args.markers, expected_attempt_id=args.attempt_id, expected_schema_sha256=schema_sha, expected_contract_sha256=args.contract_sha256)
    if args.validation_output:
        atomic_write_json(args.validation_output, validation)
    return 0 if validation["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
