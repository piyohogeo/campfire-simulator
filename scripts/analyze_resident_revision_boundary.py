"""Analyze and visualize the Phase 6AZ revision/dirty ownership trial."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_REPORT = ASSET_ROOT / "resident_revision_boundary_report.json"
DEFAULT_SVG = ASSET_ROOT / "resident_revision_boundary_report.svg"
LABELS = {
    "clean_revision_check": "20-log revision check",
    "one_log_dirty_sync": "One dirty log import",
    "full_twenty_log_import": "Full 20-log import",
}


def analyze(raw: dict, raw_path: Path) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6az":
        raise ValueError("Unexpected Phase 6AZ raw schema")
    proof = raw["proof"]
    if not proof["state_mutation"]["array_equivalence"]["passed"]:
        raise ValueError("One-log dirty import did not reproduce the public state")
    if proof["structural_mutation"]["rebuild_required_logs"] != [
        proof["state_mutation"]["log_index"]
    ]:
        raise ValueError("Structural mutation did not request a rebuild")
    if proof["unmarked_legacy_mutation"]["detected_by_revision_check"]:
        raise ValueError("Revision check unexpectedly detected an unmarked write")
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
    check = next(row for row in rows if row["method"] == "clean_revision_check")
    dirty = next(row for row in rows if row["method"] == "one_log_dirty_sync")
    full = next(row for row in rows if row["method"] == "full_twenty_log_import")
    return {
        "schema_version": 1,
        "phase": "phase6az",
        "status": "qualified" if check["meets_4ms_p95"] and dirty["meets_4ms_p95"] else "rejected",
        "source_raw": str(raw_path),
        "runtime": raw["runtime"],
        "source_sha256": raw["source_sha256"],
        "measurement": raw["measurement"],
        "contract": raw["contract"],
        "proof": proof,
        "budget_ms": raw["budget_ms"],
        "method_rows": rows,
        "decision": {
            "explicit_revision_check_qualified": check["meets_4ms_p95"],
            "one_log_dirty_import_qualified": dirty["meets_4ms_p95"],
            "full_import_each_tick_rejected": not full["meets_4ms_p95"],
            "unmarked_legacy_write_compatible": False,
            "production_backend_qualified": False,
            "scheduler_integration_pending": True,
            "full_import_slowdown_vs_one_dirty": full["median_p95_ms"]
            / dirty["median_p95_ms"],
            "next_step": (
                "integrate the explicit ownership boundary with the 5 Hz / 12-slot "
                "scheduler and verify immutable consumer revisions"
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
    proof = report["proof"]
    decision = report["decision"]
    equivalence = proof["state_mutation"]["array_equivalence"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AZ explicit revision and dirty ownership</title>
  <desc id="desc">Twenty logs compare a clean revision check, one dirty log import, and a full twenty-log import.</desc>
  <style>.title{{fill:#f8fafc;font:700 29px system-ui,sans-serif}}.sub{{fill:#cbd5e1;font:16px system-ui,sans-serif}}.label{{fill:#f8fafc;font:600 16px system-ui,sans-serif}}.value{{fill:#f8fafc;font:700 15px ui-monospace,monospace}}.small{{fill:#94a3b8;font:14px system-ui,sans-serif}}.decision{{fill:#fde68a;font:700 19px system-ui,sans-serif}}</style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="76" class="title">Check ownership metadata, not every public cell</text>
  <text x="58" y="112" class="sub">20 logs · explicit revision/dirty marks · one-log state import · structural rebuild classification</text>
  <rect x="58" y="148" width="1084" height="62" rx="16" fill="#1e293b"/>
  <text x="82" y="174" class="small">OWNERSHIP CONTRACT</text>
  <text x="82" y="198" class="label">one dirty log exact: Δ {equivalence["maximum_absolute_float_error"]:.0f} · volume edit → rebuild · unmarked direct write intentionally unsupported</text>
  <line x1="{budget_x:.1f}" y1="230" x2="{budget_x:.1f}" y2="520" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="228" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="542" width="1084" height="82" rx="18" fill="#1e293b"/>
  <text x="82" y="574" class="decision">Revision check + one-log import {'QUALIFY' if report['status'] == 'qualified' else 'DO NOT QUALIFY'}; every-tick full import rejected</text>
  <text x="82" y="603" class="sub">Next: 5 Hz / 12-slot scheduler integration and immutable consumer-revision audit</text>
  <text x="58" y="656" class="small">Architecture trial only. Existing public writes still work in Python mode; native mode requires an explicit managed edit or dirty mark.</text>
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
