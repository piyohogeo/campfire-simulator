"""Validate and visualize Phase 6BE redundant USD Set auditing."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "resident_write_audit_report.json"
DEFAULT_SVG = ASSETS / "resident_write_audit_report.svg"
EXPECTED_WRITES = 19
EXPECTED_SAMPLES = 236


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


def _aggregate_timing(timings):
    if not timings:
        return None
    return {
        "run_count": len(timings),
        "sample_count": sum(item["sample_count"] for item in timings),
        "total_ms": round(sum(item["total_ms"] for item in timings), 4),
        "weighted_mean_ms": round(
            sum(item["total_ms"] for item in timings)
            / sum(item["sample_count"] for item in timings),
            4,
        ),
        "median_run_p95_ms": round(
            statistics.median(item["p95_ms"] for item in timings), 4
        ),
        "maximum_ms": round(max(item["max_ms"] for item in timings), 4),
    }


def analyze(summaries):
    _require(len(summaries) >= 3, "Need at least three audit runs")
    expected_signature = _signature(summaries[0])
    profiles = []
    for index, summary in enumerate(summaries, start=1):
        _require(
            summary.get("phase") == "phase3" and summary.get("status") == "ok",
            f"Run {index} is not a successful Phase 3 summary",
        )
        contract = summary["scenario"]["resident_snapshot_adapter"]
        status = contract["status_after_timeline_stop"]
        profile = contract["transaction_profile"]
        _require(contract["enabled"] and contract["transaction_timing_enabled"], "Audit disabled")
        _require(not contract["native_producer_connected"], "Native producer must remain disconnected")
        _require(
            not status["active"]
            and status["publish_count"] == 240
            and status["revision"] == 1200
            and status["start_count"] == status["stop_count"] == 1,
            f"Run {index} lifecycle failed",
        )
        _require(contract["final_usd_state"]["revision_consistent"], "Consumer revision mismatch")
        _require(_signature(summary) == expected_signature, "Authoritative output changed")
        _require(summary["flow"]["active_blocks_peak"] > 0, "Flow was not active")
        _require(profile["sample_count"] == EXPECTED_SAMPLES, "Unexpected sample count")
        _require(profile["status_counts"] == {"committed": 240, "rolled_back": 0}, "Commit failed")
        counts = profile["counts"]
        _require(counts["write_count"] == {"minimum": 19, "maximum": 19}, "Write count changed")
        _require(
            counts["changed_write_count"]["minimum"]
            + counts["unchanged_write_count"]["maximum"]
            <= EXPECTED_WRITES,
            "Invalid disposition bounds",
        )
        disposition = profile["write_disposition"]
        _require(
            disposition["changed"] + disposition["unchanged"]
            == EXPECTED_SAMPLES * EXPECTED_WRITES,
            "Disposition total does not cover every write",
        )
        profiles.append(profile)

    transaction_count = len(profiles) * EXPECTED_SAMPLES
    attribute_names = tuple(profiles[0]["write_disposition"]["attributes"])
    attribute_rows = []
    for name in attribute_names:
        changed = sum(
            profile["write_disposition"]["attributes"][name]["changed"]
            for profile in profiles
        )
        unchanged = sum(
            profile["write_disposition"]["attributes"][name]["unchanged"]
            for profile in profiles
        )
        _require(changed + unchanged == transaction_count, f"Incomplete {name} audit")
        changed_set = _aggregate_timing(
            [
                profile["attribute_set_disposition"][name]["changed"]
                for profile in profiles
                if profile["attribute_set_disposition"][name]["changed"] is not None
            ]
        )
        unchanged_set = _aggregate_timing(
            [
                profile["attribute_set_disposition"][name]["unchanged"]
                for profile in profiles
                if profile["attribute_set_disposition"][name]["unchanged"] is not None
            ]
        )
        attribute_rows.append(
            {
                "name": name,
                "changed": changed,
                "unchanged": unchanged,
                "unchanged_rate": round(unchanged / transaction_count, 6),
                "changed_set_timing_ms": changed_set,
                "unchanged_set_timing_ms": unchanged_set,
            }
        )
    attribute_rows.sort(
        key=lambda item: (
            item["unchanged_rate"],
            item["unchanged_set_timing_ms"]["total_ms"]
            if item["unchanged_set_timing_ms"]
            else 0.0,
        ),
        reverse=True,
    )

    group_names = tuple(profiles[0]["write_disposition"]["groups"])
    group_rows = {}
    for name in group_names:
        changed = sum(
            profile["write_disposition"]["groups"][name]["changed"]
            for profile in profiles
        )
        unchanged = sum(
            profile["write_disposition"]["groups"][name]["unchanged"]
            for profile in profiles
        )
        group_rows[name] = {
            "changed": changed,
            "unchanged": unchanged,
            "unchanged_rate": round(unchanged / (changed + unchanged), 6),
        }

    total_unchanged = sum(item["unchanged"] for item in attribute_rows)
    unchanged_set_total_ms = sum(
        item["unchanged_set_timing_ms"]["total_ms"]
        for item in attribute_rows
        if item["unchanged_set_timing_ms"]
    )
    required_revision_names = [
        item["name"] for item in attribute_rows if item["name"].endswith("residentRevision")
    ]
    _require(len(required_revision_names) == 3, "Expected three revision attributes")
    return {
        "schema_version": 1,
        "phase": "phase6be",
        "status": "ok",
        "measurement": {
            "hardware": "NVIDIA GeForce RTX 3090 / D3D12",
            "scenario": "Phase 3 dry/wet logs, 1200 steps, 240 model seconds",
            "run_count": len(profiles),
            "measured_transactions": transaction_count,
            "writes_per_transaction": EXPECTED_WRITES,
            "audited_writes": transaction_count * EXPECTED_WRITES,
            "audit_default_enabled": False,
        },
        "contracts": {
            "all_transactions_committed": True,
            "revision_and_lifecycle_preserved": True,
            "authoritative_outputs_exact_across_runs": True,
            "native_producer_connected": False,
        },
        "write_summary": {
            "changed": transaction_count * EXPECTED_WRITES - total_unchanged,
            "unchanged": total_unchanged,
            "unchanged_rate": round(
                total_unchanged / (transaction_count * EXPECTED_WRITES), 6
            ),
            "unchanged_writes_per_transaction": round(
                total_unchanged / transaction_count, 4
            ),
            "measured_unchanged_set_ms_per_transaction": round(
                unchanged_set_total_ms / transaction_count, 4
            ),
        },
        "groups": group_rows,
        "attributes": attribute_rows,
        "decision": {
            "optimization_adopted": False,
            "no_op_only_candidate_deferred": True,
            "revision_writes_remain_mandatory": required_revision_names,
            "candidate_rule": (
                "After reading the current authored value for rollback, omit journal and Set "
                "only when the USD-typed value is exactly unchanged; always publish revision."
            ),
            "consumer_event_semantics_require_audit": True,
            "p95_below_4ms_claimed": False,
            "reason": (
                "Although unchanged values account for many writes, their measured Set time "
                "is too small to close the current p95 gap by itself; skipping them also needs "
                "a consumer event-semantics contract."
            ),
            "next_gate": (
                "Prototype prim and attribute handle caching behind an opt-in flag while retaining "
                "actual old-value capture and rollback; combine exact no-op skipping only if needed."
            ),
        },
    }


def _short_name(name):
    return name.replace("campfire:", "").replace("Emitter.", "E.").replace("Log_00.", "D.").replace("Log_01.", "W.")


def _svg(report):
    rows = report["attributes"][:8]
    bars = []
    for index, item in enumerate(rows):
        y = 278 + index * 42
        width = 410.0 * item["unchanged_rate"]
        bars.append(
            f'<text x="76" y="{y + 17}" class="small">{html.escape(_short_name(item["name"]))}</text>'
            f'<rect x="310" y="{y}" width="{width:.1f}" height="24" rx="12" class="bar"/>'
            f'<text x="{326 + width:.1f}" y="{y + 17}" class="value">{item["unchanged_rate"] * 100:.1f}%</text>'
        )
    summary = report["write_summary"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<style>
 .bg{{fill:#0d1222}} .panel{{fill:#171f34}} .title{{fill:#f5f7ff;font:700 30px system-ui,sans-serif}}
 .sub{{fill:#a9b4cc;font:16px system-ui,sans-serif}} .label{{fill:#edf1ff;font:600 17px system-ui,sans-serif}}
 .metric{{fill:#ff8a4c;font:700 28px ui-monospace,monospace}} .small{{fill:#b8c2d9;font:14px system-ui,sans-serif}}
 .value{{fill:#fff;font:700 14px ui-monospace,monospace}} .bar{{fill:#4f9cf9}} .hold{{fill:#ffd166;font:700 18px system-ui,sans-serif}}
</style>
<rect width="1200" height="680" class="bg"/><text x="64" y="62" class="title">Phase 6BE - Redundant USD Set audit</text>
<text x="64" y="92" class="sub">3 real-Kit runs · 708 transactions · 13,452 writes · post-Set value audit opt-in/default OFF</text>
<rect x="50" y="120" width="1100" height="116" rx="18" class="panel"/>
<text x="80" y="157" class="label">Unchanged writes</text><text x="80" y="201" class="metric">{summary["unchanged_writes_per_transaction"]:.4f} / 19 per transaction</text>
<text x="600" y="157" class="label">Measured Set time on unchanged values</text><text x="600" y="201" class="metric">{summary["measured_unchanged_set_ms_per_transaction"]:.4f} ms mean</text>
<text x="64" y="265" class="label">Highest unchanged frequency by attribute</text>{''.join(bars)}
<rect x="840" y="278" width="300" height="258" rx="16" class="panel"/>
<text x="870" y="318" class="label">Safety boundary</text><text x="870" y="356" class="small">read actual authored old value</text>
<text x="870" y="387" class="small">skip journal + Set only if exact</text><text x="870" y="418" class="small">always Set 3 revision attributes</text>
<text x="870" y="449" class="small">rollback touched attributes only</text><text x="870" y="480" class="small">external edit test required</text>
<text x="870" y="518" class="hold">NO-OP ONLY: DEFERRED</text>
<rect x="50" y="620" width="1100" height="1" fill="#35405b"/><text x="64" y="650" class="small">next: opt-in prim / attribute handle cache · retain actual old-value rollback · alternating 3-pair p95 gate</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", nargs="+", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(_load(arguments.summary))
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
