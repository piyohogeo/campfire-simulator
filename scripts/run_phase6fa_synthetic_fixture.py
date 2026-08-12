"""Exercise the frozen Phase 6FA dynamic/constant occupancy branches."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from phase6fa_occupancy_contract import evaluate


def rows(active, memory):
    return [
        {
            "wall_seconds": index * 0.5,
            "active_blocks": float(blocks),
            "kit_private_bytes": float(private),
            "kit_working_set_bytes": float(private * 0.8),
            "tree_private_bytes": float(private + 64 * 1024**2),
            "gpu_dedicated_memory_mib": 3000.0,
        }
        for index, (blocks, private) in enumerate(zip(active, memory))
    ]


def functional(**overrides):
    value = {
        "telemetry_fresh": True,
        "timeline_advanced": True,
        "timeline_playing": True,
        "emitter_input_positive": True,
        "point_revision_expected": True,
        "stage_identity_unchanged": True,
        "flow_identity_unchanged": True,
        "meaningful_flow_field": True,
    }
    value.update(overrides)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    thresholds = contract["occupancy_stationarity_thresholds"]
    count = 49
    base = 10 * 1024**3
    periodic_active = [900 + int(110 * math.sin(index * 0.55)) for index in range(count)]
    periodic_memory = [base + (blocks - 900) * 2 * 1024**2 for blocks in periodic_active]
    recovery_cycle = [1100, 1050, 1000, 950, 1000, 1050]
    decrease_active = [recovery_cycle[index % len(recovery_cycle)] for index in range(count)]
    decrease_memory = [base + (blocks - 900) * 1024**2 for blocks in decrease_active]
    cases = {
        "constant_flat": (rows([900] * count, [base] * count), functional(), True),
        "constant_bounded_noise": (
            rows([900] * count, [base + ((index % 5) - 2) * 4 * 1024**2 for index in range(count)]),
            functional(), True,
        ),
        "dynamic_bounded": (rows(periodic_active, periodic_memory), functional(), True),
        "drop_memory_recovery": (rows(decrease_active, decrease_memory), functional(), True),
        "constant_linear_memory_growth": (
            rows([900] * count, [base + index * 16 * 1024**2 for index in range(count)]), functional(), False,
        ),
        "constant_accelerating_memory_growth": (
            rows([900] * count, [base + index * index * 1024**2 for index in range(count)]), functional(), False,
        ),
        "stale_active_telemetry": (rows([900] * count, [base] * count), functional(telemetry_fresh=False), False),
        "timeline_stopped": (rows([900] * count, [base] * count), functional(timeline_advanced=False, timeline_playing=False), False),
        "emitter_input_missing": (rows([900] * count, [base] * count), functional(emitter_input_positive=False), False),
        "empty_flow_field": (rows([900] * count, [base] * count), functional(meaningful_flow_field=False), False),
        "unrepresentative_24_blocks": (rows([24] * count, [base] * count), functional(), False),
        "drop_without_memory_recovery": (
            rows(decrease_active, [base + index * 12 * 1024**2 for index in range(count)]), functional(), False,
        ),
    }
    output = {}
    success = True
    for name, (series, facts, expected) in cases.items():
        result = evaluate(series, thresholds, facts)
        actual = bool(result["gate_pass"])
        output[name] = {
            "expected_gate_pass": expected,
            "actual_gate_pass": actual,
            "classification": result["classification"],
            "failed_checks": [key for key, passed in result["checks"].items() if not passed],
        }
        success = success and actual == expected
    payload = {
        "schema": "campfire.phase6fa.synthetic-occupancy-fixture.v1",
        "status": "pass" if success else "fail",
        "cases": output,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "synthetic_fixture_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    raise SystemExit(0 if success else 2)


if __name__ == "__main__":
    main()
