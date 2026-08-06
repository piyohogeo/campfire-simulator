"""Validate and visualize the Phase 6AX native parallel-Arrhenius trial."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "devlog" / "assets" / "phase6"
PIECEWISE_ANALYZER = ROOT / "scripts" / "analyze_native_piecewise_complete_step.py"
PHASE6AV_REPORT = ASSET_ROOT / "native_conduction_boundary_report.json"
PRIOR_REPORT = ASSET_ROOT / "native_piecewise_complete_step_report.json"
DEFAULT_REPORT = ASSET_ROOT / "native_arrhenius_complete_step_report.json"
DEFAULT_SVG = ASSET_ROOT / "native_arrhenius_complete_step_report.svg"


def _load_piecewise_analyzer():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6aw_analyzer_base", PIECEWISE_ANALYZER
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AW analyzer: {PIECEWISE_ANALYZER}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


piecewise = _load_piecewise_analyzer()


def analyze(raw: dict, raw_path: Path, prior: dict, phase6av: dict) -> dict:
    if raw.get("schema_version") != 1 or raw.get("phase") != "phase6ax":
        raise ValueError("Unexpected Phase 6AX raw schema")
    kinetics = raw.get("kinetics", {})
    if (
        kinetics.get("gas_constant_j_mol_k") != 8.31446261815324
        or kinetics.get("parallel_common_scale") != 1.0
        or kinetics.get("secondary_residence_time_s") != 1.0
        or kinetics.get("secondary_temperature_range_k") != [773.0, 1073.0]
        or kinetics.get("source_pathways") != ["gas", "tar", "char"]
    ):
        raise ValueError("Phase 6AX kinetics contract changed")
    evidence = raw.get("reaction_evidence", {})
    required_products = (
        "primary_gas_kg",
        "primary_tar_kg",
        "primary_char_kg",
        "secondary_tar_cracked_kg",
        "uncracked_tar_kg",
    )
    if any(float(evidence.get(field, 0.0)) <= 0.0 for field in required_products):
        raise ValueError("Phase 6AX did not exercise every Arrhenius/tar output")

    compatible_raw = copy.deepcopy(raw)
    compatible_raw["phase"] = "phase6aw"
    report = piecewise.analyze(compatible_raw, raw_path, phase6av)
    resident = next(
        row for row in report["method_rows"] if row["method"] == "native_resident_complete_step"
    )
    python = next(
        row for row in report["method_rows"] if row["method"] == "python_complete_step"
    )
    roundtrip = next(
        row for row in report["method_rows"] if row["method"] == "native_roundtrip_complete_step"
    )
    prior_resident = next(
        row for row in prior["method_rows"] if row["method"] == "native_resident_complete_step"
    )
    qualified = report["equivalence"]["passed"] and resident["meets_4ms_p95"]
    report["phase"] = "phase6ax"
    report["measurement"]["scope"] = raw["measurement"]["scope"]
    report["kinetics"] = kinetics
    report["reaction_evidence"] = evidence
    report["prior_context"] = {
        "phase6aw_piecewise_resident_p95_ms": prior_resident["median_p95_ms"],
        "arrhenius_and_tar_increment_p95_ms": resident["median_p95_ms"]
        - prior_resident["median_p95_ms"],
    }
    report["decision"] = {
        "arrhenius_complete_resident_boundary_qualified": qualified,
        "per_step_aos_roundtrip_rejected": not roundtrip["meets_4ms_p95"],
        "resident_speedup_vs_python": python["median_p95_ms"]
        / resident["median_p95_ms"],
        "production_backend_qualified": False,
        "runtime_metrics_gate_pending": True,
        "mutable_state_fallback_gate_pending": True,
        "app_contract_gate_pending": True,
        "production_model_changed": raw["boundary"]["production_model_changed"],
        "next_step": "add runtime metrics/mutable fallback, then measure the app contract",
    }
    report["limitations"] = raw["boundary"]["excluded"]
    return report


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
    evidence = report["reaction_evidence"]
    context = report["prior_context"]
    decision = report["decision"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AX resident native parallel Arrhenius complete step</title>
  <desc id="desc">Twenty burning logs compare Python, per-step conversion, and resident native parallel Arrhenius execution with bounded secondary tar conversion.</desc>
  <style>.title{{fill:#f8fafc;font:700 29px system-ui,sans-serif}}.sub{{fill:#cbd5e1;font:16px system-ui,sans-serif}}.label{{fill:#f8fafc;font:600 16px system-ui,sans-serif}}.value{{fill:#f8fafc;font:700 15px ui-monospace,monospace}}.small{{fill:#94a3b8;font:14px system-ui,sans-serif}}.decision{{fill:#fde68a;font:700 19px system-ui,sans-serif}}</style>
  <rect width="1200" height="680" rx="28" fill="#0f172a"/>
  <text x="58" y="76" class="title">Keep all three Arrhenius pathways resident</text>
  <text x="58" y="112" class="sub">20 logs · gas + tar + char competition · bounded secondary tar split · exact step/cumulative outputs</text>
  <rect x="58" y="148" width="1084" height="62" rx="16" fill="#1e293b"/>
  <text x="82" y="174" class="small">ARRHENIUS COMPLETE-STEP GATE</text>
  <text x="82" y="198" class="label">ΔT {eq["maximum_temperature_error_k"]:.3g} K · Δmass {eq["maximum_cell_mass_error_kg"]:.3g} kg · output {eq["maximum_step_output_error"]:.3g} · ignition {ignition["dry_seconds"]:.1f} / {ignition["wet_seconds"]:.1f} s</text>
  <line x1="{budget_x:.1f}" y1="230" x2="{budget_x:.1f}" y2="520" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1030.0, budget_x + 10):.1f}" y="228" class="value">4 ms p95 gate</text>
  {''.join(bars)}
  <rect x="58" y="542" width="1084" height="82" rx="18" fill="#1e293b"/>
  <text x="82" y="574" class="decision">Arrhenius resident complete step {'QUALIFIES' if decision['arrhenius_complete_resident_boundary_qualified'] else 'DOES NOT QUALIFY'}; production gate remains closed</text>
  <text x="82" y="603" class="sub">vs Phase 6AW: {context["arrhenius_and_tar_increment_p95_ms"]:+.3f} ms · secondary tar {evidence["secondary_tar_cracked_kg"]:.3g} kg · app-contract gates remain</text>
  <text x="58" y="656" class="small">Production backend unchanged. Fixed A/E pairs and the 773–1073 K diagnostic tar boundary are preserved.</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--prior", type=Path, default=PRIOR_REPORT)
    parser.add_argument("--phase6av", type=Path, default=PHASE6AV_REPORT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    prior = json.loads(arguments.prior.read_text(encoding="utf-8"))
    phase6av = json.loads(arguments.phase6av.read_text(encoding="utf-8"))
    report = analyze(raw, arguments.raw.resolve(), prior, phase6av)
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
