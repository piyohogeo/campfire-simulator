"""Publish Phase 6CP StageUpdate boundary evidence."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--owner", type=Path, required=True)
    parser.add_argument("--interactive", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    owner = json.loads(args.owner.read_text(encoding="utf-8-sig"))
    interactive = json.loads(args.interactive.read_text(encoding="utf-8-sig"))
    node_names = [node["name"] for node in interactive["stage_update_nodes"]]
    gates = {
        "normal_and_benchmark_nodes_match": (
            inventory["normal_node_count"] == inventory["benchmark_node_count"] == 5
            and not inventory["normal_only_nodes"]
            and not inventory["benchmark_only_nodes"]
        ),
        "plain_stage_remained_playing": (
            inventory["normal_remained_playing"]
            and inventory["benchmark_remained_playing"]
        ),
        "resident_owner_remained_playing": owner["timeline"]["remained_playing"],
        "interactive_lifecycle_remained_playing": interactive["timeline"]["remained_playing"],
        "interactive_timeline_advanced": interactive["timeline"]["advanced_from_zero"],
        "interactive_owner_published": interactive["owner_evidence"]["interactive_step_published"],
        "no_interactive_stop_event": interactive["timeline"]["stop_event_count"] == 0,
        "all_stage_update_nodes_enabled": all(
            node["enabled"] for node in interactive["stage_update_nodes"]
        ),
        "production_unchanged": not any(
            source.get("scope", {}).get("production_changed", False)
            for source in (owner, interactive)
        ),
    }
    report = {
        "schema_version": 1,
        "phase": "phase6cp",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage_update_nodes": node_names,
        "node_orders": {
            node["name"]: node["order"] for node in interactive["stage_update_nodes"]
        },
        "plain_stage": {
            "normal_remained_playing": inventory["normal_remained_playing"],
            "benchmark_remained_playing": inventory["benchmark_remained_playing"],
        },
        "resident_owner": {
            "remained_playing": owner["timeline"]["remained_playing"],
            "stop_event_count": owner["timeline"]["stop_event_count"],
            "steps_issued": owner["owner"]["steps_issued"],
        },
        "interactive_lifecycle": {
            "remained_playing": interactive["timeline"]["remained_playing"],
            "stop_event_count": interactive["timeline"]["stop_event_count"],
            "timeline_end_s": max(
                sample["time_s"] for sample in interactive["timeline"]["samples"]
            ),
            **interactive["owner_evidence"],
        },
        "conclusion": {
            "stage_update_node_disable_matrix_started": False,
            "reason": (
                "The all-enabled baseline does not reproduce STOP in the plain stage, "
                "composed owner, or extension interactive lifecycle. Disabling nodes "
                "would not identify a requester without a reproducing baseline."
            ),
            "remaining_boundary": (
                "The PLAY-to-STOP event remains confined to the RTX capture qualification "
                "path measured by Phase 6CO; renderer-enabled interactive playback is not "
                "yet qualified."
            ),
            "production_interactive_continuity_qualified": False,
            "capture_harness_continuity_qualified": False,
        },
        "gates": gates,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    nodes = " · ".join(html.escape(name) for name in node_names)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CP StageUpdate boundary isolation</title><desc id="desc">All five StageUpdate nodes remain enabled while the plain stage, composed Resident owner, and renderer-disabled interactive lifecycle remain playing. The Point revision advances from zero to four.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#172554"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#93c5fd;letter-spacing:2px}}.t{{font:700 38px system-ui;fill:#f8fafc}}.s{{font:20px system-ui;fill:#cbd5e1}}.n{{font:700 44px system-ui;fill:#86efac}}.l{{font:18px system-ui;fill:#dbeafe}}.c{{fill:#0f172a;stroke:#334155;stroke-width:2}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CP · STAGEUPDATE BOUNDARY</text><text x="64" y="116" class="t">Interactive PLAY survives the all-enabled graph</text><text x="64" y="154" class="s">Flow 110.0.0 · default OFF · no production change</text>
<rect x="64" y="202" width="328" height="190" rx="20" class="c"/><text x="92" y="248" class="s">plain saved stage</text><text x="92" y="318" class="n">PLAY</text><text x="92" y="356" class="l">normal + benchmark</text>
<rect x="436" y="202" width="328" height="190" rx="20" class="c"/><text x="464" y="248" class="s">Resident owner composed</text><text x="464" y="318" class="n">PLAY</text><text x="464" y="356" class="l">0 STOP · 0 publications</text>
<rect x="808" y="202" width="328" height="190" rx="20" class="c"/><text x="836" y="248" class="s">interactive lifecycle</text><text x="836" y="318" class="n">0 → 4</text><text x="836" y="356" class="l">revision · 0 STOP</text>
<text x="64" y="452" class="k">ALL ENABLED</text><text x="64" y="492" class="l">{nodes}</text><rect x="64" y="536" width="1072" height="92" rx="18" fill="#3f1d2e" stroke="#9f1239" stroke-width="2"/><text x="92" y="574" class="s">Remaining boundary: renderer-enabled RTX capture qualification only</text><text x="92" y="606" class="l">Do not disable nodes until that baseline reproduces outside the capture harness.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    if report["status"] != "ok":
        raise SystemExit("Phase 6CP gates failed")


if __name__ == "__main__":
    main()
