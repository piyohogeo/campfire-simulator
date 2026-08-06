"""Validate and visualize the Phase 6AW native piecewise complete-step trial."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_REPORT = ASSET_ROOT / "native_piecewise_complete_step_report.json"
DEFAULT_SVG = ASSET_ROOT / "native_piecewise_complete_step_report.svg"
PRIOR_REPORT = ASSET_ROOT / "native_conduction_boundary_report.json"
METHODS = (
    "python_complete_step",
    "native_roundtrip_complete_step",
    "native_resident_complete_step",
)
LABELS = {
    "python_complete_step": "Python complete step",
    "native_roundtrip_complete_step": "AoS ↔ native complete",
    "native_resident_complete_step": "Resident native complete",
}
BUDGET_MS = 4.0


def analyze(raw: dict, raw_path: Path, prior: dict) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6aw":
        raise ValueError("Unexpected Phase 6AW raw schema")
    if raw.get("status") != "ok" or not raw["runtime"]["kit_python"]:
        raise ValueError("Phase 6AW did not complete with Kit Python")
    measurement = raw["measurement"]
    runs = raw["runs"]
    if measurement["log_count"] != 20 or measurement["combined_cell_count"] != 23040:
        raise ValueError("Phase 6AW requires 20 logs / 23,040 cells")
    if len(runs) < 3 or not measurement["balanced_method_order"]:
        raise ValueError("Phase 6AW requires three balanced runs")
    if any(set(run["methods"]) != set(METHODS) for run in runs):
        raise ValueError("A Phase 6AW method is missing")
    comparisons = [
        comparison
        for run in runs
        for comparison in run["comparisons"].values()
    ]
    if not all(comparison["within_tolerance"] for comparison in comparisons):
        raise ValueError("Native piecewise complete step exceeded a tolerance")
    maximum_conduction_error = max(
        method["conduction_balance_error_j"] or 0.0
        for run in runs
        for method in run["methods"].values()
    )
    if maximum_conduction_error > raw["tolerances"]["maximum_conduction_balance_error_j"]:
        raise ValueError("Native complete step violated conduction conservation")

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
    python = by_name["python_complete_step"]
    roundtrip = by_name["native_roundtrip_complete_step"]
    resident = by_name["native_resident_complete_step"]
    prior_resident = next(
        row
        for row in prior["method_rows"]
        if row["method"] == "native_resident_soa_conduction"
    )
    max_temperature = max(c["maximum_temperature_error_k"] for c in comparisons)
    max_cell_mass = max(c["maximum_cell_mass_error_kg"] for c in comparisons)
    max_cumulative = max(c["maximum_cumulative_error"] for c in comparisons)
    max_output = max(c["maximum_step_output_error"] for c in comparisons)
    max_ignition = max(c["maximum_ignition_time_error_s"] for c in comparisons)
    max_balance = max(c["maximum_candidate_mass_balance_error_kg"] for c in comparisons)
    max_phase = max(c["phase_mismatch_count"] for c in comparisons)
    exact_state = all(c["exact_state_sha256_match"] for c in comparisons)
    exact_history = all(c["exact_step_history_sha256_match"] for c in comparisons)
    native_ignitions = runs[0]["methods"]["native_resident_complete_step"][
        "ignition_times_s"
    ]
    dry_ignitions = native_ignitions[0::2]
    wet_ignitions = native_ignitions[1::2]
    import_ms = statistics.median(
        run["methods"]["native_resident_complete_step"]["boundary"][
            "one_time_import_ms"
        ]
        for run in runs
    )
    export_ms = statistics.median(
        run["methods"]["native_resident_complete_step"]["boundary"][
            "one_time_export_ms"
        ]
        for run in runs
    )
    equivalence_passed = all(c["within_tolerance"] for c in comparisons)
    return {
        "schema_version": 1,
        "phase": "phase6aw",
        "status": "ok",
        "measurement": {
            **measurement,
            "scope": "piecewise complete wood step + result/cumulative products",
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
            "passed": equivalence_passed,
            "all_exact_state_sha256_match": exact_state,
            "all_exact_step_history_sha256_match": exact_history,
            "maximum_temperature_error_k": max_temperature,
            "maximum_cell_mass_error_kg": max_cell_mass,
            "maximum_cumulative_error": max_cumulative,
            "maximum_step_output_error": max_output,
            "maximum_phase_mismatch_count": max_phase,
            "maximum_ignition_time_error_s": max_ignition,
            "maximum_candidate_mass_balance_error_kg": max_balance,
            "maximum_conduction_balance_error_j": maximum_conduction_error,
        },
        "ignition": {
            "dry_seconds": statistics.median(dry_ignitions),
            "wet_seconds": statistics.median(wet_ignitions),
            "all_replicas_match_by_kind": len(set(dry_ignitions)) == 1
            and len(set(wet_ignitions)) == 1,
        },
        "prior_context": {
            "phase6av_resident_p95_ms": prior_resident["median_p95_ms"],
            "reaction_and_output_increment_p95_ms": resident["median_p95_ms"]
            - prior_resident["median_p95_ms"],
        },
        "decision": {
            "piecewise_complete_resident_boundary_qualified": equivalence_passed
            and resident["meets_4ms_p95"],
            "per_step_aos_roundtrip_rejected": not roundtrip["meets_4ms_p95"],
            "resident_speedup_vs_python": python["median_p95_ms"]
            / resident["median_p95_ms"],
            "production_backend_qualified": False,
            "arrhenius_gate_pending": True,
            "app_contract_gate_pending": True,
            "production_model_changed": raw["boundary"]["production_model_changed"],
            "next_step": "add Arrhenius/secondary-tar parity, then measure the app contract",
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
    ignition = report["ignition"]
    context = report["prior_context"]
    decision = report["decision"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AW resident native piecewise complete step</title>
  <desc id="desc">Twenty burning logs compare complete Python, per-step conversion, and resident native piecewise reaction execution.</desc>
  <style>.title{{fill:#f8fafc;font:700 29px system-ui,sans-serif}}.sub{{fill:#cbd5e1;font:16px system-ui,sans-serif}}.label{{fill:#f8fafc;font:600 16px system-ui,sans-serif}}.value{{fill:#f8fafc;font:700 15px ui-monospace,monospace}}.small{{fill:#94a3b8;font:14px system-ui,sans-serif}}.decision{{fill:#fde68a;font:700 19px system-ui,sans-serif}}</style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="76" class="title">Keep reaction state and emitted products resident</text>
  <text x="58" y="112" class="sub">20 logs · conduction + evaporation + piecewise pyrolysis + char oxidation · step/cumulative outputs</text>
  <rect x="58" y="148" width="1084" height="62" rx="16" fill="#1e293b"/>
  <text x="82" y="174" class="small">COMPLETE-STEP GATE</text>
  <text x="82" y="198" class="label">ΔT {eq["maximum_temperature_error_k"]:.3g} K · Δmass {eq["maximum_cell_mass_error_kg"]:.3g} kg · output {eq["maximum_step_output_error"]:.3g} · ignition {ignition["dry_seconds"]:.1f} / {ignition["wet_seconds"]:.1f} s</text>
  <line x1="{budget_x:.1f}" y1="230" x2="{budget_x:.1f}" y2="520" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="228" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="542" width="1084" height="82" rx="18" fill="#1e293b"/>
  <text x="82" y="574" class="decision">Piecewise resident complete step {'QUALIFIES' if decision['piecewise_complete_resident_boundary_qualified'] else 'DOES NOT QUALIFY'}; production gate remains closed</text>
  <text x="82" y="603" class="sub">Reaction/output increment vs Phase 6AV: {context["reaction_and_output_increment_p95_ms"]:+.3f} ms · Arrhenius and app-contract gates remain</text>
  <text x="58" y="656" class="small">Production backend unchanged. Exact state/history hashes are reported separately from declared floating-point tolerances.</text>
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

