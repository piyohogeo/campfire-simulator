"""Validate and visualize the Phase 6DM compatibility audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_layout_compatibility_report.json"
DEFAULT_SVG = ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_layout_compatibility_report.svg"


def analyze(raw, raw_path, production_unchanged):
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6dm":
        raise ValueError("Unexpected Phase 6DM raw schema")
    if raw.get("status") != "ok":
        raise ValueError("Phase 6DM audit did not complete successfully")
    checks = dict(raw["gates"]["checks"])
    checks["production_extension_sources_unchanged"] = production_unchanged
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Phase 6DM gates failed: {failed}")
    report = dict(raw)
    report["gates"] = {
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
        "checks": checks,
    }
    report["raw_report"] = str(raw_path.resolve().relative_to(ROOT))
    report["contracts"] = {
        "production_extension_sources_changed": not production_unchanged,
        "production_sphere_default": True,
        "point_emitter_default_off": True,
        "flow_version": "110.0.0",
        "physics_changed": False,
        "wood_json_schema_changed": False,
        "checkpoint_v1_changed": False,
        "usd_stage_changed": False,
        "rollback_changed": False,
        "revision_changed": False,
    }
    return report


def render_svg(report):
    gate_text = f'{report["gates"]["passed"]} / {report["gates"]["total"]}'
    field_count = len(report["audit"]["payload_fields"])
    call_count = len(report["audit"]["payload_constructor_sites"])
    delta_count = len(report["minimum_production_delta"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6DM layout representation compatibility audit</title>
  <desc id="desc">The audit identifies the minimum future Point-specific production delta while keeping wood JSON and checkpoint version 1 unchanged.</desc>
  <rect width="1200" height="680" rx="28" fill="#111827"/>
  <text x="58" y="72" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="32" font-weight="700">Phase 6DM / COMPATIBILITY + MINIMUM DIFF</text>
  <text x="58" y="108" fill="#aebbd0" font-family="Segoe UI, sans-serif" font-size="18">Static AST/source audit · production unchanged · implementation still blocked</text>
  <rect x="58" y="148" width="330" height="190" rx="18" fill="#1d3038" stroke="#4b8496" stroke-width="2"/>
  <text x="82" y="190" fill="#e2f6ff" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Current surface</text>
  <text x="82" y="230" fill="#7ee0b5" font-family="Consolas, monospace" font-size="25" font-weight="700">{field_count} payload fields</text>
  <text x="82" y="268" fill="#c6d4dd" font-family="Segoe UI, sans-serif" font-size="16">{call_count} constructor sites · 1 production</text>
  <text x="82" y="300" fill="#c6d4dd" font-family="Segoe UI, sans-serif" font-size="16">pending payload already reused exactly</text>
  <rect x="414" y="148" width="354" height="190" rx="18" fill="#302a20" stroke="#a98243" stroke-width="2"/>
  <text x="438" y="190" fill="#fff2cf" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Confirmed missing guards</text>
  <text x="438" y="230" fill="#f3bd6d" font-family="Segoe UI, sans-serif" font-size="17">payload / sidecar representation</text>
  <text x="438" y="266" fill="#f3bd6d" font-family="Segoe UI, sans-serif" font-size="17">consumer replacement comparison</text>
  <text x="438" y="302" fill="#f3bd6d" font-family="Segoe UI, sans-serif" font-size="17">static USD representation token</text>
  <rect x="792" y="148" width="350" height="190" rx="18" fill="#272940" stroke="#7378a5" stroke-width="2"/>
  <text x="816" y="190" fill="#eceeff" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Minimum future delta</text>
  <text x="816" y="230" fill="#c9cbff" font-family="Consolas, monospace" font-size="25" font-weight="700">{delta_count} code/test areas</text>
  <text x="816" y="268" fill="#d0d2e8" font-family="Segoe UI, sans-serif" font-size="16">one pre-authored Token · zero live Sets</text>
  <text x="816" y="300" fill="#d0d2e8" font-family="Segoe UI, sans-serif" font-size="16">legacy default · frame explicit opt-in</text>
  <rect x="58" y="380" width="1084" height="184" rx="20" fill="#191f2b" stroke="#465269" stroke-width="2"/>
  <text x="84" y="422" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Compatibility boundary</text>
  <text x="84" y="464" fill="#cad3e0" font-family="Segoe UI, sans-serif" font-size="17">Wood JSON and Resident snapshot schema remain untouched; layout is application state, not wood authority state.</text>
  <text x="84" y="500" fill="#cad3e0" font-family="Segoe UI, sans-serif" font-size="17">Checkpoint v1 stays unchanged because it contains Sphere consumers only; a future Point checkpoint must use a new version.</text>
  <text x="84" y="538" fill="#f2b36f" font-family="Segoe UI, sans-serif" font-size="17" font-weight="700">A legacy Point stage without the token must be regenerated offline, never guessed during a connected session.</text>
  <text x="58" y="620" fill="#72e0af" font-family="Consolas, monospace" font-size="22" font-weight="700">{gate_text} audit gates</text>
  <text x="1142" y="646" text-anchor="end" fill="#778196" font-family="Consolas, monospace" font-size="14">Sphere default / Point OFF / Flow 110.0.0</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--production-unchanged", required=True, choices=("true", "false"))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(
        json.loads(arguments.raw.read_text(encoding="utf-8")),
        arguments.raw,
        arguments.production_unchanged == "true",
    )
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    print(
        f"Phase 6DM layout compatibility: {report['gates']['passed']} / "
        f"{report['gates']['total']} gates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
