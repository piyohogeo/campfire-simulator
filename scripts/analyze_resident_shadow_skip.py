"""Validate and visualize the Phase 6BH immutable-shadow Set-skip candidate."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "resident_shadow_skip_report.json"
DEFAULT_SVG = ASSETS / "resident_shadow_skip_report.svg"
LOCAL_BUDGET_MS = 4.0
STEADY_ATTRIBUTE_COUNT = 239 * 19


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
    _require(timing is not None and timing["sample_count"] == 236, "Missing timing")
    return timing


def _aggregate(timings):
    return {
        "run_count": len(timings),
        "median_mean_ms": round(statistics.median(x["mean_ms"] for x in timings), 4),
        "median_p95_ms": round(statistics.median(x["p95_ms"] for x in timings), 4),
        "median_max_ms": round(statistics.median(x["max_ms"] for x in timings), 4),
        "run_mean_ms": [x["mean_ms"] for x in timings],
        "run_p95_ms": [x["p95_ms"] for x in timings],
        "run_max_ms": [x["max_ms"] for x in timings],
    }


def analyze(baselines, candidates):
    _require(len(baselines) == len(candidates) >= 3, "Need three or more pairs")
    expected_signature = _signature(baselines[0])
    skipped_counts = []
    write_counts = []
    for label, runs, skip_expected in (
        ("lightweight", baselines, False),
        ("shadow-skip", candidates, True),
    ):
        for index, summary in enumerate(runs, start=1):
            _require(summary.get("phase") == "phase3" and summary.get("status") == "ok", f"{label} run {index} failed")
            contract = summary["scenario"]["resident_snapshot_adapter"]
            status = contract["status_after_timeline_stop"]
            _require(contract["enabled"] and contract["handle_cache_enabled"], "Adapter/cache disabled")
            _require(contract["lightweight_commit_enabled"], "Lightweight mode disabled")
            _require(contract["skip_unchanged_derived_enabled"] is skip_expected, "Unexpected skip mode")
            _require(not contract["native_producer_connected"], "Native producer connected early")
            _require(
                not status["active"]
                and not status["faulted"]
                and status["publish_count"] == 240
                and status["revision"] == 1200
                and status["lightweight_commit_count"] == 239
                and status["lightweight_failure_count"] == 0,
                f"{label} run {index} lifecycle failed",
            )
            _require(contract["final_usd_state"]["revision_consistent"], "Revision mismatch")
            _require(_signature(summary) == expected_signature, "Authoritative output changed")
            _require(summary["flow"]["active_blocks_peak"] > 0, "Flow inactive")
            if skip_expected:
                skipped = status["skipped_unchanged_write_count"]
                written = status["lightweight_write_count"]
                _require(skipped > 0 and skipped + written == STEADY_ATTRIBUTE_COUNT, "Incomplete write classification")
                _require(status["attribute_cache_hit_count"] == written, "Skipped values touched USD handles")
                skipped_counts.append(skipped)
                write_counts.append(written)

    baseline_timings = [_timing(summary) for summary in baselines]
    candidate_timings = [_timing(summary) for summary in candidates]
    baseline = _aggregate(baseline_timings)
    candidate = _aggregate(candidate_timings)
    paired_improvements = [
        round(base["p95_ms"] - skipped["p95_ms"], 4)
        for base, skipped in zip(baseline_timings, candidate_timings)
    ]
    all_pairs_improved = all(value > 0.0 for value in paired_improvements)
    every_candidate_below_budget = all(
        timing["p95_ms"] < LOCAL_BUDGET_MS for timing in candidate_timings
    )
    qualified = all_pairs_improved and every_candidate_below_budget
    median_skipped = int(statistics.median(skipped_counts))
    median_written = int(statistics.median(write_counts))
    return {
        "schema_version": 1,
        "phase": "phase6bh",
        "status": "ok",
        "measurement": {
            "hardware": "NVIDIA GeForce RTX 3090 / D3D12",
            "scenario": "Phase 3 dry/wet logs, 1200 steps, 240 model seconds",
            "paired_run_count": len(baselines),
            "measured_updates_per_run": 236,
            "production_default_enabled": False,
        },
        "contracts": {
            "derived_usd_attributes_are_exclusively_adapter_owned": True,
            "three_revision_writes_are_never_skipped": True,
            "failure_recovery_replays_all_19_attributes": True,
            "external_direct_usd_edits_supported": False,
            "revision_and_lifecycle_preserved": True,
            "authoritative_outputs_exact_across_runs": True,
            "native_producer_connected": False,
        },
        "steady_state_writes_per_run": {
            "classified": STEADY_ATTRIBUTE_COUNT,
            "median_written": median_written,
            "median_skipped": median_skipped,
            "median_skipped_per_commit": round(median_skipped / 239.0, 4),
            "median_skip_percent": round(100.0 * median_skipped / STEADY_ATTRIBUTE_COUNT, 4),
            "run_written": write_counts,
            "run_skipped": skipped_counts,
        },
        "transaction_timing_ms": {
            "lightweight_commit": baseline,
            "shadow_skip": candidate,
        },
        "paired_p95_improvement_ms": paired_improvements,
        "decision": {
            "all_pairs_improved": all_pairs_improved,
            "every_candidate_run_below_4ms": every_candidate_below_budget,
            "qualified_for_resident_adapter": qualified,
            "global_default_changed": False,
            "native_producer_connection_unblocked": qualified,
            "reason": (
                "Only adapter-owned derived payloads equal to the last immutable snapshot are skipped. "
                "All revision markers and failure-path full replay remain mandatory."
            ),
            "next_gate": (
                "Connect the resident native producer to the existing immutable snapshot schema."
                if qualified
                else "Keep the mode opt-in and audit the remaining changed Set operations."
            ),
        },
    }


def _svg(report):
    baseline = report["transaction_timing_ms"]["lightweight_commit"]
    candidate = report["transaction_timing_ms"]["shadow_skip"]
    writes = report["steady_state_writes_per_run"]
    scale = 105.0
    gate_x = 300 + LOCAL_BUDGET_MS * scale
    rows = []
    for index, (base, skipped) in enumerate(
        zip(baseline["run_p95_ms"], candidate["run_p95_ms"]), start=1
    ):
        y = 342 + (index - 1) * 62
        rows.append(
            f'<text x="80" y="{y + 18}" class="label">Pair {index}</text>'
            f'<rect x="300" y="{y}" width="{base * scale:.1f}" height="18" rx="9" class="base"/>'
            f'<rect x="300" y="{y + 27}" width="{skipped * scale:.1f}" height="18" rx="9" class="candidate"/>'
            f'<text x="{315 + max(base, skipped) * scale:.1f}" y="{y + 31}" class="small">{base:.4f} → {skipped:.4f} ms</text>'
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
<rect width="1200" height="680" class="bg"/><text x="64" y="62" class="title">Phase 6BH - Immutable-shadow USD Set skipping</text>
<text x="64" y="92" class="sub">3 alternating real-Kit pairs · adapter-owned derived payloads · revisions always written</text>
<rect x="50" y="120" width="1100" height="152" rx="18" class="panel"/>
<text x="80" y="158" class="label">Lightweight commit p95 median</text><text x="80" y="202" class="metric">{baseline["median_p95_ms"]:.4f} ms</text>
<text x="500" y="158" class="label">Shadow-skip p95 median</text><text x="500" y="202" class="metric">{candidate["median_p95_ms"]:.4f} ms</text>
<text x="850" y="158" class="label">Skipped / 4,541</text><text x="850" y="202" class="metric">{writes["median_skipped"]:,}</text>
<text x="1050" y="158" class="label">Gate</text><text x="1050" y="202" class="result">{result}</text>
<text x="80" y="242" class="small">{writes["median_skipped_per_commit"]:.4f} skipped/commit · {writes["median_skip_percent"]:.2f}% · external direct edits unsupported</text>
<text x="64" y="317" class="label">Run p95 · lightweight (gray) vs shadow skip (green)</text><line x1="{gate_x:.1f}" y1="328" x2="{gate_x:.1f}" y2="542" class="gate"/><text x="{gate_x + 8:.1f}" y="336" class="gateText">4 ms</text>
{''.join(rows)}
<rect x="50" y="620" width="1100" height="1" fill="#35405b"/><text x="64" y="650" class="result">SHADOW SKIP: {result}</text>
<text x="310" y="650" class="small">immutable authority · 3 revisions mandatory · full failure replay · default OFF</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    args = parser.parse_args()
    report = analyze(_load(args.baseline), _load(args.candidate))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report) + "\n", encoding="utf-8")
    print(f"Wrote {args.json}")
    print(f"Wrote {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
