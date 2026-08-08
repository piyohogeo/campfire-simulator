"""Validate and publish Phase 6CN partial continuity-fix evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _svg(report):
    issue = report["known_issue"]
    lifecycle = report["lifecycle"]
    before_mm = lifecycle["alignment_before_first_publication"]["max_error_m"] * 1000.0
    maximum_mm = issue["maximum_observed_alignment_error_m"] * 1000.0
    playing = issue["timeline_playing_sample_count"]
    stopped = issue["timeline_stopped_sample_count"]
    gates = len(report["gates"])
    blocks = report["flow"]["active_blocks_peak"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CN atomic stopped-layout publication</title><desc id="desc">Stopped layout positions and their layout revision are published atomically without advancing the Resident revision. Timeline playback and Flow solver-field continuity remain unresolved.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#082f49"/><stop offset="1" stop-color="#172554"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 25px 'Segoe UI',sans-serif;fill:#86efac}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.warn{{font:750 21px 'Segoe UI',sans-serif;fill:#fbbf24}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CN · PARTIAL CONTINUITY FIX</text><text x="64" y="113" class="t">Layout is visible before the next physics tick</text><text x="64" y="150" class="s">Flow 110.0.0 · default OFF · Resident revision remains tick/snapshot authority</text>
<rect x="64" y="190" width="520" height="126" rx="18" fill="#102a43"/><text x="88" y="228" class="h">Stopped layout transaction</text><text x="88" y="269" class="v">pre-publish gap {before_mm:.6f} mm</text><text x="88" y="296" class="m">pointPositions + layoutRevision 2 · Resident revision unchanged at 300</text>
<rect x="600" y="190" width="536" height="126" rx="18" fill="#102a43"/><text x="624" y="228" class="h">Frame-aligned pose samples</text><text x="624" y="269" class="v">max {maximum_mm:.6f} mm</text><text x="624" y="296" class="m">720 points · 2 logs × 360 contiguous surface samples</text>
<rect x="64" y="338" width="1072" height="114" rx="18" fill="#102a43"/><text x="88" y="376" class="h">Timeline evidence (still unresolved)</text><text x="88" y="416" class="warn">PLAY {playing} samples · STOPPED {stopped} samples</text>
<rect x="64" y="476" width="1072" height="106" rx="18" fill="#3a2b12" stroke="#d97706"/><text x="88" y="514" class="h">Still unresolved</text><text x="88" y="552" class="warn">Flow solver-field continuity and stage-recovery visuals are NOT QUALIFIED</text>
<text x="64" y="632" class="v">{gates}/{gates} gates · {blocks} active blocks · 60/60 unique RTX frames</text><text x="64" y="660" class="m">Sphere production default, wood authority, physics equations, and snapshot rollback contract are unchanged.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path)
    arguments = parser.parse_args()
    report = json.loads(arguments.raw.read_text(encoding="utf-8"))
    issue = report.get("known_issue", {})
    if (
        report.get("phase") != "phase6cn"
        or report.get("status") != "ok"
        or not all(report.get("gates", {}).values())
        or issue.get("classification") != "partially_mitigated"
        or issue.get("layout_publication_continuity_qualified") is not True
        or issue.get("timeline_continuity_qualified") is not False
        or issue.get("seamless_visual_continuity_qualified") is not False
    ):
        raise ValueError("Phase 6CN did not preserve the partial-fix boundary")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CN requires 60 video frames, got {len(frames)}")
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    report["decision"] = {
        "layout_publication": "qualified while stopped",
        "resident_revision": "unchanged by layout-only transaction",
        "timeline": "not qualified; PLAY is followed by STOP in the headless Flow/PhysX boundary",
        "flow_solver_field_continuity": "not qualified",
        "production_default": "Sphere unchanged; Point remains explicit opt-in",
        "next_boundary": "measure and control Flow reset on Point relocation",
    }
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(
        f"Phase 6CN report written: gates={len(report['gates'])}, "
        f"playing={issue['timeline_playing_sample_count']}"
    )


if __name__ == "__main__":
    main()
