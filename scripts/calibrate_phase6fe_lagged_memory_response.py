"""Read-only historical audit and synthetic calibration for Phase 6FE."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

try:
    from .calibrate_phase6ey_dynamic_stationarity import aligned_rows
    from .phase6fe_lagged_memory_response import evaluate
except ImportError:
    from calibrate_phase6ey_dynamic_stationarity import aligned_rows
    from phase6fe_lagged_memory_response import evaluate


MIB = 1024 * 1024


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _history(repo: Path) -> list[dict]:
    cases = []
    ey = _json(repo / "artifacts/phase6ey-dynamic-stationarity-2/dynamic_stationarity_report.json")
    for label, case in ey["cases"].items():
        cases.append(("phase6ey", label, case["aligned_time_series"], case))
    ex_root = repo / "artifacts/phase6ex-r0-stability-1"
    ex_case = ex_root / "calibration/run01/R0_none"
    ex_rows = aligned_rows(
        ex_case / "resource_markers.jsonl",
        ex_root / "runner-logs/run01_R0_none.resource.jsonl",
        ex_root / "runner-logs/run01_R0_none.gpu.csv",
    )
    ex_report = _json(ex_root / "r0_stability_report.json")["cases"]["R0_run01"]
    cases.append(("phase6ex", "R0_run01", ex_rows, ex_report))
    fd = _json(repo / "artifacts/phase6fd-fuel-alias-lifetime-1/fuel_alias_lifetime_report.json")
    for label, case in fd["cases"].items():
        cases.append(("phase6fd", label, case["aligned_time_series"], case))

    output = []
    for phase, label, rows, source in cases:
        output.append({
            "phase": phase,
            "condition": label,
            "source_is_read_only": True,
            "formal_population_reuse": False,
            "source_path": source.get("path"),
            "lifecycle": {
                "normal_exit": source.get("normal_exit"),
                "stage_close_seconds": source.get("stage_close_seconds"),
                "last_probe_marker": source.get("last_probe_marker"),
            },
            "readback_boundary": source.get("memory_deltas_bytes"),
            "evaluation": None,
            "time_series": rows,
        })
    return output


def _synthetic_rows(kind: str, count: int = 80) -> list[dict]:
    rows = []
    private = 13.0 * 1024**3
    for index in range(count):
        active = 1320.0 + 130.0 * math.sin(2.0 * math.pi * index / 12.0)
        if kind == "immediate_reclaim":
            private = 12.8 * 1024**3 + active * 0.22 * MIB
        elif kind == "delayed_reclaim":
            # Model a bounded allocator whose occupancy-linked memory trails by two samples.
            delayed_index = max(0, index - 2)
            delayed_active = 1320.0 + 130.0 * math.sin(2.0 * math.pi * delayed_index / 12.0)
            private = 12.8 * 1024**3 + delayed_active * 0.22 * MIB
        elif kind == "bounded_cache_retention":
            private = 13.0 * 1024**3 + 24 * MIB * math.sin(index * 0.19)
        elif kind == "periodic_bounded":
            private = 12.8 * 1024**3 + active * 0.2 * MIB + 8 * MIB * math.sin(index * 0.4)
        elif kind == "drop_cancelled_by_rebound":
            private = 13.0 * 1024**3 + 20 * MIB * math.sin(index * 0.3)
        elif kind == "constant_occupancy_bounded_noise":
            active = 1300.0
            private = 13.0 * 1024**3 + 12 * MIB * math.sin(index * 0.37)
        elif kind == "occupancy_independent_monotonic_growth":
            private = 12.2 * 1024**3 + index * 10 * MIB
        elif kind == "constant_accelerating_growth":
            active = 1300.0
            private = 12.0 * 1024**3 + index * index * 0.30 * MIB
        elif kind == "post_drop_continued_growth":
            private = 12.2 * 1024**3 + index * 18 * MIB
        elif kind == "repeated_accumulation":
            private = 12.3 * 1024**3 + index * 12 * MIB + (index // 12) * 96 * MIB
        elif kind == "short_plateau_long_divergence":
            private = 12.4 * 1024**3 + max(0, index - 20) * 11 * MIB
        elif kind in ("stale_telemetry", "resource_ceiling", "shutdown_incomplete"):
            private = 13.0 * 1024**3 + active * 0.1 * MIB
            if kind == "resource_ceiling":
                private += 2.0 * 1024**3
        else:
            raise ValueError(kind)
        rows.append({
            "marker": "synthetic_sample",
            "timestamp_utc": None,
            "wall_seconds": index * 0.5,
            "timeline_frame": 320 + index,
            "active_blocks": int(round(active)),
            "kit_private_bytes": int(round(private)),
            "kit_working_set_bytes": int(round(private * 0.62)),
            "tree_private_bytes": int(round(private + 160 * MIB)),
            "gpu_dedicated_memory_mib": 6800.0,
        })
    return rows


def synthetic_evaluation(kind: str, contract: dict) -> dict:
    result = evaluate(_synthetic_rows(kind), contract)
    evidence = {
        "telemetry_fresh": kind != "stale_telemetry",
        "resource_ceiling_ok": kind != "resource_ceiling",
        "shutdown_complete": kind != "shutdown_incomplete",
    }
    result["synthetic_external_checks"] = evidence
    result["full_contract_gate_pass"] = result["gate_pass"] and all(evidence.values())
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Phase 6FE calibration refuses output reuse: {args.output}")
    args.output.mkdir(parents=True)
    contract = _json(args.contract)
    historical = _history(args.repo.resolve())
    for item in historical:
        item["evaluation"] = evaluate(item["time_series"], contract)
    expectations = {
        "immediate_reclaim": True,
        "delayed_reclaim": True,
        "bounded_cache_retention": True,
        "periodic_bounded": True,
        "drop_cancelled_by_rebound": True,
        "constant_occupancy_bounded_noise": True,
        "occupancy_independent_monotonic_growth": False,
        "constant_accelerating_growth": False,
        "post_drop_continued_growth": False,
        "repeated_accumulation": False,
        "short_plateau_long_divergence": False,
        "stale_telemetry": False,
        "resource_ceiling": False,
        "shutdown_incomplete": False,
    }
    synthetic = {}
    for name, expected in expectations.items():
        result = synthetic_evaluation(name, contract)
        result["expected_gate_pass"] = expected
        result["expectation_met"] = result["full_contract_gate_pass"] is expected
        synthetic[name] = result
    report = {
        "schema": "campfire.phase6fe.lagged-memory-response-calibration.v1",
        "phase": "phase6fe",
        "status": "pass" if all(value["expectation_met"] for value in synthetic.values()) else "fail",
        "purpose": "read-only historical audit and pre-runtime synthetic calibration",
        "historical_results_are_not_formal_population": True,
        "historical": historical,
        "synthetic": synthetic,
    }
    (args.output / "lagged_memory_response_calibration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
