"""Compare a rejected Python sensible-heat loop trial at the Phase 3 boundary."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT / "docs" / "devlog" / "assets" / "phase6"
    / "phase3_sensible_heat_trial_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")
INTERNAL_SEGMENTS = {
    "input_validation",
    "conduction",
    "sensible_heat",
    "evaporation",
    "pyrolysis",
    "char_oxidation",
    "state_finalize",
    "result_aggregation",
}


def _load(paths: list[Path]) -> list[dict]:
    if len(paths) < 3:
        raise ValueError("Each comparison group requires at least three runs")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _value_at(run: dict, path: tuple[str, ...]):
    value = run
    for key in path:
        value = value[key]
    return value


def _validate(groups: dict[str, list[dict]]) -> dict:
    reference = groups["before_profile"][0]
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
    for group_name, runs in groups.items():
        expect_profile = group_name.endswith("profile") and not group_name.endswith(
            "unprofile"
        )
        for run in runs:
            if run.get("status") != "ok" or run.get("phase") != "phase3":
                raise ValueError(f"{group_name} contains an unsuccessful Phase 3 run")
            scenario = run["scenario"]
            if scenario.get("wood_array_backend") != "python":
                raise ValueError(f"{group_name} did not use the Python backend")
            if not scenario.get("debugger_free"):
                raise ValueError(f"{group_name} loaded a forbidden debug extension")
            if bool(scenario.get("wood_internal_timing_enabled")) != expect_profile:
                raise ValueError(f"{group_name} has the wrong profiling mode")
            segments = run["timing"].get("wood_model_internal_segments", {})
            if expect_profile:
                if set(segments) != INTERNAL_SEGMENTS:
                    raise ValueError(f"{group_name} has unexpected internal segments")
                if any(value.get("sample_count") != 1180 for value in segments.values()):
                    raise ValueError(f"{group_name} has an invalid sample count")
            elif segments:
                raise ValueError(f"{group_name} unexpectedly contains internal timings")
            for path in invariant_paths:
                if _value_at(run, path) != _value_at(reference, path):
                    raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")
    return reference


def _median(runs: list[dict], path: tuple[str, ...]) -> float:
    return statistics.median(float(_value_at(run, path)) for run in runs)


def _comparison(before: float, after: float) -> dict:
    return {
        "before_median": before,
        "after_median": after,
        "improvement_percent": (before - after) / before * 100.0,
    }


def build_report(
    paths: dict[str, list[Path]], groups: dict[str, list[dict]]
) -> dict:
    reference = _validate(groups)
    before_profile = groups["before_profile"]
    after_profile = groups["after_profile"]
    before_unprofile = groups["before_unprofile"]
    after_unprofile = groups["after_unprofile"]
    profile = {
        "sensible_heat_mean_ms": _comparison(
            _median(
                before_profile,
                ("timing", "wood_model_internal_segments", "sensible_heat", "mean_ms"),
            ),
            _median(
                after_profile,
                ("timing", "wood_model_internal_segments", "sensible_heat", "mean_ms"),
            ),
        ),
        "two_log_step_mean_ms": _comparison(
            _median(before_profile, ("timing", "two_log_model_step_mean_ms")),
            _median(after_profile, ("timing", "two_log_model_step_mean_ms")),
        ),
    }
    unprofiled = {
        "two_log_step_mean_ms": _comparison(
            _median(before_unprofile, ("timing", "two_log_model_step_mean_ms")),
            _median(after_unprofile, ("timing", "two_log_model_step_mean_ms")),
        ),
        "two_log_step_p95_ms": _comparison(
            _median(before_unprofile, ("timing", "two_log_model_step_p95_ms")),
            _median(after_unprofile, ("timing", "two_log_model_step_p95_ms")),
        ),
        "scenario_seconds": _comparison(
            _median(before_unprofile, ("scenario", "simulation_wall_seconds")),
            _median(after_unprofile, ("scenario", "simulation_wall_seconds")),
        ),
        "runner_seconds": _comparison(
            _median(before_unprofile, ("runner_wall_seconds",)),
            _median(after_unprofile, ("runner_wall_seconds",)),
        ),
    }
    internal_improved = profile["sensible_heat_mean_ms"]["improvement_percent"] > 0
    production_improved = (
        unprofiled["two_log_step_mean_ms"]["improvement_percent"] > 0
        and unprofiled["scenario_seconds"]["improvement_percent"] > 0
    )
    return {
        "schema_version": 1,
        "phase": "phase6z",
        "status": "ok",
        "trial": {
            "description": (
                "split scalar heat-flux loop and hoist ambient power and coefficient "
                "lookups without changing equations"
            ),
            "production_code_retained": "original Python loop",
            "trial_reverted": True,
        },
        "run_counts": {name: len(runs) for name, runs in groups.items()},
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "profile_and_unprofiled_evidence_separated": True,
        },
        "profiled": profile,
        "unprofiled": unprofiled,
        "equivalence": {
            "exact_authoritative_outputs_all_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {
                "dry": reference["wood"]["dry"]["ignition_seconds"],
                "wet": reference["wood"]["wet"]["ignition_seconds"],
            },
            "flow_peak_before": sorted(
                {run["flow"]["active_blocks_peak"] for run in before_unprofile}
            ),
            "flow_peak_after": sorted(
                {run["flow"]["active_blocks_peak"] for run in after_unprofile}
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_trial": internal_improved and production_improved,
            "internal_candidate_improved": internal_improved,
            "unprofiled_step_and_scenario_improved": production_improved,
            "reason": (
                "the isolated sensible-heat segment improved, but unprofiled wood-step "
                "and scenario medians regressed; keep the original loop"
            ),
        },
        "measurement_limit": (
            "before and after were separate three-run cohorts, not alternating pairs; "
            "the absence of an end-to-end gain is sufficient for conservative rejection"
        ),
        "runs": {name: [str(path) for path in group] for name, group in paths.items()},
    }


def render_svg(report: dict) -> str:
    sensible = report["profiled"]["sensible_heat_mean_ms"]
    step = report["unprofiled"]["two_log_step_mean_ms"]
    scenario = report["unprofiled"]["scenario_seconds"]
    runner = report["unprofiled"]["runner_seconds"]
    sensible_gain = sensible["improvement_percent"]
    step_regression = -step["improvement_percent"]
    scenario_regression = -scenario["improvement_percent"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6Z sensible-heat optimization trial decision</title>
  <desc id="desc">Three profiled and three unprofiled runs before and after show an internal improvement but no end-to-end gain, so the trial is rejected.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#16120f"/><stop offset="1" stop-color="#251313"/></linearGradient></defs>
  <style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#fff7ed}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#fb923c;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 29px 'Segoe UI',sans-serif}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 25px 'Segoe UI',sans-serif;fill:#fca5a5}}</style>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="64" class="kicker">PHASE 6Z · CONSERVATIVE PERFORMANCE GATE</text>
  <text x="64" y="114" class="title">A faster inner segment is not enough</text>
  <text x="64" y="148" class="sub">3 profiled + 3 unprofiled runs before and after · debugger-free Phase 3</text>
  <rect x="64" y="188" width="500" height="300" rx="22" fill="#17251f" stroke="#15803d"/>
  <text x="94" y="232" class="heading">PROFILED SENSIBLE-HEAT SEGMENT</text>
  <text x="94" y="288" class="value" fill="#86efac">{sensible_gain:.2f}% faster</text>
  <text x="94" y="326" class="sub">{sensible['before_median']:.4f} → {sensible['after_median']:.4f} ms</text>
  <text x="94" y="382" class="small">Scalar branch split · ambient T⁴ hoisted</text>
  <text x="94" y="410" class="small">Authoritative state, CSV, ignition exact</text>
  <text x="94" y="438" class="small">Useful diagnosis, not an adoption result</text>
  <rect x="594" y="188" width="542" height="300" rx="22" fill="#32191a" stroke="#dc2626"/>
  <text x="624" y="232" class="heading">UNPROFILED APPLICATION BOUNDARY</text>
  <text x="624" y="282" class="value" fill="#fca5a5">Step {step_regression:.2f}% slower</text>
  <text x="624" y="318" class="sub">{step['before_median']:.4f} → {step['after_median']:.4f} ms</text>
  <text x="624" y="368" class="value" fill="#fca5a5">Scenario {scenario_regression:.2f}% slower</text>
  <text x="624" y="404" class="sub">{scenario['before_median']:.4f} → {scenario['after_median']:.4f} s</text>
  <text x="624" y="450" class="small">Runner {runner['before_median']:.3f} → {runner['after_median']:.3f} s</text>
  <rect x="64" y="526" width="1072" height="92" rx="18" fill="#351718" stroke="#ef4444" stroke-width="2"/>
  <text x="92" y="568" class="decision">REJECTED · original Python loop retained</text>
  <text x="92" y="596" class="sub">No physical equations, grid, dt, backend default, or authoritative output changed.</text>
  <text x="64" y="654" class="small">Cohorts were not alternating pairs. With no end-to-end gain, conservative rejection does not require attributing the regression to the trial.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-profile", type=Path, nargs="+", required=True)
    parser.add_argument("--after-profile", type=Path, nargs="+", required=True)
    parser.add_argument("--before-unprofile", type=Path, nargs="+", required=True)
    parser.add_argument("--after-unprofile", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    paths = {
        "before_profile": arguments.before_profile,
        "after_profile": arguments.after_profile,
        "before_unprofile": arguments.before_unprofile,
        "after_unprofile": arguments.after_unprofile,
    }
    groups = {name: _load(group) for name, group in paths.items()}
    report = build_report(paths, groups)
    if report["decision"]["adopt_trial"]:
        raise RuntimeError("This report records a rejected trial, but adoption gates passed")
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
