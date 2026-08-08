"""Validate and publish Phase 6CM continuity-gap evidence."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path


def _polyline(samples, width=1010, height=190):
    values = [float(sample["max_error_m"]) * 1000.0 for sample in samples]
    maximum = max(values, default=1.0) or 1.0
    points = []
    for index, value in enumerate(values):
        x = 95.0 + (width * index / max(len(values) - 1, 1))
        y = 455.0 - height * value / maximum
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points), maximum


def _svg(report):
    samples = report["lifecycle"]["alignment_samples"]
    line, maximum_mm = _polyline(samples)
    before_mm = report["lifecycle"]["alignment_before_first_publication"]["max_error_m"] * 1000.0
    issue = report["known_issue"]
    blocks = report["flow"]["active_blocks_peak"]
    gates = len(report["gates"])
    note = html.escape(issue["classification"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CM Resident Point continuity audit</title><desc id="desc">Frame-aligned log and Point centroid telemetry records an unresolved visual continuity defect; seamless editing and Flow recovery are not qualified.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#3b120f"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#fca5a5;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 24px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.bad{{font:750 22px 'Segoe UI',sans-serif;fill:#fca5a5}}.ok{{font:700 18px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CM · UNRESOLVED CONTINUITY DEFECT</text><text x="64" y="113" class="t">Revision continuity is not visual continuity</text><text x="64" y="150" class="s">Flow 110.0.0 · default OFF diagnostic · no production physics or schema change</text>
<rect x="64" y="184" width="1072" height="106" rx="18" fill="#3a1719" stroke="#ef4444"/><text x="88" y="220" class="h">Classification</text><text x="88" y="260" class="bad">{note} · seamless visual continuity = NOT QUALIFIED</text>
<rect x="64" y="312" width="1072" height="184" rx="18" fill="#111f2f"/><text x="88" y="345" class="h">Point-group centroid ↔ PhysX log origin error · frame-aligned samples (mm)</text><line x1="95" y1="455" x2="1105" y2="455" stroke="#475569"/><polyline points="{line}" fill="none" stroke="#fb7185" stroke-width="4"/><text x="88" y="482" class="m">0</text><text x="1040" y="482" class="m">samples {len(samples)}</text><text x="940" y="378" class="v">max {maximum_mm:.3f} mm</text>
<rect x="64" y="520" width="520" height="94" rx="16" fill="#172033"/><text x="88" y="552" class="h">Before first Point publication</text><text x="88" y="588" class="v">{before_mm:.3f} mm gap</text><rect x="600" y="520" width="536" height="94" rx="16" fill="#172033"/><text x="624" y="552" class="h">Audit execution</text><text x="624" y="588" class="v">{gates}/{gates} gates · {blocks} blocks · timeline NOT continuous</text>
<text x="64" y="650" class="ok">Diagnostic reproduced and recorded; dynamic Point tracking and Flow-field checkpoint remain unimplemented.</text></svg>'''


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
        report.get("phase") != "phase6cm"
        or report.get("status") != "ok"
        or not all(report.get("gates", {}).values())
        or issue.get("classification") != "unresolved_defect"
        or issue.get("seamless_visual_continuity_qualified") is not False
    ):
        raise ValueError("Phase 6CM did not record the unresolved continuity defect")
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if len(frames) != 60:
        raise ValueError(f"Phase 6CM requires 60 video frames, got {len(frames)}")
    capture_samples = [
        sample
        for sample in report["lifecycle"]["alignment_samples"]
        if "capture_frame" in sample
    ]
    poster_index = max(
        capture_samples,
        key=lambda sample: sample["max_error_m"],
    )["capture_frame"]
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    report["decision"] = {
        "qualification": "diagnostic reproduction only",
        "visual_continuity": "not qualified",
        "dynamic_point_tracking": "unimplemented",
        "flow_solver_checkpoint": "unimplemented",
        "production_default": "Sphere unchanged; Point remains explicit opt-in",
        "next_boundary": "separate pose synchronization from Flow-field recovery",
    }
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[int(poster_index)], arguments.poster)
    print(
        "Phase 6CM diagnostic written: "
        f"samples={len(report['lifecycle']['alignment_samples'])}, "
        f"max_error_m={issue['maximum_observed_alignment_error_m']}"
    )


if __name__ == "__main__":
    main()
