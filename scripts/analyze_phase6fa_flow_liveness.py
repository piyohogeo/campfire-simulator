"""Aggregate the predeclared Phase 6FA Flow-liveness diagnosis."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_phase6ey_dynamic_stationarity import _case as phase6ey_case, _lifecycle_pass
from analyze_phase6ew_r0_lifecycle import _json
from phase6fa_occupancy_contract import evaluate


ENTRIES = (
    ("D0_no_readback", "D0_no_readback"),
    ("D1_readback_release", "D1_readback_release"),
    ("D2_fuel_asarray", "D2_fuel_asarray"),
)


def _boundary(raw: dict) -> dict:
    for sample in raw.get("samples", []):
        if sample.get("readback_boundary"):
            return sample["readback_boundary"]
    return {}


def _case(root: Path, label: str, contract: dict) -> dict:
    compatibility = dict(contract)
    compatibility["dynamic_stationarity_thresholds"] = contract["occupancy_stationarity_thresholds"][
        "dynamic_thresholds"
    ]
    result = phase6ey_case(root, label, label, compatibility)
    raw = _json(root / label / "raw.json") or {}
    audit = raw.get("flow_liveness_audit") or {}
    boundary = _boundary(raw)
    fuel = boundary.get("fuel_liveness") or {}
    point = raw.get("point_payload") or {}
    source = raw.get("source_sums") or {}
    threshold = contract["functional_liveness"]
    active = [float(row["active_blocks"]) for row in result.get("aligned_time_series", [])]
    requires_decode = label != "D0_no_readback"
    meaningful = bool(
        active and max(active) >= float(threshold["minimum_representative_active_blocks"])
        and (
            not requires_decode
            or (
                int(fuel.get("active_voxel_count", 0)) >= int(threshold["minimum_public_fuel_active_voxels"])
                and int(fuel.get("emitter_position_nonzero_count_1e_6", 0))
                >= int(threshold["minimum_emitter_position_nonzero_samples"])
                and float(fuel.get("emitter_position_maximum") or 0.0) > float(threshold["fuel_significance_threshold"])
            )
        )
    )
    functional = {
        "telemetry_fresh": audit.get("telemetry_fresh") is True,
        "timeline_advanced": audit.get("timeline_advanced") is True,
        "timeline_playing": result.get("stability_timeline_playing_at_end") is True,
        "emitter_input_positive": bool(
            float(source.get("fuel") or 0.0) >= float(threshold["expected_positive_fuel_sum_minimum"])
            and int(point.get("active_point_count") or 0) == int(threshold["expected_active_point_count"])
            and int(point.get("original_point_count") or 0) == int(threshold["expected_total_point_count"])
        ),
        "point_revision_expected": int(raw.get("revision") or -1) == int(threshold["expected_point_revision"]),
        "stage_identity_unchanged": audit.get("stage_identity_unchanged") is True,
        "flow_identity_unchanged": audit.get("flow_identity_unchanged") is True,
        "meaningful_flow_field": meaningful,
        "public_fuel_decode_required": requires_decode,
        "public_fuel_active_voxels": fuel.get("active_voxel_count"),
        "public_fuel_emitter_nonzero_count": fuel.get("emitter_position_nonzero_count_1e_6"),
        "public_fuel_emitter_maximum": fuel.get("emitter_position_maximum"),
    }
    occupancy = evaluate(result.get("aligned_time_series", []), contract["occupancy_stationarity_thresholds"], functional)
    counts = boundary.get("operation_counts") or {}
    expected_asarray = 1 if label == "D2_fuel_asarray" else 0
    operation_pass = bool(
        (label == "D0_no_readback" and not boundary)
        or (
            label != "D0_no_readback"
            and counts.get("public_readback_calls") == 1
            and counts.get("numpy_asarray_calls") == expected_asarray
            and counts.get("temporary_fuel_liveness_decode_calls") == 1
        )
    )
    result.update({
        "flow_liveness_audit": audit,
        "readback_boundary": boundary,
        "functional_liveness": functional,
        "occupancy_stationarity": occupancy,
        "operation_contract_pass": operation_pass,
        "condition_gate_pass": bool(_lifecycle_pass(result) and occupancy["gate_pass"] and operation_pass),
    })
    result["condition_gate_failures"] = [
        name for name, passed in {
            "lifecycle": _lifecycle_pass(result),
            "occupancy_stationarity": occupancy["gate_pass"],
            "operation_contract": operation_pass,
        }.items() if not passed
    ]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    for label, _prefix in ENTRIES:
        if (args.root / label).exists():
            cases[label] = _case(args.root, label, contract)
    d0, d1, d2 = (cases.get(label) for label, _ in ENTRIES)
    allocation = None if d2 is None else (
        (d2.get("readback_boundary") or {}).get("observable_copy_contract") or {}
    ).get("allocation_classification")
    report = {
        "schema": "campfire.phase6fa.flow-liveness-qualification-report.v1",
        "phase": "phase6fa",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": True,
        "cases": cases,
        "d0_gate_pass": bool(d0 and d0["condition_gate_pass"]),
        "d1_started": d1 is not None,
        "d1_gate_pass": bool(d1 and d1["condition_gate_pass"]),
        "d2_started": d2 is not None,
        "d2_gate_pass": bool(d2 and d2["condition_gate_pass"]),
        "numpy_asarray_allocation_classification": allocation,
        "single_fuel_alias_lifetime_qualified": bool(
            d0 and d1 and d2 and all(item["condition_gate_pass"] for item in (d0, d1, d2))
            and allocation in ("same_object_zero_copy_alias", "distinct_python_object_shared_memory_alias")
        ),
        "repeated_readback_qualified": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
