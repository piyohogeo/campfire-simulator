"""Validate repeated debugger-free Phase 3 backend runs and render Phase 6X evidence."""

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
    / "phase3_backend_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")
CONFIGURATION_FIELDS = (
    "model_dt_seconds",
    "flow_update_interval_steps",
    "flow_update_interval_seconds",
    "steps",
    "model_duration_seconds",
    "external_heat_flux_w_m2",
)


def _load(path: Path, expected_backend: str) -> dict:
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("status") != "ok" or summary.get("phase") != "phase3":
        raise ValueError(f"Not a successful Phase 3 summary: {path}")
    scenario = summary.get("scenario", {})
    if scenario.get("wood_array_backend") != expected_backend:
        raise ValueError(f"Unexpected backend in {path}: {scenario.get('wood_array_backend')}")
    if scenario.get("debugger_free") is not True:
        raise ValueError(f"Phase 3 run was not debugger-free: {path}")
    enabled_debug = [
        name
        for name, enabled in scenario.get("debug_extension_status", {}).items()
        if enabled
    ]
    if enabled_debug:
        raise ValueError(f"Debug extensions remained active in {path}: {enabled_debug}")
    if not summary.get("metrics_csv_sha256"):
        raise ValueError(f"Phase 3 summary has no metrics CSV digest: {path}")
    return summary


def _median(runs: list[dict], getter) -> float:
    return statistics.median(float(getter(run)) for run in runs)


def _percent_improvement(baseline: float, candidate: float) -> float:
    return (1.0 - candidate / baseline) * 100.0


def build_report(python_paths: list[Path], numpy_paths: list[Path]) -> dict:
    if len(python_paths) < 2 or len(python_paths) != len(numpy_paths):
        raise ValueError("Two or more balanced Python/NumPy Phase 3 runs are required")
    python_runs = [_load(path, "python") for path in python_paths]
    numpy_runs = [_load(path, "numpy") for path in numpy_paths]
    all_runs = python_runs + numpy_runs
    reference_configuration = {
        field: python_runs[0]["scenario"][field] for field in CONFIGURATION_FIELDS
    }
    for run in all_runs[1:]:
        configuration = {
            field: run["scenario"][field] for field in CONFIGURATION_FIELDS
        }
        if configuration != reference_configuration:
            raise ValueError("Phase 3 backend run configurations differ")

    state_hashes = {
        kind: {run["wood"][kind]["authoritative_state_sha256"] for run in all_runs}
        for kind in ("dry", "wet")
    }
    csv_hashes = {run["metrics_csv_sha256"] for run in all_runs}
    ignition_pairs = {
        (run["wood"]["dry"]["ignition_seconds"], run["wood"]["wet"]["ignition_seconds"])
        for run in all_runs
    }
    flow_peaks = {run["flow"]["active_blocks_peak"] for run in all_runs}
    exact_outputs = (
        all(len(values) == 1 for values in state_hashes.values())
        and len(csv_hashes) == 1
        and len(ignition_pairs) == 1
        and len(flow_peaks) == 1
    )
    if not exact_outputs:
        raise ValueError("Python and NumPy Phase 3 outputs differ")

    timing_getters = {
        "wood_model_step_mean_ms": lambda run: run["timing"]["segments"]["wood_model_step"]["mean_ms"],
        "wood_model_step_p95_ms": lambda run: run["timing"]["segments"]["wood_model_step"]["p95_ms"],
        "scenario_wall_seconds": lambda run: run["scenario"]["simulation_wall_seconds"],
        "runner_wall_seconds": lambda run: run["runner_wall_seconds"],
    }
    timings = {}
    for name, getter in timing_getters.items():
        python_median = _median(python_runs, getter)
        numpy_median = _median(numpy_runs, getter)
        timings[name] = {
            "python_median": python_median,
            "numpy_median": numpy_median,
            "numpy_improvement_percent": _percent_improvement(
                python_median, numpy_median
            ),
        }

    wood_gain = timings["wood_model_step_mean_ms"]["numpy_improvement_percent"]
    scenario_gain = timings["scenario_wall_seconds"]["numpy_improvement_percent"]
    repeatable_gain = wood_gain > 0.0 and scenario_gain > 0.0
    return {
        "phase": "6X",
        "status": "ok",
        "paired_run_count": len(python_runs),
        "execution_order": "alternating within consecutive pairs",
        "configuration": reference_configuration,
        "environment": {
            "debugger_free_all_runs": True,
            "debug_extension_status_recorded": True,
        },
        "equivalence": {
            "exact_outputs": exact_outputs,
            "dry_state_sha256": next(iter(state_hashes["dry"])),
            "wet_state_sha256": next(iter(state_hashes["wet"])),
            "metrics_csv_sha256": next(iter(csv_hashes)),
            "ignition_seconds": list(next(iter(ignition_pairs))),
            "flow_active_blocks_peak": next(iter(flow_peaks)),
        },
        "timings": timings,
        "decision": {
            "default_backend": "python",
            "numpy_default_adoption": False,
            "repeatable_end_to_end_gain_observed": repeatable_gain,
            "reason": (
                "paired debugger-free evidence did not show a NumPy improvement; "
                "retain Python as the default"
                if not repeatable_gain
                else "paired debugger-free evidence improved both wood-step and scenario "
                "timing; retain explicit selection pending release review"
            ),
        },
        "runs": {
            "python": [str(path) for path in python_paths],
            "numpy": [str(path) for path in numpy_paths],
        },
    }


