"""Validate and publish Phase 6CI normal-owner evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _svg(report):
    gates = len(report["gates"])
    points = report["scope"]["point_count"]
    revision = report["publication"]["revisions"][0]
    blocks = report["flow"]["active_blocks_peak"]
    unique = report["flow"]["unique_video_frame_hashes"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CI normal Resident Point owner</title><desc id="desc">The normal campfire application owns one default-off Resident backend, primary snapshot adapter, Point sidecar, and stage recovery composition.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071d2b"/><stop offset="1" stop-color="#35170b"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 23px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CI · NORMAL APPLICATION OWNER</text><text x="64" y="113" class="t">One owner, one revision chain, one Point emitter</text><text x="64" y="150" class="s">Flow 110.0.0 · explicit opt-in · production default remains Sphere</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Owned composition</text><text x="90" y="270" class="v">backend → immutable snapshot → primary adapter + {points}-point sidecar</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Live publication boundary</text><text x="90" y="404" class="v">existing arrays only · resync 0 · matched revision {revision}</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Lifecycle</text><text x="88" y="534" class="v">extension startup → play → stop → clean close</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Real Flow / RTX</text><text x="624" y="534" class="v">{blocks} blocks · {unique}/60 unique frames</text>
<text x="64" y="616" class="ok">{gates}/{gates} gates · stage complete before context connection</text><text x="64" y="650" class="m">Sphere fallback, physics, JSON schema, rollback, and immutable snapshot contracts remain unchanged.</text></svg>'''


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
        report.get("phase") != "phase6ci"
        or report.get("status") != "ok"
        or not all(report.get("gates", {}).values())
    ):
        raise ValueError("Phase 6CI raw report did not pass every gate")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CI requires 60 video frames, got {len(frames)}")
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    report["decision"] = {
        "normal_application_owner": "qualified behind explicit default-off setting",
        "production_default": "Sphere unchanged",
        "next_boundary": "interactive layout refresh and recovery exercise",
    }
    arguments.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(
        f"Phase 6CI report written: gates={len(report['gates'])}, "
        f"revision={report['publication']['revisions'][0]}"
    )


if __name__ == "__main__":
    main()
