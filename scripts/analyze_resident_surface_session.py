"""Validate and publish Phase 6CD Resident Point-sidecar evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def _svg(report):
    gates = len(report["gates"])
    blocks = report["flow"]["active_blocks_peak"]
    unique_frames = report["flow"]["unique_video_frame_hashes"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CD Resident session Point-sidecar lifecycle</title><desc id="desc">Point arrays and the primary immutable snapshot share pending retry, rollback, layout revision, and stage replacement ownership.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#081c2c"/><stop offset="1" stop-color="#28150d"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 25px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CD · SESSION-OWNED POINT SIDECAR</text><text x="64" y="113" class="t">One pending revision, two consumer publications</text><text x="64" y="150" class="s">ResidentNativeStep + immutable 7,200-point payload · owner thread · Flow 110.0.0</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Point publication failure at revision 2</text><text x="90" y="270" class="v">backend 2 · primary 1 · Point 1 → exact payload retry → all 2</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Primary publication failure at revision 3</text><text x="90" y="404" class="v">Point rolls 3 → 2 · primary replays 2 → exact retry → all 3</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Layout + stage lifecycle</text><text x="88" y="534" class="v">layout rev 2 · stage change fail-closed</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Real Flow capture</text><text x="624" y="534" class="v">60 frames · {unique_frames} unique · {blocks} active blocks</text>
<text x="64" y="616" class="ok">{gates}/{gates} gates · no live structural resync · production activation unchanged</text><text x="64" y="650" class="m">Next: rebuild the sidecar on a replacement stage and qualify normal recovery instead of forced pending discard.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path)
    arguments = parser.parse_args()
    report = json.loads(arguments.raw.read_text(encoding="utf-8"))
    if report.get("status") != "ok" or not all(report.get("gates", {}).values()):
        raise ValueError("Phase 6CD raw report did not pass every gate")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CD requires 60 video frames, got {len(frames)}")
    unique_hashes = len({hashlib.sha256(path.read_bytes()).hexdigest() for path in frames})
    if unique_hashes < 55:
        raise ValueError(f"Phase 6CD video is not sufficiently continuous: {unique_hashes} unique frames")
    report["flow"]["unique_video_frame_hashes"] = unique_hashes
    report["decision"] = {
        "session_sidecar_contract": "qualified default-off",
        "production_activation": "deferred",
        "next_boundary": "replacement-stage sidecar reconstruction and pending retry",
    }
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(f"Phase 6CD report written: gates={len(report['gates'])}, unique frames={unique_hashes}")


if __name__ == "__main__":
    main()
