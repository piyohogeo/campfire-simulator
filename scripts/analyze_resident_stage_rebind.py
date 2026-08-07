"""Validate and publish Phase 6CE replacement-stage recovery evidence."""

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
    final_revision = report["checkpoints"]["final"]["backend"]["revision"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CE replacement-stage Resident recovery</title><desc id="desc">A pending immutable Resident revision survives an official Kit stage replacement, consumer reconstruction, and exact retry.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071d2b"/><stop offset="1" stop-color="#30150b"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 37px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 24px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CE · REPLACEMENT-STAGE RECOVERY</text><text x="64" y="113" class="t">Keep the pending value; replace only its consumers</text><text x="64" y="150" class="s">UsdContext close + attach · stopped owner handoff · Flow 110.0.0</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Replacement detected at pending revision 3</text><text x="90" y="270" class="v">backend 3 · old primary 2 · old Point 2 · next tick blocked</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Validated handoff and exact retry</text><text x="90" y="404" class="v">new consumers seed 2 · same payload identity + digest · all become 3</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Continuous session</text><text x="88" y="534" class="v">final revision {final_revision} · no pending discard</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Recovered Flow capture</text><text x="624" y="534" class="v">60 frames · {unique_frames} unique · {blocks} blocks</text>
<text x="64" y="616" class="ok">{gates}/{gates} gates · zero post-attach live resync · production unchanged</text><text x="64" y="650" class="m">Next: qualify scheduler-driven automatic stop/rebind/retry while keeping the same explicit lifecycle contract.</text></svg>'''


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
        raise ValueError("Phase 6CE raw report did not pass every gate")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CE requires 60 video frames, got {len(frames)}")
    unique_hashes = len(
        {hashlib.sha256(path.read_bytes()).hexdigest() for path in frames}
    )
    if unique_hashes < 55:
        raise ValueError(
            f"Phase 6CE video is not sufficiently continuous: {unique_hashes} unique frames"
        )
    report["flow"]["unique_video_frame_hashes"] = unique_hashes
    report["decision"] = {
        "replacement_stage_recovery": "qualified default-off",
        "production_activation": "deferred",
        "next_boundary": "scheduler-driven automatic replacement handoff",
    }
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(
        f"Phase 6CE report written: gates={len(report['gates'])}, "
        f"unique frames={unique_hashes}"
    )


if __name__ == "__main__":
    main()
