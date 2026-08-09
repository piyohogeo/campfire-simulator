"""Publish Phase 6DP rigid-owner qualification evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _svg(report: dict) -> str:
    gates = report["gates"]
    layout = report["layout"]
    publication = report["publication"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DP rigid-frame application owner</title><desc id="desc">A real Kit stage lifecycle qualifies a new default-off rigid session through transform refresh, unchanged skip, consumer replacement, post-recovery publication, and shutdown.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0b1720"/><stop offset="1" stop-color="#1b2941"/></linearGradient></defs><rect width="1200" height="680" rx="30" fill="url(#bg)"/>
<g font-family="Segoe UI, sans-serif"><text x="70" y="68" fill="#93c5fd" font-size="18" font-weight="700" letter-spacing="3">PHASE 6DP - RIGID OWNER LIFECYCLE</text><text x="70" y="118" fill="#f8fafc" font-size="38" font-weight="800">One new rigid session survives the real stage lifecycle</text><text x="70" y="154" fill="#a7b2c2" font-size="18">Production owner composition - Point remains default OFF - no live migration</text>
<rect x="70" y="198" width="330" height="168" rx="18" fill="#10261f" stroke="#34d399"/><text x="96" y="238" fill="#d1fae5" font-size="18">Real Kit gates</text><text x="96" y="292" fill="#6ee7b7" font-size="34" font-weight="800">{gates['passed']} / {gates['total']}</text><text x="96" y="330" fill="#a7f3d0" font-size="17">owner - refresh - replace - close</text>
<rect x="435" y="198" width="330" height="168" rx="18" fill="#172554" stroke="#60a5fa"/><text x="461" y="238" fill="#dbeafe" font-size="18">Arbitrary transform</text><text x="461" y="292" fill="#93c5fd" font-size="31" font-weight="800">{layout['initial_rotation_degrees']:.0f}° → {layout['refreshed_rotation_degrees']:.0f}°</text><text x="461" y="330" fill="#bfdbfe" font-size="17">layout revision {layout['layout_revision']} - unchanged skip</text>
<rect x="800" y="198" width="330" height="168" rx="18" fill="#312e1b" stroke="#fbbf24"/><text x="826" y="238" fill="#fef3c7" font-size="18">Publication continuity</text><text x="826" y="292" fill="#fbbf24" font-size="34" font-weight="800">REV {publication['revision']}</text><text x="826" y="330" fill="#fde68a" font-size="17">{publication['consumer_replace_count']} consumer replacement</text>
<rect x="70" y="400" width="1060" height="148" rx="18" fill="#111e2a"/><text x="96" y="441" fill="#f8fafc" font-size="22" font-weight="700">Stage close / attach / rebuild remains representation-safe</text><text x="96" y="482" fill="#cbd5e1" font-size="18">The replacement consumer restores rigid_frame_v1 at revision 2, then publishes revision 3.</text><text x="96" y="518" fill="#cbd5e1" font-size="18">Running layout writes and live representation migration are rejected; shutdown is idempotent.</text>
<text x="70" y="610" fill="#94a3b8" font-size="17">Next gate: expose this proven path through one explicit default-off normal-app setting; legacy remains the fallback.</text></g></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    checks = probe.get("gates", {})
    passed = sum(value is True for value in checks.values())
    qualified = probe.get("status") == "ok" and checks and passed == len(checks)
    report = {
        "schema": "campfire.phase6dp.rigid_owner_report.v1",
        "phase": "phase6dp",
        "status": "qualified_default_off" if qualified else "failed",
        "gates": {"passed": passed, "total": len(checks), "checks": checks},
        "layout": probe.get("layout", {}),
        "publication": probe.get("publication", {}),
        "non_changes": probe.get("non_changes", {}),
        "decision": {
            "production_owner_composition_qualified": qualified,
            "normal_app_rigid_setting_exposed": False,
            "point_default_enabled": False,
            "live_representation_migration": False,
            "next_gate": "explicit default-off normal-app rigid-session setting",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg.write_text(_svg(report), encoding="utf-8")
    if not qualified:
        raise RuntimeError("Phase 6DP rigid owner did not qualify")
    print(f"Phase 6DP qualified: {passed}/{len(checks)} gates")


if __name__ == "__main__":
    main()
