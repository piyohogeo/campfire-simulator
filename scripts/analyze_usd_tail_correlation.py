"""Analyze Phase 6BK lightweight USD tail-correlation runs."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "usd_tail_correlation_report.json"
)
DEFAULT_SVG = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "usd_tail_correlation_report.svg"
)


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _p95(values):
    ordered = sorted(float(value) for value in values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def _correlation(left, right):
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right)
    )
    left_energy = sum((value - left_mean) ** 2 for value in left)
    right_energy = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_energy * right_energy)
    return numerator / denominator if denominator else 0.0


def _timing(summary, name):
    return summary["timing"]["segments"][name]["p95_ms"]


def _equivalent(control, profiled):
    checks = {
        "dry_authoritative_sha256": (
            control["wood"]["dry"]["authoritative_state_sha256"]
            == profiled["wood"]["dry"]["authoritative_state_sha256"]
        ),
        "wet_authoritative_sha256": (
            control["wood"]["wet"]["authoritative_state_sha256"]
            == profiled["wood"]["wet"]["authoritative_state_sha256"]
        ),
        "metrics_csv_sha256": (
            control["metrics_csv_sha256"] == profiled["metrics_csv_sha256"]
        ),
        "ignition": (
            control["wood"]["dry"]["ignition_seconds"]
            == profiled["wood"]["dry"]["ignition_seconds"]
            and control["wood"]["wet"]["ignition_seconds"]
            == profiled["wood"]["wet"]["ignition_seconds"]
        ),
        "final_usd_state": (
            control["scenario"]["resident_snapshot_adapter"]["final_usd_state"]
            == profiled["scenario"]["resident_snapshot_adapter"]["final_usd_state"]
        ),
    }
    _require(all(checks.values()), "Profiler changed authoritative output")
    return checks


def _run_correlation(profile):
    samples = profile["samples"]
    outer = [sample["outer_transaction_ms"] for sample in samples]
    flow = [sample["flow_render_update_ms"] for sample in samples]
    profile_total = [sample["profile_total_ms"] for sample in samples]
    writes = [sample["write_count"] for sample in samples]
    attribute_set = [
        sample["operations_ms"]["attribute_set_ms"] for sample in samples
    ]
    attribute_set_per_write = [
        set_ms / write_count
        for set_ms, write_count in zip(attribute_set, writes)
    ]
    active_blocks = [sample["active_block_count"] for sample in samples]
    operation_names = tuple(samples[0]["operations_ms"])
    group_names = tuple(
        sorted({name for sample in samples for name in sample["groups_ms"]})
    )
    slowest = sorted(
        samples, key=lambda sample: sample["outer_transaction_ms"], reverse=True
    )[:5]
    return {
        "sample_count": len(samples),
        "outer_transaction_p95_ms": _p95(outer),
        "profile_total_p95_ms": _p95(profile_total),
        "attribute_set_p95_share": _p95(attribute_set) / _p95(profile_total),
        "attribute_set_per_write_median_ms": statistics.median(
            attribute_set_per_write
        ),
        "flow_render_update_p95_ms": _p95(flow),
        "profile_coverage_ratio_median": statistics.median(
            profile_value / outer_value
            for profile_value, outer_value in zip(profile_total, outer)
            if outer_value > 0.0
        ),
        "correlation": {
            "profile_total_vs_outer_transaction": _correlation(
                profile_total, outer
            ),
            "flow_render_update_vs_outer_transaction": _correlation(flow, outer),
            "write_count_vs_outer_transaction": _correlation(writes, outer),
            "attribute_set_per_write_vs_outer_transaction": _correlation(
                attribute_set_per_write, outer
            ),
            "active_blocks_vs_outer_transaction": _correlation(
                active_blocks, outer
            ),
            "operations_vs_outer_transaction": {
                name: _correlation(
                    [sample["operations_ms"][name] for sample in samples], outer
                )
                for name in operation_names
            },
            "groups_vs_outer_transaction": {
                name: _correlation(
                    [sample["groups_ms"].get(name, 0.0) for sample in samples],
                    outer,
                )
                for name in group_names
            },
        },
        "operation_p95_ms": {
            name: _p95(
                [sample["operations_ms"][name] for sample in samples]
            )
            for name in operation_names
        },
        "group_p95_ms": {
            name: _p95(
                [sample["groups_ms"].get(name, 0.0) for sample in samples]
            )
            for name in group_names
        },
        "slowest_samples": slowest,
    }


def analyze(run_root, run_count):
    pairs = []
    for index in range(1, run_count + 1):
        control = _load(run_root / f"control-{index:02d}" / "summary.json")
        profiled = _load(run_root / f"profiled-{index:02d}" / "summary.json")
        for summary in (control, profiled):
            _require(summary["status"] == "ok", "Phase 3 run failed")
            adapter = summary["scenario"]["resident_snapshot_adapter"]
            _require(adapter["native_producer_connected"], "Native producer missing")
            _require(
                adapter["status_after_timeline_stop"]["revision"] == 1200,
                "Resident revision mismatch",
            )
            _require(
                adapter["final_usd_state"]["revision_consistent"],
                "USD revisions are inconsistent",
            )
        control_adapter = control["scenario"]["resident_snapshot_adapter"]
        profiled_adapter = profiled["scenario"]["resident_snapshot_adapter"]
        _require(
            not control_adapter["lightweight_tail_timing_enabled"]
            and control_adapter["lightweight_tail_profile"] is None,
            "Control unexpectedly enabled tail profiling",
        )
        _require(
            profiled_adapter["lightweight_tail_timing_enabled"],
            "Profiled run did not enable tail profiling",
        )
        tail_profile = profiled_adapter["lightweight_tail_profile"]
        _require(tail_profile["sample_count"] == 236, "Tail sample count mismatch")
        _require(
            tail_profile["status_counts"] == {
                "committed": 239,
                "recovered": 0,
                "faulted": 0,
            },
            "Unexpected lightweight publication status",
        )
        equivalence = _equivalent(control, profiled)
        pairs.append(
            {
                "pair": index,
                "order": (
                    ["control", "profiled"]
                    if index % 2
                    else ["profiled", "control"]
                ),
                "equivalence": equivalence,
                "control": {
                    "usd_transaction_p95_ms": _timing(
                        control, "resident_snapshot_transaction"
                    ),
                    "flow_render_update_p95_ms": _timing(
                        control, "kit_flow_render_update"
                    ),
                },
                "profiled": {
                    "usd_transaction_p95_ms": _timing(
                        profiled, "resident_snapshot_transaction"
                    ),
                    "flow_render_update_p95_ms": _timing(
                        profiled, "kit_flow_render_update"
                    ),
                    "tail": _run_correlation(tail_profile),
                },
            }
        )

    control_p95 = [pair["control"]["usd_transaction_p95_ms"] for pair in pairs]
    profiled_p95 = [pair["profiled"]["usd_transaction_p95_ms"] for pair in pairs]
    correlations = {
        name: [
            pair["profiled"]["tail"]["correlation"][name] for pair in pairs
        ]
        for name in (
            "profile_total_vs_outer_transaction",
            "flow_render_update_vs_outer_transaction",
            "write_count_vs_outer_transaction",
            "attribute_set_per_write_vs_outer_transaction",
            "active_blocks_vs_outer_transaction",
        )
    }
    operation_names = tuple(
        pairs[0]["profiled"]["tail"]["correlation"][
            "operations_vs_outer_transaction"
        ]
    )
    group_names = tuple(
        pairs[0]["profiled"]["tail"]["correlation"][
            "groups_vs_outer_transaction"
        ]
    )
    return {
        "schema_version": 1,
        "phase": "phase6bk",
        "status": "characterized",
        "measurement": {
            "pairs": run_count,
            "balanced_order": True,
            "steps_per_run": 1200,
            "published_revisions_per_run": 240,
            "profiled_lightweight_revisions_per_run": 239,
            "analyzed_samples_per_run": 236,
            "production_default_enabled": False,
            "additional_usd_get_calls": 0,
        },
        "equivalence": {
            "all_pairs_exact": all(
                all(pair["equivalence"].values()) for pair in pairs
            )
        },
        "overhead": {
            "control_usd_p95_ms": control_p95,
            "profiled_usd_p95_ms": profiled_p95,
            "median_p95_delta_ms": (
                statistics.median(profiled_p95) - statistics.median(control_p95)
            ),
        },
        "correlation_median": {
            name: statistics.median(values)
            for name, values in correlations.items()
        },
        "attribution": {
            "attribute_set_p95_share": [
                pair["profiled"]["tail"]["attribute_set_p95_share"]
                for pair in pairs
            ],
            "median_attribute_set_p95_share": statistics.median(
                pair["profiled"]["tail"]["attribute_set_p95_share"]
                for pair in pairs
            ),
            "attribute_set_per_write_median_ms": [
                pair["profiled"]["tail"][
                    "attribute_set_per_write_median_ms"
                ]
                for pair in pairs
            ],
        },
        "operation_correlation_median": {
            name: statistics.median(
                pair["profiled"]["tail"]["correlation"][
                    "operations_vs_outer_transaction"
                ][name]
                for pair in pairs
            )
            for name in operation_names
        },
        "group_correlation_median": {
            name: statistics.median(
                pair["profiled"]["tail"]["correlation"][
                    "groups_vs_outer_transaction"
                ][name]
                for pair in pairs
            )
            for name in group_names
        },
        "pairs": pairs,
        "decision": {
            "production_default_changed": False,
            "rollback_changed": False,
            "revision_last_changed": False,
            "next_step": (
                "Use the measured tail attribution to choose the smallest default-off "
                "USD notification or publication-boundary experiment."
            ),
        },
    }


def render_svg(report):
    overhead = report["overhead"]
    correlation = report["correlation_median"]
    control = " / ".join(f"{value:.3f}" for value in overhead["control_usd_p95_ms"])
    profiled = " / ".join(
        f"{value:.3f}" for value in overhead["profiled_usd_p95_ms"]
    )
    group = max(
        report["group_correlation_median"],
        key=lambda name: abs(report["group_correlation_median"][name]),
    )
    group_value = report["group_correlation_median"][group]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BK USD tail correlation</title>
  <desc id="desc">Balanced real-Kit runs classify lightweight USD publication tails without adding USD reads.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="76" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">PHASE 6BK · LIGHTWEIGHT USD TAIL TRACE</text>
  <text x="70" y="126" fill="#fff" font-family="Segoe UI, sans-serif" font-size="37" font-weight="700">Measure the tail without restoring old-value reads</text>
  <rect x="70" y="170" width="1060" height="105" rx="20" fill="#192734" stroke="#315269"/>
  <text x="105" y="214" fill="#8fbcd4" font-family="Consolas, monospace" font-size="18">validate → handles → payload → Set → revision-last</text>
  <text x="105" y="250" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="17">3 balanced control/profile pairs · no extra UsdAttribute.Get · defaults remain OFF</text>
  <rect x="70" y="315" width="510" height="182" rx="20" fill="#182128"/>
  <text x="105" y="360" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">External USD transaction p95</text>
  <text x="105" y="405" fill="#a8beca" font-family="Consolas, monospace" font-size="18">control   {control} ms</text>
  <text x="105" y="445" fill="#f4b860" font-family="Consolas, monospace" font-size="18">profiled  {profiled} ms</text>
  <rect x="620" y="315" width="510" height="182" rx="20" fill="#182128"/>
  <text x="655" y="360" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Median correlations with USD tail</text>
  <text x="655" y="405" fill="#f4b860" font-family="Consolas, monospace" font-size="18">Flow/render  r={correlation['flow_render_update_vs_outer_transaction']:+.3f}</text>
  <text x="655" y="441" fill="#a8beca" font-family="Consolas, monospace" font-size="18">Set / write  r={correlation['attribute_set_per_write_vs_outer_transaction']:+.3f}</text>
  <text x="655" y="477" fill="#a8beca" font-family="Consolas, monospace" font-size="18">top group {group}  r={group_value:+.3f}</text>
  <rect x="70" y="540" width="1060" height="86" rx="20" fill="#203126" stroke="#65c18c"/>
  <text x="105" y="592" fill="#65c18c" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">CHARACTERIZED · CONTRACT UNCHANGED</text>
  <text x="660" y="580" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">state SHA · CSV · final USD exact</text>
  <text x="660" y="607" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">rollback · revision-last · production OFF</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(arguments.run_root, arguments.runs)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
