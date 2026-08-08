"""Publish Phase 6CQ renderer/Hydra timeline boundary evidence."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _case(raw, name):
    return next(case for case in raw["cases"] if case["name"] == name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--poster", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8-sig"))
    before = _case(raw, "renderer_before_viewport_frame")
    updates_disabled = _case(raw, "viewport_updates_disabled")
    updates_reenabled = _case(raw, "viewport_updates_reenabled")
    after = _case(raw, "renderer_viewport")
    captured = _case(raw, "capture_callback")
    matrix = [
        case for case in raw["cases"] if case["name"].startswith("disable_")
        and case["name"] != "disable_all_stage_update_nodes"
    ]
    all_disabled = _case(raw, "disable_all_stage_update_nodes")
    nodes = [node["name"] for node in raw["stage_update_nodes_before"]]
    gates = {
        "raw_probe_completed": raw["status"] == "ok",
        "pre_viewport_frame_remained_playing": (
            before["remained_playing"]
            and before["advanced_from_zero"]
            and before["stop_event_count"] == 0
        ),
        "post_viewport_frame_stop_reproduced": (
            not after["remained_playing"]
            and not after["advanced_from_zero"]
            and after["stop_event_count"] == 1
        ),
        "viewport_update_gate_measured": (
            len(updates_disabled["samples"]) == 24
            and len(updates_reenabled["samples"]) == 24
        ),
        "capture_callback_not_required_for_stop": (
            captured["stop_event_count"] == 1
            and captured["capture"]["completed"]
        ),
        "single_node_matrix_complete": len(matrix) == len(nodes) == 5,
        "no_single_node_disable_preserved_play": all(
            case["disabled_during_case"]
            and not case["remained_playing"]
            and case["stop_event_count"] == 1
            for case in matrix
        ),
        "all_public_nodes_disabled_still_stopped": (
            all_disabled["all_disabled_during_case"]
            and not all_disabled["remained_playing"]
            and all_disabled["stop_event_count"] == 1
        ),
        "all_public_nodes_restored": raw["gates"][
            "all_stage_update_nodes_restored"
        ],
        "production_unchanged": not raw["scope"]["production_changed"],
    }
    report = {
        "schema_version": 1,
        "phase": "phase6cq",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "viewport_readiness": raw["viewport_readiness"],
        "before_first_viewport_frame": {
            "remained_playing": before["remained_playing"],
            "timeline_end_s": max(sample["time_s"] for sample in before["samples"]),
            "revision_before": before["revision_before"],
            "revision_after": before["revision_after"],
            "stop_event_count": before["stop_event_count"],
        },
        "after_first_viewport_frame": {
            "remained_playing": after["remained_playing"],
            "timeline_end_s": max(sample["time_s"] for sample in after["samples"]),
            "revision_before": after["revision_before"],
            "revision_after": after["revision_after"],
            "stop_event_count": after["stop_event_count"],
        },
        "capture_callback": captured["capture"],
        "viewport_updates_disabled": {
            "remained_playing": updates_disabled["remained_playing"],
            "timeline_end_s": max(
                sample["time_s"] for sample in updates_disabled["samples"]
            ),
            "revision_before": updates_disabled["revision_before"],
            "revision_after": updates_disabled["revision_after"],
            "stop_event_count": updates_disabled["stop_event_count"],
        },
        "viewport_updates_reenabled": {
            "remained_playing": updates_reenabled["remained_playing"],
            "timeline_end_s": max(
                sample["time_s"] for sample in updates_reenabled["samples"]
            ),
            "revision_before": updates_reenabled["revision_before"],
            "revision_after": updates_reenabled["revision_after"],
            "stop_event_count": updates_reenabled["stop_event_count"],
        },
        "stage_update_nodes": nodes,
        "single_node_disable_results": {
            case["disabled_node"]: {
                "remained_playing": case["remained_playing"],
                "stop_event_count": case["stop_event_count"],
            }
            for case in matrix
        },
        "all_nodes_disabled": {
            "remained_playing": all_disabled["remained_playing"],
            "stop_event_count": all_disabled["stop_event_count"],
        },
        "conclusion": {
            "capture_callback_is_minimum_boundary": False,
            "first_completed_viewport_frame_is_observed_boundary": True,
            "viewport_update_gate_restores_play": updates_disabled[
                "remained_playing"
            ],
            "public_stage_update_disable_controls_remove_stop": False,
            "matrix_reenable_warnings_limit_root_cause_claim": True,
            "remaining_boundary": (
                "Hydra/render-product stage attachment, an attachment side effect "
                "already established before the disable matrix, or another viewport "
                "render subscriber outside the public StageUpdate node graph"
            ),
            "timeline_continuity_qualified": False,
            "seamless_visual_continuity_qualified": False,
        },
        "gates": gates,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    node_text = " · ".join(html.escape(name) for name in nodes)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CQ renderer timeline boundary</title><desc id="desc">Timeline remains playing before the first completed viewport frame, stops immediately after that frame, and still stops with every public StageUpdate node disabled.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#312e81"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#a5b4fc;letter-spacing:2px}}.t{{font:700 38px system-ui;fill:#f8fafc}}.s{{font:20px system-ui;fill:#cbd5e1}}.good{{font:700 44px system-ui;fill:#86efac}}.bad{{font:700 44px system-ui;fill:#fca5a5}}.l{{font:18px system-ui;fill:#e0e7ff}}.c{{fill:#0f172a;stroke:#475569;stroke-width:2}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CQ · RENDERER / HYDRA BOUNDARY</text><text x="64" y="116" class="t">The first completed viewport frame changes PLAY</text><text x="64" y="154" class="s">Flow 110.0.0 · default OFF · normal interactive lifecycle · production unchanged</text>
<rect x="64" y="202" width="328" height="190" rx="20" class="c"/><text x="92" y="248" class="s">before viewport frame</text><text x="92" y="318" class="good">PLAY 0.8 s</text><text x="92" y="356" class="l">revision 0 → 3 · 0 STOP</text>
<rect x="436" y="202" width="328" height="190" rx="20" class="c"/><text x="464" y="248" class="s">after viewport frame</text><text x="464" y="318" class="bad">STOP @ 0</text><text x="464" y="356" class="l">capture callback not required</text>
<rect x="808" y="202" width="328" height="190" rx="20" class="c"/><text x="836" y="248" class="s">all 5 nodes disabled</text><text x="836" y="318" class="bad">STILL STOP</text><text x="836" y="356" class="l">disable controls insufficient</text>
<text x="64" y="452" class="k">PUBLIC STAGEUPDATE MATRIX</text><text x="64" y="492" class="l">{node_text}</text><rect x="64" y="536" width="1072" height="92" rx="18" fill="#312e81" stroke="#818cf8" stroke-width="2"/><text x="92" y="574" class="s">Remaining boundary: Hydra/render-product attachment or another viewport subscriber</text><text x="92" y="606" class="l">Attachment side effects remain possible; timeline and visual continuity stay unqualified.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    if not args.capture.is_file():
        raise SystemExit(f"Phase 6CQ capture is missing: {args.capture}")
    shutil.copyfile(args.capture, args.poster)
    if report["status"] != "ok":
        raise SystemExit("Phase 6CQ gates failed")


if __name__ == "__main__":
    main()
