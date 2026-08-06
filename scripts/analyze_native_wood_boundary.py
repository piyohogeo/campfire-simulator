"""Validate and visualize the Phase 6AU native boundary probe."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "devlog" / "assets" / "phase6" / "native_wood_boundary_report.json"
DEFAULT_SVG = ROOT / "docs" / "devlog" / "assets" / "phase6" / "native_wood_boundary_report.svg"
METHODS = ("python_aos", "native_aos_roundtrip", "native_resident_soa")
LABELS = {
    "python_aos": "Python AoS",
    "native_aos_roundtrip": "AoS ↔ native each step",
    "native_resident_soa": "Resident native SoA",
}
WOOD_BUDGET_MS = 4.0


def _median(values):
    return statistics.median(values)


def analyze(raw: dict, raw_path: Path) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6au":
        raise ValueError("Unexpected Phase 6AU raw schema")
    if raw.get("status") != "ok" or not raw["runtime"]["kit_python"]:
        raise ValueError("Benchmark did not complete with Kit Python")
    measurement = raw["measurement"]
    runs = raw["runs"]
    if measurement["log_count"] != 20 or measurement["combined_cell_count"] != 23040:
        raise ValueError("Phase 6AU must measure 20 logs / 23,040 cells")
    if len(runs) < 3 or not measurement["balanced_method_order"]:
        raise ValueError("Phase 6AU requires at least three balanced runs")
    expected_methods = set(METHODS)
    if any(set(run["methods"]) != expected_methods for run in runs):
        raise ValueError("A benchmark run is missing a required method")
    if any(set(run["order"]) != expected_methods for run in runs):
        raise ValueError("A benchmark order is incomplete")

    comparisons = [
        comparison
        for run in runs
        for comparison in run["comparisons"].values()
    ]
    if not all(comparison["within_tolerance"] for comparison in comparisons):
        raise ValueError("A native result exceeded the declared tolerance")
    max_temperature_error = max(
        comparison["maximum_temperature_error_k"] for comparison in comparisons
    )
    max_mass_error = max(
        comparison["maximum_mass_error_kg"] for comparison in comparisons
    )
    max_phase_mismatches = max(
        comparison["phase_mismatch_count"] for comparison in comparisons
    )
    exact_hashes = all(
        comparison["exact_state_sha256_match"] for comparison in comparisons
    )

    rows = []
    for method in METHODS:
        mean_ms = _median(
            [run["methods"][method]["timing"]["mean_ms"] for run in runs]
        )
        p95_ms = _median(
            [run["methods"][method]["timing"]["p95_ms"] for run in runs]
        )
        rows.append(
            {
                "method": method,
                "label": LABELS[method],
                "median_mean_ms": mean_ms,
                "median_p95_ms": p95_ms,
                "meets_4ms_p95": p95_ms <= WOOD_BUDGET_MS,
            }
        )
    by_method = {row["method"]: row for row in rows}
    resident = by_method["native_resident_soa"]
    roundtrip = by_method["native_aos_roundtrip"]
    python = by_method["python_aos"]
    import_ms = _median(
        [
            run["methods"]["native_resident_soa"]["boundary"]["one_time_import_ms"]
            for run in runs
        ]
    )
    export_ms = _median(
        [
            run["methods"]["native_resident_soa"]["boundary"]["one_time_export_ms"]
            for run in runs
        ]
    )
    equivalence_passed = (
        max_temperature_error <= raw["tolerances"]["maximum_temperature_error_k"]
        and max_mass_error <= raw["tolerances"]["maximum_mass_error_kg"]
        and max_phase_mismatches == 0
    )
    boundary_qualified = equivalence_passed and resident["meets_4ms_p95"]
    return {
        "schema_version": 1,
        "phase": "phase6au",
        "status": "ok",
        "measurement": {
            **measurement,
            "scope": "isolated sensible heat + clamp + phase classification",
            "full_solver_measured": False,
        },
        "native_toolchain": raw["native_toolchain"],
        "runtime": raw["runtime"],
        "budget_ms": WOOD_BUDGET_MS,
        "method_rows": rows,
        "boundary_cost": {
            "median_one_time_import_ms": import_ms,
            "median_one_time_export_ms": export_ms,
            "median_one_time_roundtrip_ms": import_ms + export_ms,
        },
        "equivalence": {
            "passed": equivalence_passed,
            "all_exact_state_sha256_match": exact_hashes,
            "maximum_temperature_error_k": max_temperature_error,
            "maximum_mass_error_kg": max_mass_error,
            "maximum_phase_mismatch_count": max_phase_mismatches,
            "tolerances": raw["tolerances"],
        },
        "decision": {
            "resident_native_boundary_qualified": boundary_qualified,
            "per_step_aos_roundtrip_rejected": not roundtrip["meets_4ms_p95"],
            "resident_speedup_vs_python_isolated": (
                python["median_p95_ms"] / resident["median_p95_ms"]
            ),
            "full_native_solver_qualified": False,
            "production_model_changed": raw["boundary"]["production_model_changed"],
            "gpu_work_deferred": True,
            "next_step": (
                "prototype the complete wood step on resident native state, with "
                "serialization and app outputs as explicit synchronization boundaries"
            ),
        },
        "limitations": raw["boundary"]["excluded"],
        "raw_report": str(raw_path.relative_to(ROOT)),
    }


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_svg(report: dict) -> str:
    rows = report["method_rows"]
    maximum = max(max(row["median_p95_ms"] for row in rows) * 1.08, 4.8)
    scale = 460.0 / maximum
    budget_x = 360.0 + report["budget_ms"] * scale
    bars = []
    for index, row in enumerate(rows):
        y = 250 + index * 92
        width = row["median_p95_ms"] * scale
        color = "#22c55e" if row["meets_4ms_p95"] else "#fb7185"
        bars.extend(
            [
                f'<text x="58" y="{y + 22}" class="label">{_escape(row["label"])}</text>',
                f'<rect x="360" y="{y}" width="{width:.1f}" height="34" rx="17" fill="{color}"/>',
                f'<text x="{min(1080.0, 374.0 + width):.1f}" y="{y + 23}" class="value">p95 {row["median_p95_ms"]:.3f} ms</text>',
                f'<text x="360" y="{y + 58}" class="small">mean {row["median_mean_ms"]:.3f} ms</text>',
            ]
        )
    equivalence = report["equivalence"]
    boundary = report["boundary_cost"]
    decision = report["decision"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AU native contiguous wood-state boundary</title>
  <desc id="desc">Twenty-log isolated kernel compares Python object state, per-step conversion, and resident native structure-of-arrays execution.</desc>
  <style>
    .title {{ fill:#f8fafc;font:700 29px system-ui,sans-serif }}
    .sub {{ fill:#cbd5e1;font:16px system-ui,sans-serif }}
    .label {{ fill:#f8fafc;font:600 17px system-ui,sans-serif }}
    .value {{ fill:#f8fafc;font:700 15px ui-monospace,monospace }}
    .small {{ fill:#94a3b8;font:14px system-ui,sans-serif }}
    .decision {{ fill:#fde68a;font:700 19px system-ui,sans-serif }}
  </style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="76" class="title">Keep authoritative wood state contiguous across steps</text>
  <text x="58" y="112" class="sub">20 logs · 23,040 cells · Kit Python · MSVC /O2 /fp:strict · isolated cell-local kernel</text>
  <rect x="58" y="148" width="1084" height="62" rx="16" fill="#1e293b"/>
  <text x="82" y="174" class="small">EQUIVALENCE GATE</text>
  <text x="82" y="198" class="label">ΔT {equivalence["maximum_temperature_error_k"]:.3g} K · Δmass {equivalence["maximum_mass_error_kg"]:.3g} kg · phase {equivalence["maximum_phase_mismatch_count"]} · exact hash {str(equivalence["all_exact_state_sha256_match"]).lower()}</text>
  <line x1="{budget_x:.1f}" y1="230" x2="{budget_x:.1f}" y2="520" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="228" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="542" width="1084" height="82" rx="18" fill="#1e293b"/>
  <text x="82" y="574" class="decision">Resident boundary {'QUALIFIES' if decision['resident_native_boundary_qualified'] else 'DOES NOT QUALIFY'}; per-step object roundtrip {'REJECTED' if decision['per_step_aos_roundtrip_rejected'] else 'within gate'}</text>
  <text x="82" y="603" class="sub">One-time import / export: {boundary["median_one_time_import_ms"]:.3f} / {boundary["median_one_time_export_ms"]:.3f} ms · full conduction/reaction solver not measured</text>
  <text x="58" y="656" class="small">Necessary boundary evidence only. Production physics, JSON schema, Flow, USD, rendering, PhysX, and GPU path remain unchanged.</text>
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

