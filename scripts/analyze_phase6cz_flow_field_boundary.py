"""Validate and publish the Phase 6CZ sampled Flow-field boundary."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _svg(report: dict) -> str:
    observation = report["observation"]
    boundary = report["layout_boundary"]
    pre = observation["active_blocks"]["pre_layout_revision_350"]
    post = observation["active_blocks"]["post_first_publication_revision_351"]
    gates = report["gates"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CZ sampled Flow field boundary</title><desc id="desc">NanoVDB readback and active blocks are nonzero at both samples around the 40 millimeter Resident log-layout boundary, without claiming complete Flow solver checkpoint continuity between them.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#102a43"/><stop offset="1" stop-color="#3f1d2e"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 26px 'Segoe UI',sans-serif;fill:#86efac}}.w{{font:750 23px 'Segoe UI',sans-serif;fill:#fbbf24}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CZ · SAMPLED FLOW FIELD BOUNDARY</text><text x="64" y="113" class="t">Fields nonempty at both samples</text><text x="64" y="150" class="s">Existing Phase 6CO scenario · Flow 110.0.0 · default OFF · production unchanged</text>
<rect x="64" y="190" width="1072" height="126" rx="18" fill="#0f2438"/><text x="88" y="228" class="h">Resident layout boundary</text><text x="88" y="270" class="v">Y {boundary['point_centroid_delta_m'][1] * 1000.0:.3f} mm · Z {boundary['point_centroid_delta_m'][2] * 1000.0:.3f} mm Point jump</text><text x="88" y="298" class="m">revision 350 → 351 total {boundary['point_centroid_displacement_m'] * 1000.0:.3f} mm · log, Point, Flow readback sampled together</text>
<rect x="64" y="338" width="1072" height="112" rx="18" fill="#0f2438"/><text x="88" y="376" class="h">Flow active blocks at the two observable samples</text><text x="88" y="416" class="v">revision 350: {pre}  →  revision 351: {post}</text>
<rect x="64" y="474" width="1072" height="112" rx="18" fill="#3a2b12" stroke="#d97706"/><text x="88" y="512" class="h">Scope limit</text><text x="88" y="550" class="w">Readback stayed nonempty; complete solver checkpoint continuity is NOT proven</text>
<text x="64" y="632" class="v">{sum(gates.values())}/{len(gates)} gates · temperature/fuel/burn/smoke/velocity nonempty</text><text x="64" y="660" class="m">A reset and repopulation inside one Kit update remains below this probe's sampling boundary.</text></svg>'''


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
    arguments = parser.parse_args()
    report = json.loads(arguments.raw.read_text(encoding="utf-8"))
    base = json.loads(arguments.base.read_text(encoding="utf-8"))
    frames = sorted(arguments.frames.glob("frame_*.png"))
    if report.get("phase") != "phase6cz" or report.get("status") != "ok":
        raise ValueError("Phase 6CZ probe did not complete successfully")
    if not all(report.get("gates", {}).values()):
        raise ValueError(f"Phase 6CZ gates failed: {report.get('gates')}")
    legacy_false_gates = {
        "stopped_layout_published_atomically",
        "point_pose_alignment_remained_within_tolerance",
        "point_flow_timeline_stop_reproduced",
        "timeline_held_at_zero_despite_explicit_transport",
    }
    unexpected_base_failures = {
        name
        for name, passed in base.get("gates", {}).items()
        if not passed and name not in legacy_false_gates
    }
    if base.get("phase") != "phase6co" or unexpected_base_failures:
        raise ValueError(
            f"Phase 6CZ base scenario has unexpected failures: {unexpected_base_failures}"
        )
    if len(frames) != 60:
        raise ValueError(f"Phase 6CZ requires 60 boundary frames, got {len(frames)}")
    if arguments.production_sha256_before != arguments.production_sha256_after:
        raise ValueError("Phase 6CZ changed the production application")

    report["production_app"] = {
        "sha256_before": arguments.production_sha256_before,
        "sha256_after": arguments.production_sha256_after,
        "changed": False,
    }
    report["superseded_phase6co_expectations"] = {
        "legacy_false_gates": sorted(legacy_false_gates),
        "unexpected_failures": sorted(unexpected_base_failures),
        "reason": (
            "The corrected 30000-frame safety cap preserves PLAY, so the old "
            "negative STOP and stopped-layout alignment gates are not Phase 6CZ "
            "success criteria."
        ),
    }
    report["video"] = {
        "frame_count": len(frames),
        "boundary_frame": 10,
        "segments": {
            "before_layout_edit": 10,
            "after_layout_edit": 50,
        },
        "human_review": {
            "status": "pending for this independently instrumented run",
            "prior_phase6co_observation": (
                "log placement jump visible; complete flame extinction and "
                "re-ignition from zero not visually observed"
            ),
        },
    }
    report["decision"] = {
        "sampled_flow_boundary": "qualified; required readbacks and active blocks remain nonzero",
        "visible_flame_reset": "not inferred from telemetry; direct review of this video remains pending",
        "flow_solver_state_checkpointed": False,
        "seamless_visual_continuity_qualified": False,
        "dynamic_log_point_tracking_implemented": False,
        "limitation": "reset and repopulation within one Kit update cannot be excluded",
        "next_boundary": (
            "run the same synchronized telemetry on the uninterrupted single-PLAY "
            "renderer harness and remove the stopped layout transition"
        ),
    }
    for path in (arguments.report, arguments.svg, arguments.poster):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    shutil.copy2(frames[10], arguments.poster)
    print(f"Phase 6CZ: {sum(report['gates'].values())}/{len(report['gates'])} gates passed")


if __name__ == "__main__":
    main()
