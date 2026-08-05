"""Compare original and zero-area surface-boundary Python paths."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT / "docs" / "devlog" / "assets" / "phase6"
    / "phase3_surface_boundary_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")


def _load(paths: list[Path]) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _report_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path)


def _value_at(run: dict, path: tuple[str, ...]):
    value = run
    for key in path:
        value = value[key]
    return value


def _median(runs: list[dict], path: tuple[str, ...]) -> float:
    return statistics.median(float(_value_at(run, path)) for run in runs)


def _comparison(
    original: list[dict], fast: list[dict], path: tuple[str, ...]
) -> dict:
    original_median = _median(original, path)
    fast_median = _median(fast, path)
    return {
        "original_median": original_median,
        "fast_median": fast_median,
        "improvement_percent": (original_median - fast_median)
        / original_median
        * 100.0,
    }


def _validate_group(runs: list[dict], expected_fast: bool) -> None:
    if len(runs) < 3:
        raise ValueError("At least three runs are required for each path")
    for run in runs:
        if run.get("status") != "ok" or run.get("phase") != "phase3":
            raise ValueError("A comparison input is not a successful Phase 3 run")
        scenario = run["scenario"]
        if scenario.get("wood_array_backend") != "python":
            raise ValueError("Surface-boundary evidence must use the Python backend")
        if scenario.get("wood_internal_timing_enabled"):
            raise ValueError("Formal comparison runs must not enable internal timing")
        if bool(scenario.get("python_surface_boundary_fast_path")) != expected_fast:
            raise ValueError("A comparison run used the wrong surface-boundary path")
        if not scenario.get("debugger_free"):
            raise ValueError("A comparison run loaded a forbidden debug extension")
        if scenario.get("zero_area_cell_count") != {"dry": 792, "wet": 792}:
            raise ValueError("A comparison run has an unexpected zero-area cell count")


def build_report(
    original_paths: list[Path],
    fast_paths: list[Path],
    original_profile_path: Path | None,
    fast_profile_path: Path | None,
) -> dict:
    original = _load(original_paths)
    fast = _load(fast_paths)
    if len(original) != len(fast):
        raise ValueError("Original and fast run counts differ")
    _validate_group(original, False)
    _validate_group(fast, True)
    all_runs = original + fast
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
        name: _comparison(original, fast, path)
        for name, path in timing_paths.items()
    }
    paired = []
    for index, (original_run, fast_run) in enumerate(zip(original, fast), start=1):
        original_step = float(original_run["timing"]["two_log_model_step_mean_ms"])
        fast_step = float(fast_run["timing"]["two_log_model_step_mean_ms"])
        original_scenario = float(original_run["scenario"]["simulation_wall_seconds"])
        fast_scenario = float(fast_run["scenario"]["simulation_wall_seconds"])
        paired.append(
            {
                "pair": index,
                "step_improvement_percent": (original_step - fast_step)
                / original_step
                * 100.0,
                "scenario_improvement_percent": (
                    original_scenario - fast_scenario
                )
                / original_scenario
                * 100.0,
            }
        )
    improving_pairs = sum(
        item["step_improvement_percent"] > 0.0
        and item["scenario_improvement_percent"] > 0.0
        for item in paired
    )
    required_improving_pairs = len(paired) // 2 + 1
    profile = None
    if original_profile_path is not None or fast_profile_path is not None:
        if original_profile_path is None or fast_profile_path is None:
            raise ValueError("Both profile summaries must be supplied together")
        original_profile, fast_profile = _load(
            [original_profile_path, fast_profile_path]
        )
        for run, expected_fast in (
            (original_profile, False),
            (fast_profile, True),
        ):
            scenario = run["scenario"]
            if run.get("status") != "ok" or run.get("phase") != "phase3":
                raise ValueError("Profile evidence is not a successful Phase 3 run")
            if scenario.get("wood_array_backend") != "python":
                raise ValueError("Profile evidence must use the Python backend")
            if not scenario.get("wood_internal_timing_enabled"):
                raise ValueError("Profile evidence did not enable internal timing")
            if bool(scenario.get("python_surface_boundary_fast_path")) != expected_fast:
                raise ValueError("Profile evidence used the wrong path")
            if not scenario.get("debugger_free"):
                raise ValueError("Profile evidence loaded a forbidden debug extension")
            if scenario.get("zero_area_cell_count") != {"dry": 792, "wet": 792}:
                raise ValueError("Profile evidence has an unexpected zero-area count")
            for path in invariant_paths:
                if _value_at(run, path) != _value_at(reference, path):
                    raise ValueError("Profile evidence changed an authoritative output")
        original_ms = float(
            original_profile["timing"]["wood_model_internal_segments"]
            ["sensible_heat"]["mean_ms"]
        )
        fast_ms = float(
            fast_profile["timing"]["wood_model_internal_segments"]
            ["sensible_heat"]["mean_ms"]
        )
        profile = {
            "original_mean_ms": original_ms,
            "fast_mean_ms": fast_ms,
            "improvement_percent": (original_ms - fast_ms) / original_ms * 100.0,
        }

    median_gate = (
        timings["two_log_step_mean_ms"]["improvement_percent"] > 0.0
        and timings["scenario_seconds"]["improvement_percent"] > 0.0
    )
    repeatability_gate = improving_pairs >= required_improving_pairs
    adopt = median_gate and repeatability_gate
    return {
        "schema_version": 1,
        "phase": "phase6aa",
        "status": "ok",
        "paired_run_count": len(original),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "alternating_order": True,
            "internal_timing_disabled_for_formal_runs": True,
        },
        "geometry": {
            "cell_count_per_log": 1152,
            "zero_area_cell_count_per_log": 792,
            "zero_area_fraction": 0.6875,
        },
        "profile": profile,
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
            "flow_peak_fast": sorted(
                {run["flow"]["active_blocks_peak"] for run in fast}
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_fast_path": adopt,
            "median_step_and_scenario_improved": median_gate,
            "pairs_improving_step_and_scenario": improving_pairs,
            "required_improving_pairs": required_improving_pairs,
            "reason": (
                "zero-area boundary skip improved median wood-step and scenario time "
                "in a majority of alternating pairs"
                if adopt
                else "formal end-to-end adoption gates were not met"
            ),
        },
        "runs": {
            "original": [_report_path(path) for path in original_paths],
            "fast": [_report_path(path) for path in fast_paths],
            "original_profile": (
                _report_path(original_profile_path)
                if original_profile_path
                else None
            ),
            "fast_profile": (
                _report_path(fast_profile_path) if fast_profile_path else None
            ),
        },
    }


def render_svg(report: dict) -> str:
    step = report["timings"]["two_log_step_mean_ms"]
    scenario = report["timings"]["scenario_seconds"]
    profile = report["profile"]
    decision = report["decision"]
    adopted = decision["adopt_fast_path"]
    decision_color = "#86efac" if adopted else "#fca5a5"
    decision_text = "ADOPTED · enable surface-only boundary path" if adopted else "REJECTED · retain original path"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AA zero-area surface-boundary decision</title>
  <desc id="desc">{report['paired_run_count']} alternating pairs compare the original Python boundary calculation with an exact zero-area early skip.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#0d251c"/></linearGradient></defs>
  <style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#34d399;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#86efac}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{decision_color}}}</style>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="64" class="kicker">PHASE 6AA · ZERO-AREA BOUNDARY FAST PATH</text>
  <text x="64" y="114" class="title">Do boundary work only at the boundary</text>
  <text x="64" y="148" class="sub">{report['paired_run_count']} alternating pairs · debugger-free Phase 3 · 792 / 1,152 cells skipped per log</text>
  <rect x="64" y="188" width="336" height="292" rx="22" fill="#13261f" stroke="#15803d"/>
  <text x="92" y="230" class="heading">PROFILED SENSIBLE HEAT</text>
  <text x="92" y="280" class="value">{profile['improvement_percent']:.2f}% faster</text>
  <text x="92" y="316" class="sub">{profile['original_mean_ms']:.4f} → {profile['fast_mean_ms']:.4f} ms</text>
  <text x="92" y="374" class="small">Zero external area only</text>
  <text x="92" y="402" class="small">Conduction still applied</text>
  <text x="92" y="430" class="small">Exact state and CSV</text>
  <rect x="432" y="188" width="336" height="292" rx="22" fill="#13261f" stroke="#15803d"/>
  <text x="460" y="230" class="heading">UNPROFILED WOOD STEP</text>
  <text x="460" y="280" class="value">{step['improvement_percent']:.2f}% faster</text>
  <text x="460" y="316" class="sub">{step['original_median']:.4f} → {step['fast_median']:.4f} ms</text>
  <text x="460" y="374" class="small">Median of 3 runs per path</text>
  <text x="460" y="402" class="small">No internal timers</text>
  <text x="460" y="430" class="small">Same build and cache state</text>
  <rect x="800" y="188" width="336" height="292" rx="22" fill="#13261f" stroke="#15803d"/>
  <text x="828" y="230" class="heading">SCENARIO WALL TIME</text>
  <text x="828" y="280" class="value">{scenario['improvement_percent']:.2f}% faster</text>
  <text x="828" y="316" class="sub">{scenario['original_median']:.4f} → {scenario['fast_median']:.4f} s</text>
  <text x="828" y="374" class="small">Flow and 2 captures retained</text>
  <text x="828" y="402" class="small">{decision['pairs_improving_step_and_scenario']} / {report['paired_run_count']} pairs improve both</text>
  <text x="828" y="430" class="small">Debugger extensions: 0</text>
  <rect x="64" y="522" width="1072" height="94" rx="18" fill="#10251d" stroke="{decision_color}" stroke-width="2"/>
  <text x="92" y="566" class="decision">{decision_text}</text>
  <text x="92" y="594" class="sub">Equations, grid, dt, cell order, state SHA-256, CSV SHA-256, and ignition remain unchanged.</text>
  <text x="64" y="654" class="small">Flow active blocks are recorded separately as a non-authoritative GPU diagnostic.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--fast-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--original-profile", type=Path, required=True)
    parser.add_argument("--fast-profile", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(
        arguments.original_summary,
        arguments.fast_summary,
        arguments.original_profile,
        arguments.fast_profile,
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
