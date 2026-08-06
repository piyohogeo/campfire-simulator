"""Aggregate Phase 6AH sensible-heat subsegment profiles."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/devlog/assets/phase6"
DEFAULT_JSON = ASSETS / "phase3_sensible_heat_profile_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
LABELS = {
    "heat_capacity_evaluation": "Heat capacity evaluation",
    "interior_conduction_update": "Interior conduction-only update",
    "surface_boundary_update": "Surface boundary update",
    "loop_and_timer_overhead": "Loop and timer overhead",
}
OPERATION_SEGMENTS = tuple(name for name in LABELS if name != "loop_and_timer_overhead")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _at(document: dict, path: tuple[str, ...]):
    value = document
    for key in path:
        value = value[key]
    return value


def _validate(runs: list[dict]) -> dict:
    if len(runs) < 3:
        raise ValueError("At least three sensible-heat profiles are required")
    reference = runs[0]
    invariants = (
        ("metrics_csv_sha256",),
        ("wood", "dry", "authoritative_state_sha256"),
        ("wood", "wet", "authoritative_state_sha256"),
        ("wood", "dry", "ignition_seconds"),
        ("wood", "wet", "ignition_seconds"),
    )
    for run in runs:
        scenario = run.get("scenario", {})
        if run.get("status") != "ok" or run.get("phase") != "phase3":
            raise ValueError("A profile is not a successful Phase 3 run")
        if not (
            scenario.get("wood_array_backend") == "python"
            and scenario.get("wood_internal_timing_enabled")
            and scenario.get("wood_sensible_heat_timing_enabled")
            and scenario.get("python_surface_boundary_fast_path")
            and scenario.get("python_state_clamp_fast_path")
            and scenario.get("deferred_cell_phase_updates")
            and scenario.get("compact_runtime_metrics")
            and not scenario.get("precomputed_runtime_topology")
            and scenario.get("debugger_free")
        ):
            raise ValueError("A profile did not use the Phase 6AH control path")
        if scenario.get("zero_area_cell_count") != {"dry": 792, "wet": 792}:
            raise ValueError("The expected 792 interior cells per log were not present")
        segments = run["timing"].get("wood_sensible_heat_segments", {})
        if set(segments) != set(LABELS):
            raise ValueError("Unexpected sensible-heat timing schema")
        if any(item.get("sample_count") != 1180 for item in segments.values()):
            raise ValueError("Every sensible-heat segment must contain 1,180 samples")
        parent = run["timing"]["wood_model_internal_segments"]["sensible_heat"]
        if parent.get("sample_count") != 1180:
            raise ValueError("The parent sensible-heat segment must contain 1,180 samples")
        subtotal = sum(item["mean_ms"] for item in segments.values())
        if abs(subtotal - parent["mean_ms"]) > 0.003:
            raise ValueError("Sensible-heat subsegments do not reconcile with the parent")
        for path in invariants:
            if _at(run, path) != _at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")
    return reference


def build_report(paths: list[Path]) -> dict:
    runs = [_load(path) for path in paths]
    reference = _validate(runs)
    segments = {}
    for name, label in LABELS.items():
        mean_ms = statistics.median(
            run["timing"]["wood_sensible_heat_segments"][name]["mean_ms"]
            for run in runs
        )
        p95_ms = statistics.median(
            run["timing"]["wood_sensible_heat_segments"][name]["p95_ms"]
            for run in runs
        )
        segments[name] = {"label": label, "median_mean_ms": mean_ms, "median_p95_ms": p95_ms}
    detailed_total = sum(item["median_mean_ms"] for item in segments.values())
    operation_total = sum(segments[name]["median_mean_ms"] for name in OPERATION_SEGMENTS)
    for name, item in segments.items():
        item["inclusive_share_percent"] = item["median_mean_ms"] / detailed_total * 100.0
        item["operation_share_percent"] = (
            item["median_mean_ms"] / operation_total * 100.0
            if name in OPERATION_SEGMENTS
            else None
        )
    operation_order = sorted(
        OPERATION_SEGMENTS,
        key=lambda name: segments[name]["median_mean_ms"],
        reverse=True,
    )
    return {
        "schema_version": 1,
        "phase": "phase6ah",
        "status": "ok",
        "run_count": len(runs),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "profile_mode": "per-cell sensible-heat operation timers",
            "profile_is_for_candidate_selection_not_adoption": True,
            "interior_cells_per_log": 792,
            "surface_cells_per_log": 360,
        },
        "timing": {
            "detailed_total_median_mean_ms": detailed_total,
            "operation_total_median_mean_ms": operation_total,
            "profiled_parent_sensible_heat_median_mean_ms": statistics.median(
                run["timing"]["wood_model_internal_segments"]["sensible_heat"]["mean_ms"]
                for run in runs
            ),
            "profiled_two_log_step_median_mean_ms": statistics.median(
                run["timing"]["two_log_model_step_mean_ms"] for run in runs
            ),
            "profiled_scenario_median_seconds": statistics.median(
                run["scenario"]["simulation_wall_seconds"] for run in runs
            ),
            "segments": segments,
        },
        "selection": {
            "primary_candidate": operation_order[0],
            "operation_order": operation_order,
            "next_trial": "specialize constant dry-wood heat-capacity evaluation without changing bounds or material APIs",
            "next_gate": "exact outputs plus alternating unprofiled step-loop and scenario improvement",
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
            "flow_active_blocks_peak_observed": sorted(
                {run["flow"]["active_blocks_peak"] for run in runs}
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "runs": [str(path.resolve().relative_to(ROOT)) for path in paths],
    }


def render_svg(report: dict) -> str:
    segments = report["timing"]["segments"]
    order = report["selection"]["operation_order"] + ["loop_and_timer_overhead"]
    maximum = max(segments[name]["median_mean_ms"] for name in order)
    rows = []
    for index, name in enumerate(order):
        item = segments[name]
        y = 246 + index * 76
        width = 500.0 * item["median_mean_ms"] / maximum
        color = "#fb923c" if name == report["selection"]["primary_candidate"] else "#38bdf8"
        if name == "loop_and_timer_overhead":
            color = "#64748b"
        share = item["inclusive_share_percent"]
        rows.append(
            f'<text x="92" y="{y}" class="label">{html.escape(item["label"])}</text>'
            f'<rect x="348" y="{y - 20}" width="{width:.1f}" height="28" rx="14" fill="{color}"/>'
            f'<text x="870" y="{y}" class="value">{item["median_mean_ms"]:.3f} ms / {share:.1f}%</text>'
        )
    timing = report["timing"]
    selected = segments[report["selection"]["primary_candidate"]]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc"><title id="title">Phase 6AH sensible heat profile</title><desc id="desc">Three debugger-free profiles split sensible heat into heat capacity, interior update, surface boundary update, and profiler overhead.</desc><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0c2d48"/><stop offset="1" stop-color="#1c1917"/></linearGradient></defs><style>.title{{font:750 37px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#7dd3fc;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.label{{font:650 15px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:14px 'Segoe UI',sans-serif;fill:#bae6fd}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 22px 'Segoe UI',sans-serif;fill:#fdba74}}</style><rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="60" class="kicker">PHASE 6AH - SENSIBLE-HEAT DECOMPOSITION</text><text x="64" y="110" class="title">Heat-capacity evaluation dominates measured work</text><text x="64" y="145" class="sub">{report['run_count']} runs - 1,180 measured two-log steps each - 792 interior + 360 surface cells per log</text><rect x="64" y="184" width="1072" height="372" rx="22" fill="#0f2535" stroke="#0ea5e9"/>{''.join(rows)}<text x="64" y="600" class="decision">Next candidate: {html.escape(selected['label'])}</text><text x="64" y="630" class="small">{selected['median_mean_ms']:.3f} ms - {selected['operation_share_percent']:.1f}% of measured operations; per-cell timers make this selection-only evidence.</text><text x="64" y="658" class="small">Profiled parent {timing['profiled_parent_sensible_heat_median_mean_ms']:.3f} ms - exact state, CSV, and ignition across all runs.</text></svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    args = parser.parse_args()
    report = build_report(args.summary)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
