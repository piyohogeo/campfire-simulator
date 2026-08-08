"""Validate and publish Phase 6CK owner-thread command evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _svg(report):
    gates = len(report["gates"])
    commands = report["lifecycle"]["commands"]
    blocks = report["flow"]["active_blocks_peak"]
    unique = report["flow"]["unique_video_frame_hashes"]
    revision = report["publication"]["revisions"][0]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CK Resident Point owner-thread commands</title><desc id="desc">An unsupported 45 degree log rotation is rejected without changing Point values or revisions, then a restored cardinal layout is committed through the same command queue and Flow continues.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071c2b"/><stop offset="1" stop-color="#351509"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 23px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}.no{{font:750 22px 'Segoe UI',sans-serif;fill:#fca5a5}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CK · OWNER-THREAD COMMAND BOUNDARY</text><text x="64" y="113" class="t">Unsupported layout fails closed</text><text x="64" y="150" class="s">Flow 110.0.0 · UI and headless share one bounded FIFO and result schema</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#31171b" stroke="#b91c1c"/><text x="90" y="228" class="h">Command #{commands[0]['sequence']} · 45° log rotation</text><text x="90" y="270" class="no">REJECTED · {commands[0]['code']} · Point values and revision unchanged</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#102b25" stroke="#15803d"/><text x="90" y="362" class="h">Command #{commands[1]['sequence']} · restored cardinal layout</text><text x="90" y="404" class="ok">ACCEPTED · layout revision 1 → {commands[1]['layout_revision']} · simulation resumed</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Authority and ordering</text><text x="88" y="534" class="v">2 submitted · 2 drained · 1 rejected</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Real Flow / RTX</text><text x="624" y="534" class="v">rev {revision} × 3 · {blocks} blocks · {unique}/60 frames</text>
<text x="64" y="616" class="ok">{gates}/{gates} gates · no Prim resync · no new state authority</text><text x="64" y="650" class="m">Point remains explicit opt-in; Sphere default, physics, JSON, rollback, and snapshot contracts are unchanged.</text></svg>'''


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
        report.get("phase") != "phase6ck"
        or report.get("status") != "ok"
        or not all(report.get("gates", {}).values())
    ):
        raise ValueError("Phase 6CK raw report did not pass every gate")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CK requires 60 video frames, got {len(frames)}")
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    report["decision"] = {
        "unsupported_layout": "reject without Point/revision mutation",
        "execution_thread": "owner thread only",
        "submitters": "UI, timeline, and headless share the same queue/result schema",
        "production_default": "Sphere unchanged; Point remains explicit opt-in",
        "next_boundary": "interactive transform edit observation and queue backpressure",
    }
    arguments.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[len(frames) // 2], arguments.poster)
    print(
        f"Phase 6CK report written: gates={len(report['gates'])}, "
        f"revision={report['publication']['revisions'][0]}"
    )


if __name__ == "__main__":
    main()
