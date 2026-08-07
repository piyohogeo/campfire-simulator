"""Validate and visualize Phase 6BD transactional USD publication profiling."""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "resident_snapshot_transaction_profile_report.json"
DEFAULT_SVG = ASSETS / "resident_snapshot_transaction_profile_report.svg"
LOCAL_BUDGET_MS = 4.0


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _load(paths):
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _timing(summary, name):
    timing = summary["timing"]["segments"][name]
    _require(timing is not None, f"Missing timing segment: {name}")
    for field in ("mean_ms", "p95_ms", "max_ms"):
        value = float(timing[field])
        _require(math.isfinite(value) and value >= 0.0, f"Invalid {name}.{field}")
    return timing


def _aggregate_timings(timings):
    return {
        "run_count": len(timings),
        "sample_count_per_run": [item["sample_count"] for item in timings],
        "median_mean_ms": round(statistics.median(item["mean_ms"] for item in timings), 4),
        "median_p95_ms": round(statistics.median(item["p95_ms"] for item in timings), 4),
        "median_max_ms": round(statistics.median(item["max_ms"] for item in timings), 4),
        "run_p95_ms": [item["p95_ms"] for item in timings],
    }


def _authoritative_signature(summary):
    return (
        summary["wood"]["dry"]["authoritative_state_sha256"],
        summary["wood"]["wet"]["authoritative_state_sha256"],
        summary["metrics_csv_sha256"],
        summary["wood"]["dry"]["ignition_seconds"],
        summary["wood"]["wet"]["ignition_seconds"],
    )


def analyze(plain_runs, profile_runs):
    _require(len(plain_runs) == len(profile_runs) >= 3, "Need at least three paired runs")
    all_runs = plain_runs + profile_runs
    expected_signature = _authoritative_signature(all_runs[0])
    for index, summary in enumerate(all_runs, start=1):
        _require(
            summary.get("phase") == "phase3" and summary.get("status") == "ok",
            f"Run {index} is not a successful Phase 3 summary",
        )
        contract = summary["scenario"]["resident_snapshot_adapter"]
        status = contract["status_after_timeline_stop"]
        _require(contract["enabled"], f"Run {index} did not enable the adapter")
        _require(not contract["native_producer_connected"], "Native producer must remain disconnected")
        _require(
            not status["active"]
            and status["start_count"] == status["stop_count"] == 1
            and status["publish_count"] == 240
            and status["revision"] == 1200,
            f"Run {index} lifecycle/revision contract failed",
        )
        _require(contract["final_usd_state"]["revision_consistent"], "Consumer revisions diverged")
        _require(_authoritative_signature(summary) == expected_signature, "Authoritative output changed")
        _require(summary["flow"]["active_blocks_peak"] > 0, "Flow was not active")

    for summary in plain_runs:
        contract = summary["scenario"]["resident_snapshot_adapter"]
        _require(not contract["transaction_timing_enabled"], "Plain run enabled profiling")
        _require(contract["transaction_profile"] is None, "Plain run emitted detailed timings")
    profiles = []
    for summary in profile_runs:
        contract = summary["scenario"]["resident_snapshot_adapter"]
        _require(contract["transaction_timing_enabled"], "Profile run omitted profiling")
        profile = contract["transaction_profile"]
        _require(profile["sample_count"] == 236, "Unexpected profiled sample count")
        _require(
            profile["status_counts"] == {"committed": 240, "rolled_back": 0},
            "A profiled transaction did not commit",
        )
        for count_name, expected in (
            ("write_count", 19),
            ("existing_property_count", 19),
            ("created_property_count", 0),
            ("authored_old_value_count", 19),
        ):
            observed = profile["counts"][count_name]
            _require(
                observed["minimum"] == observed["maximum"] == expected,
                f"Unexpected {count_name}: {observed}",
            )
        profiles.append(profile)

    plain_integrated = _aggregate_timings(
        [_timing(summary, "resident_snapshot_usd") for summary in plain_runs]
    )
    plain_build = _aggregate_timings(
        [_timing(summary, "resident_snapshot_build") for summary in plain_runs]
    )
    plain_transaction = _aggregate_timings(
        [_timing(summary, "resident_snapshot_transaction") for summary in plain_runs]
    )
    profiled_transaction = _aggregate_timings(
        [_timing(summary, "resident_snapshot_transaction") for summary in profile_runs]
    )
    operation_names = tuple(profiles[0]["operations"])
    operation_timings = {
        name: _aggregate_timings([profile["operations"][name] for profile in profiles])
        for name in operation_names
    }
    group_timings = {
        name: _aggregate_timings([profile["groups"][name] for profile in profiles])
        for name in profiles[0]["groups"]
    }
    attribute_timings = {
        name: _aggregate_timings([profile["attributes"][name] for profile in profiles])
        for name in profiles[0]["attributes"]
    }
    total_mean = operation_timings["total_ms"]["median_mean_ms"]
    ranked_operations = sorted(
        (
            {
                "name": name,
                "median_mean_ms": timing["median_mean_ms"],
                "share_of_profiled_total": round(
                    timing["median_mean_ms"] / total_mean, 4
                ) if total_mean else 0.0,
            }
            for name, timing in operation_timings.items()
            if name not in {"total_ms", "rollback_ms"}
        ),
        key=lambda item: item["median_mean_ms"],
        reverse=True,
    )
    within_budget = plain_transaction["median_p95_ms"] < LOCAL_BUDGET_MS
    return {
        "schema_version": 1,
        "phase": "phase6bd",
        "status": "ok",
        "measurement": {
            "hardware": "NVIDIA GeForce RTX 3090 / D3D12",
            "scenario": "Phase 3 dry/wet logs, 1200 steps, 240 model seconds",
            "paired_run_count": len(plain_runs),
            "measured_updates_per_run": 236,
            "writes_per_transaction": 19,
            "profiling_default_enabled": False,
        },
        "contracts": {
            "all_transactions_committed": True,
            "revision_and_lifecycle_preserved": True,
            "authoritative_outputs_exact_across_runs": True,
            "native_producer_connected": False,
        },
        "boundary_timing_ms": {
            "plain_integrated_snapshot_build_and_transaction": plain_integrated,
            "plain_snapshot_build": plain_build,
            "plain_adapter_transaction": plain_transaction,
            "profiled_adapter_transaction": profiled_transaction,
        },
        "profiled_operations_ms": operation_timings,
        "profiled_groups_ms": group_timings,
        "profiled_attributes_ms": attribute_timings,
        "ranked_operation_cost": ranked_operations,
        "decision": {
            "transaction_p95_below_4ms": within_budget,
            "production_optimization_adopted": False,
            "keep_profiling_default_disabled": True,
            "profiling_p95_overhead_ms": round(
                profiled_transaction["median_p95_ms"] - plain_transaction["median_p95_ms"],
                4,
            ),
            "reason": (
                "This phase separates snapshot construction from the USD transaction and "
                "measures lookup, rollback-journal capture, Set, and commit costs. It does "
                "not alter publication semantics or connect the native producer."
            ),
            "next_gate": (
                "Optimize the largest measured USD transaction component while preserving "
                "full rollback, immutable snapshots, monotonic revisions, and lifecycle rules."
            ),
        },
    }


