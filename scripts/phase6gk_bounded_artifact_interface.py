"""Normalize and validate the Phase 6GK bounded field-output property."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

CANONICAL = "field_body_json_npz_or_openvdb_written"
LEGACY = "full_field_json_or_npz_written"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("bounded artifact root must be an object")
    return value


def normalize(payload: dict) -> tuple[dict | None, dict]:
    canonical_present = CANONICAL in payload
    legacy_present = LEGACY in payload
    canonical_value = payload.get(CANONICAL)
    legacy_value = payload.get(LEGACY)
    reasons: list[str] = []
    mode = "invalid"
    value = None

    if not canonical_present and not legacy_present:
        reasons.append("required_property_missing")
    else:
        if canonical_present and type(canonical_value) is not bool:
            reasons.append("canonical_value_not_boolean")
        if legacy_present and type(legacy_value) is not bool:
            reasons.append("legacy_value_not_boolean")
        if not reasons:
            if canonical_present and legacy_present:
                if canonical_value != legacy_value:
                    reasons.append("canonical_legacy_conflict")
                else:
                    mode = "dual_equal_normalized"
                    value = canonical_value
            elif canonical_present:
                mode = "canonical_only"
                value = canonical_value
            else:
                mode = "legacy_normalized"
                value = legacy_value
    if not reasons and value is True:
        reasons.append("field_body_write_detected")

    normalized = None
    if not any(reason.endswith("not_boolean") or reason in ("required_property_missing", "canonical_legacy_conflict") for reason in reasons):
        normalized = {key: item for key, item in payload.items() if key not in (CANONICAL, LEGACY)}
        normalized[CANONICAL] = value
    report = {
        "schema": "campfire.phase6gk.bounded-artifact-normalization.v1",
        "phase": "phase6gk",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not reasons else "fail",
        "pass": not reasons,
        "canonical_property": CANONICAL,
        "legacy_property": LEGACY,
        "canonical_present": canonical_present,
        "legacy_present": legacy_present,
        "canonical_input_value": canonical_value,
        "legacy_input_value": legacy_value,
        "normalization_mode": mode,
        "compatibility_normalization_applied": mode in ("legacy_normalized", "dual_equal_normalized"),
        "normalized_contains_canonical_only": bool(normalized is not None and CANONICAL in normalized and LEGACY not in normalized),
        "normalized_value": value,
        "field_body_write_detected": value is True,
        "reasons": reasons,
        "classification": "accepted_bounded_artifact" if not reasons else "bounded_artifact_interface_failure",
    }
    return normalized, report


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--normalized-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        normalized, report = normalize(load(args.input))
    except Exception as exc:
        normalized = None
        report = {
            "schema": "campfire.phase6gk.bounded-artifact-normalization.v1",
            "phase": "phase6gk", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "fail", "pass": False, "classification": "bounded_artifact_interface_failure",
            "reasons": ["invalid_json_or_root"], "error_type": type(exc).__name__, "error": str(exc),
        }
    if normalized is not None:
        write(args.normalized_output, normalized)
    write(args.report, report)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
