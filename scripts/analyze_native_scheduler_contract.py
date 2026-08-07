"""Analyze and visualize the Phase 6BA native scheduler contract."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_REPORT = ASSET_ROOT / "native_scheduler_contract_report.json"
DEFAULT_SVG = ASSET_ROOT / "native_scheduler_contract_report.svg"


def _row(raw, method, label, path):
    means = []
    p95s = []
    maximums = []
    for run in raw["runs"]:
        value = run["timing"]
        for key in path:
            value = value[key]
        if isinstance(value, dict):
            means.append(value["mean_ms"])
            p95s.append(value["p95_ms"])
            maximums.append(value["maximum_ms"])
        else:
            means.append(value)
            p95s.append(value)
            maximums.append(value)
    median_p95 = statistics.median(p95s)
    return {
        "method": method,
        "label": label,
        "median_mean_ms": statistics.median(means),
        "median_p95_ms": median_p95,
        "maximum_observed_ms": max(maximums),
        "meets_4ms_p95": median_p95 <= raw["budget_ms"],
    }


def analyze(raw: dict, raw_path: Path) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6ba":
        raise ValueError("Unexpected Phase 6BA raw schema")
    if not raw["structural_dirty_proof"]["safe_stop"]:
        raise ValueError("Structural dirty did not stop before native execution")
    if any(not run["comparison"]["within_tolerance"] for run in raw["runs"]):
        raise ValueError("Native scheduler exceeded its state/output tolerances")
    if any(
        run["consumer"]["mismatch_count"]
        or not run["consumer"]["strictly_monotonic"]
        or run["consumer"]["maximum_tick_staleness"] != 0
        for run in raw["runs"]
    ):
        raise ValueError("A consumer revision contract failed")
    rows = [
        _row(raw, "update_frame", "Native 5 Hz update frame", ("update_frames",)),
        _row(raw, "all_frames", "All 60 Hz frames", ("all_frames",)),
        _row(
            raw,
            "consumer_only_frame",
            "Consumer-only frame",
            ("consumer_only_frames",),
        ),
        _row(
            raw,
            "managed_dirty_import",
            "Managed one-log preflight",
            ("managed_dirty_import_preflight_ms",),
        ),
    ]
    update = next(row for row in rows if row["method"] == "update_frame")
    comparisons = [run["comparison"] for run in raw["runs"]]
    return {
        "schema_version": 1,
        "phase": "phase6ba",
        "status": "qualified" if update["meets_4ms_p95"] else "rejected",
        "source_raw": str(raw_path),
        "runtime": raw["runtime"],
        "native_toolchain": raw["native_toolchain"],
        "measurement": raw["measurement"],
        "contract": raw["contract"],
        "budget_ms": raw["budget_ms"],
        "method_rows": rows,
        "equivalence": {
            "maximum_temperature_error_k": max(
                row["maximum_temperature_error_k"] for row in comparisons
            ),
            "maximum_cell_mass_error_kg": max(
                row["maximum_cell_mass_error_kg"] for row in comparisons
            ),
            "phase_mismatch_count": max(
                row["phase_mismatch_count"] for row in comparisons
            ),
            "maximum_cumulative_error": max(
                row["maximum_cumulative_error"] for row in comparisons
            ),
            "maximum_published_output_error": max(
                row["maximum_published_output_error"] for row in comparisons
            ),
            "maximum_mass_balance_error_kg": max(
                row["maximum_candidate_mass_balance_error_kg"]
                for row in comparisons
            ),
            "passed": True,
        },
        "consumer": {
            "read_count_per_run": raw["runs"][0]["consumer"]["read_count"],
            "mismatch_count": sum(
                run["consumer"]["mismatch_count"] for run in raw["runs"]
            ),
            "last_revision": raw["runs"][0]["consumer"]["last_revision"],
            "strictly_monotonic_all_runs": True,
            "maximum_tick_staleness": 0,
        },
        "structural_dirty_proof": raw["structural_dirty_proof"],
        "decision": {
            "native_scheduler_contract_qualified": update["meets_4ms_p95"],
            "managed_dirty_preflight_qualified": next(
                row for row in rows if row["method"] == "managed_dirty_import"
            )["meets_4ms_p95"],
            "structural_dirty_safe_stop_qualified": raw["structural_dirty_proof"][
                "safe_stop"
            ],
            "consumer_revision_contract_qualified": True,
            "production_backend_qualified": False,
            "serialization_export_pending": True,
            "unmarked_direct_write_support_pending": True,
            "next_step": (
                "define serialization/export and production backend lifecycle gates, "
                "then run an opt-in Kit application integration trial"
            ),
        },
        "limitations": raw["boundary"]["excluded"],
        "production_model_changed": raw["boundary"]["production_model_changed"],
    }


def render_svg(report: dict) -> str:
    rows = report["method_rows"]
    maximum = max(max(row["median_p95_ms"] for row in rows) * 1.15, 4.8)
    scale = 470.0 / maximum
    budget_x = 390.0 + report["budget_ms"] * scale
    bars = []
    for index, row in enumerate(rows):
        y = 224 + index * 77
        width = row["median_p95_ms"] * scale
        color = "#22c55e" if row["meets_4ms_p95"] else "#fb7185"
        bars.append(
            f'<text x="58" y="{y + 21}" class="label">{row["label"]}</text>'
            f'<rect x="390" y="{y}" width="{width:.1f}" height="32" rx="16" fill="{color}"/>'
            f'<text x="{min(1080.0, 404.0 + width):.1f}" y="{y + 22}" class="value">p95 {row["median_p95_ms"]:.3f} ms</text>'
            f'<text x="390" y="{y + 54}" class="small">mean {row["median_mean_ms"]:.3f} ms</text>'
        )
    equivalence = report["equivalence"]
    consumer = report["consumer"]
    decision = report["decision"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BA native 5 Hz scheduler contract</title>
  <desc id="desc">Twenty logs run a resident native Arrhenius complete step and immutable publication on one of every twelve render frames.</desc>
  <style>.title{{fill:#f8fafc;font:700 29px system-ui,sans-serif}}.sub{{fill:#cbd5e1;font:16px system-ui,sans-serif}}.label{{fill:#f8fafc;font:600 16px system-ui,sans-serif}}.value{{fill:#f8fafc;font:700 15px ui-monospace,monospace}}.small{{fill:#94a3b8;font:14px system-ui,sans-serif}}.decision{{fill:#fde68a;font:700 19px system-ui,sans-serif}}</style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="72" class="title">Commit one immutable snapshot every 12 render frames</text>
  <text x="58" y="108" class="sub">20 logs · 5 Hz native Arrhenius step · 60 Hz consumers · Flow + visual + support share one revision</text>
  <rect x="58" y="137" width="1084" height="57" rx="16" fill="#1e293b"/>
  <text x="82" y="160" class="small">SCHEDULER CONTRACT</text>
  <text x="82" y="184" class="label">ΔT {equivalence["maximum_temperature_error_k"]:.3g} K · Δmass {equivalence["maximum_cell_mass_error_kg"]:.3g} kg · output {equivalence["maximum_published_output_error"]:.3g} · consumer mismatch {consumer["mismatch_count"]}</text>
  <line x1="{budget_x:.1f}" y1="207" x2="{budget_x:.1f}" y2="518" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="211" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="548" width="1084" height="78" rx="18" fill="#1e293b"/>
  <text x="82" y="578" class="decision">Native scheduler contract {'QUALIFIES' if decision['native_scheduler_contract_qualified'] else 'DOES NOT QUALIFY'}; production gate remains closed</text>
  <text x="82" y="607" class="sub">Structural dirty stops before native · next: serialization/export and opt-in Kit lifecycle</text>
  <text x="58" y="656" class="small">Headless architecture trial. Flow, USD, rendering, PhysX, and the production backend are unchanged.</text>
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
