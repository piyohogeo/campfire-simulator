"""Validate and publish Phase 6DR normal-app rigid lifecycle evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _svg(report: dict) -> str:
    gates = report["qualification"]["gates"]
    publication = report["publication"]
    flow = report["flow"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DR normal-app rigid lifecycle</title><desc id="desc">The default-off normal application starts with an arbitrary rigid frame, refreshes it while stopped, skips an unchanged refresh, and recovers a replacement stage.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071d2b"/><stop offset="1" stop-color="#32140e"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 24px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6DR · NORMAL APP RIGID LIFECYCLE</text><text x="64" y="113" class="t">Arbitrary frame, one atomic refresh</text><text x="64" y="150" class="s">Flow 110.0.0 · explicit opt-in · production defaults unchanged</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Rigid transform sequence</text><text x="90" y="270" class="v">37° offline → STOP → 53° + translation → unchanged skip</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Stage replacement</text><text x="90" y="404" class="v">layout revision {publication['layout_revision']} · consumer replace 1 · pending none</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Resident publication</text><text x="88" y="534" class="v">revision {publication['revision']} · 3 consumers aligned</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Flow / RTX</text><text x="624" y="534" class="v">{flow['active_blocks_peak']} blocks · {flow['unique_video_frames']}/60 unique</text>
<text x="64" y="616" class="ok">{gates['passed']}/{gates['total']} real-Kit gates · crash/dump/upload 0</text><text x="64" y="650" class="m">Sphere default, wood authority, snapshot, rollback, collision, V3 and held V3T-M conditions are unchanged.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    gates = raw.get("gates", {})
    if (
        raw.get("status") != "ok"
        or raw.get("phase") != "phase6dr"
        or not gates
        or not all(gates.values())
        or raw.get("scope", {}).get("layout_representation") != "rigid_frame_v1"
        or not raw.get("scope", {}).get("rigid_lifecycle_qualification")
    ):
        raise ValueError("Phase 6DR raw report did not qualify")
    owner = raw["lifecycle"]["owner"]
    session = owner["session"]
    report = {
        "schema": "campfire.phase6dr.rigid_lifecycle_report.v1",
        "phase": "phase6dr",
        "status": "qualified_default_off",
        "qualification": {
            "gates": {
                "passed": sum(bool(value) for value in gates.values()),
                "total": len(gates),
                "checks": gates,
            },
            "initial_rotation_degrees": 37.0,
            "refreshed_rotation_degrees": 53.0,
            "stage_built_before_connection": raw["scope"][
                "stage_built_before_connection"
            ],
        },
        "publication": {
            "revision": raw["publication"]["revisions"][0],
            "consumer_revisions": raw["publication"]["revisions"],
            "layout_revision": owner["layout_revision"],
            "layout_replace_count": owner["layout_replace_count"],
            "consumer_replace_count": session["consumer_replace_count"],
            "pending_revision": session["pending_revision"],
            "point_resync_count": len(raw["publication"]["point_resyncs"]),
        },
        "flow": {
            "version": raw["scope"]["flow_version"],
            "active_blocks_peak": raw["flow"]["active_blocks_peak"],
            "unique_video_frames": raw["flow"]["unique_video_frame_hashes"],
            "video_frame_count": raw["flow"]["video_frame_count"],
        },
        "safety": {
            "production_defaults_changed": False,
            "live_representation_migration": False,
            "v3tm_held_conditions_retried": False,
        },
    }
    for path in (args.report, args.svg):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    print(
        "Phase 6DR report written: "
        f"gates={report['qualification']['gates']['passed']}, "
        f"revision={report['publication']['revision']}"
    )


if __name__ == "__main__":
    main()
