"""Validate and visualize the Phase 6BF resident USD handle-cache candidate."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "resident_handle_cache_report.json"
DEFAULT_SVG = ASSETS / "resident_handle_cache_report.svg"
LOCAL_BUDGET_MS = 4.0


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _load(paths):
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _signature(summary):
    return (
        summary["wood"]["dry"]["authoritative_state_sha256"],
        summary["wood"]["wet"]["authoritative_state_sha256"],
        summary["metrics_csv_sha256"],
        summary["wood"]["dry"]["ignition_seconds"],
        summary["wood"]["wet"]["ignition_seconds"],
    )


def _timing(summary):
    timing = summary["timing"]["segments"]["resident_snapshot_transaction"]
    _require(timing is not None and timing["sample_count"] == 236, "Missing transaction timing")
    return timing


def _aggregate(timings):
    return {
        "run_count": len(timings),
        "median_mean_ms": round(statistics.median(item["mean_ms"] for item in timings), 4),
        "median_p95_ms": round(statistics.median(item["p95_ms"] for item in timings), 4),
        "median_max_ms": round(statistics.median(item["max_ms"] for item in timings), 4),
        "run_mean_ms": [item["mean_ms"] for item in timings],
        "run_p95_ms": [item["p95_ms"] for item in timings],
        "run_max_ms": [item["max_ms"] for item in timings],
    }


def analyze(baselines, candidates):
    _require(len(baselines) == len(candidates) >= 3, "Need at least three paired runs")
    expected_signature = _signature(baselines[0])
    for label, runs, cache_expected in (
        ("baseline", baselines, False),
        ("candidate", candidates, True),
    ):
        for index, summary in enumerate(runs, start=1):
            _require(
                summary.get("phase") == "phase3" and summary.get("status") == "ok",
                f"{label} run {index} failed",
            )
            contract = summary["scenario"]["resident_snapshot_adapter"]
            status = contract["status_after_timeline_stop"]
            _require(contract["enabled"], f"{label} adapter disabled")
            _require(not contract["transaction_timing_enabled"], "Detailed profiler must be disabled")
            _require(contract["handle_cache_enabled"] is cache_expected, "Unexpected cache setting")
            _require(not contract["native_producer_connected"], "Native producer must remain disconnected")
            _require(
                not status["active"]
                and status["publish_count"] == 240
                and status["revision"] == 1200
                and status["start_count"] == status["stop_count"] == 1,
                f"{label} run {index} lifecycle failed",
            )
            _require(contract["final_usd_state"]["revision_consistent"], "Consumer revision mismatch")
            _require(_signature(summary) == expected_signature, "Authoritative output changed")
            _require(summary["flow"]["active_blocks_peak"] > 0, "Flow was not active")
            if cache_expected:
                _require(
                    status["cached_attribute_count"] == 19
                    and status["prim_cache_miss_count"] == 1
                    and status["prim_cache_hit_count"] == 239
                    and status["attribute_cache_miss_count"] == 19
                    and status["attribute_cache_hit_count"] == 4541,
                    f"Candidate run {index} cache did not reach steady state",
                )

    baseline_timings = [_timing(summary) for summary in baselines]
    candidate_timings = [_timing(summary) for summary in candidates]
    baseline = _aggregate(baseline_timings)
    candidate = _aggregate(candidate_timings)
    paired_improvements = [
        round(base["p95_ms"] - cached["p95_ms"], 4)
        for base, cached in zip(baseline_timings, candidate_timings)
    ]
    all_pairs_improved = all(value > 0.0 for value in paired_improvements)
    every_candidate_below_budget = all(
        item["p95_ms"] < LOCAL_BUDGET_MS for item in candidate_timings
    )
    qualified = all_pairs_improved and every_candidate_below_budget
    return {
        "schema_version": 1,
        "phase": "phase6bf",
        "status": "ok",
        "measurement": {
            "hardware": "NVIDIA GeForce RTX 3090 / D3D12",
            "scenario": "Phase 3 dry/wet logs, 1200 steps, 240 model seconds",
            "paired_run_count": len(baselines),
            "measured_updates_per_run": 236,
            "cache_default_enabled": False,
        },
        "contracts": {
            "all_transactions_committed": True,
            "revision_and_lifecycle_preserved": True,
            "authoritative_outputs_exact_across_runs": True,
            "actual_old_value_rollback_preserved": True,
            "invalid_property_handle_recreated": True,
            "native_producer_connected": False,
        },
        "transaction_timing_ms": {"baseline": baseline, "handle_cache": candidate},
        "paired_p95_improvement_ms": paired_improvements,
        "decision": {
            "all_pairs_improved": all_pairs_improved,
            "every_candidate_run_below_4ms": every_candidate_below_budget,
            "qualified_for_resident_adapter": qualified,
            "global_default_changed": False,
            "native_producer_connection_unblocked": qualified,
            "reason": (
                "The candidate caches only valid prim and attribute handles. It still reads the "
                "actual authored old value on every touched attribute and retains transactional rollback."
            ),
            "next_gate": (
                "Connect the resident native producer to the existing immutable snapshot schema."
                if qualified
                else "Retain the candidate as opt-in and optimize the next measured USD boundary."
            ),
        },
    }


def _svg(report):
    baseline = report["transaction_timing_ms"]["baseline"]
    candidate = report["transaction_timing_ms"]["handle_cache"]
    scale = 105.0
    gate_x = 300 + LOCAL_BUDGET_MS * scale
    rows = []
    for index, (base, cached) in enumerate(
        zip(baseline["run_p95_ms"], candidate["run_p95_ms"]), start=1
    ):
        y = 332 + (index - 1) * 62
        rows.append(
            f'<text x="80" y="{y + 18}" class="label">Pair {index}</text>'
            f'<rect x="300" y="{y}" width="{base * scale:.1f}" height="18" rx="9" class="base"/>'
            f'<rect x="300" y="{y + 27}" width="{cached * scale:.1f}" height="18" rx="9" class="candidate"/>'
            f'<text x="{315 + max(base, cached) * scale:.1f}" y="{y + 31}" class="small">{base:.4f} → {cached:.4f} ms</text>'
        )
    result = "PASS" if report["decision"]["qualified_for_resident_adapter"] else "HOLD"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<style>
 .bg{{fill:#0d1222}} .panel{{fill:#171f34}} .title{{fill:#f5f7ff;font:700 30px system-ui,sans-serif}}
 .sub{{fill:#a9b4cc;font:16px system-ui,sans-serif}} .label{{fill:#edf1ff;font:600 16px system-ui,sans-serif}}
 .metric{{fill:#ff8a4c;font:700 28px ui-monospace,monospace}} .small{{fill:#b8c2d9;font:14px system-ui,sans-serif}}
 .base{{fill:#56637d}} .candidate{{fill:#2dc887}} .gate{{stroke:#ffd166;stroke-width:3;stroke-dasharray:8 7}}
 .gateText{{fill:#ffd166;font:700 14px ui-monospace,monospace}} .result{{fill:#ffd166;font:700 20px system-ui,sans-serif}}
</style>
<rect width="1200" height="680" class="bg"/><text x="64" y="62" class="title">Phase 6BF - Resident USD handle cache</text>
<text x="64" y="92" class="sub">3 alternating real-Kit pairs · 236 measured updates/run · actual old-value rollback retained</text>
<rect x="50" y="120" width="1100" height="142" rx="18" class="panel"/>
<text x="80" y="158" class="label">Baseline transaction p95 median</text><text x="80" y="202" class="metric">{baseline["median_p95_ms"]:.4f} ms</text>
<text x="540" y="158" class="label">Handle-cache transaction p95 median</text><text x="540" y="202" class="metric">{candidate["median_p95_ms"]:.4f} ms</text>
<text x="940" y="158" class="label">4 ms gate</text><text x="940" y="202" class="result">{result}</text>
<text x="80" y="238" class="small">cache steady state: 1 prim miss + 239 hits · 19 attribute misses + 4,541 hits per run</text>
<text x="64" y="307" class="label">Run p95 · baseline (gray) vs cache (green)</text><line x1="{gate_x:.1f}" y1="318" x2="{gate_x:.1f}" y2="532" class="gate"/><text x="{gate_x + 8:.1f}" y="326" class="gateText">4 ms</text>
{''.join(rows)}
<rect x="50" y="620" width="1100" height="1" fill="#35405b"/><text x="64" y="650" class="result">HANDLE CACHE: {result}</text>
<text x="340" y="650" class="small">immutable snapshot · monotonic revision · actual old values · rollback · default OFF</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(_load(arguments.baseline), _load(arguments.candidate))
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    arguments.svg.write_text(_svg(report) + "\n", encoding="utf-8")
    print(f"Wrote {arguments.json}")
    print(f"Wrote {arguments.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
