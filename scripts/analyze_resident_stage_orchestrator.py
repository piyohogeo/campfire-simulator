"""Validate and publish Phase 6CF scheduler recovery evidence."""

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
<title id="title">Phase 6CF scheduler-driven Resident stage recovery</title><desc id="desc">A scheduler orchestrator follows real Kit stage lifecycle events and retries consumer construction without losing the pending immutable value.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#081b2a"/><stop offset="1" stop-color="#2e160c"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 23px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CF · SCHEDULER RECOVERY</text><text x="64" y="113" class="t">Lifecycle events drive one safe Resident handoff</text><text x="64" y="150" class="s">Flow 110.0.0 · default OFF · owner thread · no production activation</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Real Kit event sequence</text><text x="90" y="270" class="v">CLOSING → CLOSED → OPENING → OPENED · 4 + 4 update drains</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Injected consumer-factory failure after attach</text><text x="90" y="404" class="v">pending rev 3 retained → factory retry at seed 2 → exact payload → all rev 3</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Continuous session</text><text x="88" y="534" class="v">final revision {final_revision} · no pending discard</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Recovered Flow capture</text><text x="624" y="534" class="v">60 frames · {unique_frames} unique · {blocks} blocks</text>
<text x="64" y="616" class="ok">{gates}/{gates} gates · zero live structural resync · production unchanged</text><text x="64" y="650" class="m">Next: integrate the qualified scheduler boundary only when a production Point consumer is selected.</text></svg>'''


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
        raise ValueError("Phase 6CF raw report did not pass every gate")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CF requires 60 video frames, got {len(frames)}")
    unique_hashes = len(
        {hashlib.sha256(path.read_bytes()).hexdigest() for path in frames}
    )
    if unique_hashes < 55:
        raise ValueError(
            f"Phase 6CF video is not sufficiently continuous: {unique_hashes} unique frames"
        )
    report["flow"]["unique_video_frame_hashes"] = unique_hashes
    report["decision"] = {
        "scheduler_recovery": "qualified default-off",
        "production_activation": "deferred",
        "next_boundary": "production adoption only with a selected Point consumer",
    }
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(
        f"Phase 6CF report written: gates={len(report['gates'])}, "
        f"unique frames={unique_hashes}"
    )


if __name__ == "__main__":
    main()
