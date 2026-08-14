"""Fail-closed offline validation for the Phase 6GH candidate schema."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "scripts" / "phase6gh_public_channel_schema_candidate.json"


def load_schema(path: Path = DEFAULT_SCHEMA) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_candidate(observed: dict, expected: dict) -> dict:
    reasons: list[str] = []
    if observed.get("schema_id") != expected["schema_id"]:
        reasons.append("schema_id_mismatch")
    if observed.get("flow_version") != expected["versions"]["flow"]:
        reasons.append("flow_version_mismatch")
    handles = observed.get("handles")
    if not isinstance(handles, list):
        reasons.append("handles_missing")
        handles = []
    if len(handles) != expected["expected_handle_count"]:
        reasons.append("handle_count_mismatch")
    seen: set[int] = set()
    for position, wanted in enumerate(expected["handles"]):
        if position >= len(handles):
            break
        actual = handles[position]
        index = actual.get("index")
        if index in seen:
            reasons.append("duplicate_handle")
        seen.add(index)
        if index != wanted["index"]:
            reasons.append("handle_order_mismatch")
        if actual.get("channel") != wanted["channel"]:
            reasons.append("channel_mismatch")
        empty = bool(actual.get("empty"))
        optional_empty = wanted["state"] == "enabled_nonempty_or_disabled_empty"
        if empty and not optional_empty:
            reasons.append("required_handle_empty")
        if not empty:
            if actual.get("grid_class") != wanted["grid_class"]:
                reasons.append("grid_class_mismatch")
            if str(actual.get("value_type")) != wanted["value_type"]:
                reasons.append("value_type_mismatch")
    if observed.get("unknown_handles"):
        reasons.append("unknown_handle")
    return {"pass": not reasons, "reasons": sorted(set(reasons))}


def normal_observation(schema: dict, rgba_enabled: bool = True) -> dict:
    handles = []
    for wanted in schema["handles"]:
        empty = wanted["channel"] in {"divergence", "rgba"} and (
            wanted["channel"] == "divergence" or not rgba_enabled
        )
        handles.append(
            {
                "index": wanted["index"],
                "channel": wanted["channel"],
                "empty": empty,
                "grid_class": None if empty else wanted["grid_class"],
                "value_type": None if empty else wanted["value_type"],
            }
        )
    return {
        "schema_id": schema["schema_id"],
        "flow_version": schema["versions"]["flow"],
        "handles": handles,
        "unknown_handles": [],
    }


def run_fixtures(schema: dict) -> dict:
    cases: list[tuple[str, dict, bool]] = []
    normal_on = normal_observation(schema, True)
    normal_off = normal_observation(schema, False)
    cases.extend([
        ("normal_rgba_on", normal_on, True),
        ("normal_rgba_off", normal_off, True),
    ])
    missing = copy.deepcopy(normal_on); missing["handles"].pop(3)
    added = copy.deepcopy(normal_on); added["handles"].append({"index": 7, "channel": "future", "empty": True})
    swapped = copy.deepcopy(normal_on); swapped["handles"][1], swapped["handles"][2] = swapped["handles"][2], swapped["handles"][1]
    wrong_type = copy.deepcopy(normal_on); wrong_type["handles"][6]["value_type"] = "6"
    wrong_class = copy.deepcopy(normal_on); wrong_class["handles"][6]["grid_class"] = 2
    unknown_version = copy.deepcopy(normal_on); unknown_version["flow_version"] = "future"
    legacy = copy.deepcopy(normal_on); legacy["handles"] = legacy["handles"][:6]
    unknown = copy.deepcopy(normal_on); unknown["unknown_handles"] = [6]
    duplicate = copy.deepcopy(normal_on); duplicate["handles"][6]["index"] = 5
    empty_required = copy.deepcopy(normal_on); empty_required["handles"][1]["empty"] = True
    cases.extend([
        ("missing_handle", missing, False),
        ("additional_handle", added, False),
        ("order_exchange", swapped, False),
        ("value_type_mismatch", wrong_type, False),
        ("grid_class_mismatch", wrong_class, False),
        ("unknown_version", unknown_version, False),
        ("legacy_six_handle", legacy, False),
        ("unknown_handle", unknown, False),
        ("duplicate_handle", duplicate, False),
        ("required_handle_empty", empty_required, False),
    ])
    results = []
    for name, payload, expected_pass in cases:
        result = validate_candidate(payload, schema)
        results.append({
            "name": name,
            "expected_pass": expected_pass,
            "actual_pass": result["pass"],
            "reasons": result["reasons"],
            "fixture_pass": result["pass"] == expected_pass,
        })
    return {
        "schema": "campfire.phase6gh.channel-schema-fixtures.v1",
        "candidate_schema_id": schema["schema_id"],
        "passed": sum(item["fixture_pass"] for item in results),
        "total": len(results),
        "all_pass": all(item["fixture_pass"] for item in results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.fixtures:
        parser.error("--fixtures is required")
    result = run_fixtures(load_schema(args.schema))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["all_pass"] else 1)


if __name__ == "__main__":
    main()
