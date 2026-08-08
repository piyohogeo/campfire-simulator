"""Validate and visualize the isolated Phase 6DJ rigid-frame layout spike."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_surface_frame_report.json"
)
DEFAULT_SVG = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_surface_frame_report.svg"
)


def analyze(raw: dict, raw_path: Path) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6dj":
        raise ValueError("Unexpected Phase 6DJ report schema")
    gates = raw.get("gates", {})
    if raw.get("status") != "ok" or gates.get("passed") != gates.get("total"):
        raise ValueError("Phase 6DJ correctness gates did not pass")
    if raw["measurement"]["point_count"] != 720:
        raise ValueError("Phase 6DJ first spike must use 720 points")
    if not raw["decision"]["legacy_y_mapping_is_reflection"]:
        raise ValueError("Legacy Y handedness boundary was not recorded")
    return {
        **raw,
        "scope": "isolated additive native frame ABI; no USD stage or production integration",
        "raw_report": str(raw_path.resolve().relative_to(ROOT)),
        "contracts": {
            "production_native_source_changed": False,
            "production_sphere_default": True,
            "point_emitter_default_off": True,
            "flow_version": "110.0.0",
            "physics_changed": False,
            "json_schema_changed": False,
            "serialization_changed": False,
            "rollback_changed": False,
            "revision_changed": False,
            "immutable_snapshot_changed": False,
        },
    }


def render_svg(report: dict) -> str:
    equivalence = report["equivalence"]
    legacy = report["timing"]["legacy_cardinal_720_points"]
    frame = report["timing"]["rigid_frame_720_points"]
    gate_text = f'{report["gates"]["passed"]} / {report["gates"]["total"]}'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6DJ isolated rigid-frame surface layout result</title>
  <desc id="desc">The additive frame kernel passes correctness and atomic-failure gates while exposing that the legacy Y mapping is a reflection rather than a rigid rotation.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#111827"/><stop offset="1" stop-color="#29213b"/></linearGradient>
  </defs>
  <rect width="1200" height="680" rx="28" fill="url(#bg)"/>
  <text x="58" y="72" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="32" font-weight="700">Phase 6DJ / ISOLATED NATIVE FRAME SPIKE</text>
  <text x="58" y="108" fill="#b8c1d6" font-family="Segoe UI, sans-serif" font-size="18">2 logs x 360 surface cells = 720 points / no USD stage / production source unchanged</text>
  <rect x="58" y="146" width="332" height="184" rx="18" fill="#202b3d" stroke="#52749c" stroke-width="2"/>
  <text x="82" y="184" fill="#dbeafe" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Rigid-frame correctness</text>
  <text x="82" y="226" fill="#76e0b5" font-family="Consolas, monospace" font-size="27" font-weight="700">{html.escape(gate_text)} gates</text>
  <text x="82" y="265" fill="#c9d5e7" font-family="Segoe UI, sans-serif" font-size="16">45-deg max error {equivalence['rotation_45_reference_max_error_m']:.3g} m</text>
  <text x="82" y="294" fill="#c9d5e7" font-family="Segoe UI, sans-serif" font-size="16">3D max error {equivalence['rotation_3d_reference_max_error_m']:.3g} m</text>
  <rect x="414" y="146" width="354" height="184" rx="18" fill="#342b32" stroke="#b47857" stroke-width="2"/>
  <text x="438" y="184" fill="#ffe2c7" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">Legacy Y handedness</text>
  <text x="438" y="226" fill="#f6ae72" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">REFLECTION FOUND</text>
  <text x="438" y="265" fill="#e2c9b8" font-family="Segoe UI, sans-serif" font-size="16">same-index delta {equivalence['cardinal_y_same_index_max_error_m']:.4f} m</text>
  <text x="438" y="294" fill="#e2c9b8" font-family="Segoe UI, sans-serif" font-size="16">sorted point-set delta {equivalence['cardinal_y_sorted_point_set_max_error_m']:.3g} m</text>
  <rect x="792" y="146" width="350" height="184" rx="18" fill="#262b38" stroke="#777f99" stroke-width="2"/>
  <text x="816" y="184" fill="#e8eaf2" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">720-point local timing</text>
  <text x="816" y="229" fill="#c8d0e3" font-family="Consolas, monospace" font-size="17">legacy p95 {legacy['p95_ms']:.4f} ms</text>
  <text x="816" y="265" fill="#c8d0e3" font-family="Consolas, monospace" font-size="17">frame  p95 {frame['p95_ms']:.4f} ms</text>
  <text x="816" y="299" fill="#969fb7" font-family="Segoe UI, sans-serif" font-size="15">isolated kernel only; not USD timing</text>
  <rect x="58" y="370" width="1084" height="210" rx="20" fill="#171c29" stroke="#41495e" stroke-width="2"/>
  <text x="82" y="412" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Decision boundary</text>
  <text x="82" y="454" fill="#c8d0e3" font-family="Segoe UI, sans-serif" font-size="17">Identity-X remains byte exact. Proper 90-degree Y rotation preserves the geometric point set,</text>
  <text x="82" y="486" fill="#c8d0e3" font-family="Segoe UI, sans-serif" font-size="17">but not per-cell ordering, because the legacy axis swap has determinant -1.</text>
  <text x="82" y="526" fill="#f4b86e" font-family="Segoe UI, sans-serif" font-size="17" font-weight="700">Do not integrate until fuel / temperature / smoke channel alignment is qualified.</text>
  <text x="82" y="556" fill="#aab3c8" font-family="Segoe UI, sans-serif" font-size="15">Scale, shear, reflection, NaN, and insufficient capacity fail without changing output or count.</text>
  <text x="1142" y="642" text-anchor="end" fill="#7f889e" font-family="Consolas, monospace" font-size="14">Point default OFF / Flow 110.0.0 unchanged</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    report = analyze(raw, arguments.raw)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    print(f"Wrote {arguments.report}")
    print(f"Wrote {arguments.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
