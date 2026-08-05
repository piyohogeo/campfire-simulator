"""Validate and visualize opt-in Phase 3 wood-state branch diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "phase3_state_diagnostics_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")
PHASES = ("wet_wood", "dry_wood", "pyrolyzing", "char", "ash", "depleted")
PHASE_LABELS = {
    "wet_wood": "Wet wood",
    "dry_wood": "Dry wood",
    "pyrolyzing": "Pyrolyzing",
    "char": "Char",
    "ash": "Ash",
    "depleted": "Depleted",
}
PHASE_COLORS = {
    "wet_wood": "#60a5fa",
    "dry_wood": "#d6a96c",
    "pyrolyzing": "#fb923c",
    "char": "#a78bfa",
    "ash": "#94a3b8",
    "depleted": "#475569",
}
EXPECTED_STATE_SHA256 = {
    "dry": "0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10",
    "wet": "148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9",
}
EXPECTED_CSV_SHA256 = (
    "01aaf0c659fbf9d402b536ccbc71405f5a51af7fbd5f450cdca608bc915b7759"
)


def _report_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path)


def _model_report(name: str, counts: dict[str, int], expected_cells: int) -> dict:
    cells_evaluated = int(counts.get("cells_evaluated", -1))
    if cells_evaluated != expected_cells:
        raise ValueError(f"{name} diagnostic cell count is not {expected_cells}")
    phase_counts = {
        phase: int(counts.get(f"phase_{phase}", 0)) for phase in PHASES
    }
    if sum(phase_counts.values()) != cells_evaluated:
        raise ValueError(f"{name} phase assignments do not cover every cell")
    transitions = {
        key.removeprefix("transition_"): int(value)
        for key, value in counts.items()
        if key.startswith("transition_")
    }
    phase_changes = int(counts.get("phase_changes", -1))
    if sum(transitions.values()) != phase_changes:
        raise ValueError(f"{name} transition counts do not match phase changes")
    clamp_counts = {
        "temperature_low": int(counts.get("temperature_clamped_low", 0)),
        "temperature_high": int(counts.get("temperature_clamped_high", 0)),
        "moisture_mass": int(counts.get("moisture_mass_clamped", 0)),
        "dry_wood_mass": int(counts.get("dry_wood_mass_clamped", 0)),
        "char_mass": int(counts.get("char_mass_clamped", 0)),
        "ash_mass": int(counts.get("ash_mass_clamped", 0)),
    }
    if any(value < 0 or value > cells_evaluated for value in clamp_counts.values()):
        raise ValueError(f"{name} has an invalid clamp count")
    return {
        "cells_evaluated": cells_evaluated,
        "phase_assignments": phase_counts,
        "phase_percent": {
            phase: count / cells_evaluated * 100.0
            for phase, count in phase_counts.items()
        },
        "phase_changes": phase_changes,
        "phase_change_rate_percent": phase_changes / cells_evaluated * 100.0,
        "transitions": dict(
            sorted(transitions.items(), key=lambda item: item[1], reverse=True)
        ),
        "clamps": clamp_counts,
        "clamp_total": sum(clamp_counts.values()),
    }


def build_report(summary_path: Path) -> dict:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "ok" or summary.get("phase") != "phase3":
        raise ValueError("Input is not a successful Phase 3 summary")
    scenario = summary["scenario"]
    if scenario.get("wood_array_backend") != "python":
        raise ValueError("State diagnostics require the Python backend")
    if not scenario.get("python_surface_boundary_fast_path"):
        raise ValueError("State diagnostics must use the adopted surface path")
    if scenario.get("wood_internal_timing_enabled"):
        raise ValueError("State diagnostic evidence must not enable internal timing")
    if not scenario.get("wood_state_diagnostics_enabled"):
        raise ValueError("State diagnostics were not enabled")
    if not scenario.get("debugger_free"):
        raise ValueError("State diagnostic evidence loaded a debug extension")
    if scenario.get("zero_area_cell_count") != {"dry": 792, "wet": 792}:
        raise ValueError("Unexpected Phase 3 zero-area cell count")
    if summary.get("metrics_csv_sha256") != EXPECTED_CSV_SHA256:
        raise ValueError("State diagnostics changed the authoritative CSV")
    if {
        name: summary["wood"][name]["authoritative_state_sha256"]
        for name in ("dry", "wet")
    } != EXPECTED_STATE_SHA256:
        raise ValueError("State diagnostics changed an authoritative wood state")
    if {
        name: summary["wood"][name]["ignition_seconds"]
        for name in ("dry", "wet")
    } != {"dry": 66.2, "wet": 166.4}:
        raise ValueError("State diagnostics changed ignition timing")

    steps = int(scenario["steps"])
    expected_cells = steps * 1152
    raw_diagnostics = scenario["wood_state_diagnostics"]
    models = {
        name: _model_report(name, raw_diagnostics[name], expected_cells)
        for name in ("dry", "wet")
    }
    combined_cells = sum(model["cells_evaluated"] for model in models.values())
    combined_clamps = sum(model["clamp_total"] for model in models.values())
    combined_changes = sum(model["phase_changes"] for model in models.values())
    return {
        "schema_version": 1,
        "phase": "phase6ab",
        "status": "ok",
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free": True,
            "surface_boundary_fast_path": True,
            "internal_timing_enabled": False,
            "diagnostic_timing_is_not_performance_evidence": True,
        },
        "configuration": {
            "steps": steps,
            "model_dt_seconds": scenario["model_dt_seconds"],
            "cells_per_log": 1152,
            "cell_updates_per_log": expected_cells,
        },
        "models": models,
        "combined": {
            "cells_evaluated": combined_cells,
            "clamp_total": combined_clamps,
            "clamp_rate_percent": combined_clamps / combined_cells * 100.0,
            "phase_changes": combined_changes,
            "phase_change_rate_percent": combined_changes
            / combined_cells
            * 100.0,
        },
        "equivalence": {
            "exact_authoritative_outputs": True,
            "dry_state_sha256": EXPECTED_STATE_SHA256["dry"],
            "wet_state_sha256": EXPECTED_STATE_SHA256["wet"],
            "metrics_csv_sha256": EXPECTED_CSV_SHA256,
            "ignition_seconds": {"dry": 66.2, "wet": 166.4},
        },
        "decision": {
            "production_change": False,
            "reason": "diagnostic phase only; branch frequency selects the next trial",
            "next_candidate": "conditional clamp checks preserving all bounds",
        },
        "run": _report_path(summary_path),
    }


def _phase_rows(model: dict, x: int, y: int) -> str:
    rows = []
    for index, phase in enumerate(PHASES):
        row_y = y + index * 38
        percent = model["phase_percent"][phase]
        width = max(1.0, percent / 100.0 * 300.0)
        rows.append(
            f'<text x="{x}" y="{row_y}" class="label">{PHASE_LABELS[phase]}</text>'
            f'<rect x="{x + 112}" y="{row_y - 14}" width="300" height="16" rx="8" fill="#263548"/>'
            f'<rect x="{x + 112}" y="{row_y - 14}" width="{width:.2f}" height="16" rx="8" fill="{PHASE_COLORS[phase]}"/>'
            f'<text x="{x + 424}" y="{row_y}" class="percent">{percent:.3f}%</text>'
        )
    return "".join(rows)


def render_svg(report: dict) -> str:
    dry = report["models"]["dry"]
    wet = report["models"]["wet"]
    combined = report["combined"]
    dry_top_transition = next(iter(dry["transitions"].items()), ("none", 0))
    wet_top_transition = next(iter(wet["transitions"].items()), ("none", 0))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AB state-finalize branch diagnostics</title>
  <desc id="desc">Phase assignments, clamp counts, and actual transitions for dry and wet Phase 3 logs.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#172033"/></linearGradient></defs>
  <style>.title{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#38bdf8;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 18px 'Segoe UI',sans-serif;fill:#f8fafc}}.label{{font:14px 'Segoe UI',sans-serif;fill:#cbd5e1}}.percent{{font:700 14px 'Segoe UI',sans-serif;fill:#f8fafc;text-anchor:end}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.value{{font:750 24px 'Segoe UI',sans-serif;fill:#7dd3fc}}</style>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="62" class="kicker">PHASE 6AB · STATE-FINALIZE DIAGNOSTICS</text>
  <text x="64" y="110" class="title">Measure branches before changing them</text>
  <text x="64" y="144" class="sub">2 logs · 1,200 steps · {combined['cells_evaluated']:,} cell updates · diagnostic timing excluded</text>
  <rect x="64" y="180" width="520" height="314" rx="22" fill="#172438" stroke="#2563eb"/>
  <text x="92" y="218" class="heading">DRY LOG · PHASE ASSIGNMENTS</text>
  {_phase_rows(dry, 92, 258)}
  <rect x="616" y="180" width="520" height="314" rx="22" fill="#172438" stroke="#2563eb"/>
  <text x="644" y="218" class="heading">WET LOG · PHASE ASSIGNMENTS</text>
  {_phase_rows(wet, 644, 258)}
  <rect x="64" y="522" width="1072" height="98" rx="20" fill="#12253a" stroke="#38bdf8"/>
  <text x="92" y="558" class="heading">OBSERVED CONTROL FLOW</text>
  <text x="92" y="592" class="value">{combined['clamp_total']:,} clamps</text>
  <text x="310" y="592" class="sub">across temperature + four mass bounds</text>
  <text x="650" y="558" class="small">Dry top transition: {dry_top_transition[0]} · {dry_top_transition[1]:,}</text>
  <text x="650" y="586" class="small">Wet top transition: {wet_top_transition[0]} · {wet_top_transition[1]:,}</text>
  <text x="650" y="612" class="small">Total phase changes: {combined['phase_changes']:,} ({combined['phase_change_rate_percent']:.4f}%)</text>
  <text x="64" y="654" class="small">Exact state SHA-256, CSV SHA-256, ignition, equations, grid, dt, and cell order are unchanged.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.summary)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