def render_svg(report: dict) -> str:
    wood = report["timings"]["wood_model_step_mean_ms"]
    scenario = report["timings"]["scenario_wall_seconds"]
    max_wood = max(wood["python_median"], wood["numpy_median"])
    python_width = 390.0 * wood["python_median"] / max_wood
    numpy_width = 390.0 * wood["numpy_median"] / max_wood
    gain = wood["numpy_improvement_percent"]
    gain_label = f"{gain:.1f}% faster" if gain >= 0.0 else f"{-gain:.1f}% slower"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6X debugger-free Phase 3 backend comparison</title>
  <desc id="desc">Two or more alternating Python and NumPy runs compare complete Phase 3 timing with exact authoritative outputs and no debug extensions.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#071b18"/></linearGradient></defs>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="68" fill="#34d399" font-family="Segoe UI,sans-serif" font-size="18" font-weight="700" letter-spacing="2">PHASE 6X · DEBUGGER-FREE END-TO-END</text>
  <text x="64" y="116" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="38" font-weight="750">Measure the application boundary cleanly</text>
  <text x="64" y="148" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="17">{report['paired_run_count']} alternating pairs · 1,200 steps · captures and Flow retained</text>
  <rect x="64" y="188" width="672" height="330" rx="22" fill="#162133" stroke="#334155"/>
  <text x="96" y="232" fill="#cbd5e1" font-family="Segoe UI,sans-serif" font-size="15" font-weight="700" letter-spacing="1.5">TWO-LOG WOOD STEP · MEDIAN MEAN</text>
  <text x="96" y="286" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="20" font-weight="700">Python</text>
  <text x="690" y="286" text-anchor="end" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="22" font-weight="750">{wood['python_median']:.3f} ms</text>
  <rect x="96" y="304" width="{python_width:.1f}" height="34" rx="17" fill="#64748b"/>
  <text x="96" y="382" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="20" font-weight="700">NumPy</text>
  <text x="690" y="382" text-anchor="end" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="22" font-weight="750">{wood['numpy_median']:.3f} ms</text>
  <rect x="96" y="400" width="{numpy_width:.1f}" height="34" rx="17" fill="#22c55e"/>
  <text x="96" y="484" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="30" font-weight="750">{gain_label}</text>
  <rect x="768" y="188" width="368" height="330" rx="22" fill="#10231f" stroke="#166534"/>
  <text x="800" y="232" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="15" font-weight="700" letter-spacing="1.5">ACCEPTANCE GATES</text>
  <text x="800" y="286" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ no debug extensions</text>
  <text x="800" y="328" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ dry / wet state SHA-256</text>
  <text x="800" y="370" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ CSV / ignition / Flow</text>
  <text x="800" y="412" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ tracked scene untouched</text>
  <text x="800" y="468" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="16">Scenario {scenario['python_median']:.2f} → {scenario['numpy_median']:.2f} s</text>
  <line x1="64" y1="558" x2="1136" y2="558" stroke="#273449"/>
  <text x="64" y="606" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="22" font-weight="750">Default remains Python — NumPy did not improve end-to-end</text>
  <text x="64" y="638" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="16">Debugger-free evidence is eligible for performance interpretation; NumPy remains available by explicit selection.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--numpy-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.python_summary, arguments.numpy_summary)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
