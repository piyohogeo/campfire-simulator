"""Combine Phase 6DN static and Kit runtime representation evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def svg(report):
    audit = report["audit_gates"]
    runtime = report["runtime_gates"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DN immutable layout representation contract</title><desc id="desc">The legacy cardinal layout remains the default while payload, stage, session replacement, retry identity, and owner state reject representation changes.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0d1720"/><stop offset="1" stop-color="#17243a"/></linearGradient></defs><rect width="1200" height="680" rx="30" fill="url(#bg)"/>
<g font-family="Segoe UI, sans-serif"><text x="70" y="68" fill="#93c5fd" font-size="18" font-weight="700" letter-spacing="3">PHASE 6DN · REPRESENTATION CONTRACT</text><text x="70" y="118" fill="#f8fafc" font-size="38" font-weight="800">Mode identity is immutable before rigid-frame work</text><text x="70" y="154" fill="#a7b2c2" font-size="18">Resumes the Phase 6DM minimum delta · Point remains default OFF · V3T-C remains stopped</text>
<rect x="70" y="198" width="330" height="168" rx="18" fill="#10261f" stroke="#34d399"/><text x="96" y="238" fill="#d1fae5" font-size="18">Static contract</text><text x="96" y="292" fill="#6ee7b7" font-size="34" font-weight="800">{audit['passed']} / {audit['total']}</text><text x="96" y="330" fill="#a7f3d0" font-size="17">payload · USD token · owner · defaults</text>
<rect x="435" y="198" width="330" height="168" rx="18" fill="#172554" stroke="#60a5fa"/><text x="461" y="238" fill="#dbeafe" font-size="18">Kit runtime</text><text x="461" y="292" fill="#93c5fd" font-size="34" font-weight="800">{runtime['passed']} / {runtime['total']}</text><text x="461" y="330" fill="#bfdbfe" font-size="17">publish · mismatch · rebind · close</text>
<rect x="800" y="198" width="330" height="168" rx="18" fill="#312e1b" stroke="#fbbf24"/><text x="826" y="238" fill="#fef3c7" font-size="18">Reserved, not connected</text><text x="826" y="286" fill="#fbbf24" font-size="27" font-weight="800">rigid_frame_v1</text><text x="826" y="330" fill="#fde68a" font-size="17">producer and native ABI unchanged</text>
<rect x="70" y="400" width="1060" height="148" rx="18" fill="#111e2a"/><text x="96" y="441" fill="#f8fafc" font-size="22" font-weight="700">legacy_cardinal_axes_v1 remains the only active representation</text><text x="96" y="482" fill="#cbd5e1" font-size="18">Token is authored once before stage connection. Payload mismatch is rejected before attempt accounting.</text><text x="96" y="518" fill="#cbd5e1" font-size="18">Replacement mismatch preserves old consumers; checkpoint v1, wood JSON, snapshot, Flow, and defaults do not change.</text>
<text x="70" y="610" fill="#94a3b8" font-size="17">Next independent gate: connect a rigid-frame producer only after representation/lifecycle evidence stays green.</text></g></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    audit = read(args.audit)
    probe = read(args.probe)
    audit_checks = audit["checks"]
    runtime_checks = probe["gates"]
    report = {
        "schema": "campfire.phase6dn.layout_representation_report.v1",
        "phase": "phase6dn",
        "status": (
            "qualified_default_off"
            if audit["status"] == probe["status"] == "ok"
            and all(audit_checks.values())
            and all(runtime_checks.values())
            else "failed"
        ),
        "resumes": audit["resumes"],
        "audit_gates": {
            "passed": sum(audit_checks.values()),
            "total": len(audit_checks),
            "checks": audit_checks,
        },
        "runtime_gates": {
            "passed": sum(runtime_checks.values()),
            "total": len(runtime_checks),
            "checks": runtime_checks,
        },
        "representations": audit["representations"],
        "runtime": probe,
        "source_sha256": audit["source_sha256"],
        "non_changes": audit["non_changes"],
        "decision": {
            "representation_contract_qualified": True,
            "point_default_enabled": False,
            "rigid_frame_producer_connected": False,
            "v3tc_reopened": False,
            "v3tc_safe_stop": True,
            "visual_evidence_preset": "scripts/run_visual_v3_demo.ps1",
            "v3_remaining_bottleneck": "public CPU texture upload boundary",
            "v3_reopen_conditions": [
                "public direct-GPU texture update API",
                "Kit or Flow upgrade evaluation",
                "demonstrated operator impact",
            ],
            "next_gate": "default-off rigid-frame producer with byte/revision equivalence",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg.write_text(svg(report), encoding="utf-8")
    if report["status"] != "qualified_default_off":
        raise RuntimeError("Phase 6DN layout representation did not qualify")
    print(
        f"Phase 6DN qualified: static={report['audit_gates']['passed']}/"
        f"{report['audit_gates']['total']}, runtime={report['runtime_gates']['passed']}/"
        f"{report['runtime_gates']['total']}"
    )


if __name__ == "__main__":
    main()