def _svg(report):
    boundary = report["boundary_timing_ms"]
    transaction = boundary["plain_adapter_transaction"]["median_p95_ms"]
    integrated = boundary["plain_integrated_snapshot_build_and_transaction"]["median_p95_ms"]
    build = boundary["plain_snapshot_build"]["median_p95_ms"]
    operations = report["ranked_operation_cost"][:6]
    max_value = max(item["median_mean_ms"] for item in operations) or 1.0
    bars = []
    for index, item in enumerate(operations):
        y = 316 + index * 46
        width = 330.0 * item["median_mean_ms"] / max_value
        label = html.escape(item["name"].replace("_ms", "").replace("_", " "))
        bars.append(
            f'<text x="84" y="{y + 18}" class="small">{label}</text>'
            f'<rect x="292" y="{y}" width="{width:.1f}" height="25" rx="12" class="bar"/>'
            f'<text x="{308 + width:.1f}" y="{y + 18}" class="value">{item["median_mean_ms"]:.4f} ms</text>'
        )
    result = "PASS" if report["decision"]["transaction_p95_below_4ms"] else "HOLD"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<style>
 .bg{{fill:#0d1222}} .panel{{fill:#171f34}} .title{{fill:#f5f7ff;font:700 30px system-ui,sans-serif}}
 .sub{{fill:#a9b4cc;font:16px system-ui,sans-serif}} .label{{fill:#edf1ff;font:600 17px system-ui,sans-serif}}
 .value{{fill:#fff;font:700 14px ui-monospace,monospace}} .small{{fill:#b8c2d9;font:14px system-ui,sans-serif}}
 .metric{{fill:#ff8a4c;font:700 28px ui-monospace,monospace}} .bar{{fill:#4f9cf9}}
 .gate{{fill:#ffd166;font:700 18px system-ui,sans-serif}} .ok{{fill:#2dc887}}
</style>
<rect width="1200" height="680" class="bg"/><text x="64" y="62" class="title">Phase 6BD - Transactional USD cost profile</text>
<text x="64" y="92" class="sub">3 paired real-Kit runs · detail timing opt-in/default OFF · 19 writes per immutable revision</text>
<rect x="50" y="120" width="1100" height="148" rx="18" class="panel"/>
<text x="80" y="158" class="label">Previous “snapshot USD” boundary</text><text x="80" y="201" class="metric">{integrated:.4f} ms p95</text>
<text x="430" y="158" class="label">Snapshot construction</text><text x="430" y="201" class="metric">{build:.4f} ms p95</text>
<text x="760" y="158" class="label">Adapter transaction</text><text x="760" y="201" class="metric">{transaction:.4f} ms p95</text>
<text x="80" y="240" class="small">The historical boundary included construction. The 4 ms gate now applies to the isolated adapter transaction.</text>
<text x="64" y="302" class="label">Profiled operation mean (instrumented runs)</text>{''.join(bars)}
<rect x="790" y="316" width="330" height="226" rx="16" class="panel"/>
<text x="820" y="355" class="label">Contracts held</text><text x="820" y="391" class="small">240 commits / 0 rollback</text>
<text x="820" y="423" class="small">revision 1200 on all consumers</text><text x="820" y="455" class="small">authority hashes + CSV exact</text>
<text x="820" y="487" class="small">native producer still disconnected</text><text x="820" y="522" class="gate">4 ms transaction gate: {result}</text>
<rect x="50" y="620" width="1100" height="1" fill="#35405b"/><text x="64" y="650" class="ok">MEASUREMENT COMPLETE</text>
<text x="330" y="650" class="small">next: optimize the measured dominant component without weakening rollback</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plain", nargs="+", required=True, type=Path)
    parser.add_argument("--profile", nargs="+", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(_load(arguments.plain), _load(arguments.profile))
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
