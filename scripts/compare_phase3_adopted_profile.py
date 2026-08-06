"""Re-profile the adopted Phase 3 Python path against the Phase 6Y baseline."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/devlog/assets/phase6"
BASELINE_JSON = ASSETS / "phase3_python_internal_report.json"
DEFAULT_JSON = ASSETS / "phase3_adopted_internal_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
LABELS = {
    "input_validation": "Input validation",
    "conduction": "Conduction",
    "sensible_heat": "Sensible heat",
    "evaporation": "Evaporation",
    "pyrolysis": "Pyrolysis",
    "char_oxidation": "Char oxidation",
    "state_finalize": "State finalize",
    "result_aggregation": "Result aggregation",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(runs: list[dict]) -> dict:
    if len(runs) < 3:
        raise ValueError("At least three adopted-path profiles are required")
    reference = runs[0]
    invariants = (
        ("metrics_csv_sha256",),
        ("wood", "dry", "authoritative_state_sha256"),
        ("wood", "wet", "authoritative_state_sha256"),
        ("wood", "dry", "ignition_seconds"),
        ("wood", "wet", "ignition_seconds"),
    )

    def at(run: dict, path: tuple[str, ...]):
        value = run
        for key in path:
            value = value[key]
        return value

    for run in runs:
        scenario = run.get("scenario", {})
        if run.get("status") != "ok" or run.get("phase") != "phase3":
            raise ValueError("A profile is not a successful Phase 3 run")
        if not (
            scenario.get("wood_array_backend") == "python"
            and scenario.get("wood_internal_timing_enabled")
            and scenario.get("python_surface_boundary_fast_path")
            and scenario.get("python_state_clamp_fast_path")
            and scenario.get("deferred_cell_phase_updates")
            and scenario.get("compact_runtime_metrics")
            and not scenario.get("precomputed_runtime_topology")
            and scenario.get("debugger_free")
        ):
            raise ValueError("A profile did not use the complete adopted control path")
        segments = run["timing"].get("wood_model_internal_segments", {})
        if set(segments) != set(LABELS):
            raise ValueError("Unexpected internal timing schema")
        if any(item.get("sample_count") != 1180 for item in segments.values()):
            raise ValueError("Every segment must contain 1,180 samples")
        for path in invariants:
            if at(run, path) != at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")
    return reference


def build_report(paths: list[Path], baseline_path: Path) -> dict:
    runs = [_load(path) for path in paths]
    reference = _validate(runs)
    baseline = _load(baseline_path)
    if baseline.get("phase") != "phase6y" or baseline.get("status") != "ok":
        raise ValueError("Baseline is not the accepted Phase 6Y profile")
    segments = {}
    for name, label in LABELS.items():
        current = statistics.median(
            run["timing"]["wood_model_internal_segments"][name]["mean_ms"]
            for run in runs
        )
        current_p95 = statistics.median(
            run["timing"]["wood_model_internal_segments"][name]["p95_ms"]
            for run in runs
        )
        before = float(baseline["timing"]["segments"][name]["median_mean_ms"])
        segments[name] = {
            "label": label,
            "phase6y_median_mean_ms": before,
            "current_median_mean_ms": current,
            "current_median_p95_ms": current_p95,
            "change_percent": (current - before) / before * 100.0,
        }
    current_total = sum(item["current_median_mean_ms"] for item in segments.values())
    baseline_total = float(baseline["timing"]["internal_total_median_mean_ms"])
    for item in segments.values():
        item["current_share_percent"] = item["current_median_mean_ms"] / current_total * 100.0
    order = sorted(segments, key=lambda name: segments[name]["current_median_mean_ms"], reverse=True)
    step = statistics.median(run["timing"]["two_log_model_step_mean_ms"] for run in runs)
    scenario = statistics.median(run["scenario"]["simulation_wall_seconds"] for run in runs)
    return {
        "schema_version": 1,
        "phase": "phase6ag",
        "status": "ok",
        "run_count": len(runs),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "internal_timing_opt_in": True,
            "adopted_paths": ["surface boundary", "state clamp", "deferred phase", "compact metrics"],
            "runtime_topology": "dynamic",
        },
        "timing": {
            "phase6y_internal_total_median_mean_ms": baseline_total,
            "current_internal_total_median_mean_ms": current_total,
            "internal_total_change_percent": (current_total - baseline_total) / baseline_total * 100.0,
            "current_two_log_step_median_mean_ms": step,
            "current_scenario_median_seconds": scenario,
            "segments": segments,
        },
        "selection": {
            "primary_candidate": order[0],
            "candidate_order": order,
            "profile_is_for_candidate_selection_not_adoption": True,
            "next_gate": "exact outputs plus alternating unprofiled step-loop and scenario improvement",
        },
        "equivalence": {
            "exact_authoritative_outputs_across_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {"dry": reference["wood"]["dry"]["ignition_seconds"], "wet": reference["wood"]["wet"]["ignition_seconds"]},
            "flow_active_blocks_peak_observed": sorted({run["flow"]["active_blocks_peak"] for run in runs}),
            "flow_peak_is_not_authoritative": True,
        },
        "baseline_report": str(baseline_path.relative_to(ROOT)),
        "runs": [str(path.resolve().relative_to(ROOT)) for path in paths],
    }


def render_svg(report: dict) -> str:
    segments = report["timing"]["segments"]
    order = report["selection"]["candidate_order"]
    maximum = segments[order[0]]["current_median_mean_ms"]
    rows = []
    for index, name in enumerate(order):
        item = segments[name]
        y = 214 + index * 48
        width = 390.0 * item["current_median_mean_ms"] / maximum
        color = "#fb923c" if index == 0 else "#38bdf8"
        rows.append(
            f'<text x="88" y="{y}" class="label">{html.escape(item["label"])}</text>'
            f'<rect x="260" y="{y - 17}" width="{width:.1f}" height="24" rx="12" fill="{color}"/>'
            f'<text x="666" y="{y}" class="value">{item["current_median_mean_ms"]:.3f} ms / {item["current_share_percent"]:.1f}%</text>'
        )
    selected = segments[order[0]]
    timing = report["timing"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc"><title id="title">Phase 6AG adopted-path internal profile</title><desc id="desc">Three debugger-free profiles rank current Python wood-step segments after adopted optimizations.</desc><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#082f49"/><stop offset="1" stop-color="#1c1917"/></linearGradient></defs><style>.title{{font:750 37px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#7dd3fc;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.label{{font:650 15px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:14px 'Segoe UI',sans-serif;fill:#bae6fd}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 22px 'Segoe UI',sans-serif;fill:#fdba74}}</style><rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="60" class="kicker">PHASE 6AG - ADOPTED-PATH REPROFILE</text><text x="64" y="110" class="title">Update the CPU hotspot map after cumulative changes</text><text x="64" y="144" class="sub">{report['run_count']} runs - 1,180 measured two-log steps each - exact state, CSV, and ignition</text><rect x="64" y="172" width="810" height="420" rx="22" fill="#0f2535" stroke="#0ea5e9"/>{''.join(rows)}<rect x="902" y="172" width="234" height="420" rx="22" fill="#291b13" stroke="#f97316"/><text x="928" y="214" class="kicker">NEXT CANDIDATE</text><text x="928" y="254" class="decision">{html.escape(selected['label'])}</text><text x="928" y="284" class="sub">{selected['current_median_mean_ms']:.3f} ms</text><text x="928" y="308" class="sub">{selected['current_share_percent']:.1f}% of internals</text><line x1="928" y1="338" x2="1110" y2="338" stroke="#7c2d12"/><text x="928" y="374" class="small">Internal total</text><text x="928" y="398" class="sub">{timing['phase6y_internal_total_median_mean_ms']:.3f} to {timing['current_internal_total_median_mean_ms']:.3f} ms</text><text x="928" y="438" class="small">Profiled full step</text><text x="928" y="462" class="sub">{timing['current_two_log_step_median_mean_ms']:.3f} ms</text><text x="928" y="502" class="small">Profiled scenario</text><text x="928" y="526" class="sub">{timing['current_scenario_median_seconds']:.3f} s</text><text x="928" y="566" class="small">Selection only - not adoption</text><line x1="64" y1="624" x2="1136" y2="624" stroke="#334155"/><text x="64" y="654" class="small">Any trial still requires exact outputs and alternating unprofiled step-loop + scenario improvement.</text></svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, nargs="+", required=True)
    parser.add_argument("--baseline-report", type=Path, default=BASELINE_JSON)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    args = parser.parse_args()
    report = build_report(args.summary, args.baseline_report)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
