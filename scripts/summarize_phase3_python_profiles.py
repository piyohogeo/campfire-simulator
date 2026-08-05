"""Aggregate debugger-free Phase 3 Python wood-step internal profiles."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT / "docs" / "devlog" / "assets" / "phase6"
    / "phase3_python_internal_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")
SEGMENT_LABELS = {
    "input_validation": "Input validation",
    "conduction": "Conduction",
    "sensible_heat": "Sensible heat",
    "evaporation": "Evaporation",
    "pyrolysis": "Pyrolysis",
    "char_oxidation": "Char oxidation",
    "state_finalize": "Clamp + phase",
    "result_aggregation": "Result aggregation",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(runs: list[dict]) -> dict:
    if len(runs) < 3:
        raise ValueError("At least three Phase 3 profile runs are required")
    reference = runs[0]
    invariant_paths = (
        ("metrics_csv_sha256",),
        ("wood", "dry", "authoritative_state_sha256"),
        ("wood", "wet", "authoritative_state_sha256"),
        ("wood", "dry", "ignition_seconds"),
        ("wood", "wet", "ignition_seconds"),
        ("flow", "active_blocks_peak"),
    )

    def value_at(run: dict, path: tuple[str, ...]):
        value = run
        for key in path:
            value = value[key]
        return value

    for run in runs:
        if run.get("status") != "ok" or run.get("phase") != "phase3":
            raise ValueError("A profile is not a successful Phase 3 run")
        scenario = run["scenario"]
        if scenario.get("wood_array_backend") != "python":
            raise ValueError("All profiles must use the default Python backend")
        if not scenario.get("wood_internal_timing_enabled"):
            raise ValueError("A run did not enable wood internal timing")
        if not scenario.get("debugger_free"):
            raise ValueError("A run loaded a forbidden debug extension")
        segments = run["timing"].get("wood_model_internal_segments", {})
        if set(segments) != set(SEGMENT_LABELS):
            raise ValueError(f"Unexpected timing segments: {sorted(segments)}")
        if any(segment.get("sample_count") != 1180 for segment in segments.values()):
            raise ValueError("Every internal segment must contain 1,180 samples")
        for path in invariant_paths:
            if value_at(run, path) != value_at(reference, path):
                raise ValueError(f"Phase 3 invariant differs: {'.'.join(path)}")
    return reference


def build_report(paths: list[Path]) -> dict:
    runs = [_load(path) for path in paths]
    reference = _validate(runs)
    segments = {}
    for name, label in SEGMENT_LABELS.items():
        mean_ms = statistics.median(
            run["timing"]["wood_model_internal_segments"][name]["mean_ms"]
            for run in runs
        )
        p95_ms = statistics.median(
            run["timing"]["wood_model_internal_segments"][name]["p95_ms"]
            for run in runs
        )
        segments[name] = {
            "label": label,
            "median_mean_ms": mean_ms,
            "median_p95_ms": p95_ms,
        }
    internal_total_ms = sum(value["median_mean_ms"] for value in segments.values())
    for value in segments.values():
        value["share_percent"] = value["median_mean_ms"] / internal_total_ms * 100.0
    ordered_names = sorted(
        segments, key=lambda name: segments[name]["median_mean_ms"], reverse=True
    )
    full_step_ms = statistics.median(
        run["timing"]["two_log_model_step_mean_ms"] for run in runs
    )
    scenario_seconds = statistics.median(
        run["scenario"]["simulation_wall_seconds"] for run in runs
    )
    runner_seconds = statistics.median(run["runner_wall_seconds"] for run in runs)
    return {
        "schema_version": 1,
        "phase": "phase6y",
        "status": "ok",
        "run_count": len(runs),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "internal_timing_opt_in": True,
        },
        "configuration": {
            "steps": reference["scenario"]["steps"],
            "warmup_steps_excluded": reference["timing"]["warmup_steps_excluded"],
            "model_dt_seconds": reference["scenario"]["model_dt_seconds"],
            "model_duration_seconds": reference["scenario"]["model_duration_seconds"],
        },
        "timing": {
            "two_log_step_median_mean_ms": full_step_ms,
            "internal_total_median_mean_ms": internal_total_ms,
            "scenario_median_seconds": scenario_seconds,
            "runner_median_seconds": runner_seconds,
            "segments": segments,
        },
        "selection": {
            "primary_candidate": ordered_names[0],
            "candidate_order": ordered_names,
            "constraint": "avoid new AoS-to-array roundtrips and preserve equations",
        },
        "equivalence": {
            "exact_authoritative_outputs_across_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {
                "dry": reference["wood"]["dry"]["ignition_seconds"],
                "wet": reference["wood"]["wet"]["ignition_seconds"],
            },
            "flow_active_blocks_peak": reference["flow"]["active_blocks_peak"],
            "flow_peak_consistent_across_runs": True,
        },
        "runs": [str(path) for path in paths],
    }


def render_svg(report: dict) -> str:
    segments = report["timing"]["segments"]
    order = report["selection"]["candidate_order"]
    maximum = segments[order[0]]["median_mean_ms"]
    rows = []
    for index, name in enumerate(order):
        segment = segments[name]
        y = 226 + index * 46
        width = 430.0 * segment["median_mean_ms"] / maximum
        rows.append(
            f'<text x="92" y="{y}" class="label">{html.escape(segment["label"])}</text>'
            f'<rect x="276" y="{y - 17}" width="{width:.1f}" height="24" rx="12" fill="#f59e0b"/>'
            f'<text x="724" y="{y}" class="value">{segment["median_mean_ms"]:.3f} ms · {segment["share_percent"]:.1f}%</text>'
        )
    primary = segments[order[0]]
    timing = report["timing"]
    equivalence = report["equivalence"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6Y debugger-free Python wood-step profile</title>
  <desc id="desc">Three Phase 3 runs rank eight internal Python wood-model segments while preserving exact state, CSV, ignition, and Flow outputs.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#18130c"/><stop offset="1" stop-color="#10241d"/></linearGradient></defs>
  <style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#fff7ed}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#fbbf24;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.label{{font:650 15px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:14px 'Segoe UI',sans-serif;fill:#fde68a}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <text x="64" y="62" class="kicker">PHASE 6Y · DEBUGGER-FREE PYTHON PROFILE</text>
  <text x="64" y="112" class="title">Find the next CPU hot path in the real app</text>
  <text x="64" y="146" class="sub">{report['run_count']} runs · 1,180 measured two-log steps each · Flow and captures retained</text>
  <rect x="64" y="174" width="820" height="420" rx="22" fill="#1f2937" stroke="#475569"/>
  {''.join(rows)}
  <rect x="912" y="174" width="224" height="420" rx="22" fill="#102a22" stroke="#15803d"/>
  <text x="938" y="216" class="kicker">SELECTED</text>
  <text x="938" y="258" class="decision">{html.escape(primary['label'])}</text>
  <text x="938" y="286" class="sub">{primary['median_mean_ms']:.3f} ms</text>
  <text x="938" y="310" class="sub">{primary['share_percent']:.1f}% of internals</text>
  <line x1="938" y1="340" x2="1110" y2="340" stroke="#365b4b"/>
  <text x="938" y="376" class="small">Full step median</text>
  <text x="938" y="400" class="sub">{timing['two_log_step_median_mean_ms']:.3f} ms</text>
  <text x="938" y="438" class="small">Scenario median</text>
  <text x="938" y="462" class="sub">{timing['scenario_median_seconds']:.3f} s</text>
  <text x="938" y="500" class="small">Output gates</text>
  <text x="938" y="524" class="sub">state · CSV · ignition</text>
  <text x="938" y="548" class="sub">Flow peak {equivalence['flow_active_blocks_peak']} · consistent</text>
  <line x1="64" y1="624" x2="1136" y2="624" stroke="#334155"/>
  <text x="64" y="654" class="small">Instrumentation is opt-in. Next change must avoid new AoS array roundtrips and preserve equations, grid, dt, and hashes.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, nargs="+", required=True)
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
