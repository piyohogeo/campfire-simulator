"""Phase 6GJ state-aware alias contract for the disabled RGBA handle."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import phase6gi_channel_preflight_policy as phase6gi

DEFAULT_CONTRACT = SCRIPT_DIR / "phase6gj_empty_rgba_alias_contract.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_raw_schema(observed: dict, contract: dict) -> dict:
    return phase6gi.validate_raw_schema(observed, contract)


def validate_preflight(observed: dict, contract: dict) -> dict:
    raw = validate_raw_schema(observed, contract)
    reasons = list(raw["reasons"])
    handles = observed.get("handles") if isinstance(observed.get("handles"), list) else []
    for position, wanted in enumerate(contract["schema_gate"]["handles"]):
        if position >= len(handles):
            continue
        actual = handles[position]
        if actual.get("channel") != wanted["channel"]:
            reasons.append("semantic_channel_mismatch")
        alias = actual.get("alias_contract") or {}
        if alias.get("same_python_object") is not True:
            reasons.append("same_object_required")
        if alias.get("numpy_asarray_called") is not False or alias.get("material_copy_created") is not False:
            reasons.append("material_copy_observed")
        if wanted["required_state"] == "nonempty":
            if alias.get("shares_memory") is not True:
                reasons.append("nonempty_shared_memory_required")
            if not isinstance(actual.get("data_pointer"), int) or actual["data_pointer"] <= 0:
                reasons.append("positive_pointer_missing")
        else:
            if actual.get("element_count") != 0 or actual.get("logical_bytes") != 0:
                reasons.append("empty_zero_byte_required")
            # np.shares_memory(empty, empty) is deliberately telemetry only.  A
            # zero-length array has no element whose overlap could prove ownership.
        release = actual.get("release") or {}
        if release.get("list_slot_cleared") is not True:
            reasons.append("list_slot_not_cleared")
        if release.get("weak_reference_supported") is not True:
            reasons.append("weak_reference_unsupported")
        if release.get("weak_reference_alive_after_slot_clear") is not False:
            reasons.append("weak_reference_residual")
    if observed.get("semantic_mapping_applied_after_raw_schema_validation") is not True:
        reasons.append("semantic_mapping_order_invalid")
    counts = observed.get("operation_counts") or {}
    if counts.get("public_readback_calls") != 1:
        reasons.append("readback_operation_count")
    for key in ("numpy_asarray_calls", "material_copies", "field_body_writes"):
        if counts.get(key) != 0:
            reasons.append(f"{key}_nonzero")
    if observed.get("weak_reference_alive_after_release_count") != 0:
        reasons.append("aggregate_weak_reference_residual")
    if observed.get("ownership_container_residual_count") != 0:
        reasons.append("ownership_container_residual")
    return {"pass": not reasons, "reasons": sorted(set(reasons)), "raw_schema": raw}


def normal_observation(contract: dict) -> dict:
    value = phase6gi.normal_observation(contract)
    empty = value["handles"][6]
    empty["alias_contract"]["shares_memory"] = False
    empty["data_pointer"] = 1
    return value


def run_fixtures(contract: dict) -> dict:
    normal = normal_observation(contract)
    cases: list[tuple[str, dict, bool]] = [
        ("normal_nonempty_shared_and_empty_zero_byte", normal, True),
        ("raw_artifact_end_to_end", json.loads(json.dumps(normal)), True),
    ]

    def changed(name: str, mutation, expected: bool = False) -> None:
        value = copy.deepcopy(normal)
        mutation(value)
        cases.append((name, value, expected))

    changed("nonempty_same_object_without_sharing", lambda x: x["handles"][0]["alias_contract"].update(shares_memory=False))
    changed("empty_distinct_object", lambda x: x["handles"][6]["alias_contract"].update(same_python_object=False))
    changed("empty_nonzero_elements", lambda x: x["handles"][6].update(element_count=1, logical_bytes=4))
    changed("empty_nonzero_logical_bytes", lambda x: x["handles"][6].update(logical_bytes=4))
    changed("empty_material_copy", lambda x: x["handles"][6]["alias_contract"].update(material_copy_created=True))
    changed("empty_weak_reference_residual", lambda x: x["handles"][6]["release"].update(weak_reference_alive_after_slot_clear=True))
    changed("six_handles", lambda x: x["handles"].pop())
    changed("eight_handles", lambda x: x["handles"].append(copy.deepcopy(x["handles"][-1])))
    changed("missing_handle", lambda x: x["handles"].pop(2))
    changed("duplicate_handle", lambda x: x["handles"][6].update(index=5, label="handle[5]"))
    changed("order_exchange", lambda x: x["handles"].__setitem__(slice(1, 3), [x["handles"][2], x["handles"][1]]))
    changed("dtype_mismatch", lambda x: x["handles"][1].update(dtype="float32"))
    changed("scalar_vector_class_mismatch", lambda x: x["handles"][4].update(grid_class=2, value_type="1"))
    changed("grid_name_mismatch", lambda x: x["handles"][3].update(grid_short_name="Other"))
    changed("unknown_schema", lambda x: x.update(candidate_schema_id="future"))
    changed("unknown_handle", lambda x: x.update(unknown_handles=[6]))
    changed("metadata_missing", lambda x: x["handles"][0].pop("metadata_sha256"))
    changed("nonempty_weak_reference_residual", lambda x: x["handles"][1]["release"].update(weak_reference_alive_after_slot_clear=True))
    changed("list_slot_not_cleared", lambda x: x["handles"][1]["release"].update(list_slot_cleared=False))
    changed("second_readback", lambda x: (x.update(public_readback_calls=2), x["operation_counts"].update(public_readback_calls=2)))

    results = []
    for name, payload, expected_pass in cases:
        actual = validate_preflight(payload, contract)
        results.append({"name": name, "expected_pass": expected_pass, "actual_pass": actual["pass"],
                        "reasons": actual["reasons"], "fixture_pass": actual["pass"] == expected_pass})
    return {
        "schema": "campfire.phase6gj.empty-rgba-alias-fixtures.v1",
        "phase": "phase6gj",
        "passed": sum(item["fixture_pass"] for item in results),
        "total": len(results),
        "all_pass": all(item["fixture_pass"] for item in results),
        "raw_artifact_end_to_end_pass": next(item["fixture_pass"] for item in results if item["name"] == "raw_artifact_end_to_end"),
        "results": results,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--observation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_json(args.contract)
    if args.fixtures:
        result = run_fixtures(contract)
        code = 0 if result["all_pass"] else 1
    elif args.observation:
        result = validate_preflight(load_json(args.observation), contract)
        code = 0 if result["pass"] else 1
    else:
        parser.error("--fixtures or --observation is required")
    write_json(args.output, result)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
