"""Fail-closed Phase 6GI public-channel preflight schema policy."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "scripts" / "phase6gi_s93_channel_preflight_contract.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value)


def validate_raw_schema(observed: dict, contract: dict) -> dict:
    reasons: list[str] = []
    versions = observed.get("versions") or {}
    for key in ("flow", "kit", "volume"):
        if versions.get(key) != contract["versions"][key]:
            reasons.append(f"{key}_version_mismatch")
    if observed.get("api") != contract["versions"]["api"]:
        reasons.append("api_mismatch")
    if observed.get("candidate_schema_id") != contract["candidate_schema"]["schema_id"]:
        reasons.append("schema_id_mismatch")
    if observed.get("candidate_schema_sha256") != contract["candidate_schema"]["sha256"]:
        reasons.append("candidate_schema_hash_mismatch")
    if observed.get("export_enable_state") != contract["condition"]["export_enable_state"]:
        reasons.append("export_enable_state_mismatch")
    if observed.get("public_readback_calls") != 1:
        reasons.append("readback_count_mismatch")
    handles = observed.get("handles")
    if not isinstance(handles, list):
        reasons.append("handles_missing")
        handles = []
    expected = contract["schema_gate"]["handles"]
    if len(handles) != len(expected):
        reasons.append("handle_count_mismatch")
    seen: set[int] = set()
    for position, wanted in enumerate(expected):
        if position >= len(handles):
            continue
        actual = handles[position]
        if actual.get("is_numpy_array") is not True:
            reasons.append("direct_numpy_array_required")
        index = actual.get("index")
        if index in seen:
            reasons.append("duplicate_handle")
        seen.add(index)
        if index != wanted["index"]:
            reasons.append("handle_order_mismatch")
        if actual.get("label") != f"handle[{wanted['index']}]":
            reasons.append("raw_handle_label_mismatch")
        if actual.get("dtype") != contract["schema_gate"]["required_dtype"]:
            reasons.append("dtype_mismatch")
        if not isinstance(actual.get("shape"), list) or not isinstance(actual.get("strides"), list):
            reasons.append("array_metadata_missing")
        size, logical = actual.get("element_count"), actual.get("logical_bytes")
        if not isinstance(size, int) or size < 0 or logical != size * 4:
            reasons.append("logical_bytes_inconsistent")
            size = -1
        empty = size == 0
        if wanted["required_state"] == "nonempty":
            if empty:
                reasons.append("required_handle_empty")
            if actual.get("grid_count") != 1:
                reasons.append("grid_count_mismatch")
            if actual.get("grid_short_name") != contract["schema_gate"]["required_grid_short_name"]:
                reasons.append("grid_name_mismatch")
            if actual.get("grid_class") != wanted["grid_class"]:
                reasons.append("grid_class_mismatch")
            if str(actual.get("value_type")) != wanted["value_type"]:
                reasons.append("value_type_mismatch")
        elif not empty:
            reasons.append("required_empty_handle_nonempty")
        if not _hex_digest(actual.get("metadata_sha256")):
            reasons.append("metadata_hash_missing")
    if observed.get("unknown_handles"):
        reasons.append("unknown_handle")
    return {"pass": not reasons, "reasons": sorted(set(reasons))}


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
        if alias.get("same_python_object") is not True or alias.get("shares_memory") is not True:
            reasons.append("alias_contract_mismatch")
        if alias.get("numpy_asarray_called") is not False or alias.get("material_copy_created") is not False:
            reasons.append("material_copy_observed")
        if (wanted["required_state"] == "nonempty"
                and (not isinstance(actual.get("data_pointer"), int) or actual["data_pointer"] <= 0)):
            reasons.append("positive_pointer_missing")
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
    handles = []
    for wanted in contract["schema_gate"]["handles"]:
        empty = wanted["required_state"] == "empty"
        size = 0 if empty else 1024
        handles.append({
            "index": wanted["index"], "label": f"handle[{wanted['index']}]", "channel": wanted["channel"],
            "is_numpy_array": True,
            "dtype": "uint32", "shape": [size], "strides": [4], "element_count": size,
            "logical_bytes": size * 4, "data_pointer": 4096 + wanted["index"] if not empty else None,
            "grid_count": 0 if empty else 1, "grid_short_name": None if empty else "Flow",
            "grid_class": None if empty else wanted["grid_class"], "value_type": None if empty else wanted["value_type"],
            "metadata_sha256": hashlib.sha256(f"handle-{wanted['index']}".encode()).hexdigest().upper(),
            "alias_contract": {"same_python_object": True, "shares_memory": True,
                               "numpy_asarray_called": False, "material_copy_created": False},
            "release": {"list_slot_cleared": True, "weak_reference_supported": True,
                        "weak_reference_alive_after_slot_clear": False},
        })
    return {
        "candidate_schema_id": contract["candidate_schema"]["schema_id"],
        "candidate_schema_sha256": contract["candidate_schema"]["sha256"],
        "versions": {k: contract["versions"][k] for k in ("flow", "kit", "volume")},
        "api": contract["versions"]["api"], "export_enable_state": copy.deepcopy(contract["condition"]["export_enable_state"]),
        "public_readback_calls": 1, "handles": handles, "unknown_handles": [],
        "semantic_mapping_applied_after_raw_schema_validation": True,
        "operation_counts": {"public_readback_calls": 1, "numpy_asarray_calls": 0, "material_copies": 0, "field_body_writes": 0},
        "weak_reference_alive_after_release_count": 0, "ownership_container_residual_count": 0,
    }


def run_fixtures(contract: dict) -> dict:
    normal = normal_observation(contract)
    cases: list[tuple[str, dict, bool]] = [("normal_rgba7_divergence_on_rgba_off", normal, True)]
    def changed(name: str, mutation, expected=False):
        value = copy.deepcopy(normal)
        mutation(value)
        cases.append((name, value, expected))
    changed("six_handles", lambda x: x["handles"].pop())
    changed("eight_handles", lambda x: x["handles"].append(copy.deepcopy(x["handles"][-1])))
    changed("missing_handle", lambda x: x["handles"].pop(2))
    changed("duplicate_handle", lambda x: x["handles"][6].update(index=5, label="handle[5]"))
    changed("order_exchange", lambda x: x["handles"].__setitem__(slice(1, 3), [x["handles"][2], x["handles"][1]]))
    changed("dtype_mismatch", lambda x: x["handles"][1].update(dtype="float32"))
    changed("scalar_vector_class_mismatch", lambda x: x["handles"][4].update(grid_class=2, value_type="1"))
    changed("grid_name_mismatch", lambda x: x["handles"][3].update(grid_short_name="Other"))
    changed("flow_version_mismatch", lambda x: x["versions"].update(flow="future"))
    changed("metadata_missing", lambda x: x["handles"][0].pop("metadata_sha256"))
    changed("unknown_handle", lambda x: x.update(unknown_handles=[6]))
    changed("legacy_six_channel_schema", lambda x: x["handles"].pop())
    changed("unsupported_future_schema", lambda x: x.update(candidate_schema_id="future"))
    changed("divergence_disabled_empty", lambda x: x["handles"][5].update(element_count=0, logical_bytes=0, grid_count=0,
            grid_short_name=None, grid_class=None, value_type=None, data_pointer=None))
    changed("rgba_unexpectedly_nonempty", lambda x: x["handles"][6].update(element_count=64, logical_bytes=256,
            grid_count=1, grid_short_name="Flow", grid_class=0, value_type="17", data_pointer=9999))
    changed("weak_reference_residual", lambda x: x["handles"][1]["release"].update(weak_reference_alive_after_slot_clear=True))
    changed("list_slot_not_cleared", lambda x: x["handles"][1]["release"].update(list_slot_cleared=False))
    changed("material_copy", lambda x: x["handles"][1]["alias_contract"].update(material_copy_created=True))
    changed("second_readback", lambda x: (x.update(public_readback_calls=2), x["operation_counts"].update(public_readback_calls=2)))
    results = []
    for name, payload, expected_pass in cases:
        actual = validate_preflight(payload, contract)
        results.append({"name": name, "expected_pass": expected_pass, "actual_pass": actual["pass"],
                        "reasons": actual["reasons"], "fixture_pass": actual["pass"] == expected_pass})
    return {"schema": "campfire.phase6gi.channel-preflight-fixtures.v1", "phase": "phase6gi",
            "passed": sum(item["fixture_pass"] for item in results), "total": len(results),
            "all_pass": all(item["fixture_pass"] for item in results), "results": results}


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
        exit_code = 0 if result["all_pass"] else 1
    elif args.observation:
        result = validate_preflight(load_json(args.observation), contract)
        exit_code = 0 if result["pass"] else 1
    else:
        parser.error("--fixtures or --observation is required")
    write_json(args.output, result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
