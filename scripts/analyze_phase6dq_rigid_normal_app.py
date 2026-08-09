"""Validate and publish Phase 6DQ normal-app rigid-layout evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _svg(report: dict) -> str:
    gates = report["qualification"]["gates"]
    revision = report["publication"]["revision"]
    blocks = report["flow"]["active_blocks_peak"]
    unique = report["flow"]["unique_video_frames"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DQ normal-app rigid layout</title><desc id="desc">An explicit default-off setting selects rigid-frame Point layout before offline stage authoring while the legacy fallback remains unchanged.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071d2b"/><stop offset="1" stop-color="#35170b"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 23px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6DQ · NORMAL APP RIGID SETTING</text><text x="64" y="113" class="t">Choose once before stage connection</text><text x="64" y="150" class="s">Flow 110.0.0 · explicit opt-in · Point and rigid layout remain default OFF</text>
<rect x="64" y="192" width="1072" height="112" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="228" class="h">Offline authoring boundary</text><text x="90" y="270" class="v">setting → rigid_frame_v1 → 720-point schema → context connection</text>
<rect x="64" y="326" width="1072" height="112" rx="20" fill="#231c18" stroke="#9a3412"/><text x="90" y="362" class="h">Immutable runtime contract</text><text x="90" y="404" class="v">revision {revision} · resync 0 · layout replacement 0 · clean close</text>
<rect x="64" y="462" width="520" height="104" rx="18" fill="#12202e"/><text x="88" y="498" class="h">Flow / RTX</text><text x="88" y="534" class="v">{blocks} active blocks · {unique}/60 unique frames</text>
<rect x="600" y="462" width="536" height="104" rx="18" fill="#12202e"/><text x="624" y="498" class="h">Fallback and rejection</text><text x="624" y="534" class="v">legacy default · old qualifications rejected</text>
<text x="64" y="616" class="ok">{gates['passed']}/{gates['total']} real-Kit gates · normal extension initialization</text><text x="64" y="650" class="m">Sphere production default, wood authority, snapshot schema, rollback, collision, and V3T-C remain unchanged.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    gates = raw.get("gates", {})
    if (
        raw.get("status") != "ok"
        or raw.get("phase") != "phase6dq"
        or not gates
        or not all(gates.values())
        or raw.get("scope", {}).get("layout_representation") != "rigid_frame_v1"
    ):
        raise ValueError("Phase 6DQ raw report did not qualify")
    report = {
        "schema": "campfire.phase6dq.rigid_normal_app_report.v1",
        "phase": "phase6dq",
        "status": "qualified_default_off",
        "qualification": {
            "gates": {
                "passed": sum(bool(value) for value in gates.values()),
                "total": len(gates),
                "checks": gates,
            },
            "normal_application": raw["scope"]["normal_application"],
            "stage_built_before_connection": raw["scope"][
                "stage_built_before_connection"
            ],
            "layout_representation": raw["scope"]["layout_representation"],
        },
        "publication": {
            "revision": raw["publication"]["revisions"][0],
            "consumer_revisions": raw["publication"]["revisions"],
            "point_resync_count": len(raw["publication"]["point_resyncs"]),
            "layout_revision": raw["lifecycle"]["owner"]["layout_revision"],
            "layout_replace_count": raw["lifecycle"]["owner"][
                "layout_replace_count"
            ],
        },
        "flow": {
            "version": raw["scope"]["flow_version"],
            "point_count": raw["scope"]["point_count"],
            "active_blocks_peak": raw["flow"]["active_blocks_peak"],
            "unique_video_frames": raw["flow"]["unique_video_frame_hashes"],
            "video_frame_count": raw["flow"]["video_frame_count"],
        },
        "decision": {
            "point_default_enabled": False,
            "rigid_layout_default_enabled": False,
            "sphere_production_default": True,
            "legacy_fallback_preserved": True,
            "legacy_qualification_mix_rejected_before_authoring": True,
            "live_representation_migration": False,
            "next_gate": "interactive arbitrary-transform refresh through normal app",
        },
    }
    for path in (arguments.report, arguments.svg):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    print(
        "Phase 6DQ report written: "
        f"gates={report['qualification']['gates']['passed']}, "
        f"revision={report['publication']['revision']}"
    )


if __name__ == "__main__":
    main()
