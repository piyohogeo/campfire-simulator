"""Payload-native float32 source contract for Phase 6GC.

The primary path compares canonical authoring and live arrays exactly.  The
ULP-derived sum budget is only available when an explicitly declared alternate
accumulation order is used; it never substitutes for array identity checks.
"""

from __future__ import annotations

import hashlib
import math
from typing import Mapping

import numpy as np


ARRAY_NAMES = ("points", "fuel", "temperature", "smoke")
SOURCE_NAMES = ("fuel", "temperature", "smoke")


def _array(value, *, dtype=None) -> np.ndarray:
    array = np.asarray(value, dtype=dtype)
    return np.ascontiguousarray(array)


def _array_contract(value, *, dtype=None) -> dict:
    array = _array(value, dtype=dtype)
    finite = bool(np.isfinite(array).all()) if np.issubdtype(array.dtype, np.number) else True
    return {
        "shape": [int(component) for component in array.shape],
        "dtype": str(array.dtype),
        "strides": [int(component) for component in array.strides],
        "c_contiguous": bool(array.flags.c_contiguous),
        "logical_bytes": int(array.nbytes),
        "finite": finite,
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest().upper(),
    }


def _canonical_hash(arrays: Mapping[str, np.ndarray], revision: int, payload_identity: str) -> str:
    digest = hashlib.sha256()
    digest.update(b"campfire.phase6gc.payload-native-source.v1\0")
    digest.update(int(revision).to_bytes(8, "little", signed=True))
    identity_bytes = payload_identity.encode("utf-8")
    digest.update(len(identity_bytes).to_bytes(8, "little"))
    digest.update(identity_bytes)
    for name in ARRAY_NAMES:
        array = _array(arrays[name])
        name_bytes = name.encode("ascii")
        dtype_bytes = str(array.dtype).encode("ascii")
        digest.update(len(name_bytes).to_bytes(4, "little"))
        digest.update(name_bytes)
        digest.update(len(dtype_bytes).to_bytes(4, "little"))
        digest.update(dtype_bytes)
        digest.update(array.ndim.to_bytes(4, "little"))
        for size in array.shape:
            digest.update(int(size).to_bytes(8, "little"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest().upper()


def _float32_ulp_budget(values: np.ndarray) -> dict:
    values = _array(values, dtype=np.float32).reshape(-1)
    finite = values[np.isfinite(values)]
    if finite.size:
        toward = np.where(finite >= 0.0, np.float32(np.inf), np.float32(-np.inf))
        ulps = np.abs(np.nextafter(finite, toward, dtype=np.float32) - finite).astype(np.float64)
        maximum_ulp = float(np.max(ulps))
    else:
        maximum_ulp = float("nan")
    count = int(values.size)
    return {
        "element_count": count,
        "maximum_float32_ulp": maximum_ulp,
        "alternate_accumulation_absolute_budget": float(count * maximum_ulp),
        "derivation": "element_count * maximum_float32_ulp; independent of observed error",
    }


def build_contract(
    *,
    points,
    fuel,
    temperature,
    smoke,
    revision: int,
    payload_identity: str,
    coerce_float32: bool = True,
) -> dict:
    dtype = np.float32 if coerce_float32 else None
    arrays = {
        "points": _array(points, dtype=dtype),
        "fuel": _array(fuel, dtype=dtype),
        "temperature": _array(temperature, dtype=dtype),
        "smoke": _array(smoke, dtype=dtype),
    }
    array_contracts = {name: _array_contract(value) for name, value in arrays.items()}
    source_sums = {
        name: float(np.sum(arrays[name].astype(np.float64), dtype=np.float64))
        for name in SOURCE_NAMES
    }
    return {
        "schema": "campfire.phase6gc.payload-native-source.v1",
        "payload_identity": str(payload_identity),
        "revision": int(revision),
        "total_point_count": int(arrays["fuel"].size),
        "active_point_count": int(np.count_nonzero(arrays["fuel"] > np.float32(0.0))),
        "arrays": array_contracts,
        "canonical_payload_sha256": _canonical_hash(arrays, revision, str(payload_identity)),
        "source_sums_float64_accumulator": source_sums,
        "decimal_reference_telemetry": {
            "fuel": float(0.8 * np.count_nonzero(arrays["fuel"] > 0.0)),
            "temperature": float(2.0 * np.count_nonzero(arrays["temperature"] > 0.0)),
            "smoke": float(0.08 * np.count_nonzero(arrays["smoke"] > 0.0)),
            "qualification_role": "telemetry_only",
        },
        "alternate_accumulation_budgets": {
            name: _float32_ulp_budget(arrays[name]) for name in SOURCE_NAMES
        },
        "accumulator_semantics": "sum(float64(float32(source_i))) in payload order with float64 accumulator",
    }


def validate_contract(expected: Mapping, observed: Mapping, *, accumulator_order: str = "payload_order") -> dict:
    failures = []
    if expected.get("schema") != "campfire.phase6gc.payload-native-source.v1":
        failures.append("expected_schema")
    if observed.get("schema") != expected.get("schema"):
        failures.append("observed_schema")
    for key in ("payload_identity", "revision", "total_point_count", "active_point_count"):
        if observed.get(key) != expected.get(key):
            failures.append(key)
    for name in ARRAY_NAMES:
        wanted = (expected.get("arrays") or {}).get(name) or {}
        actual = (observed.get("arrays") or {}).get(name) or {}
        for key in ("shape", "dtype", "strides", "c_contiguous", "logical_bytes", "finite", "sha256"):
            if actual.get(key) != wanted.get(key):
                failures.append(f"{name}_{key}")
        if not actual.get("finite", False):
            failures.append(f"{name}_nonfinite")
    if observed.get("canonical_payload_sha256") != expected.get("canonical_payload_sha256"):
        failures.append("canonical_payload_sha256")
    sum_evidence = {}
    for name in SOURCE_NAMES:
        wanted = float((expected.get("source_sums_float64_accumulator") or {}).get(name, float("nan")))
        actual = float((observed.get("source_sums_float64_accumulator") or {}).get(name, float("nan")))
        budget = 0.0
        if accumulator_order == "alternate":
            budget = float(expected["alternate_accumulation_budgets"][name]["alternate_accumulation_absolute_budget"])
        difference = abs(actual - wanted)
        accepted = bool(math.isfinite(actual) and difference <= budget)
        sum_evidence[name] = {
            "expected": wanted,
            "observed": actual,
            "absolute_difference": difference,
            "absolute_budget": budget,
            "accumulator_order": accumulator_order,
            "pass": accepted,
        }
        if not accepted:
            failures.append(f"{name}_source_sum")
    return {
        "pass": not failures,
        "failures": list(dict.fromkeys(failures)),
        "accumulator_order": accumulator_order,
        "source_sum_evidence": sum_evidence,
        "expected_payload_sha256": expected.get("canonical_payload_sha256"),
        "observed_payload_sha256": observed.get("canonical_payload_sha256"),
    }
