"""Re-profile the fully adopted Phase 3 Python path at two timing depths."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "phase3_adopted_reprofile_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
PHASE6AG_JSON = ASSETS / "phase3_adopted_internal_report.json"
PHASE6AH_JSON = ASSETS / "phase3_sensible_heat_profile_report.json"
INTERNAL_LABELS = {
    "input_validation": "Input validation",
    "conduction": "Conduction",
    "sensible_heat": "Sensible heat",
    "evaporation": "Evaporation",
    "pyrolysis": "Pyrolysis",
    "char_oxidation": "Char oxidation",
    "state_finalize": "State finalize",
    "result_aggregation": "Result aggregation",
}
SENSIBLE_LABELS = {
    "heat_capacity_evaluation": "Heat capacity evaluation",
    "interior_conduction_update": "Interior conduction-only update",
    "surface_boundary_update": "Surface boundary update",
    "loop_and_timer_overhead": "Loop and timer overhead",
}
SENSIBLE_OPERATIONS = tuple(
    name for name in SENSIBLE_LABELS if name != "loop_and_timer_overhead"
)
INVARIANTS = (
    ("metrics_csv_sha256",),
    ("wood", "dry", "authoritative_state_sha256"),
    ("wood", "wet", "authoritative_state_sha256"),
    ("wood", "dry", "ignition_seconds"),
    ("wood", "wet", "ignition_seconds"),
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _at(document: dict, path: tuple[str, ...]):
    value = document
    for key in path:
        value = value[key]
    return value


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def _validate_common(run: dict, expect_sensible_timing: bool) -> None:
    if run.get("status") != "ok" or run.get("phase") != "phase3":
        raise ValueError("A profile is not a successful Phase 3 run")
    scenario = run.get("scenario", {})
    expected = {
        "wood_array_backend": "python",
        "wood_internal_timing_enabled": True,
        "wood_sensible_heat_timing_enabled": expect_sensible_timing,
        "python_constant_heat_capacity_fast_path": True,
        "wood_state_diagnostics_enabled": False,
        "python_surface_boundary_fast_path": True,
        "python_state_clamp_fast_path": True,
        "deferred_cell_phase_updates": True,
        "compact_runtime_metrics": True,
        "precomputed_runtime_topology": False,
        "debugger_free": True,
    }
    for name, expected_value in expected.items():
        if scenario.get(name) != expected_value:
            raise ValueError(
                f"A profile has unexpected {name}: {scenario.get(name)!r}"
            )
    if scenario.get("zero_area_cell_count") != {"dry": 792, "wet": 792}:
        raise ValueError("A profile has an unexpected zero-area cell count")
    segments = run["timing"].get("wood_model_internal_segments", {})
    if set(segments) != set(INTERNAL_LABELS):
        raise ValueError("Unexpected wood internal timing schema")
    if any(item.get("sample_count") != 1180 for item in segments.values()):
        raise ValueError("Every wood internal segment must contain 1,180 samples")


def _validate(
    internal_runs: list[dict], sensible_runs: list[dict]
) -> dict:
    if len(internal_runs) < 3 or len(sensible_runs) < 3:
        raise ValueError("At least three profiles are required at each timing depth")
    if len(internal_runs) != len(sensible_runs):
        raise ValueError("Internal and sensible profile counts differ")
    reference = internal_runs[0]
    for run in internal_runs:
        _validate_common(run, False)
        if run["timing"].get("wood_sensible_heat_segments"):
            raise ValueError("Internal-only profile unexpectedly has detailed timing")
    for run in sensible_runs:
        _validate_common(run, True)
        segments = run["timing"].get("wood_sensible_heat_segments", {})
        if set(segments) != set(SENSIBLE_LABELS):
            raise ValueError("Unexpected sensible-heat timing schema")
        if any(item.get("sample_count") != 1180 for item in segments.values()):
            raise ValueError("Every sensible-heat segment must contain 1,180 samples")
        parent = run["timing"]["wood_model_internal_segments"]["sensible_heat"]
        subtotal = sum(item["mean_ms"] for item in segments.values())
        if abs(subtotal - parent["mean_ms"]) > 0.003:
            raise ValueError("Sensible-heat detail does not reconcile with its parent")
    for run in internal_runs + sensible_runs:
        for path in INVARIANTS:
            if _at(run, path) != _at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")
    return reference


def _median_segments(runs: list[dict], group: str, labels: dict) -> dict:
    result = {}
    for name, label in labels.items():
        result[name] = {
            "label": label,
            "median_mean_ms": statistics.median(
                run["timing"][group][name]["mean_ms"] for run in runs
            ),
            "median_p95_ms": statistics.median(
                run["timing"][group][name]["p95_ms"] for run in runs
            ),
        }
    total = sum(item["median_mean_ms"] for item in result.values())
    for item in result.values():
        item["share_percent"] = item["median_mean_ms"] / total * 100.0
    return result


def build_report(
    internal_paths: list[Path],
    sensible_paths: list[Path],
    phase6ag_path: Path,
    phase6ah_path: Path,
) -> dict:
    internal_runs = [_load(path) for path in internal_paths]
    sensible_runs = [_load(path) for path in sensible_paths]
    reference = _validate(internal_runs, sensible_runs)
    phase6ag = _load(phase6ag_path)
    phase6ah = _load(phase6ah_path)
    if phase6ag.get("phase") != "phase6ag" or phase6ag.get("status") != "ok":
        raise ValueError("Phase 6AG baseline report is invalid")
    if phase6ah.get("phase") != "phase6ah" or phase6ah.get("status") != "ok":
        raise ValueError("Phase 6AH baseline report is invalid")

    internal = _median_segments(
        internal_runs, "wood_model_internal_segments", INTERNAL_LABELS
    )
    sensible = _median_segments(
        sensible_runs, "wood_sensible_heat_segments", SENSIBLE_LABELS
    )
    internal_total = sum(item["median_mean_ms"] for item in internal.values())
    sensible_total = sum(item["median_mean_ms"] for item in sensible.values())
    internal_order = sorted(
        internal, key=lambda name: internal[name]["median_mean_ms"], reverse=True
    )
    operation_order = sorted(
        SENSIBLE_OPERATIONS,
        key=lambda name: sensible[name]["median_mean_ms"],
        reverse=True,
    )
    broad_candidate = internal_order[0]
    primary_candidate = (
        operation_order[0] if broad_candidate == "sensible_heat" else broad_candidate
    )
    previous_internal_total = float(
        phase6ag["timing"]["current_internal_total_median_mean_ms"]
    )
    previous_heat_capacity = float(
        phase6ah["timing"]["segments"]["heat_capacity_evaluation"][
            "median_mean_ms"
        ]
    )
    current_heat_capacity = sensible["heat_capacity_evaluation"]["median_mean_ms"]
    return {
        "schema_version": 1,
        "phase": "phase6aj",
        "status": "ok",
        "run_count_per_depth": len(internal_runs),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "constant_heat_capacity_fast_path": True,
            "adopted_paths": [
                "surface boundary",
                "state clamp",
                "deferred phase",
                "compact metrics",
                "constant-model heat capacity",
            ],
            "runtime_topology": "dynamic",
            "timing_depths_kept_separate": True,
        },
        "internal_profile": {
            "median_total_ms": internal_total,
            "phase6ag_median_total_ms": previous_internal_total,
            "change_since_phase6ag_percent": (
                (internal_total - previous_internal_total)
                / previous_internal_total
                * 100.0
            ),
            "two_log_step_median_mean_ms": statistics.median(
                run["timing"]["two_log_model_step_mean_ms"]
                for run in internal_runs
            ),
            "scenario_median_seconds": statistics.median(
                run["scenario"]["simulation_wall_seconds"]
                for run in internal_runs
            ),
            "segments": internal,
            "order": internal_order,
        },
        "sensible_detail": {
            "median_total_ms": sensible_total,
            "profiled_parent_median_mean_ms": statistics.median(
                run["timing"]["wood_model_internal_segments"]["sensible_heat"][
                    "mean_ms"
                ]
                for run in sensible_runs
            ),
            "segments": sensible,
            "operation_order": operation_order,
            "heat_capacity_change_since_phase6ah_percent": (
                (current_heat_capacity - previous_heat_capacity)
                / previous_heat_capacity
                * 100.0
            ),
        },
        "selection": {
            "broad_candidate": broad_candidate,
            "primary_candidate": primary_candidate,
            "profile_is_for_candidate_selection_not_adoption": True,
            "next_audit": (
                "per-step homogeneous constant-model boundary without cross-step cache"
                if primary_candidate == "heat_capacity_evaluation"
                else f"public-state and arithmetic contract for {primary_candidate}"
            ),
            "next_gate": (
                "exact outputs plus alternating unprofiled wood-step and scenario "
                "improvement"
            ),
        },
        "equivalence": {
            "exact_authoritative_outputs_all_runs": True,
            "dry_state_sha256": reference["wood"]["dry"][
                "authoritative_state_sha256"
            ],
            "wet_state_sha256": reference["wood"]["wet"][
                "authoritative_state_sha256"
            ],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {
                "dry": reference["wood"]["dry"]["ignition_seconds"],
                "wet": reference["wood"]["wet"]["ignition_seconds"],
            },
            "flow_active_blocks_peak_observed": sorted(
                {
                    run["flow"]["active_blocks_peak"]
                    for run in internal_runs + sensible_runs
                }
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "baselines": {
            "phase6ag": _relative(phase6ag_path),
            "phase6ah": _relative(phase6ah_path),
        },
        "runs": {
            "internal": [_relative(path) for path in internal_paths],
            "sensible": [_relative(path) for path in sensible_paths],
        },
    }


def render_svg(report: dict) -> str:
    internal = report["internal_profile"]["segments"]
    internal_order = report["internal_profile"]["order"]
    sensible = report["sensible_detail"]["segments"]
    sensible_order = report["sensible_detail"]["operation_order"] + [
        "loop_and_timer_overhead"
    ]
    internal_max = internal[internal_order[0]]["median_mean_ms"]
    sensible_max = max(sensible[name]["median_mean_ms"] for name in sensible_order)
    internal_rows = []
    for index, name in enumerate(internal_order):
        item = internal[name]
        y = 212 + index * 43
        width = 260.0 * item["median_mean_ms"] / internal_max
        color = "#fb923c" if index == 0 else "#38bdf8"
        internal_rows.append(
            f'<text x="70" y="{y}" class="label">{html.escape(item["label"])}</text>'
            f'<rect x="218" y="{y - 15}" width="{width:.1f}" height="21" rx="10" fill="{color}"/>'
            f'<text x="490" y="{y}" class="value">{item["median_mean_ms"]:.3f} ms / {item["share_percent"]:.1f}%</text>'
        )
    sensible_rows = []
    for index, name in enumerate(sensible_order):
        item = sensible[name]
        y = 248 + index * 76
        width = 190.0 * item["median_mean_ms"] / sensible_max
        color = "#fbbf24" if name == report["selection"]["primary_candidate"] else "#22c55e"
        if name == "loop_and_timer_overhead":
            color = "#64748b"
        sensible_rows.append(
            f'<text x="710" y="{y}" class="label">{html.escape(item["label"])}</text>'
            f'<rect x="710" y="{y + 12}" width="{width:.1f}" height="20" rx="10" fill="{color}"/>'
            f'<text x="912" y="{y + 28}" class="value">{item["median_mean_ms"]:.3f} ms / {item["share_percent"]:.1f}%</text>'
        )
    selected_name = report["selection"]["primary_candidate"]
    selected = (
        sensible[selected_name]
        if selected_name in sensible
        else internal[selected_name]
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AJ adopted-path two-depth profile</title>
  <desc id="desc">Three internal-only runs and three detailed sensible-heat runs rank the current Python wood-step costs after Phase 6AI.</desc>
  <style>.title{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 16px 'Segoe UI',sans-serif;fill:#fbbf24;letter-spacing:2px}}.sub{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 19px 'Segoe UI',sans-serif;fill:#f8fafc}}.label{{font:650 13px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:13px 'Segoe UI',sans-serif;fill:#cbd5e1}}.small{{font:13px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 21px 'Segoe UI',sans-serif;fill:#fde68a}}</style>
  <rect width="1200" height="680" rx="30" fill="#111827"/>
  <text x="58" y="56" class="kicker">PHASE 6AJ - ADOPTED-PATH REPROFILE</text>
  <text x="58" y="104" class="title">Separate broad timing from per-cell detail</text>
  <text x="58" y="137" class="sub">3 internal-only + 3 detailed runs - constant-model fast path - exact state, CSV, and ignition</text>
  <rect x="42" y="168" width="620" height="414" rx="20" fill="#142033" stroke="#0ea5e9"/>
  <text x="70" y="194" class="heading">Wood-step internals</text>
  {''.join(internal_rows)}
  <rect x="682" y="168" width="476" height="414" rx="20" fill="#211d15" stroke="#ca8a04"/>
  <text x="710" y="204" class="heading">Sensible-heat detail</text>
  {''.join(sensible_rows)}
  <text x="58" y="620" class="decision">Next audit: {html.escape(selected['label'])} - {selected['median_mean_ms']:.3f} ms</text>
  <text x="58" y="648" class="small">Selection only. No cross-step cache; any trial still needs alternating unprofiled end-to-end improvement.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--sensible-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--phase6ag-report", type=Path, default=PHASE6AG_JSON)
    parser.add_argument("--phase6ah-report", type=Path, default=PHASE6AH_JSON)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = build_report(
        arguments.internal_summary,
        arguments.sensible_summary,
        arguments.phase6ag_report,
        arguments.phase6ah_report,
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
