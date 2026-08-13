"""Synthetic and historical read-only calibration for Phase 6FF."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

try:
    from .phase6ff_memory_boundedness import evaluate
except ImportError:
    from phase6ff_memory_boundedness import evaluate


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024


def synthetic_rows(name: str, count: int = 97, cadence: float = 0.5) -> list[dict]:
    rows = []
    baseline = 10 * 1024**3
    for index in range(count):
        t = index * cadence
        active = 1200 + int(90 * math.sin(index / 6.0))
        if name == "startup_then_plateau":
            delta = min(index, 12) * 40 * MIB
        elif name == "brief_over_8mib_then_recovery":
            delta = (index * 12 * MIB if index < 12 else max(0, (24 - index) * 12 * MIB))
        elif name == "bounded_allocator_cache":
            delta = min(index, 12) * 16 * MIB + (int(8 * MIB * math.sin(index / 5.0)) if index < 60 else 0)
        elif name == "active_following_bounded":
            delta = (active - 1110) * 2 * MIB
        elif name == "shader_resource_transient":
            delta = 640 * MIB if 20 <= index < 28 else 0
        elif name == "delayed_reclaim_after_disappearance":
            if index >= 44:
                active = 24
            delta = 320 * MIB if 44 <= index < 68 else 0
        elif name == "occupancy_independent_monotonic":
            delta = index * 4 * MIB
        elif name == "late_positive_slope":
            delta = max(0, index - 48) * 6 * MIB
        elif name == "staircase_accumulation":
            delta = (index // 12) * 48 * MIB
        elif name == "per_block_growth":
            delta = index * active * 4096
        elif name == "absolute_limit":
            delta = 5 * 1024**3
        else:
            raise ValueError(name)
        private = baseline + delta
        rows.append({
            "wall_seconds": t,
            "timestamp_utc": f"synthetic-{index:03d}",
            "timeline_frame": 320 + index,
            "active_blocks": active,
            "kit_private_bytes": private,
            "kit_working_set_bytes": private * 0.6,
            "tree_private_bytes": private + 128 * MIB,
            "gpu_dedicated_memory_mib": 7000.0,
        })
    return rows


def _historical(report_path: Path, key: str, contract: dict) -> dict | None:
    if not report_path.is_file():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    case = (report.get("cases") or {}).get(key)
    if not case:
        return None
    rows = case.get("aligned_time_series") or []
    if not rows:
        return None
    result = evaluate(rows, contract)
    return {
        "source": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "case": key,
        "historical_only": True,
        "sample_count": len(rows),
        "observation_seconds": rows[-1]["wall_seconds"] - rows[0]["wall_seconds"],
        "phase6ff_offline_evaluation": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    accepted = [
        "startup_then_plateau", "brief_over_8mib_then_recovery", "bounded_allocator_cache",
        "active_following_bounded", "shader_resource_transient", "delayed_reclaim_after_disappearance",
    ]
    rejected = [
        "occupancy_independent_monotonic", "late_positive_slope", "staircase_accumulation",
        "per_block_growth", "absolute_limit",
    ]
    synthetic = {}
    for name in accepted + rejected:
        result = evaluate(synthetic_rows(name), contract)
        synthetic[name] = {"expected": "accept" if name in accepted else "reject", "evaluation": result}
    synthetic["shutdown_incomplete"] = {
        "expected": "reject",
        "evaluation": {"gate_pass": False, "checks": {"normal_os_exit": False, "cleanup_residual_zero": False}},
    }
    historical = [
        _historical(ROOT / "artifacts/phase6fd-fuel-alias-lifetime-1/fuel_alias_lifetime_report.json", key, contract)
        for key in ("C0_acquire_discard", "C1_fuel_alias")
    ]
    historical.append(_historical(
        ROOT / "artifacts/phase6fe-lagged-memory-response-2/lagged_memory_response_report.json",
        "run01_C0_acquire_discard", contract,
    ))
    pass_expected = all(
        item["evaluation"]["gate_pass"] == (item["expected"] == "accept")
        for item in synthetic.values()
    )
    payload = {
        "schema": "campfire.phase6ff.memory-boundedness-calibration.v1",
        "status": "pass" if pass_expected else "fail",
        "contract_sha256": __import__("hashlib").sha256(args.contract.read_bytes()).hexdigest().upper(),
        "synthetic": synthetic,
        "historical_read_only_audit": [item for item in historical if item is not None],
        "historical_samples_reused_in_formal_population": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    raise SystemExit(0 if pass_expected else 2)


if __name__ == "__main__":
    main()
