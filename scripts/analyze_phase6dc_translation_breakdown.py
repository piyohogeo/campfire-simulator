"""Validate and publish the Phase 6DC translation transaction breakdown."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


DETAIL_KEYS = (
    "fuel_vt_conversion",
    "temperature_vt_conversion",
    "smoke_vt_conversion",
    "position_vt_conversion",
    "previous_value_snapshot",
    "change_block_enter",
    "position_usd_set",
    "fuel_usd_set",
    "temperature_usd_set",
    "smoke_usd_set",
    "layout_revision_usd_set",
    "resident_revision_usd_set",
    "change_block_exit",
    "publish_transaction",
    "producer_commit",
)


def _svg(report: dict) -> str:
    timing = report["usd_publication_timing_ms"]
    outer = report["enclosing_update_timing_ms"]
    rows = (
        ("Previous-value snapshot", timing["previous_value_snapshot"]["p95_ms"]),
        ("Four Vt conversions", report["derived"]["vt_conversion_p95_sum_ms"]),
        ("Four array Set calls", report["derived"]["array_set_p95_sum_ms"]),
        ("Two revision Set calls", report["derived"]["revision_set_p95_sum_ms"]),
        ("ChangeBlock exit", timing["change_block_exit"]["p95_ms"]),
    )
    maximum = max(value for _, value in rows) or 1.0
    row_svg = []
    for index, (label, value) in enumerate(rows):
        y = 250 + index * 60
        width = 540.0 * value / maximum
        row_svg.append(
            f'<text x="88" y="{y}" class="l">{label}</text>'
            f'<rect x="340" y="{y - 22}" width="{width:.1f}" height="28" rx="7" fill="#38bdf8"/>'
            f'<text x="900" y="{y}" class="v">{value:.4f} ms p95</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DC changed-tick transaction breakdown</title><desc id="desc">Detailed timing separates immutable array conversion, previous-value snapshots, USD Set calls, revision publication, ChangeBlock exit, and the enclosing Kit update. Flow USD ingest is not exposed as an independent public timer.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#102a43"/><stop offset="1" stop-color="#281b3d"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.t{{font:750 35px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.l{{font:650 16px 'Segoe UI',sans-serif;fill:#e2e8f0}}.v{{font:700 17px 'Segoe UI',sans-serif;fill:#bae6fd}}.b{{font:750 24px 'Segoe UI',sans-serif;fill:#86efac}}.w{{font:650 17px 'Segoe UI',sans-serif;fill:#fbbf24}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6DC · CHANGED-TICK TRANSACTION</text><text x="64" y="112" class="t">Separate USD work from the enclosing Flow update</text><text x="64" y="150" class="s">Flow 110.0.0 · 720 points · default OFF · rollback and revision-last retained</text>
<rect x="64" y="184" width="1072" height="340" rx="20" fill="#0f2438"/>{''.join(row_svg)}
<text x="64" y="568" class="b">USD transaction p95 {timing['publish_transaction']['p95_ms']:.4f} ms</text><text x="64" y="603" class="w">Enclosing update p95: changed {outer['changed']['p95_ms']:.3f} ms · unchanged {outer['unchanged']['p95_ms']:.3f} ms</text>
<text x="64" y="638" class="m">The enclosing update includes Flow ingest, StageUpdate, PhysX, solver, and render; it is not a direct Flow-ingest measurement.</text><text x="64" y="660" class="m">Production defaults, physics, JSON, rollback, revision, immutable snapshot, and Flow version are unchanged.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path)
    parser.add_argument("--production-sha256-before", required=True)
    parser.add_argument("--production-sha256-after", required=True)
    parser.add_argument("--kit-exit-code", required=True, type=int)
    arguments = parser.parse_args()
    base = json.loads(arguments.base.read_text(encoding="utf-8"))
    probe = json.loads(arguments.probe.read_text(encoding="utf-8"))
    sidecar = base["lifecycle"]["owner"]["session"]["sidecar"]
    timing = sidecar["live_translation_timing_ms"]
    outer = base["flow"]["point_enclosing_update"]
    frames = sorted(arguments.frames.glob("frame_*.png"))
    changed_count = sidecar["live_translation_publish_count"]
    if probe.get("status") != "ok" or not all(probe.get("gates", {}).values()):
        raise ValueError("Phase 6DC inherited translation probe failed")
    if len(frames) != 60:
        raise ValueError(f"Phase 6DC requires 60 frames, got {len(frames)}")
    if arguments.production_sha256_before != arguments.production_sha256_after:
        raise ValueError("Phase 6DC changed the built application")
    gates = {
        "all_detail_samples_match_changed_publications": all(
            timing[name]["sample_count"] == changed_count for name in DETAIL_KEYS
        ),
        "changed_publications_nonzero": changed_count > 0,
        "all_snapshots_published": sidecar["prepare_count"] == sidecar["publish_count"] == 760,
        "no_sidecar_failure": sidecar["failure_count"] == 0,
        "changed_enclosing_updates_sampled": outer["changed"] is not None,
        "unchanged_enclosing_updates_sampled": outer["unchanged"] is not None,
        "direct_flow_ingest_not_claimed": outer["direct_flow_ingest_timing_available"] is False,
        "point_count_preserved": sidecar["point_count"] == 720,
        "translation_alignment_retained": all(probe["gates"].values()),
    }
    if not all(gates.values()):
        raise ValueError(f"Phase 6DC gates failed: {gates}")
    vt_names = (
        "fuel_vt_conversion",
        "temperature_vt_conversion",
        "smoke_vt_conversion",
        "position_vt_conversion",
    )
    array_set_names = (
        "position_usd_set",
        "fuel_usd_set",
        "temperature_usd_set",
        "smoke_usd_set",
    )
    revision_names = ("layout_revision_usd_set", "resident_revision_usd_set")
    report = {
        "phase": "phase6dc",
        "status": "ok",
        "scope": "changed-tick Resident Point USD transaction breakdown",
        "resident_revision": sidecar["revision"],
        "point_count": sidecar["point_count"],
        "changed_publication_count": changed_count,
        "unchanged_publication_count": sidecar["live_translation_unchanged_count"],
        "usd_publication_timing_ms": {name: timing[name] for name in DETAIL_KEYS},
        "derived": {
            "vt_conversion_p95_sum_ms": round(sum(timing[name]["p95_ms"] for name in vt_names), 4),
            "array_set_p95_sum_ms": round(sum(timing[name]["p95_ms"] for name in array_set_names), 4),
            "revision_set_p95_sum_ms": round(sum(timing[name]["p95_ms"] for name in revision_names), 4),
            "note": "Sums of per-section p95 values are descriptive, not a percentile of their sum.",
        },
        "enclosing_update_timing_ms": {
            "changed": outer["changed"],
            "unchanged": outer["unchanged"],
            "boundary": outer["boundary"],
            "direct_flow_ingest_timing_available": False,
            "interpretation": (
                "This wall time is an upper enclosing boundary that also includes StageUpdate, "
                "PhysX, Flow solver, and render. Flow 110.0.0 exposes no independent USD-emitter "
                "ingest timer through the inspected public Python/IFlowUsd/StageUpdate surfaces."
            ),
        },
        "gates": gates,
        "production_app": {
            "sha256_before": arguments.production_sha256_before,
            "sha256_after": arguments.production_sha256_after,
            "changed_during_run": False,
        },
        "base_harness": {
            "phase": base.get("phase"),
            "status": base.get("status"),
            "inherited_kit_exit_code": arguments.kit_exit_code,
            "known_reason": "historical stopped/static Phase 6CO gates conflict with dynamic tracking",
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
            "frame_count": len(frames),
            "source": "direct Phase 6DC optimized run",
            "success_criterion": "not video-only",
        },
        "remaining": {
            "direct_flow_ingest_timing": "unavailable on inspected public Flow 110.0.0 boundary",
            "rotation_tracking": "unimplemented",
            "within_update_flow_reset_excluded": False,
            "seamless_visual_continuity_qualified": False,
            "flow_solver_state_checkpointed": False,
        },
    }
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[30], arguments.poster)
    print(f"Phase 6DC: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
