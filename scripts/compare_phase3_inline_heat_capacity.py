"""Compare closure-based and inline homogeneous sensible heat capacity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import compare_phase3_homogeneous_heat_capacity as phase6ak


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = (
    ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "phase3_inline_heat_capacity_report.json"
)
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")


def _validate_run(run: dict, expected_inline: bool) -> None:
    phase6ak._validate_run(run, True)
    actual = run["scenario"].get(
        "python_inline_homogeneous_sensible_heat_capacity_fast_path"
    )
    if actual is not expected_inline:
        raise ValueError(f"Evidence has unexpected inline path setting: {actual!r}")


def build_report(baseline_paths: list[Path], inline_paths: list[Path]) -> dict:
    baseline = phase6ak._load(baseline_paths)
    inline = phase6ak._load(inline_paths)
    if len(baseline) != len(inline) or len(baseline) < 3:
        raise ValueError("At least three matched runs are required for each path")
    for run in baseline:
        _validate_run(run, False)
    for run in inline:
        _validate_run(run, True)
    all_runs = baseline + inline
    reference = all_runs[0]
    invariant_paths = (
        ("metrics_csv_sha256",),
        ("wood", "dry", "authoritative_state_sha256"),
        ("wood", "wet", "authoritative_state_sha256"),
        ("wood", "dry", "ignition_seconds"),
        ("wood", "wet", "ignition_seconds"),
        ("scenario", "steps"),
        ("scenario", "model_dt_seconds"),
        ("scenario", "external_heat_flux_w_m2"),
    )
    for run in all_runs:
        for path in invariant_paths:
            if phase6ak._value_at(run, path) != phase6ak._value_at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")
    timing_paths = {
        "two_log_step_mean_ms": ("timing", "two_log_model_step_mean_ms"),
        "two_log_step_p95_ms": ("timing", "two_log_model_step_p95_ms"),
        "scenario_seconds": ("scenario", "simulation_wall_seconds"),
    }
    timings = {
        name: phase6ak._comparison(baseline, inline, path)
        for name, path in timing_paths.items()
    }
    paired = []
    for index, (baseline_run, inline_run) in enumerate(zip(baseline, inline), start=1):
        baseline_step = float(baseline_run["timing"]["two_log_model_step_mean_ms"])
        inline_step = float(inline_run["timing"]["two_log_model_step_mean_ms"])
        baseline_scenario = float(
            baseline_run["scenario"]["simulation_wall_seconds"]
        )
        inline_scenario = float(inline_run["scenario"]["simulation_wall_seconds"])
        paired.append(
            {
                "pair": index,
                "step_improvement_percent": (
                    (baseline_step - inline_step) / baseline_step * 100.0
                ),
                "scenario_improvement_percent": (
                    (baseline_scenario - inline_scenario)
                    / baseline_scenario
                    * 100.0
                ),
            }
        )
    improving_pairs = sum(
        item["step_improvement_percent"] > 0.0
        and item["scenario_improvement_percent"] > 0.0
        for item in paired
    )
    required_pairs = len(paired) // 2 + 1
    median_gate = (
        timings["two_log_step_mean_ms"]["improvement_percent"] > 0.0
        and timings["scenario_seconds"]["improvement_percent"] > 0.0
    )
    adopt = median_gate and improving_pairs >= required_pairs
    return {
        "schema_version": 1,
        "phase": "phase6am",
        "status": "ok",
        "paired_run_count": len(baseline),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "alternating_order": True,
            "internal_timing_disabled": True,
            "runner_time_excluded_from_adoption": True,
        },
        "trial": {
            "baseline": "step-local homogeneous per-cell closure",
            "inline": "step-local homogeneous sensible loop with inline capacity arithmetic",
            "scope": "sensible heat only; pyrolysis and char oxidation retain evaluator",
            "cross_step_cache": False,
            "mass_and_temperature_reads_remain_per_cell": True,
            "heterogeneous_fallback_unchanged": True,
        },
        "timings": timings,
        "paired_results": paired,
        "equivalence": {
            "exact_authoritative_outputs_all_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {
                "dry": reference["wood"]["dry"]["ignition_seconds"],
                "wet": reference["wood"]["wet"]["ignition_seconds"],
            },
            "flow_peak_baseline": sorted(
                {run["flow"]["active_blocks_peak"] for run in baseline}
            ),
            "flow_peak_inline": sorted(
                {run["flow"]["active_blocks_peak"] for run in inline}
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_inline_path": adopt,
            "median_step_and_scenario_improved": median_gate,
            "pairs_improving_step_and_scenario": improving_pairs,
            "required_improving_pairs": required_pairs,
            "reason": "inline loop met alternating end-to-end gates" if adopt else "formal end-to-end adoption gates were not met",
        },
        "runs": {
            "baseline": [phase6ak._report_path(path) for path in baseline_paths],
            "inline": [phase6ak._report_path(path) for path in inline_paths],
        },
    }


def render_svg(report: dict) -> str:
    step = report["timings"]["two_log_step_mean_ms"]
    scenario = report["timings"]["scenario_seconds"]
    decision = report["decision"]
    adopted = decision["adopt_inline_path"]
    color = "#86efac" if adopted else "#fca5a5"
    verdict = (
        "ADOPTED - inline homogeneous sensible capacity"
        if adopted
        else "REJECTED - retain closure-based path"
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AM inline homogeneous heat-capacity decision</title>
  <desc id="desc">Three alternating pairs compare closure-based and inline sensible heat-capacity evaluation.</desc>
  <style>.title{{font:750 37px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#a5f3fc}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{color}}}</style>
  <rect width="1200" height="680" rx="30" fill="#0f172a"/>
  <text x="64" y="64" class="kicker">PHASE 6AM - INLINE SENSIBLE CAPACITY</text>
  <text x="64" y="114" class="title">Remove the per-cell closure, keep every read</text>
  <text x="64" y="148" class="sub">{report['paired_run_count']} alternating pairs - no cache - exact state, CSV, and ignition</text>
  <rect x="64" y="188" width="520" height="292" rx="22" fill="#172033" stroke="#0891b2"/>
  <text x="92" y="230" class="heading">UNPROFILED WOOD STEP</text>
  <text x="92" y="280" class="value">{step['improvement_percent']:.2f}% faster</text>
  <text x="92" y="316" class="sub">{step['original_median']:.4f} to {step['homogeneous_median']:.4f} ms</text>
  <text x="92" y="374" class="small">Temperature and four masses still read per cell</text>
  <text x="92" y="402" class="small">Same arithmetic order and 1e-9 J/K floor</text>
  <text x="92" y="430" class="small">Pyrolysis and char oxidation unchanged</text>
  <rect x="616" y="188" width="520" height="292" rx="22" fill="#172033" stroke="#0891b2"/>
  <text x="644" y="230" class="heading">SCENARIO WALL TIME</text>
  <text x="644" y="280" class="value">{scenario['improvement_percent']:.2f}% faster</text>
  <text x="644" y="316" class="sub">{scenario['original_median']:.4f} to {scenario['homogeneous_median']:.4f} s</text>
  <text x="644" y="374" class="small">Flow, CSV, USD, and two captures retained</text>
  <text x="644" y="402" class="small">{decision['pairs_improving_step_and_scenario']} / {report['paired_run_count']} pairs improve both</text>
  <text x="644" y="430" class="small">Internal timers disabled for adoption</text>
  <rect x="64" y="522" width="1072" height="94" rx="18" fill="#111827" stroke="{color}" stroke-width="2"/>
  <text x="92" y="566" class="decision">{verdict}</text>
  <text x="92" y="594" class="sub">No equations, coefficients, grid, step size, cell order, or public edit semantics changed.</text>
  <text x="64" y="654" class="small">Profile selected the trial; alternating unprofiled end-to-end measurements decide adoption.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--inline-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.baseline_summary, arguments.inline_summary)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
