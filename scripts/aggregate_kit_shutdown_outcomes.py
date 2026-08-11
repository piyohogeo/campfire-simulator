"""Aggregate Kit shutdown outcomes without accepting invalid records as success."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


OUTCOME_SCHEMA = "campfire.kit-shutdown-outcome.v1"


def _valid_outcome(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("schema") != OUTCOME_SCHEMA:
        return False
    return (
        value.get("functional_status") in {"pass", "fail"}
        and value.get("lifecycle_status")
        in {"normal_exit", "known_ngx_shutdown_residual", "unknown_shutdown_failure"}
        and type(value.get("performance_sample_accepted")) is bool
        and type(value.get("normal_exit_sample_accepted")) is bool
        and isinstance(value.get("reasons"), list)
    )


def aggregate(records: Any) -> dict[str, Any]:
    invalid_input = not isinstance(records, list)
    source = records if isinstance(records, list) else []
    counts: Counter[str] = Counter()
    groups: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    consecutive_known = 0
    maximum_consecutive_known = 0

    for record in source:
        counts["total_processes"] += 1
        if not isinstance(record, dict) or not _valid_outcome(record.get("outcome")):
            counts["invalid_records"] += 1
            counts["unknown_shutdown_failures"] += 1
            consecutive_known = 0
            continue

        outcome = record["outcome"]
        lifecycle = outcome["lifecycle_status"]
        functional_pass = outcome["functional_status"] == "pass"
        accepted_lifecycle = lifecycle
        if not functional_pass:
            accepted_lifecycle = "unknown_shutdown_failure"
        elif lifecycle == "normal_exit" and outcome.get("normal_exit_sample_accepted") is not True:
            accepted_lifecycle = "unknown_shutdown_failure"
        elif lifecycle == "known_ngx_shutdown_residual" and (
            outcome.get("normal_exit_sample_accepted") is not False
            or outcome.get("performance_sample_accepted") is not False
        ):
            accepted_lifecycle = "unknown_shutdown_failure"

        if accepted_lifecycle == "normal_exit":
            counts["normal_exits"] += 1
            consecutive_known = 0
        elif accepted_lifecycle == "known_ngx_shutdown_residual":
            counts["known_ngx_shutdown_residuals"] += 1
            consecutive_known += 1
            maximum_consecutive_known = max(maximum_consecutive_known, consecutive_known)
        else:
            counts["unknown_shutdown_failures"] += 1
            consecutive_known = 0

        native_crash = record.get("native_crash")
        device_lost = record.get("device_lost_or_tdr")
        if type(native_crash) is not bool or type(device_lost) is not bool:
            counts["invalid_records"] += 1
            counts["unknown_evidence_records"] += 1
        counts["native_crashes"] += int(native_crash is True)
        counts["device_lost_or_tdr"] += int(device_lost is True)

        key = (
            str(record.get("condition", "unknown")),
            str(record.get("driver_version", "unknown")),
            str(record.get("kit_build", "unknown")),
        )
        groups[key]["total"] += 1
        groups[key][accepted_lifecycle] += 1

    total = counts["total_processes"]
    residual_rate = counts["known_ngx_shutdown_residuals"] / total if total else 0.0
    for name in (
        "total_processes",
        "normal_exits",
        "known_ngx_shutdown_residuals",
        "unknown_shutdown_failures",
        "invalid_records",
        "unknown_evidence_records",
        "native_crashes",
        "device_lost_or_tdr",
    ):
        counts[name] += 0
    triggers = {
        "two_consecutive_known_residuals": maximum_consecutive_known >= 2,
        "over_five_percent_at_twenty_or_more": total >= 20 and residual_rate > 0.05,
        "unknown_shutdown_failure": counts["unknown_shutdown_failures"] > 0,
        "invalid_input_or_record": invalid_input or counts["invalid_records"] > 0,
        "native_crash": counts["native_crashes"] > 0,
        "device_lost_or_tdr": counts["device_lost_or_tdr"] > 0,
    }
    return {
        "schema": "campfire.kit-shutdown-aggregate.v1",
        "input_valid": not invalid_input and counts["invalid_records"] == 0,
        "counts": dict(counts),
        "known_residual_rate": residual_rate,
        "maximum_consecutive_known_residuals": maximum_consecutive_known,
        "reinvestigation_triggered": triggers,
        "reinvestigation_required": any(triggers.values()),
        "by_condition_driver_kit": [
            {
                "condition": key[0],
                "driver_version": key[1],
                "kit_build": key[2],
                **dict(value),
            }
            for key, value in sorted(groups.items())
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        records = None
    result = aggregate(records)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
