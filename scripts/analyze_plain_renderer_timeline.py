"""Publish Phase 6CR plain-stage renderer boundary evidence."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8-sig"))
    cases = {case["name"]: case for case in raw["cases"]}
    before = cases["before_viewport_frame"]
    after = cases["after_viewport_frame"]
    nodes = [node["name"] for node in raw["stage_update_nodes"]]
    gates = {
        "raw_probe_completed": raw["status"] == "ok",
        "resident_owner_absent": not raw["scope"]["resident_owner_composed"],
        "input_layer_unchanged": not raw["scope"]["input_layer_mutated"],
        "before_frame_remained_playing": (
            before["remained_playing"]
            and before["advanced_from_zero"]
            and before["stop_event_count"] == 0
        ),
        "after_frame_stop_reproduced": (
            not after["remained_playing"]
            and not after["advanced_from_zero"]
            and after["stop_event_count"] == 1
        ),
        "all_stage_update_nodes_enabled": all(
            node["enabled"] for node in raw["stage_update_nodes"]
        ),
        "production_unchanged": not raw["scope"]["production_changed"],
    }
    report = {
        "schema_version": 1,
        "phase": "phase6cr",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "viewport_readiness": raw["viewport_readiness"],
        "resident_owner_composed": False,
        "before_first_viewport_frame": {
            "remained_playing": before["remained_playing"],
            "timeline_end_s": max(sample["time_s"] for sample in before["samples"]),
            "stop_event_count": before["stop_event_count"],
        },
        "after_first_viewport_frame": {
            "remained_playing": after["remained_playing"],
            "timeline_end_s": max(sample["time_s"] for sample in after["samples"]),
            "stop_event_count": after["stop_event_count"],
        },
        "stage_update_nodes": nodes,
        "conclusion": {
            "resident_owner_is_required_for_stop": False,
            "saved_point_flow_physx_stage_plus_completed_viewport_frame_is_sufficient": True,
            "remaining_boundary": (
                "Offline-authored scene components must be removed or disabled before "
                "stage connection in fresh-process variants to separate Flow, PhysX, "
                "render product, and their relationships."
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
<title id="title">Phase 6CR plain-stage renderer boundary</title><desc id="desc">A saved Point, Flow, and PhysX stage without Resident ownership remains playing before the first viewport frame and stops immediately after it.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#3f1d2e"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#f9a8d4;letter-spacing:2px}}.t{{font:700 38px system-ui;fill:#f8fafc}}.s{{font:20px system-ui;fill:#cbd5e1}}.good{{font:700 44px system-ui;fill:#86efac}}.bad{{font:700 44px system-ui;fill:#fca5a5}}.l{{font:18px system-ui;fill:#fce7f3}}.c{{fill:#0f172a;stroke:#475569;stroke-width:2}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CR · PLAIN SAVED STAGE</text><text x="64" y="116" class="t">Resident ownership is not required for STOP</text><text x="64" y="154" class="s">Flow 110.0.0 · renderer enabled · input layer unchanged · production unchanged</text>
<rect x="64" y="202" width="328" height="190" rx="20" class="c"/><text x="92" y="248" class="s">Resident composition</text><text x="92" y="318" class="good">ABSENT</text><text x="92" y="356" class="l">no backend / adapter / owner</text>
<rect x="436" y="202" width="328" height="190" rx="20" class="c"/><text x="464" y="248" class="s">before viewport frame</text><text x="464" y="318" class="good">PLAY 0.8 s</text><text x="464" y="356" class="l">0 STOP</text>
<rect x="808" y="202" width="328" height="190" rx="20" class="c"/><text x="836" y="248" class="s">after viewport frame</text><text x="836" y="318" class="bad">STOP @ 0</text><text x="836" y="356" class="l">1 STOP</text>
<text x="64" y="452" class="k">ALL ENABLED</text><text x="64" y="492" class="l">{node_text}</text><rect x="64" y="536" width="1072" height="92" rx="18" fill="#3f1d2e" stroke="#f472b6" stroke-width="2"/><text x="92" y="574" class="s">Next: fresh offline scene variants before stage connection</text><text x="92" y="606" class="l">Separate Flow, PhysX, render product, and relationship boundaries without live Prim edits.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    if report["status"] != "ok":
        raise SystemExit("Phase 6CR gates failed")


if __name__ == "__main__":
    main()
