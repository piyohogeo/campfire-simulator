"""Validate and visualize Phase 6DL layout-representation evidence."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_layout_representation_report.json"
DEFAULT_SVG = ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_layout_representation_report.svg"


def analyze(raw, raw_path, production_unchanged):
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6dl":
        raise ValueError("Unexpected Phase 6DL raw schema")
    if raw.get("status") != "ok":
        raise ValueError("Phase 6DL probe did not complete successfully")
    checks = dict(raw["gates"]["checks"])
    checks["production_extension_sources_unchanged"] = production_unchanged
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Phase 6DL gates failed: {failed}")
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
        "json_schema_changed": False,
        "serialization_changed": False,
        "usd_save_changed": False,
        "rollback_changed": False,
        "revision_changed": False,
        "immutable_snapshot_changed": False,
    }
    return report


def render_svg(report):
    gate_text = f'{report["gates"]["passed"]} / {report["gates"]["total"]}'
    p95 = report["digest_timing_ms"]["p95"]
    byte_count = report["representations"]["same_numeric_array_bytes"]
    legacy = html.escape(report["representations"]["legacy"])
    frame = html.escape(report["representations"]["frame"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6DL immutable layout representation prototype</title>
  <desc id="desc">Legacy and rigid-frame payloads keep their representation fixed through rollback, retry, and replacement-consumer recovery without production changes.</desc>
  <rect width="1200" height="680" rx="28" fill="#111827"/>
  <text x="58" y="72" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="32" font-weight="700">Phase 6DL / IMMUTABLE LAYOUT REPRESENTATION</text>
  <text x="58" y="108" fill="#aebbd0" font-family="Segoe UI, sans-serif" font-size="18">Isolated session wrapper / no USD or Flow / production ResidentApplicationSession unchanged</text>
  <rect x="58" y="150" width="514" height="166" rx="18" fill="#172f35" stroke="#3f8992" stroke-width="2"/>
  <text x="84" y="192" fill="#d9fbff" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Legacy lane</text>
  <text x="84" y="232" fill="#8ae3c1" font-family="Consolas, monospace" font-size="18">{legacy}</text>
  <text x="84" y="270" fill="#c1d7dc" font-family="Segoe UI, sans-serif" font-size="17">commit 1 → fail 2 → rollback 1 → exact retry 2 → commit 3</text>
  <text x="84" y="298" fill="#9fb8bf" font-family="Segoe UI, sans-serif" font-size="15">wrong frame replacement rejected before consumer close</text>
  <rect x="628" y="150" width="514" height="166" rx="18" fill="#28283e" stroke="#7274a4" stroke-width="2"/>
  <text x="654" y="192" fill="#ececff" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Rigid-frame lane</text>
  <text x="654" y="232" fill="#b9baff" font-family="Consolas, monospace" font-size="18">{frame}</text>
  <text x="654" y="270" fill="#d1d2e6" font-family="Segoe UI, sans-serif" font-size="17">commit 1 → fail 2 → rollback 1 → exact retry 2 → commit 3</text>
  <text x="654" y="298" fill="#b2b3cc" font-family="Segoe UI, sans-serif" font-size="15">wrong legacy replacement rejected before consumer close</text>
  <rect x="58" y="354" width="1084" height="202" rx="20" fill="#191f2b" stroke="#465269" stroke-width="2"/>
  <text x="84" y="398" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">One rule across failure and recovery</text>
  <text x="84" y="440" fill="#cad3e0" font-family="Segoe UI, sans-serif" font-size="17">Representation and its immutable descriptor are in the payload digest; equal numeric arrays cannot hide a layout-mode change.</text>
  <text x="84" y="476" fill="#cad3e0" font-family="Segoe UI, sans-serif" font-size="17">A replacement consumer accepts an equal descriptor value, not object identity, and retries the original pending payload object.</text>
  <text x="84" y="518" fill="#f2b36f" font-family="Segoe UI, sans-serif" font-size="17" font-weight="700">Live legacy ↔ frame migration remains forbidden; production integration remains unqualified.</text>
  <text x="58" y="616" fill="#72e0af" font-family="Consolas, monospace" font-size="22" font-weight="700">{gate_text} gates</text>
  <text x="330" y="616" fill="#aebbd0" font-family="Consolas, monospace" font-size="16">same arrays {byte_count:,} B · digest p95 {p95:.4f} ms</text>
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
        f"Phase 6DL layout representation: {report['gates']['passed']} / "
        f"{report['gates']['total']} gates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
