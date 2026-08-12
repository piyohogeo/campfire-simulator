"""Validate the frozen Phase 6EY metric contract without launching Kit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .calibrate_phase6ey_dynamic_stationarity import _synthetic_rows
    from .phase6ey_dynamic_stationarity import evaluate
except ImportError:
    from calibrate_phase6ey_dynamic_stationarity import _synthetic_rows
    from phase6ey_dynamic_stationarity import evaluate


EXPECTATIONS = {
    "constant_noise": True,
    "periodic": True,
    "drop_recovery": True,
    "linear_growth": False,
    "accelerating_growth": False,
    "memory_only_growth": False,
    "bounded_correlated_growth": True,
    "cache_after_drop": False,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Phase 6EY synthetic fixture refuses output reuse: {args.output}")
    args.output.mkdir(parents=True)
    payload = args.contract.read_bytes()
    contract = json.loads(payload.decode("utf-8"))
    thresholds = contract["dynamic_stationarity_thresholds"]
    cases = {}
    for name, expected in EXPECTATIONS.items():
        evaluation = evaluate(_synthetic_rows(name), thresholds)
        cases[name] = {
            "expected_gate_pass": expected,
            "actual_gate_pass": evaluation["gate_pass"],
            "expectation_met": evaluation["gate_pass"] is expected,
            "failed_checks": [key for key, value in evaluation["checks"].items() if not value],
            "metrics": evaluation["metrics"],
        }
    report = {
        "schema": "campfire.phase6ey.synthetic-dynamic-stationarity-fixture.v1",
        "phase": "phase6ey",
        "contract_sha256": hashlib.sha256(payload).hexdigest().upper(),
        "status": "pass" if all(case["expectation_met"] for case in cases.values()) else "fail",
        "cases": cases,
    }
    (args.output / "synthetic_fixture_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
