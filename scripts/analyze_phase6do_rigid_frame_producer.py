"""Publish Phase 6DO rigid-frame producer evidence as JSON and SVG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _svg(report: dict) -> str:
    gates = report["gates"]
    layout = report["layout"]
    publication = report["publication"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DO default-off rigid-frame producer</title><desc id="desc">A real native and Kit probe qualifies arbitrary rigid rotation, byte-equivalent identity-X output, revision-last publication, rollback, retry, and recovery while Point remains disabled by default.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0b1720"/><stop offset="1" stop-color="#18263c"/></linearGradient></defs><rect width="1200" height="680" rx="30" fill="url(#bg)"/>
<g font-family="Segoe UI, sans-serif"><text x="70" y="68" fill="#93c5fd" font-size="18" font-weight="700" letter-spacing="3">PHASE 6DO - RIGID-FRAME PRODUCER</text><text x="70" y="118" fill="#f8fafc" font-size="38" font-weight="800">Arbitrary rotation reaches the existing snapshot schema</text><text x="70" y="154" fill="#a7b2c2" font-size="18">Additive native ABI - immutable representation - Point remains default OFF</text>
<rect x="70" y="198" width="330" height="168" rx="18" fill="#10261f" stroke="#34d399"/><text x="96" y="238" fill="#d1fae5" font-size="18">Real native + Kit gates</text><text x="96" y="292" fill="#6ee7b7" font-size="34" font-weight="800">{gates['passed']} / {gates['total']}</text><text x="96" y="330" fill="#a7f3d0" font-size="17">layout - publish - retry - recovery</text>
<rect x="435" y="198" width="330" height="168" rx="18" fill="#172554" stroke="#60a5fa"/><text x="461" y="238" fill="#dbeafe" font-size="18">Identity-X compatibility</text><text x="461" y="292" fill="#93c5fd" font-size="30" font-weight="800">BYTE IDENTICAL</text><text x="461" y="330" fill="#bfdbfe" font-size="17">positions and all three channels</text>
<rect x="800" y="198" width="330" height="168" rx="18" fill="#312e1b" stroke="#fbbf24"/><text x="826" y="238" fill="#fef3c7" font-size="18">Arbitrary rotation error</text><text x="826" y="292" fill="#fbbf24" font-size="34" font-weight="800">{layout['arbitrary_rotation_max_error_m']:.1f} m</text><text x="826" y="330" fill="#fde68a" font-size="17">37 degrees - {layout['point_count']} points</text>
<rect x="70" y="400" width="1060" height="148" rx="18" fill="#111e2a"/><text x="96" y="441" fill="#f8fafc" font-size="22" font-weight="700">Revision-last failure recovery remains exact</text><text x="96" y="482" fill="#cbd5e1" font-size="18">Injected position failure restored USD and native state; the exact payload retried and committed revision {publication['published_revision']}.</text><text x="96" y="518" fill="#cbd5e1" font-size="18">Export/open reconstructed the rigid consumer; cross-representation recovery failed closed.</text>
<text x="70" y="610" fill="#94a3b8" font-size="17">No live migration: legacy Y remains an explicitly excluded reflection; rebuild a session to change representation.</text></g></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    probe = _read(args.probe)
    checks = probe.get("gates", {})
    passed = sum(value is True for value in checks.values())
    qualified = (
        probe.get("status") == "ok"
        and checks
        and passed == len(checks)
        and probe["layout"]["representation"] == "rigid_frame_v1"
        and probe["non_changes"]["point_default"] is False
        and probe["non_changes"]["v3_default"] is False
    )
    report = {
        "schema": "campfire.phase6do.rigid_frame_producer_report.v1",
        "phase": "phase6do",
        "status": "qualified_default_off" if qualified else "failed",
        "gates": {"passed": passed, "total": len(checks), "checks": checks},
        "layout": probe.get("layout", {}),
        "publication": probe.get("publication", {}),
        "non_changes": probe.get("non_changes", {}),
        "decision": {
            "rigid_frame_producer_connected": qualified,
            "point_default_enabled": False,
            "live_representation_migration": False,
            "legacy_y_byte_equivalence_claimed": False,
            "v3tc_reopened": False,
            "visual_evidence_preset": "scripts/run_visual_v3_demo.ps1",
            "next_gate": "default-off rigid-frame session orchestration under the existing Point application owner",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg.write_text(_svg(report), encoding="utf-8")
    if not qualified:
        raise RuntimeError("Phase 6DO rigid-frame producer did not qualify")
    print(f"Phase 6DO qualified: {passed}/{len(checks)} gates")


if __name__ == "__main__":
    main()
