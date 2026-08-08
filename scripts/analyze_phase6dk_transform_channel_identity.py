"""Validate and visualize Phase 6DK USD transform/channel identity evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_transform_channel_report.json"
DEFAULT_SVG = ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_transform_channel_report.svg"


def analyze(raw: dict, raw_path: Path, app_unchanged: bool, native_unchanged: bool) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6dk":
        raise ValueError("Unexpected Phase 6DK raw schema")
    if raw.get("status") != "ok":
        raise ValueError(f"Phase 6DK probe failed: {raw.get('error', 'unknown error')}")
    checks = dict(raw["gates"]["checks"])
    checks["production_app_unchanged"] = app_unchanged
    checks["production_native_source_unchanged"] = native_unchanged
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Phase 6DK gates failed: {failed}")
    report = dict(raw)
    report["gates"] = {
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
        "checks": checks,
    }
    report["raw_report"] = str(raw_path.resolve().relative_to(ROOT))
    report["contracts"] = {
        "production_app_changed": not app_unchanged,
        "production_native_source_changed": not native_unchanged,
        "production_sphere_default": True,
        "point_emitter_default_off": True,
        "flow_version": "110.0.0",
        "physics_changed": False,
        "json_schema_changed": False,
        "serialization_changed": False,
        "rollback_changed": False,
        "revision_changed": False,
        "immutable_snapshot_changed": False,
    }
    return report


def render_svg(report: dict) -> str:
    identity = report["position_identity"]
    legacy = report["legacy_y_channel_boundary"]
    gate_text = f'{report["gates"]["passed"]} / {report["gates"]["total"]}'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6DK USD transform and surface-channel identity</title>
  <desc id="desc">Production wood USD transforms produce correct right-handed frames and preserve stable surface-cell channel identity, while the legacy Y reflection misplaces cell-varying temperatures.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#1f2937"/></linearGradient></defs>
  <rect width="1200" height="680" rx="28" fill="url(#bg)"/>
  <text x="58" y="72" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="32" font-weight="700">Phase 6DK / USD TRANSFORM + CELL IDENTITY</text>
  <text x="58" y="108" fill="#bbc6d8" font-family="Segoe UI, sans-serif" font-size="18">Production wood authoring / anonymous USD stage / two independent 720-point scenarios</text>
  <rect x="58" y="148" width="330" height="184" rx="18" fill="#1f3340" stroke="#4f8198" stroke-width="2"/>
  <text x="82" y="188" fill="#dff5ff" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">USD frame extraction</text>
  <text x="82" y="232" fill="#73dfb3" font-family="Consolas, monospace" font-size="27" font-weight="700">{gate_text} gates</text>
  <text x="82" y="273" fill="#c2d2df" font-family="Segoe UI, sans-serif" font-size="16">right-handed / orthonormal</text>
  <text x="82" y="302" fill="#c2d2df" font-family="Segoe UI, sans-serif" font-size="16">translate + orient sampled once</text>
  <rect x="414" y="148" width="354" height="184" rx="18" fill="#252c3d" stroke="#68749b" stroke-width="2"/>
  <text x="438" y="188" fill="#e6eaff" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Stable cell identity</text>
  <text x="438" y="231" fill="#c9d2eb" font-family="Consolas, monospace" font-size="17">cardinal error {identity['cardinal_max_error_m']:.3g} m</text>
  <text x="438" y="268" fill="#c9d2eb" font-family="Consolas, monospace" font-size="17">45-deg + 3D {identity['arbitrary_max_error_m']:.3g} m</text>
  <text x="438" y="302" fill="#aab5d1" font-family="Segoe UI, sans-serif" font-size="15">position + fuel + temperature + smoke</text>
  <rect x="792" y="148" width="350" height="184" rx="18" fill="#3a2925" stroke="#b56e4d" stroke-width="2"/>
  <text x="816" y="188" fill="#ffe2d3" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Legacy Y reflection</text>
  <text x="816" y="232" fill="#ffad78" font-family="Consolas, monospace" font-size="24" font-weight="700">TEMP {legacy['temperature_mismatch_count']} / {legacy['common_coordinate_count']}</text>
  <text x="816" y="271" fill="#e4c4b5" font-family="Segoe UI, sans-serif" font-size="16">fuel mismatch {legacy['fuel_mismatch_count']}</text>
  <text x="816" y="302" fill="#e4c4b5" font-family="Segoe UI, sans-serif" font-size="16">smoke mismatch {legacy['smoke_mismatch_count']}</text>
  <rect x="58" y="372" width="1084" height="210" rx="20" fill="#171d29" stroke="#424b61" stroke-width="2"/>
  <text x="82" y="414" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Decision boundary</text>
  <text x="82" y="456" fill="#c7d0df" font-family="Segoe UI, sans-serif" font-size="17">The frame kernel preserves the original surface-cell order for cardinal, 45-degree, and 3D USD transforms.</text>
  <text x="82" y="490" fill="#c7d0df" font-family="Segoe UI, sans-serif" font-size="17">The legacy Y point set is complete, but its reflection assigns all cell-varying temperatures to other coordinates.</text>
  <text x="82" y="530" fill="#f2b36f" font-family="Segoe UI, sans-serif" font-size="17" font-weight="700">Integration remains blocked until an explicit migration policy for existing Y layouts is selected.</text>
  <text x="82" y="560" fill="#a7b1c4" font-family="Segoe UI, sans-serif" font-size="15">No Kit-context stage, Flow simulation, USD Point publication, payload, revision, or rollback change.</text>
  <text x="1142" y="642" text-anchor="end" fill="#7f899d" font-family="Consolas, monospace" font-size="14">Sphere default / Point OFF / Flow 110.0.0</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--production-app-unchanged", required=True, choices=("true", "false"))
    parser.add_argument("--production-native-source-unchanged", required=True, choices=("true", "false"))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(
        json.loads(arguments.raw.read_text(encoding="utf-8")),
        arguments.raw,
        arguments.production_app_unchanged == "true",
        arguments.production_native_source_unchanged == "true",
    )
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    print(f"Phase 6DK transform/channel identity: {report['gates']['passed']} / {report['gates']['total']} gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
