"""Validate and publish Phase 6CJ normal-owner layout/recovery evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _svg(report):
    gates = len(report["gates"])
    revision = report["publication"]["revisions"][0]
    blocks = report["flow"]["active_blocks_peak"]
    unique = report["flow"]["unique_video_frame_hashes"]
    changed = report["lifecycle"]["layout_changed_point_count"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CJ normal-owner Point layout and stage recovery</title><desc id="desc">The normal default-off Resident Point owner refreshes a stopped log layout, closes and attaches a replacement stage, rebuilds consumers with the current layout, and continues the same revision chain.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071d2b"/><stop offset="1" stop-color="#35170b"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 23px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CJ · LAYOUT + STAGE RECOVERY</text><text x="64" y="113" class="t">Current layout survives consumer reconstruction</text><text x="64" y="150" class="s">Flow 110.0.0 · normal application owner · explicit opt-in only</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Stopped layout refresh</text><text x="90" y="270" class="v">log +0.04 m · layout revision 1 → 2 · {changed} Point positions changed</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Normal-owner stage recovery</text><text x="90" y="404" class="v">closing → closed → opening → opened · consumer rebind 1</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Revision continuity</text><text x="88" y="534" class="v">301 attach seed → final {revision} × 3</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Real Flow / RTX</text><text x="624" y="534" class="v">{blocks} blocks · {unique}/60 unique frames</text>
<text x="64" y="616" class="ok">{gates}/{gates} gates · Point resync 0 · pending discard 0</text><text x="64" y="650" class="m">Sphere default, physics, JSON, rollback, and immutable snapshot contracts remain unchanged.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path)
    arguments = parser.parse_args()
    report = json.loads(arguments.raw.read_text(encoding="utf-8"))
    if (
        report.get("phase") != "phase6cj"
        or report.get("status") != "ok"
        or not all(report.get("gates", {}).values())
    ):
        raise ValueError("Phase 6CJ raw report did not pass every gate")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CJ requires 60 video frames, got {len(frames)}")
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    report["decision"] = {
        "layout_refresh": "qualified only while stopped with monotonic revision",
        "normal_owner_recovery": "qualified with current-layout consumer rebuild",
        "production_default": "Sphere unchanged",
        "next_boundary": "interactive command queue and unsupported-layout UX",
    }
    arguments.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(
        f"Phase 6CJ report written: gates={len(report['gates'])}, "
        f"revision={report['publication']['revisions'][0]}"
    )


if __name__ == "__main__":
    main()
