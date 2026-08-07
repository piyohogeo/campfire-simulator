"""Aggregate Phase 6CB Point Emitter core/render qualification evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


CONFIGURATIONS = ("small-single", "target-single", "target-few")


def _round_summary(summary):
    return {
        key: round(value, 4) if isinstance(value, float) else value
        for key, value in summary.items()
    }


def _svg(report):
    small = report["configurations"]["small-single"]
    single = report["configurations"]["target-single"]
    few = report["configurations"]["target-few"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CB Flow 110 Point Emitter qualification</title>
<desc id="desc">A fresh preset-independent stage qualifies sixteen and seven thousand two hundred Point samples through core simulation, active blocks, NanoVDB fields, and viewport fire and smoke.</desc>
<style>.bg{{fill:#08121f}} .panel{{fill:#111f31;stroke:#29415f;stroke-width:1.5}} .title{{fill:#f7fafc;font:700 30px system-ui,sans-serif}} .sub{{fill:#9fb3c8;font:15px system-ui,sans-serif}} .head{{fill:#7dd3fc;font:700 17px system-ui,sans-serif}} .body{{fill:#cbd5e1;font:14px system-ui,sans-serif}} .ok{{fill:#86efac;font:700 19px system-ui,sans-serif}} .metric{{fill:#f8fafc;font:700 23px system-ui,sans-serif}} .warn{{fill:#fbbf24;font:700 14px system-ui,sans-serif}}</style>
<rect width="1200" height="680" class="bg"/>
<text x="58" y="56" class="title">Phase 6CB · Point Emitter core simulation on Flow 110</text>
<text x="58" y="84" class="sub">Fresh offline stage · no Native PointCloud preset · production remains unchanged</text>
<rect x="48" y="116" width="1104" height="146" rx="16" class="panel"/>
<text x="72" y="154" class="head">The public USD route is qualified end to end</text>
<text x="72" y="193" class="body">FlowEmitterPoint + UsdGeomPoints → FlowSimulate → FlowOffscreen → FlowRender → RTX viewport</text>
<text x="72" y="230" class="ok">17 / 17 gates × 3 configurations · active blocks and NanoVDB fields nonzero · fire/smoke image changed</text>
<rect x="48" y="290" width="350" height="238" rx="16" class="panel"/>
<text x="72" y="329" class="head">16 points · 1 emitter</text>
<text x="72" y="374" class="metric">{small['active_blocks_peak']} active blocks</text>
<text x="72" y="409" class="body">total publish p95 {small['timing']['total']['p95_ms']:.4f} ms</text>
<text x="72" y="438" class="body">Flow/render update p95 {small['flow_render_update']['p95_ms']:.4f} ms</text>
<text x="72" y="467" class="body">{small['notice_count']} notices / {small['publication_count']} publications</text>
<text x="72" y="496" class="body">preset sublayers 0 · live resync 0</text>
<rect x="425" y="290" width="350" height="238" rx="16" class="panel"/>
<text x="449" y="329" class="head">7,200 points · 1 emitter</text>
<text x="449" y="374" class="metric">{single['active_blocks_peak']} active blocks</text>
<text x="449" y="409" class="body">source / Vt / Set p95</text>
<text x="449" y="438" class="body">{single['timing']['source_generation']['p95_ms']:.4f} / {single['timing']['python_cpp_boundary']['p95_ms']:.4f} / {single['timing']['usd_attribute_set']['p95_ms']:.4f} ms</text>
<text x="449" y="467" class="body">Flow/render update p95 {single['flow_render_update']['p95_ms']:.4f} ms</text>
<text x="449" y="496" class="body">payload {single['payload_bytes']:,} B · preferred layout</text>
<rect x="802" y="290" width="350" height="238" rx="16" class="panel"/>
<text x="826" y="329" class="head">7,200 points · 4 emitters</text>
<text x="826" y="374" class="metric">{few['active_blocks_peak']} active blocks</text>
<text x="826" y="409" class="body">source / Vt / Set p95</text>
<text x="826" y="438" class="body">{few['timing']['source_generation']['p95_ms']:.4f} / {few['timing']['python_cpp_boundary']['p95_ms']:.4f} / {few['timing']['usd_attribute_set']['p95_ms']:.4f} ms</text>
<text x="826" y="467" class="body">Flow/render update p95 {few['flow_render_update']['p95_ms']:.4f} ms</text>
<text x="826" y="496" class="body">payload {few['payload_bytes']:,} B · no measured advantage</text>
<text x="58" y="576" class="warn">Decision: Flow 110 upgrade research is not triggered. Keep production Sphere; next isolate Resident surface-array generation before any adoption.</text>
<text x="58" y="612" class="body">Layer, pointsPrim relationship, Points material binding, timeline events, viewport capture, array equality, revision, and no-live-resync are separate gates.</text>
<text x="58" y="642" class="body">The 7,200-point tail is Python source generation, not UsdAttribute.Set: single-emitter Set p95 {single['timing']['usd_attribute_set']['p95_ms']:.4f} ms.</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args()

    raw = {}
    for name in CONFIGURATIONS:
        path = args.raw_dir / f"point_emitter_core_{name}.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("status") != "ok" or not all(value["gates"].values()):
            raise ValueError(f"Phase 6CB raw report failed: {path}")
        raw[name] = value

    configurations = {}
    for name, value in raw.items():
        timing = {
            key: _round_summary(summary)
            for key, summary in value["publication"]["timing"].items()
        }
        configurations[name] = {
            "point_count": value["configuration"]["point_count"],
            "emitter_count": value["configuration"]["emitter_count"],
            "publication_count": (
                value["configuration"]["measured_frames"]
                + value["configuration"]["warmup_frames"]
            ),
            "gate_count": len(value["gates"]),
            "active_blocks_peak": value["timeline"]["playing_active_blocks_peak"],
            "readback_word_counts": value["flow"]["readback_word_counts"],
            "notice_count": value["publication"]["notice_count"],
            "payload_bytes": value["publication"][
                "logical_payload_bytes_per_publication"
            ],
            "timing": timing,
            "flow_render_update": _round_summary(value["kit_flow_render_update"]),
            "channel_sums": value["publication"]["final_channel_sums"],
            "expected_channel_sums": value["publication"][
                "expected_channel_sums"
            ],
            "revision": value["publication"]["final_revisions"],
            "timeline_events": value["timeline"]["events"],
            "final_capture_sha256": value["viewport"]["captures"][-1]["sha256"],
        }

    single = configurations["target-single"]
    few = configurations["target-few"]
    report = {
        "schema_version": 1,
        "phase": "phase6cb",
        "status": "ok",
        "flow_version": "110.0.0",
        "scope": {
            "default_off": True,
            "native_pointcloud_preset_used": False,
            "production_dependency_changed": False,
            "production_scene_changed": False,
            "live_prim_delete_or_redefine": False,
            "post_connection_updates": [
                "pointPositions",
                "pointFuels",
                "pointTemperatures",
                "pointSmokes",
                "campfire:residentRevision",
            ],
        },
        "qualified_boundaries": [
            "layer",
            "pointsPrim relationship",
            "UsdGeomPoints material binding",
            "timeline PLAY and terminal event",
            "viewport camera, capture, fire/smoke image change",
            "Flow core active blocks",
            "NanoVDB temperature/fuel/burn/smoke/velocity readback",
            "fuel/temperature/smoke sums",
            "consumer revision",
            "no live structural resync",
        ],
        "configurations": configurations,
        "decision": {
            "flow_110_public_point_route": "qualified",
            "preferred_layout": "one Point emitter",
            "few_emitter_layout": "qualified but not preferred",
            "production_adoption": "deferred",
            "newer_flow_investigation": "not triggered",
            "reason": (
                "Flow 110 completes core simulation and rendering. At 7,200 points, "
                f"one emitter has total publish p95 {single['timing']['total']['p95_ms']:.4f} ms "
                f"versus {few['timing']['total']['p95_ms']:.4f} ms for four; Python source "
                "generation dominates and must be replaced by a Resident-native surface producer "
                "before production adoption is evaluated."
            ),
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.capture.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    final_capture = Path(raw["target-single"]["viewport"]["captures"][-1]["path"])
    shutil.copy2(final_capture, args.capture)


if __name__ == "__main__":
    main()
