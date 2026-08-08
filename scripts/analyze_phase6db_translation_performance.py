"""Validate and publish the Phase 6DB translation-performance comparison."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _sidecar(summary: dict) -> dict:
    return summary["lifecycle"]["owner"]["session"]["sidecar"]


def _svg(report: dict) -> str:
    baseline = report["runs"]["baseline"]
    optimized = report["runs"]["optimized"]
    saved = report["comparison"]["candidate_build_total_saved_ms"]
    avoided = report["comparison"]["candidate_builds_avoided"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DB translation authoring cost</title><desc id="desc">The default-off optimized path checks unchanged translations before allocating and building a native Point layout candidate. Position conversion and USD publication remain transactional on changed updates.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#102a43"/><stop offset="1" stop-color="#1f2937"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 27px 'Segoe UI',sans-serif;fill:#86efac}}.b{{font:750 24px 'Segoe UI',sans-serif;fill:#fbbf24}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6DB · REPEATED TRANSLATION COST</text><text x="64" y="113" class="t">Skip unchanged native layout candidates</text><text x="64" y="150" class="s">Flow 110.0.0 · 720 points · default OFF · identical transactional publication on changed ticks</text>
<rect x="64" y="190" width="510" height="150" rx="18" fill="#0f2438"/><text x="88" y="228" class="h">Baseline</text><text x="88" y="270" class="b">{baseline['candidate_build']['sample_count']} candidate builds</text><text x="88" y="307" class="s">{baseline['unchanged_count']} updates were unchanged</text>
<rect x="626" y="190" width="510" height="150" rx="18" fill="#0f2438"/><text x="650" y="228" class="h">Precheck enabled</text><text x="650" y="270" class="v">{optimized['candidate_build']['sample_count']} candidate builds</text><text x="650" y="307" class="s">changed updates still publish one immutable candidate</text>
<rect x="64" y="370" width="1072" height="118" rx="18" fill="#123528" stroke="#22c55e"/><text x="88" y="408" class="h">Removed diagnostic-path work</text><text x="88" y="450" class="v">{avoided} builds avoided · {saved:.3f} ms measured candidate time removed</text>
<rect x="64" y="516" width="1072" height="92" rx="18" fill="#3a2b12" stroke="#d97706"/><text x="88" y="552" class="h">Boundary retained</text><text x="88" y="586" class="b">This does not remove Vt conversion, USD Set, Flow ingest, or solver cost on changed updates</text>
<text x="64" y="650" class="m">Production default, physics, revision, rollback, and immutable snapshot contracts are unchanged.</text></svg>'''


def _run_record(summary: dict) -> dict:
    sidecar = _sidecar(summary)
    timing = sidecar["live_translation_timing_ms"]
    return {
        "resident_revision": sidecar["revision"],
        "point_count": sidecar["point_count"],
        "prepare_count": sidecar["prepare_count"],
        "publish_count": sidecar["publish_count"],
        "changed_count": sidecar["live_translation_publish_count"],
        "unchanged_count": sidecar["live_translation_unchanged_count"],
        "skip_unchanged_translation_layout": sidecar[
            "skip_unchanged_translation_layout"
        ],
        "provider": timing["provider"],
        "candidate_build": timing["candidate_build"],
        "position_vt_conversion": timing["position_vt_conversion"],
        "position_usd_set": timing["position_usd_set"],
        "publish_transaction": timing["publish_transaction"],
        "failure_count": sidecar["failure_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--baseline-probe", required=True, type=Path)
    parser.add_argument("--optimized", required=True, type=Path)
    parser.add_argument("--optimized-probe", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path)
    parser.add_argument("--production-sha256-before", required=True)
    parser.add_argument("--production-sha256-after", required=True)
    arguments = parser.parse_args()
    baseline_summary = json.loads(arguments.baseline.read_text(encoding="utf-8"))
    optimized_summary = json.loads(arguments.optimized.read_text(encoding="utf-8"))
    baseline_probe = json.loads(arguments.baseline_probe.read_text(encoding="utf-8"))
    optimized_probe = json.loads(arguments.optimized_probe.read_text(encoding="utf-8"))
    frames = sorted(arguments.frames.glob("frame_*.png"))
    baseline = _run_record(baseline_summary)
    optimized = _run_record(optimized_summary)
    if arguments.production_sha256_before != arguments.production_sha256_after:
        raise ValueError("Phase 6DB changed the built application")
    if len(frames) != 60:
        raise ValueError(f"Phase 6DB requires 60 optimized frames, got {len(frames)}")
    if any(probe.get("status") != "ok" for probe in (baseline_probe, optimized_probe)):
        raise ValueError("Phase 6DB dynamic-translation probe failed")
    if not all(all(probe.get("gates", {}).values()) for probe in (baseline_probe, optimized_probe)):
        raise ValueError("Phase 6DB inherited alignment gates failed")
    gates = {
        "baseline_builds_every_prepare": (
            baseline["candidate_build"]["sample_count"] == baseline["prepare_count"]
        ),
        "optimized_builds_changed_only": (
            optimized["candidate_build"]["sample_count"] == optimized["changed_count"]
        ),
        "optimized_avoids_unchanged_builds": (
            optimized["candidate_build"]["sample_count"]
            < baseline["candidate_build"]["sample_count"]
        ),
        "position_conversion_matches_changed": (
            optimized["position_vt_conversion"]["sample_count"]
            == optimized["changed_count"]
        ),
        "position_set_matches_changed": (
            optimized["position_usd_set"]["sample_count"]
            == optimized["changed_count"]
        ),
        "transaction_matches_changed": (
            optimized["publish_transaction"]["sample_count"]
            == optimized["changed_count"]
        ),
        "no_publication_failures": (
            baseline["failure_count"] == optimized["failure_count"] == 0
        ),
        "point_count_preserved": baseline["point_count"] == optimized["point_count"] == 720,
    }
    if not all(gates.values()):
        raise ValueError(f"Phase 6DB gates failed: {gates}")
    report = {
        "phase": "phase6db",
        "status": "ok",
        "scope": "default-off repeated translation layout and pointPositions authoring cost",
        "runs": {"baseline": baseline, "optimized": optimized},
        "comparison": {
            "candidate_builds_avoided": (
                baseline["candidate_build"]["sample_count"]
                - optimized["candidate_build"]["sample_count"]
            ),
            "candidate_build_total_saved_ms": round(
                baseline["candidate_build"]["total_ms"]
                - optimized["candidate_build"]["total_ms"],
                4,
            ),
            "interpretation": (
                "The precheck removes native layout allocation/build work on unchanged ticks. "
                "Changed ticks retain Vt conversion, transactional USD authoring, Flow ingest, "
                "and solver work."
            ),
        },
        "gates": gates,
        "production_app": {
            "sha256_before": arguments.production_sha256_before,
            "sha256_after": arguments.production_sha256_after,
            "changed_during_run": False,
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
            "source": "optimized run using the same deterministic 60-frame renderer harness",
            "success_criterion": "not video-only",
            "human_review": {
                "status": "completed",
                "frames_reviewed": [4, 30],
                "observation": (
                    "The optimized run renders the expected campfire and later visible flame. "
                    "The opening running-edit boundary still has negligible visible flame, so "
                    "this performance run does not qualify flame continuity."
                ),
            },
        },
        "remaining": {
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
    print(f"Phase 6DB: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
