"""Validate and visualize the Phase 6AV native conduction boundary."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_REPORT = ASSET_ROOT / "native_conduction_boundary_report.json"
DEFAULT_SVG = ASSET_ROOT / "native_conduction_boundary_report.svg"
PRIOR_REPORT = ASSET_ROOT / "native_wood_boundary_report.json"
METHODS = (
    "python_aos_conduction",
    "native_aos_roundtrip_conduction",
    "native_resident_soa_conduction",
)
LABELS = {
    "python_aos_conduction": "Python AoS + conduction",
    "native_aos_roundtrip_conduction": "AoS ↔ native each step",
    "native_resident_soa_conduction": "Resident native + conduction",
}
BUDGET_MS = 4.0


def analyze(raw: dict, raw_path: Path, prior: dict) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6av":
        raise ValueError("Unexpected Phase 6AV raw schema")
    if raw.get("status") != "ok" or not raw["runtime"]["kit_python"]:
        raise ValueError("Phase 6AV did not complete with Kit Python")
    measurement = raw["measurement"]
    runs = raw["runs"]
    if measurement["log_count"] != 20 or measurement["combined_cell_count"] != 23040:
        raise ValueError("Phase 6AV requires 20 logs / 23,040 cells")
    if len(runs) < 3 or not measurement["balanced_method_order"]:
        raise ValueError("Phase 6AV requires at least three balanced runs")
    if any(set(run["methods"]) != set(METHODS) for run in runs):
        raise ValueError("A Phase 6AV method is missing")
    comparisons = [
        comparison
        for run in runs
        for comparison in run["comparisons"].values()
    ]
    if not all(comparison["within_tolerance"] for comparison in comparisons):
        raise ValueError("Native conduction exceeded the state tolerance")
    maximum_balance_error = max(
        method["conduction_balance_error_j"]
        for run in runs
        for method in run["methods"].values()
    )
    if maximum_balance_error > raw["tolerances"]["maximum_conduction_balance_error_j"]:
        raise ValueError("Pairwise conduction violated energy conservation")

    rows = []
    for name in METHODS:
        mean_ms = statistics.median(
            run["methods"][name]["timing"]["mean_ms"] for run in runs
        )
        p95_ms = statistics.median(
            run["methods"][name]["timing"]["p95_ms"] for run in runs
        )
        rows.append(
            {
                "method": name,
                "label": LABELS[name],
                "median_mean_ms": mean_ms,
                "median_p95_ms": p95_ms,
                "meets_4ms_p95": p95_ms <= BUDGET_MS,
            }
        )
    by_name = {row["method"]: row for row in rows}
    resident = by_name["native_resident_soa_conduction"]
    python = by_name["python_aos_conduction"]
    roundtrip = by_name["native_aos_roundtrip_conduction"]
    import_ms = statistics.median(
        run["methods"]["native_resident_soa_conduction"]["boundary"]["one_time_import_ms"]
        for run in runs
    )
    export_ms = statistics.median(
        run["methods"]["native_resident_soa_conduction"]["boundary"]["one_time_export_ms"]
        for run in runs
    )
    max_temperature_error = max(
        comparison["maximum_temperature_error_k"] for comparison in comparisons
    )
    max_mass_error = max(
        comparison["maximum_mass_error_kg"] for comparison in comparisons
    )
    max_phase_mismatch = max(
        comparison["phase_mismatch_count"] for comparison in comparisons
    )
    exact_hash = all(
        comparison["exact_state_sha256_match"] for comparison in comparisons
    )
    prior_resident = next(
        row for row in prior["method_rows"] if row["method"] == "native_resident_soa"
    )
    return {
        "schema_version": 1,
        "phase": "phase6av",
        "status": "ok",
        "measurement": {
            **measurement,
            "scope": "immutable pair topology + conduction + sensible + finalize",
            "full_solver_measured": False,
        },
        "runtime": raw["runtime"],
        "native_toolchain": raw["native_toolchain"],
        "budget_ms": BUDGET_MS,
        "method_rows": rows,
        "boundary_cost": {
            "median_one_time_import_ms": import_ms,
            "median_one_time_export_ms": export_ms,
        },
        "equivalence": {
            "passed": True,
            "all_exact_state_sha256_match": exact_hash,
            "maximum_temperature_error_k": max_temperature_error,
            "maximum_mass_error_kg": max_mass_error,
            "maximum_phase_mismatch_count": max_phase_mismatch,
            "maximum_conduction_balance_error_j": maximum_balance_error,
        },
        "prior_context": {
            "phase6au_resident_p95_ms": prior_resident["median_p95_ms"],
            "added_topology_p95_ms": (
                resident["median_p95_ms"] - prior_resident["median_p95_ms"]
            ),
        },
        "decision": {
            "resident_conduction_boundary_qualified": resident["meets_4ms_p95"],
            "per_step_aos_roundtrip_rejected": not roundtrip["meets_4ms_p95"],
            "resident_speedup_vs_python": python["median_p95_ms"] / resident["median_p95_ms"],
            "full_native_solver_qualified": False,
            "production_model_changed": raw["boundary"]["production_model_changed"],
            "next_step": "add evaporation and reaction state/output accumulators to the resident ABI",
        },
        "limitations": raw["boundary"]["excluded"],
        "raw_report": str(raw_path.relative_to(ROOT)),
    }


def render_svg(report: dict) -> str:
    rows = report["method_rows"]
    maximum = max(max(row["median_p95_ms"] for row in rows) * 1.08, 4.8)
    scale = 450.0 / maximum
    budget_x = 380.0 + report["budget_ms"] * scale
    bars = []
    for index, row in enumerate(rows):
        y = 250 + index * 92
        width = row["median_p95_ms"] * scale
        color = "#22c55e" if row["meets_4ms_p95"] else "#fb7185"
        bars.append(
            f'<text x="58" y="{y + 22}" class="label">{row["label"]}</text>'
            f'<rect x="380" y="{y}" width="{width:.1f}" height="34" rx="17" fill="{color}"/>'
            f'<text x="{min(1080.0, 394.0 + width):.1f}" y="{y + 23}" class="value">p95 {row["median_p95_ms"]:.3f} ms</text>'
            f'<text x="380" y="{y + 58}" class="small">mean {row["median_mean_ms"]:.3f} ms</text>'
        )
    eq = report["equivalence"]
    decision = report["decision"]
    context = report["prior_context"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AV resident native conduction topology</title>
  <desc id="desc">Twenty logs compare Python, per-step conversion, and resident native execution after adding immutable pairwise conduction.</desc>
  <style>.title{{fill:#f8fafc;font:700 29px system-ui,sans-serif}}.sub{{fill:#cbd5e1;font:16px system-ui,sans-serif}}.label{{fill:#f8fafc;font:600 16px system-ui,sans-serif}}.value{{fill:#f8fafc;font:700 15px ui-monospace,monospace}}.small{{fill:#94a3b8;font:14px system-ui,sans-serif}}.decision{{fill:#fde68a;font:700 19px system-ui,sans-serif}}</style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="76" class="title">Move immutable neighbor topology beside resident state</text>
  <text x="58" y="112" class="sub">20 logs · {report["measurement"]["combined_cell_count"]:,} cells · {report["measurement"]["combined_conduction_pair_count"]:,} pairs · Kit Python · /fp:strict</text>
  <rect x="58" y="148" width="1084" height="62" rx="16" fill="#1e293b"/>
  <text x="82" y="174" class="small">STATE + CONSERVATION GATE</text>
  <text x="82" y="198" class="label">ΔT {eq["maximum_temperature_error_k"]:.3g} K · Δmass {eq["maximum_mass_error_kg"]:.3g} kg · phase {eq["maximum_phase_mismatch_count"]} · ΣQ error {eq["maximum_conduction_balance_error_j"]:.3g} J</text>
  <line x1="{budget_x:.1f}" y1="230" x2="{budget_x:.1f}" y2="520" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="228" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="542" width="1084" height="82" rx="18" fill="#1e293b"/>
  <text x="82" y="574" class="decision">Resident conduction boundary {'QUALIFIES' if decision['resident_conduction_boundary_qualified'] else 'DOES NOT QUALIFY'}; full reactions remain outside</text>
  <text x="82" y="603" class="sub">Added topology p95 vs Phase 6AU: {context["added_topology_p95_ms"]:+.3f} ms · per-step object roundtrip {'rejected' if decision['per_step_aos_roundtrip_rejected'] else 'within gate'}</text>
  <text x="58" y="656" class="small">Production state and physics remain unchanged. Next gate adds evaporation, pyrolysis, char oxidation, and emitted-product accounting.</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--prior", type=Path, default=PRIOR_REPORT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    prior = json.loads(arguments.prior.read_text(encoding="utf-8"))
    report = analyze(raw, arguments.raw.resolve(), prior)
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

