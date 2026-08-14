"""Exercise the Phase 6GC payload-native source contract without launching Kit."""

from __future__ import annotations

import argparse
import copy
import json
import os
import math
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6er_point_collision_geometry import SUPPORT_RADIUS_ASSUMPTION_M, corrected_plan_payload
from phase6gc_payload_native_source import build_contract, validate_contract


def _arrays(policy: str):
    plan = corrected_plan_payload("production_four", -0.0125, SUPPORT_RADIUS_ASSUMPTION_M, True, policy)
    points = np.asarray(plan["positions"], dtype=np.float32)
    active = np.asarray(plan["active"], dtype=np.float32)
    arrays = {
        "points": points,
        "fuel": np.asarray(active * np.float32(0.8), dtype=np.float32),
        "temperature": np.asarray(active * np.float32(2.0), dtype=np.float32),
        "smoke": np.asarray(active * np.float32(0.08), dtype=np.float32),
    }
    # Round-trip the same compressed-array boundary used by the formal probe.
    return arrays, plan


def _round_trip(root: Path, label: str, arrays: dict) -> dict:
    path = root / f"{label}.payload.npz"
    np.savez_compressed(path, **arrays)
    with np.load(path, allow_pickle=False) as loaded:
        return {name: np.array(loaded[name], copy=True) for name in arrays}


def _contract(arrays, identity, revision=1, coerce=True):
    return build_contract(
        points=arrays["points"], fuel=arrays["fuel"], temperature=arrays["temperature"],
        smoke=arrays["smoke"], revision=revision, payload_identity=identity,
        coerce_float32=coerce,
    )


def run(output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Phase 6GC fixture refuses output reuse: {output}")
    output.mkdir(parents=True)
    s93, s93_plan = _arrays("allow_self_center")
    s100, s100_plan = _arrays("allow_other_support")
    s93 = _round_trip(output, "S93", s93)
    s100 = _round_trip(output, "S100", s100)
    expected93 = _contract(s93, "phase6gc:S93")
    expected100 = _contract(s100, "phase6gc:S100")
    cases = []

    def add(name, expected, observed, wanted, order="payload_order"):
        result = validate_contract(expected, observed, accumulator_order=order)
        cases.append({"name": name, "expected_pass": wanted, "actual_pass": result["pass"], "result": result,
                      "expected": expected, "observed": observed})

    add("normal_s93", expected93, _contract(s93, "phase6gc:S93"), True)
    add("normal_s100", expected100, _contract(s100, "phase6gc:S100"), True)
    missing = {key: value[:-1] for key, value in s93.items()}
    add("one_point_missing", expected93, _contract(missing, "phase6gc:S93"), False)
    duplicate = {key: np.concatenate((value, value[-1:]), axis=0) for key, value in s93.items()}
    add("one_point_duplicate", expected93, _contract(duplicate, "phase6gc:S93"), False)
    changed = {key: value.copy() for key, value in s93.items()}; changed["fuel"][0] += np.float32(0.125)
    add("one_fuel_changed", expected93, _contract(changed, "phase6gc:S93"), False)
    reordered = {key: value.copy() for key, value in s93.items()}
    for value in reordered.values(): value[[0, 1]] = value[[1, 0]]
    add("point_order_changed", expected93, _contract(reordered, "phase6gc:S93"), False)
    wrong_dtype = {key: value.astype(np.float64) for key, value in s93.items()}
    add("dtype_float64", expected93, _contract(wrong_dtype, "phase6gc:S93", coerce=False), False)
    wrong_shape = {key: value.copy() for key, value in s93.items()}; wrong_shape["fuel"] = wrong_shape["fuel"].reshape(-1, 1)
    add("shape_column_vector", expected93, _contract(wrong_shape, "phase6gc:S93"), False)
    for label, bad in (("nan", np.nan), ("positive_infinity", np.inf), ("negative_infinity", -np.inf)):
        corrupted = {key: value.copy() for key, value in s93.items()}; corrupted["fuel"][0] = np.float32(bad)
        add(label, expected93, _contract(corrupted, "phase6gc:S93"), False)
    add("stale_revision", expected93, _contract(s93, "phase6gc:S93", revision=0), False)
    add("different_payload_identity", expected93, _contract(s93, "phase6gc:other"), False)
    decimal_difference = _contract(s93, "phase6gc:S93")
    add("correct_float32_differs_from_decimal", expected93, decimal_difference, True)
    alternate = copy.deepcopy(expected93)
    for channel in ("fuel", "temperature", "smoke"):
        alternate["source_sums_float64_accumulator"][channel] += expected93["alternate_accumulation_budgets"][channel]["alternate_accumulation_absolute_budget"] * 0.5
    add("alternate_accumulation_within_ulp_budget", expected93, alternate, True, "alternate")
    beyond = copy.deepcopy(expected93)
    for channel in ("fuel", "temperature", "smoke"):
        beyond["source_sums_float64_accumulator"][channel] += expected93["alternate_accumulation_budgets"][channel]["alternate_accumulation_absolute_budget"] * 1.01
    add("alternate_accumulation_exceeds_ulp_budget", expected93, beyond, False, "alternate")
    passed = all(case["actual_pass"] == case["expected_pass"] for case in cases)
    report = {
        "schema": "campfire.phase6gc.source-contract-fixtures.v1", "passed": passed,
        "kit_launched": False, "case_count": len(cases), "cases": cases,
        "payloads": {
            "S93": {"active_points": int(s93_plan["active_point_count"]), "contract": expected93},
            "S100": {"active_points": int(s100_plan["active_point_count"]), "contract": expected100},
        },
    }
    path = output / "source_contract_fixture_report.json"
    temporary = path.with_suffix(".json.partial")
    def json_safe(value):
        if isinstance(value, float) and not math.isfinite(value):
            return "NaN" if math.isnan(value) else ("+Infinity" if value > 0 else "-Infinity")
        if isinstance(value, dict): return {key: json_safe(item) for key, item in value.items()}
        if isinstance(value, list): return [json_safe(item) for item in value]
        return value
    with temporary.open("wb") as stream:
        stream.write((json.dumps(json_safe(report), indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    report = run(arguments.output)
    print(json.dumps({"passed": report["passed"], "case_count": report["case_count"]}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
