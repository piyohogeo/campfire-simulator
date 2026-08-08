"""Validate and publish the Phase 6DA running-translation qualification."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _svg(report: dict) -> str:
    boundary = report["boundary"]
    pre = boundary["pre"]
    post = boundary["post"]
    gates = report["gates"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DA running Point translation</title><desc id="desc">A running Resident snapshot advances the Point layout revision and keeps the published Point centroid aligned with the translated log while preserving the existing rollback contract.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#102a43"/><stop offset="1" stop-color="#2b193d"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 26px 'Segoe UI',sans-serif;fill:#86efac}}.w{{font:750 23px 'Segoe UI',sans-serif;fill:#fbbf24}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6DA · RUNNING TRANSLATION SNAPSHOT</text><text x="64" y="113" class="t">Point layout follows the running log</text><text x="64" y="150" class="s">Flow 110.0.0 · default OFF · immutable payload · transactional rollback retained</text>
<rect x="64" y="190" width="1072" height="126" rx="18" fill="#0f2438"/><text x="88" y="228" class="h">Same snapshot boundary</text><text x="88" y="270" class="v">revision {pre['revision']} → {post['revision']} · layout {pre['layout_revision']} → {post['layout_revision']}</text><text x="88" y="298" class="m">positions, layoutRevision, fuel, temperature, smoke, and consumer revision are authored together</text>
<rect x="64" y="338" width="1072" height="112" rx="18" fill="#0f2438"/><text x="88" y="376" class="h">Post-publication alignment</text><text x="88" y="416" class="v">{post['maximum_alignment_error_m'] * 1000.0:.3f} mm max error · target ≤ 2.000 mm</text>
<rect x="64" y="474" width="1072" height="112" rx="18" fill="#3a2b12" stroke="#d97706"/><text x="88" y="512" class="h">Still outside this qualification</text><text x="88" y="550" class="w">Rotation tracking and complete Flow solver continuity remain unqualified</text>
<text x="64" y="632" class="v">{sum(gates.values())}/{len(gates)} gates · active blocks and required Flow fields nonzero</text><text x="64" y="660" class="m">The video also contains the existing later stopped-layout diagnostic; Phase 6DA's injected running edit occurs near its opening.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--frames", required=True, type=Path)
    parser.add_argument("--production-sha256-before", required=True)
    parser.add_argument("--production-sha256-after", required=True)
    parser.add_argument("--kit-exit-code", required=True, type=int)
    arguments = parser.parse_args()
    report = json.loads(arguments.raw.read_text(encoding="utf-8"))
    base = json.loads(arguments.base.read_text(encoding="utf-8"))
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if report.get("phase") != "phase6da" or report.get("status") != "ok":
        raise ValueError("Phase 6DA probe did not complete successfully")
    if not all(report.get("gates", {}).values()):
        raise ValueError(f"Phase 6DA gates failed: {report.get('gates')}")
    if len(frames) != 60:
        raise ValueError(f"Phase 6DA requires 60 diagnostic frames, got {len(frames)}")
    if arguments.production_sha256_before != arguments.production_sha256_after:
        raise ValueError("Phase 6DA run changed the built application")
    report["production_app"] = {
        "sha256_before": arguments.production_sha256_before,
        "sha256_after": arguments.production_sha256_after,
        "changed_during_run": False,
    }
    report["base_scenario"] = {
        "phase": base.get("phase"),
        "status": base.get("status"),
        "kit_exit_code": arguments.kit_exit_code,
        "purpose": "provides the existing deterministic 60-frame renderer harness",
    }
    report["video"] = {
        "frame_count": len(frames),
        "running_edit_near_frame": 4,
        "includes_later_stopped_layout_boundary": True,
        "human_review": {
            "status": "completed",
            "boundary_frames_reviewed": [3, 4],
            "observation": (
                "No abrupt log-placement jump is visible across the injected "
                "running boundary. Visible flame is negligible at that opening "
                "boundary and grows later, so flame continuity at the edit is "
                "not qualified."
            ),
        },
    }
    report["decision"] = {
        "running_translation_snapshot": "qualified at the public USD consumer boundary",
        "production_default": "remain OFF",
        "rotation_tracking": "not implemented",
        "flow_solver_state_checkpointed": False,
        "seamless_visual_continuity_qualified": False,
        "next_boundary": "measure repeated PhysX-driven translations and per-step position authoring cost",
    }
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[4], arguments.poster)
    print(f"Phase 6DA: {sum(report['gates'].values())}/{len(report['gates'])} gates passed")


if __name__ == "__main__":
    main()
