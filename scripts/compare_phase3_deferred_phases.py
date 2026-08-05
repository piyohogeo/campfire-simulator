"""Compare eager and deferred Phase 3 cell-phase classification."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT / "docs" / "devlog" / "assets" / "phase6"
    / "phase3_deferred_phase_report.json"
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


def _comparison(eager: list[dict], deferred: list[dict], path: tuple[str, ...]) -> dict:
    eager_median = statistics.median(float(_value_at(run, path)) for run in eager)
    deferred_median = statistics.median(
        float(_value_at(run, path)) for run in deferred
    )
    return {
        "eager_median": eager_median,
        "deferred_median": deferred_median,
        "improvement_percent": (eager_median - deferred_median) / eager_median * 100.0,
    }


def _validate_run(run: dict, deferred: bool, profiled: bool) -> None:
    scenario = run["scenario"]
    if run.get("status") != "ok" or run.get("phase") != "phase3":
        raise ValueError("Comparison input is not a successful Phase 3 run")
    if scenario.get("wood_array_backend") != "python":
        raise ValueError("Deferred-phase evidence must use the Python backend")
    if bool(scenario.get("wood_internal_timing_enabled")) != profiled:
        raise ValueError("Comparison input has the wrong internal-timing setting")
    if scenario.get("wood_state_diagnostics_enabled"):
        raise ValueError("Comparison input enabled state diagnostics")
    if not scenario.get("python_surface_boundary_fast_path"):
        raise ValueError("Comparison input disabled the adopted surface path")
    if not scenario.get("python_state_clamp_fast_path"):
        raise ValueError("Comparison input disabled the adopted clamp path")
    if bool(scenario.get("deferred_cell_phase_updates")) != deferred:
        raise ValueError("Comparison input used the wrong phase-update path")
    if not scenario.get("debugger_free"):
        raise ValueError("Comparison input loaded a forbidden debug extension")


def build_report(
    eager_paths: list[Path],
    deferred_paths: list[Path],
    eager_profile_path: Path,
    deferred_profile_path: Path,
) -> dict:
    eager = _load(eager_paths)
    deferred = _load(deferred_paths)
    if len(eager) != len(deferred) or len(eager) < 3:
        raise ValueError("At least three equal eager/deferred pairs are required")
    for run in eager:
        _validate_run(run, False, False)
    for run in deferred:
        _validate_run(run, True, False)

    all_runs = eager + deferred
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
        "runner_seconds": ("runner_wall_seconds",),
    }
    timings = {
        name: _comparison(eager, deferred, path)
        for name, path in timing_paths.items()
    }
    paired_results = []
    for index, (eager_run, deferred_run) in enumerate(zip(eager, deferred), start=1):
        eager_step = float(eager_run["timing"]["two_log_model_step_mean_ms"])
        deferred_step = float(deferred_run["timing"]["two_log_model_step_mean_ms"])
        eager_scenario = float(eager_run["scenario"]["simulation_wall_seconds"])
        deferred_scenario = float(deferred_run["scenario"]["simulation_wall_seconds"])
        paired_results.append({
            "pair": index,
            "step_improvement_percent": (eager_step - deferred_step) / eager_step * 100.0,
            "scenario_improvement_percent": (eager_scenario - deferred_scenario) / eager_scenario * 100.0,
        })
    improving_pairs = sum(
        pair["step_improvement_percent"] > 0.0
        and pair["scenario_improvement_percent"] > 0.0
        for pair in paired_results
    )
    required_pairs = len(paired_results) // 2 + 1

    eager_profile, deferred_profile = _load(
        [eager_profile_path, deferred_profile_path]
    )
    _validate_run(eager_profile, False, True)
    _validate_run(deferred_profile, True, True)
    for run in (eager_profile, deferred_profile):
        for path in invariant_paths:
            if _value_at(run, path) != _value_at(reference, path):
                raise ValueError("Profile run changed an authoritative output")
    eager_finalize = float(
        eager_profile["timing"]["wood_model_internal_segments"]["state_finalize"]["mean_ms"]
    )
    deferred_finalize = float(
        deferred_profile["timing"]["wood_model_internal_segments"]["state_finalize"]["mean_ms"]
    )
    profile = {
        "eager_mean_ms": eager_finalize,
        "deferred_mean_ms": deferred_finalize,
        "improvement_percent": (eager_finalize - deferred_finalize) / eager_finalize * 100.0,
        "final_refresh_ms": float(
            deferred_profile["scenario"]["final_phase_refresh_seconds"]
        ) * 1000.0,
    }

    median_gate = (
        timings["two_log_step_mean_ms"]["improvement_percent"] > 0.0
        and timings["scenario_seconds"]["improvement_percent"] > 0.0
    )
    repeatability_gate = improving_pairs >= required_pairs
    adopt = median_gate and repeatability_gate
    return {
        "schema_version": 1,
        "phase": "phase6ad",
        "status": "ok",
        "paired_run_count": len(eager),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "adopted_surface_and_clamp_paths": True,
            "alternating_order": True,
            "internal_timing_disabled_for_formal_runs": True,
        },
        "dependency_audit": {
            "hot_loop_consumers": ["thermal state", "Flow source", "CSV metrics", "visual metrics", "ignition"],
            "cell_phase_consumers": ["state diagnostics", "final persistent state"],
            "public_step_default_remains_eager": True,
            "diagnostics_require_eager_updates": True,
        },
        "profile": profile,
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
            "flow_peak_eager": sorted({run["flow"]["active_blocks_peak"] for run in eager}),
            "flow_peak_deferred": sorted({run["flow"]["active_blocks_peak"] for run in deferred}),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_deferred_updates": adopt,
            "median_step_and_scenario_improved": median_gate,
            "pairs_improving_step_and_scenario": improving_pairs,
            "required_improving_pairs": required_pairs,
            "reason": (
                "deferred classification improved median wood-step and scenario time in a majority of alternating pairs"
                if adopt else "formal end-to-end adoption gates were not met"
            ),
        },
        "runs": {
            "eager": [_report_path(path) for path in eager_paths],
            "deferred": [_report_path(path) for path in deferred_paths],
            "eager_profile": _report_path(eager_profile_path),
            "deferred_profile": _report_path(deferred_profile_path),
        },
    }


def render_svg(report: dict) -> str:
    step = report["timings"]["two_log_step_mean_ms"]
    scenario = report["timings"]["scenario_seconds"]
    profile = report["profile"]
    decision = report["decision"]
    adopted = decision["adopt_deferred_updates"]
    color = "#86efac" if adopted else "#fca5a5"
    verdict = "ADOPTED - defer phase classification" if adopted else "REJECTED - retain eager classification"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AD deferred cell-phase decision</title>
  <desc id="desc">{report['paired_run_count']} alternating pairs compare eager per-step classification with one final refresh.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#25160d"/></linearGradient></defs>
  <style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#fb923c;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#fdba74}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{color}}}</style>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="64" class="kicker">PHASE 6AD - DOWNSTREAM DEPENDENCY AUDIT</text>
  <text x="64" y="114" class="title">Classify when the phase value is consumed</text>
  <text x="64" y="148" class="sub">{report['paired_run_count']} alternating pairs - final refresh retained - exact persistent state</text>
  <rect x="64" y="188" width="336" height="292" rx="22" fill="#2a1d16" stroke="#c2410c"/>
  <text x="92" y="230" class="heading">PROFILED STATE FINALIZE</text>
  <text x="92" y="280" class="value">{profile['improvement_percent']:.2f}% faster</text>
  <text x="92" y="316" class="sub">{profile['eager_mean_ms']:.4f} to {profile['deferred_mean_ms']:.4f} ms</text>
  <text x="92" y="374" class="small">One final refresh: {profile['final_refresh_ms']:.3f} ms</text>
  <text x="92" y="402" class="small">Numerical clamps remain per step</text>
  <text x="92" y="430" class="small">Diagnostics force eager mode</text>
  <rect x="432" y="188" width="336" height="292" rx="22" fill="#2a1d16" stroke="#c2410c"/>
  <text x="460" y="230" class="heading">UNPROFILED WOOD STEP</text>
  <text x="460" y="280" class="value">{step['improvement_percent']:.2f}% faster</text>
  <text x="460" y="316" class="sub">{step['eager_median']:.4f} to {step['deferred_median']:.4f} ms</text>
  <text x="460" y="374" class="small">Flow, CSV, visuals do not read cell.phase</text>
  <text x="460" y="402" class="small">Public step API remains eager</text>
  <text x="460" y="430" class="small">Exact authoritative outputs</text>
  <rect x="800" y="188" width="336" height="292" rx="22" fill="#2a1d16" stroke="#c2410c"/>
  <text x="828" y="230" class="heading">SCENARIO WALL TIME</text>
  <text x="828" y="280" class="value">{scenario['improvement_percent']:.2f}% faster</text>
  <text x="828" y="316" class="sub">{scenario['eager_median']:.4f} to {scenario['deferred_median']:.4f} s</text>
  <text x="828" y="374" class="small">Flow and 2 captures retained</text>
  <text x="828" y="402" class="small">{decision['pairs_improving_step_and_scenario']} / {report['paired_run_count']} pairs improve both</text>
  <text x="828" y="430" class="small">Debugger extensions: 0</text>
  <rect x="64" y="522" width="1072" height="94" rx="18" fill="#251a14" stroke="{color}" stroke-width="2"/>
  <text x="92" y="566" class="decision">{verdict}</text>
  <text x="92" y="594" class="sub">State SHA-256, CSV SHA-256, ignition, equations, grid, dt, and cell order remain unchanged.</text>
  <text x="64" y="654" class="small">Only unprofiled end-to-end timing drives adoption; profile timing explains the affected segment.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eager-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--deferred-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--eager-profile", type=Path, required=True)
    parser.add_argument("--deferred-profile", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(
        arguments.eager_summary,
        arguments.deferred_summary,
        arguments.eager_profile,
        arguments.deferred_profile,
    )
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
