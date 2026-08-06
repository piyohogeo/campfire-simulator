"""Compare adopted and step-local homogeneous heat-capacity paths."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "phase3_homogeneous_heat_capacity_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")


def _load(paths: list[Path]) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _value_at(run: dict, path: tuple[str, ...]):
    value = run
    for key in path:
        value = value[key]
    return value


def _report_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path.resolve())


def _comparison(
    original: list[dict], homogeneous: list[dict], path: tuple[str, ...]
) -> dict:
    original_median = statistics.median(
        float(_value_at(run, path)) for run in original
    )
    homogeneous_median = statistics.median(
        float(_value_at(run, path)) for run in homogeneous
    )
    return {
        "original_median": original_median,
        "homogeneous_median": homogeneous_median,
        "improvement_percent": (
            (original_median - homogeneous_median) / original_median * 100.0
        ),
    }


def _validate_run(run: dict, expected_homogeneous: bool) -> None:
    if run.get("status") != "ok" or run.get("phase") != "phase3":
        raise ValueError("Evidence is not a successful Phase 3 run")
    scenario = run["scenario"]
    expected_settings = {
        "wood_array_backend": "python",
        "wood_internal_timing_enabled": False,
        "wood_sensible_heat_timing_enabled": False,
        "python_constant_heat_capacity_fast_path": True,
        "python_homogeneous_heat_capacity_fast_path": expected_homogeneous,
        "wood_state_diagnostics_enabled": False,
        "python_surface_boundary_fast_path": True,
        "python_state_clamp_fast_path": True,
        "deferred_cell_phase_updates": True,
        "compact_runtime_metrics": True,
        "precomputed_runtime_topology": False,
        "debugger_free": True,
        "steps": 1200,
        "model_dt_seconds": 0.2,
    }
    for name, expected in expected_settings.items():
        if scenario.get(name) != expected:
            raise ValueError(f"Evidence has unexpected {name}: {scenario.get(name)!r}")
    if scenario.get("zero_area_cell_count") != {"dry": 792, "wet": 792}:
        raise ValueError("Evidence has an unexpected zero-area cell count")


def build_report(original_paths: list[Path], homogeneous_paths: list[Path]) -> dict:
    original = _load(original_paths)
    homogeneous = _load(homogeneous_paths)
    if len(original) != len(homogeneous) or len(original) < 3:
        raise ValueError("At least three matched runs are required for each path")
    for run in original:
        _validate_run(run, False)
    for run in homogeneous:
        _validate_run(run, True)

    all_runs = original + homogeneous
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
            if _value_at(run, path) != _value_at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")

    timing_paths = {
        "two_log_step_mean_ms": ("timing", "two_log_model_step_mean_ms"),
        "two_log_step_p95_ms": ("timing", "two_log_model_step_p95_ms"),
        "scenario_seconds": ("scenario", "simulation_wall_seconds"),
    }
    timings = {
        name: _comparison(original, homogeneous, path)
        for name, path in timing_paths.items()
    }
    paired = []
    for index, (original_run, homogeneous_run) in enumerate(
        zip(original, homogeneous), start=1
    ):
        original_step = float(original_run["timing"]["two_log_model_step_mean_ms"])
        homogeneous_step = float(
            homogeneous_run["timing"]["two_log_model_step_mean_ms"]
        )
        original_scenario = float(original_run["scenario"]["simulation_wall_seconds"])
        homogeneous_scenario = float(
            homogeneous_run["scenario"]["simulation_wall_seconds"]
        )
        paired.append(
            {
                "pair": index,
                "step_improvement_percent": (
                    (original_step - homogeneous_step) / original_step * 100.0
                ),
                "scenario_improvement_percent": (
                    (original_scenario - homogeneous_scenario)
                    / original_scenario
                    * 100.0
                ),
            }
        )
    improving_pairs = sum(
        item["step_improvement_percent"] > 0.0
        and item["scenario_improvement_percent"] > 0.0
        for item in paired
    )
    required_improving_pairs = len(paired) // 2 + 1
    median_gate = (
        timings["two_log_step_mean_ms"]["improvement_percent"] > 0.0
        and timings["scenario_seconds"]["improvement_percent"] > 0.0
    )
    repeatability_gate = improving_pairs >= required_improving_pairs
    adopt = median_gate and repeatability_gate
    return {
        "schema_version": 1,
        "phase": "phase6ak",
        "status": "ok",
        "paired_run_count": len(original),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "alternating_order": True,
            "internal_timing_disabled": True,
            "runner_time_excluded_from_adoption": True,
        },
        "trial": {
            "original": "per-cell constant-model specialized evaluation",
            "homogeneous": "step-local homogeneous coefficient evaluation",
            "cross_step_cache": False,
            "public_cell_state_rescanned_each_step": True,
            "heterogeneous_or_temperature_dependent_fallback": True,
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
            "flow_peak_original": sorted(
                {run["flow"]["active_blocks_peak"] for run in original}
            ),
            "flow_peak_homogeneous": sorted(
                {run["flow"]["active_blocks_peak"] for run in homogeneous}
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_homogeneous_path": adopt,
            "median_step_and_scenario_improved": median_gate,
            "pairs_improving_step_and_scenario": improving_pairs,
            "required_improving_pairs": required_improving_pairs,
            "reason": (
                "step-local specialization improved median wood-step and scenario "
                "time in a majority of alternating pairs"
                if adopt
                else "formal end-to-end adoption gates were not met"
            ),
        },
        "runs": {
            "original": [_report_path(path) for path in original_paths],
            "homogeneous": [_report_path(path) for path in homogeneous_paths],
        },
    }


def render_svg(report: dict) -> str:
    step = report["timings"]["two_log_step_mean_ms"]
    scenario = report["timings"]["scenario_seconds"]
    decision = report["decision"]
    adopted = decision["adopt_homogeneous_path"]
    color = "#86efac" if adopted else "#fca5a5"
    decision_text = (
        "ADOPTED - enable step-local homogeneous path"
        if adopted
        else "REJECTED - retain per-cell specialized path"
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AK step-local homogeneous heat-capacity decision</title>
  <desc id="desc">Three alternating pairs compare per-cell and step-local homogeneous constant heat-capacity paths.</desc>
  <style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#fbbf24;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#fde68a}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{color}}}</style>
  <rect width="1200" height="680" rx="30" fill="#17130d"/>
  <text x="64" y="64" class="kicker">PHASE 6AK - STEP-LOCAL HOMOGENEITY</text>
  <text x="64" y="114" class="title">Rescan public state, specialize only this step</text>
  <text x="64" y="148" class="sub">{report['paired_run_count']} alternating pairs - no cross-step cache - exact state, CSV, and ignition</text>
  <rect x="64" y="188" width="520" height="292" rx="22" fill="#272016" stroke="#a16207"/>
  <text x="92" y="230" class="heading">UNPROFILED WOOD STEP</text>
  <text x="92" y="280" class="value">{step['improvement_percent']:.2f}% faster</text>
  <text x="92" y="316" class="sub">{step['original_median']:.4f} to {step['homogeneous_median']:.4f} ms</text>
  <text x="92" y="374" class="small">All cells rescanned at every step</text>
  <text x="92" y="402" class="small">Mixed overrides and temperature models fall back</text>
  <text x="92" y="430" class="small">No internal timers in formal runs</text>
  <rect x="616" y="188" width="520" height="292" rx="22" fill="#272016" stroke="#a16207"/>
  <text x="644" y="230" class="heading">SCENARIO WALL TIME</text>
  <text x="644" y="280" class="value">{scenario['improvement_percent']:.2f}% faster</text>
  <text x="644" y="316" class="sub">{scenario['original_median']:.4f} to {scenario['homogeneous_median']:.4f} s</text>
  <text x="644" y="374" class="small">Flow, CSV, USD, and two captures retained</text>
  <text x="644" y="402" class="small">{decision['pairs_improving_step_and_scenario']} / {report['paired_run_count']} pairs improve both</text>
  <text x="644" y="430" class="small">RTX-ready wait excluded from adoption</text>
  <rect x="64" y="522" width="1072" height="94" rx="18" fill="#211b12" stroke="{color}" stroke-width="2"/>
  <text x="92" y="566" class="decision">{decision_text}</text>
  <text x="92" y="594" class="sub">No equations, SI coefficients, grid, time step, cell order, or public edit semantics changed.</text>
  <text x="64" y="654" class="small">Exact authoritative outputs plus alternating unprofiled timing control adoption.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-summary", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--homogeneous-summary", type=Path, nargs="+", required=True
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.original_summary, arguments.homogeneous_summary)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
