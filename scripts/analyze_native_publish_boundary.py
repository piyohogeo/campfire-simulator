"""Analyze and visualize the Phase 6AY native publication boundary."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_REPORT = ASSET_ROOT / "native_publish_boundary_report.json"
DEFAULT_SVG = ASSET_ROOT / "native_publish_boundary_report.svg"

LABELS = {
    "python_object_publish": "Python object publish",
    "native_resident_publish": "Native resident publish",
    "public_mutable_guard_scan": "Full public-state guard scan",
}


def analyze(raw: dict, raw_path: Path) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6ay":
        raise ValueError("Unexpected Phase 6AY raw schema")
    if not raw["equivalence"]["passed"] or not raw["mutation_probe"]["detected"]:
        raise ValueError("Phase 6AY equivalence or mutation detection failed")
    rows = []
    for method, label in LABELS.items():
        means = [run["methods"][method]["mean_ms"] for run in raw["runs"]]
        p95s = [run["methods"][method]["p95_ms"] for run in raw["runs"]]
        median_mean = statistics.median(means)
        median_p95 = statistics.median(p95s)
        rows.append(
            {
                "method": method,
                "label": label,
                "median_mean_ms": median_mean,
                "median_p95_ms": median_p95,
                "meets_4ms_p95": median_p95 <= raw["budget_ms"],
            }
        )
    native = next(row for row in rows if row["method"] == "native_resident_publish")
    python = next(row for row in rows if row["method"] == "python_object_publish")
    guard = next(row for row in rows if row["method"] == "public_mutable_guard_scan")
    return {
        "schema_version": 1,
        "phase": "phase6ay",
        "status": "qualified" if native["meets_4ms_p95"] else "rejected",
        "source_raw": str(raw_path),
        "runtime": raw["runtime"],
        "native_toolchain": raw["native_toolchain"],
        "measurement": raw["measurement"],
        "contract": raw["contract"],
        "budget_ms": raw["budget_ms"],
        "method_rows": rows,
        "equivalence": raw["equivalence"],
        "mutation_probe": raw["mutation_probe"],
        "decision": {
            "resident_publish_boundary_qualified": native["meets_4ms_p95"],
            "native_speedup_vs_python": python["median_p95_ms"]
            / native["median_p95_ms"],
            "transparent_full_scan_fallback_qualified": guard["meets_4ms_p95"],
            "production_backend_qualified": False,
            "scheduler_integration_pending": True,
            "next_step": (
                "add an explicit revision/dirty boundary, then integrate the immutable "
                "published snapshot into the 5 Hz app scheduler"
            ),
        },
        "limitations": raw["boundary"]["excluded"],
        "production_model_changed": raw["boundary"]["production_model_changed"],
    }


def render_svg(report: dict) -> str:
    rows = report["method_rows"]
    maximum = max(max(row["median_p95_ms"] for row in rows) * 1.08, 4.8)
    scale = 470.0 / maximum
    budget_x = 390.0 + report["budget_ms"] * scale
    bars = []
    for index, row in enumerate(rows):
        y = 250 + index * 92
        width = row["median_p95_ms"] * scale
        color = "#22c55e" if row["meets_4ms_p95"] else "#fb7185"
        bars.append(
            f'<text x="58" y="{y + 22}" class="label">{row["label"]}</text>'
            f'<rect x="390" y="{y}" width="{width:.1f}" height="34" rx="17" fill="{color}"/>'
            f'<text x="{min(1080.0, 404.0 + width):.1f}" y="{y + 23}" class="value">p95 {row["median_p95_ms"]:.3f} ms</text>'
            f'<text x="390" y="{y + 58}" class="small">mean {row["median_mean_ms"]:.3f} ms</text>'
        )
    decision = report["decision"]
    equivalence = report["equivalence"]
    mutation = report["mutation_probe"]
    guard_text = (
        "fits the budget" if decision["transparent_full_scan_fallback_qualified"] else "is too costly"
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AY native resident output publication</title>
  <desc id="desc">Twenty logs compare Python publication, native resident aggregation, and a full public mutable state scan.</desc>
  <style>.title{{fill:#f8fafc;font:700 29px system-ui,sans-serif}}.sub{{fill:#cbd5e1;font:16px system-ui,sans-serif}}.label{{fill:#f8fafc;font:600 16px system-ui,sans-serif}}.value{{fill:#f8fafc;font:700 15px ui-monospace,monospace}}.small{{fill:#94a3b8;font:14px system-ui,sans-serif}}.decision{{fill:#fde68a;font:700 19px system-ui,sans-serif}}</style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="76" class="title">Publish app outputs without leaving resident SoA</text>
  <text x="58" y="112" class="sub">20 logs · 11 immutable values/log · runtime metrics + Flow source + support ratio</text>
  <rect x="58" y="148" width="1084" height="62" rx="16" fill="#1e293b"/>
  <text x="82" y="174" class="small">PUBLICATION CONTRACT</text>
  <text x="82" y="198" class="label">max error {equivalence["maximum_absolute_error"]:.3g} · injected +{mutation["injected_delta_k"]:.0f} K mutation detected · production unchanged</text>
  <line x1="{budget_x:.1f}" y1="230" x2="{budget_x:.1f}" y2="520" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="228" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="542" width="1084" height="82" rx="18" fill="#1e293b"/>
  <text x="82" y="574" class="decision">Resident publication {'QUALIFIES' if decision['resident_publish_boundary_qualified'] else 'DOES NOT QUALIFY'}; full transparent guard {guard_text}</text>
  <text x="82" y="603" class="sub">Next: explicit revision/dirty ownership, then immutable snapshots in the 5 Hz scheduler</text>
  <text x="58" y="656" class="small">Headless architecture trial only. Flow, USD, rendering, PhysX, and production backend are unchanged.</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    report = analyze(raw, arguments.raw.resolve())
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
