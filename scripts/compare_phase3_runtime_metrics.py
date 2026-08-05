"""Compare full and compact Phase 3 hot-loop metrics aggregation."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT / "docs" / "devlog" / "assets" / "phase6"
    / "phase3_runtime_metrics_report.json"
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
        return str(path)


def _comparison(full: list[dict], compact: list[dict], path: tuple[str, ...]) -> dict:
    full_median = statistics.median(float(_value_at(run, path)) for run in full)
    compact_median = statistics.median(
        float(_value_at(run, path)) for run in compact
    )
    return {
        "full_median": full_median,
        "compact_median": compact_median,
        "improvement_percent": (full_median - compact_median) / full_median * 100.0,
    }


def _validate_run(run: dict, compact: bool) -> None:
    scenario = run["scenario"]
    if run.get("status") != "ok" or run.get("phase") != "phase3":
        raise ValueError("Comparison input is not a successful Phase 3 run")
    if scenario.get("wood_array_backend") != "python":
        raise ValueError("Runtime-metrics evidence must use the Python backend")
    if scenario.get("wood_internal_timing_enabled"):
        raise ValueError("Formal runs must disable wood internal timing")
    if scenario.get("wood_state_diagnostics_enabled"):
        raise ValueError("Formal runs must disable state diagnostics")
    if not scenario.get("python_surface_boundary_fast_path"):
        raise ValueError("Comparison input disabled the adopted surface path")
    if not scenario.get("python_state_clamp_fast_path"):
        raise ValueError("Comparison input disabled the adopted clamp path")
    if not scenario.get("deferred_cell_phase_updates"):
        raise ValueError("Comparison input disabled adopted deferred phases")
    if bool(scenario.get("compact_runtime_metrics")) != compact:
        raise ValueError("Comparison input used the wrong metrics path")
    if not scenario.get("debugger_free"):
        raise ValueError("Comparison input loaded a forbidden debug extension")


def build_report(full_paths: list[Path], compact_paths: list[Path]) -> dict:
    full = _load(full_paths)
    compact = _load(compact_paths)
    if len(full) != len(compact) or len(full) < 3:
        raise ValueError("At least three equal full/compact pairs are required")
    for run in full:
        _validate_run(run, False)
    for run in compact:
        _validate_run(run, True)

    all_runs = full + compact
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
        "metrics_mean_ms": ("timing", "segments", "wood_metrics", "mean_ms"),
        "metrics_p95_ms": ("timing", "segments", "wood_metrics", "p95_ms"),
        "step_loop_mean_ms": ("timing", "segments", "step_loop", "mean_ms"),
        "step_loop_p95_ms": ("timing", "segments", "step_loop", "p95_ms"),
        "wood_model_control_mean_ms": ("timing", "two_log_model_step_mean_ms"),
        "scenario_seconds": ("scenario", "simulation_wall_seconds"),
        "runner_seconds": ("runner_wall_seconds",),
    }
    timings = {
        name: _comparison(full, compact, path)
        for name, path in timing_paths.items()
    }
    paired_results = []
    for index, (full_run, compact_run) in enumerate(zip(full, compact), start=1):
        full_step = float(full_run["timing"]["segments"]["step_loop"]["mean_ms"])
        compact_step = float(
            compact_run["timing"]["segments"]["step_loop"]["mean_ms"]
        )
        full_scenario = float(full_run["scenario"]["simulation_wall_seconds"])
        compact_scenario = float(compact_run["scenario"]["simulation_wall_seconds"])
        paired_results.append({
            "pair": index,
            "metrics_improvement_percent": (
                float(full_run["timing"]["segments"]["wood_metrics"]["mean_ms"])
                - float(compact_run["timing"]["segments"]["wood_metrics"]["mean_ms"])
            ) / float(full_run["timing"]["segments"]["wood_metrics"]["mean_ms"]) * 100.0,
            "step_loop_improvement_percent": (full_step - compact_step) / full_step * 100.0,
            "scenario_improvement_percent": (full_scenario - compact_scenario) / full_scenario * 100.0,
        })
    improving_pairs = sum(
        pair["step_loop_improvement_percent"] > 0.0
        and pair["scenario_improvement_percent"] > 0.0
        for pair in paired_results
    )
    required_pairs = len(paired_results) // 2 + 1
    median_gate = (
        timings["metrics_mean_ms"]["improvement_percent"] > 0.0
        and timings["step_loop_mean_ms"]["improvement_percent"] > 0.0
        and timings["scenario_seconds"]["improvement_percent"] > 0.0
    )
    repeatability_gate = improving_pairs >= required_pairs
    adopt = median_gate and repeatability_gate
    return {
        "schema_version": 1,
        "phase": "phase6ae",
        "status": "ok",
        "paired_run_count": len(full),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "adopted_surface_clamp_and_phase_paths": True,
            "alternating_order": True,
        },
        "dependency_audit": {
            "hot_loop_fields": [
                "surface_mean_temperature_k", "moisture_mass_kg",
                "dry_wood_mass_kg", "char_mass_kg", "ash_mass_kg",
            ],
            "hot_loop_consumers": ["Flow source", "CSV row", "wood visual"],
            "final_only_groups": [
                "weighted and maximum temperature", "emitted totals",
                "product yields", "mass accounting",
            ],
            "public_metrics_api_unchanged": True,
        },
        "timings": timings,
        "paired_results": paired_results,
        "equivalence": {
            "exact_authoritative_outputs_all_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {
                "dry": reference["wood"]["dry"]["ignition_seconds"],
                "wet": reference["wood"]["wet"]["ignition_seconds"],
            },
            "flow_peak_full": sorted({run["flow"]["active_blocks_peak"] for run in full}),
            "flow_peak_compact": sorted({run["flow"]["active_blocks_peak"] for run in compact}),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_compact_metrics": adopt,
            "median_metrics_loop_and_scenario_improved": median_gate,
            "pairs_improving_loop_and_scenario": improving_pairs,
            "required_improving_pairs": required_pairs,
            "reason": (
                "compact aggregation improved metrics, step-loop, and scenario time in a majority of alternating pairs"
                if adopt else "formal end-to-end adoption gates were not met"
            ),
        },
        "runs": {
            "full": [_report_path(path) for path in full_paths],
            "compact": [_report_path(path) for path in compact_paths],
        },
    }


def render_svg(report: dict) -> str:
    metrics = report["timings"]["metrics_mean_ms"]
    step = report["timings"]["step_loop_mean_ms"]
    scenario = report["timings"]["scenario_seconds"]
    decision = report["decision"]
    adopted = decision["adopt_compact_metrics"]
    color = "#86efac" if adopted else "#fca5a5"
    verdict = "ADOPTED - use compact hot-loop metrics" if adopted else "REJECTED - retain full metrics per step"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AE compact runtime metrics decision</title>
  <desc id="desc">{report['paired_run_count']} alternating pairs compare full metrics with five-field hot-loop aggregation.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#25160d"/></linearGradient></defs>
  <style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#fb923c;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#fdba74}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{color}}}</style>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="64" class="kicker">PHASE 6AE - METRICS DEPENDENCY AUDIT</text>
  <text x="64" y="114" class="title">Aggregate only what the hot loop consumes</text>
  <text x="64" y="148" class="sub">{report['paired_run_count']} alternating pairs - five fields - full final summary retained</text>
  <rect x="64" y="188" width="336" height="292" rx="22" fill="#2a1d16" stroke="#c2410c"/>
  <text x="92" y="230" class="heading">METRICS AGGREGATION</text>
  <text x="92" y="280" class="value">{metrics['improvement_percent']:.2f}% faster</text>
  <text x="92" y="316" class="sub">{metrics['full_median']:.4f} to {metrics['compact_median']:.4f} ms</text>
  <text x="92" y="374" class="small">Surface temperature + four masses</text>
  <text x="92" y="402" class="small">Same cell and addition order</text>
  <text x="92" y="430" class="small">Full metrics retained at finalization</text>
  <rect x="432" y="188" width="336" height="292" rx="22" fill="#2a1d16" stroke="#c2410c"/>
  <text x="460" y="230" class="heading">STEP LOOP</text>
  <text x="460" y="280" class="value">{step['improvement_percent']:.2f}% faster</text>
  <text x="460" y="316" class="sub">{step['full_median']:.4f} to {step['compact_median']:.4f} ms</text>
  <text x="460" y="374" class="small">Thermal and reaction code unchanged</text>
  <text x="460" y="402" class="small">Includes metrics, Flow map, and CSV row</text>
  <text x="460" y="430" class="small">Exact authoritative outputs</text>
  <rect x="800" y="188" width="336" height="292" rx="22" fill="#2a1d16" stroke="#c2410c"/>
  <text x="828" y="230" class="heading">SCENARIO WALL TIME</text>
  <text x="828" y="280" class="value">{scenario['improvement_percent']:.2f}% faster</text>
  <text x="828" y="316" class="sub">{scenario['full_median']:.4f} to {scenario['compact_median']:.4f} s</text>
  <text x="828" y="374" class="small">Flow, CSV, visuals, captures retained</text>
  <text x="828" y="402" class="small">{decision['pairs_improving_loop_and_scenario']} / {report['paired_run_count']} pairs improve both</text>
  <text x="828" y="430" class="small">Debugger extensions: 0</text>
  <rect x="64" y="522" width="1072" height="94" rx="18" fill="#251a14" stroke="{color}" stroke-width="2"/>
  <text x="92" y="566" class="decision">{verdict}</text>
  <text x="92" y="594" class="sub">State SHA-256, CSV SHA-256, ignition, equations, grid, dt, and cell order remain unchanged.</text>
  <text x="64" y="654" class="small">Measured outer metrics timing and unprofiled end-to-end timing jointly drive adoption.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--compact-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.full_summary, arguments.compact_summary)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
