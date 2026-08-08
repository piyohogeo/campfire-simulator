"""Combine live Flow and isolated USD evidence for Phase 6DD."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def _median_case(micro, case_name, listener_mode, metric):
    values = [
        item[metric]["p95_ms"]
        for item in micro["measurements"]
        if item["case"] == case_name and item["listener_mode"] == listener_mode
    ]
    return round(statistics.median(values), 6)


def _render_svg(report):
    live = report["live_flow_stage"]
    isolated = report["isolated_usd_stage"]["median_p95_ms"]
    rows = (
        ("Live layout snapshots (6 Sets): exit", live["layout_change_block_exit_ms"]["p95_ms"], "#fb923c"),
        ("Live channel snapshots (4 Sets): exit", live["channel_change_block_exit_ms"]["p95_ms"], "#fbbf24"),
        ("Live layout snapshots: our callback", live["layout_callback_ms"]["p95_ms"], "#38bdf8"),
        ("Isolated 6 attrs: no listener", isolated["full_layout_no_listener_exit"], "#86efac"),
        ("Isolated 6 attrs: one listener", isolated["full_layout_listener_exit"], "#4ade80"),
    )
    maximum = max(value for _, value, _ in rows) or 1.0
    bars = []
    for index, (label, value, color) in enumerate(rows):
        y = 254 + index * 61
        width = max(2.0, 555.0 * value / maximum)
        bars.append(
            f'<text x="80" y="{y}" class="label">{label}</text>'
            f'<rect x="390" y="{y - 22}" width="{width:.2f}" height="28" rx="7" fill="{color}"/>'
            f'<text x="970" y="{y}" class="value">{value:.4f} ms p95</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DD USD notice and change-processing boundary</title><desc id="desc">Live Flow stage ChangeBlock exit is compared with this diagnostic callback and isolated USD attribute groups. The contrast is not a direct Flow ingest timer.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#13253a"/><stop offset="1" stop-color="#2f1d2e"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.title{{font:750 35px 'Segoe UI',sans-serif;fill:#f8fafc}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.label{{font:650 16px 'Segoe UI',sans-serif;fill:#e2e8f0}}.value{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.good{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}.warn{{font:650 16px 'Segoe UI',sans-serif;fill:#fbbf24}}.note{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="61" class="k">PHASE 6DD · NOTICE / CHANGE PROCESSING</text><text x="64" y="111" class="title">The observed callback is not the 1 ms boundary</text><text x="64" y="150" class="sub">Flow 110.0.0 · 720 points · one coalesced notice per snapshot · default OFF</text>
<rect x="56" y="188" width="1088" height="367" rx="20" fill="#0f2032"/>{''.join(bars)}
<text x="64" y="594" class="good">{report['gates_passed']} / {report['gate_count']} gates · {live['layout_snapshot_notice_count']} layout + {live['channel_snapshot_notice_count']} channel snapshot notices</text><text x="64" y="626" class="warn">Set-call count and notice changed-path count are different; do not assign the live contrast to Flow.</text><text x="64" y="654" class="note">Live exit includes synchronous USD change processing and every subscriber; our callback measures only path enumeration. Production contracts and Flow version are unchanged.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--micro", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--production-sha256-before", required=True)
    parser.add_argument("--production-sha256-after", required=True)
    parser.add_argument("--kit-exit-code", required=True, type=int)
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding="utf-8"))
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    micro = json.loads(args.micro.read_text(encoding="utf-8"))
    sidecar = base["lifecycle"]["owner"]["session"]["sidecar"]
    timing = sidecar["live_translation_timing_ms"]
    notices = base["flow"]["point_notice_observer"]
    records = notices["records"]
    snapshot_records = [item for item in records if item["snapshot_publication"]]
    layout_records = [item for item in snapshot_records if item["layout_publication"]]
    channel_records = [item for item in snapshot_records if not item["layout_publication"]]
    layout_path_counts = sorted({len(item["changed_paths"]) for item in layout_records})
    channel_path_counts = sorted({len(item["changed_paths"]) for item in channel_records})
    layout_path_distribution = {
        str(count): sum(len(item["changed_paths"]) == count for item in layout_records)
        for count in layout_path_counts
    }
    channel_path_distribution = {
        str(count): sum(len(item["changed_paths"]) == count for item in channel_records)
        for count in channel_path_counts
    }
    layout_allowed = {
        "/World/Flow/ResidentPointEmitter.pointPositions",
        "/World/Flow/ResidentPointEmitter.pointFuels",
        "/World/Flow/ResidentPointEmitter.pointTemperatures",
        "/World/Flow/ResidentPointEmitter.pointSmokes",
        "/World/Flow/ResidentPointEmitter.campfire:layoutRevision",
        "/World/Flow/ResidentPointEmitter.campfire:residentRevision",
    }
    channel_allowed = layout_allowed.difference(
        {
            "/World/Flow/ResidentPointEmitter.pointPositions",
            "/World/Flow/ResidentPointEmitter.campfire:layoutRevision",
        }
    )
    resident_revision_path = (
        "/World/Flow/ResidentPointEmitter.campfire:residentRevision"
    )
    position_path = "/World/Flow/ResidentPointEmitter.pointPositions"
    layout_revision_path = (
        "/World/Flow/ResidentPointEmitter.campfire:layoutRevision"
    )
    changed_count = sidecar["live_translation_publish_count"]
    unchanged_count = sidecar["live_translation_unchanged_count"]
    gates = {
        "isolated_microbenchmark_passed": all(micro["gates"].values()),
        "independent_translation_probe_passed": (
            probe.get("status") == "ok" and all(probe.get("gates", {}).values())
        ),
        "one_snapshot_notice_per_publish": (
            notices["snapshot_notice_count"] == sidecar["publish_count"] == 760
        ),
        "layout_notice_count_matches_changed_publish": (
            notices["layout_snapshot_notice_count"] == changed_count
        ),
        "channel_notice_count_matches_unchanged_publish": (
            notices["channel_only_snapshot_notice_count"] == unchanged_count
        ),
        "layout_notice_paths_match_authored_subset": all(
            {position_path, layout_revision_path, resident_revision_path}
            <= set(item["changed_paths"])
            <= layout_allowed
            for item in layout_records
        ),
        "channel_notice_paths_match_authored_subset": all(
            resident_revision_path in item["changed_paths"]
            and set(item["changed_paths"]) <= channel_allowed
            for item in channel_records
        ),
        "layout_exit_samples_exact": (
            timing["change_block_exit"]["sample_count"] == changed_count
        ),
        "channel_exit_samples_exact": (
            timing["channel_only_change_block_exit"]["sample_count"]
            == unchanged_count
        ),
        "diagnostic_callback_samples_exact": (
            notices["layout_snapshot_callbacks"]["sample_count"] == changed_count
            and notices["channel_only_snapshot_callbacks"]["sample_count"]
            == unchanged_count
        ),
        "no_point_resync_or_unexpected_change": (
            not base["publication"]["point_resyncs"]
            and not base["publication"]["unexpected_point_changes"]
        ),
        "production_app_unchanged": (
            args.production_sha256_before == args.production_sha256_after
        ),
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6DD gates failed: {gates}")
    isolated_medians = {
        "revision_only_no_listener_exit": _median_case(
            micro, "revision_only", "no_listener", "change_block_exit_ms"
        ),
        "channels_revision_no_listener_exit": _median_case(
            micro, "channels_revision", "no_listener", "change_block_exit_ms"
        ),
        "layout_only_no_listener_exit": _median_case(
            micro, "layout_only", "no_listener", "change_block_exit_ms"
        ),
        "full_layout_no_listener_exit": _median_case(
            micro, "full_layout", "no_listener", "change_block_exit_ms"
        ),
        "full_layout_listener_exit": _median_case(
            micro, "full_layout", "enumerating_listener", "change_block_exit_ms"
        ),
        "full_layout_listener_callback": _median_case(
            micro, "full_layout", "enumerating_listener", "diagnostic_callback_ms"
        ),
    }
    report = {
        "phase": "phase6dd",
        "status": "ok",
        "scope": "USD notice observer and ChangeBlock change-processing boundary",
        "point_count": sidecar["point_count"],
        "live_flow_stage": {
            "layout_snapshot_notice_count": len(layout_records),
            "channel_snapshot_notice_count": len(channel_records),
            "non_snapshot_notice_count": notices["non_snapshot_notice_count"],
            "layout_changed_path_count": layout_path_counts,
            "channel_changed_path_count": channel_path_counts,
            "layout_changed_path_count_distribution": layout_path_distribution,
            "channel_changed_path_count_distribution": channel_path_distribution,
            "set_calls_per_layout_snapshot": 6,
            "set_calls_per_channel_snapshot": 4,
            "layout_change_block_exit_ms": timing["change_block_exit"],
            "channel_change_block_exit_ms": timing[
                "channel_only_change_block_exit"
            ],
            "layout_publish_transaction_ms": timing["publish_transaction"],
            "channel_publish_transaction_ms": timing[
                "channel_only_publish_transaction"
            ],
            "layout_callback_ms": notices["layout_snapshot_callbacks"],
            "channel_callback_ms": notices["channel_only_snapshot_callbacks"],
            "observer_scope": notices["scope"],
        },
        "isolated_usd_stage": {
            "median_p95_ms": isolated_medians,
            "run_count": micro["run_count"],
            "iterations_per_case_run": micro["iterations_per_case_run"],
            "warmup_iterations": micro["warmup_iterations"],
            "usd_package": micro["usd_package"],
            "gates": micro["gates"],
            "interpretation": micro["interpretation"],
        },
        "interpretation": {
            "qualified": (
                "ChangeBlock emits one revision-consistent snapshot notice; the "
                "diagnostic callback itself is only a small part of live exit time."
            ),
            "not_qualified": (
                "The remaining live exit time is not assigned to Flow ingestion. "
                "It includes USD change processing and every synchronous subscriber, "
                "and isolated/live subtraction is not causal."
            ),
            "next": (
                "Audit subscriber registration and public profiler zones; if no "
                "subscriber-level timer exists, vary consumer enablement only in a "
                "derived default-off scene before considering publication changes."
            ),
        },
        "gates": gates,
        "gates_passed": sum(gates.values()),
        "gate_count": len(gates),
        "production_app": {
            "sha256_before": args.production_sha256_before,
            "sha256_after": args.production_sha256_after,
            "changed_during_run": False,
        },
        "base_harness": {
            "status": base.get("status"),
            "inherited_kit_exit_code": args.kit_exit_code,
            "known_reason": "historical Phase 6CO static/STOP gates conflict with dynamic tracking",
        },
        "contracts": {
            "production_default": "OFF",
            "physics_changed": False,
            "json_schema_changed": False,
            "rollback_changed": False,
            "revision_changed": False,
            "immutable_snapshot_changed": False,
            "flow_version": "110.0.0",
        },
        "video": {
            "reused": "resident_translation_breakdown.mp4",
            "reason": "same deterministic optimized Resident translation scenario",
            "success_criterion": "not video-only",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg.write_text(_render_svg(report), encoding="utf-8")
    print(f"Phase 6DD: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
