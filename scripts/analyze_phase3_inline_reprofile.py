"""Re-profile the adopted inline homogeneous sensible-heat path."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path

import analyze_phase3_adopted_reprofile as phase6aj


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "phase3_inline_reprofile_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
PHASE6AL_JSON = ASSETS / "phase3_phase6ak_reprofile_report.json"
PHASE6AM_JSON = ASSETS / "phase3_inline_heat_capacity_report.json"


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def _validate_profiles(
    internal_runs: list[dict], sensible_runs: list[dict]
) -> dict:
    reference = phase6aj._validate(internal_runs, sensible_runs)
    for run in internal_runs + sensible_runs:
        scenario = run.get("scenario", {})
        if scenario.get("python_homogeneous_heat_capacity_fast_path") is not True:
            raise ValueError("Every profile must use the homogeneous path")
        if (
            scenario.get(
                "python_inline_homogeneous_sensible_heat_capacity_fast_path"
            )
            is not True
        ):
            raise ValueError("Every profile must use the inline sensible path")
    return reference


def build_report(
    internal_paths: list[Path],
    sensible_paths: list[Path],
    phase6al_path: Path,
    phase6am_path: Path,
) -> dict:
    internal_runs = [phase6aj._load(path) for path in internal_paths]
    sensible_runs = [phase6aj._load(path) for path in sensible_paths]
    reference = _validate_profiles(internal_runs, sensible_runs)
    previous = phase6aj._load(phase6al_path)
    adopted = phase6aj._load(phase6am_path)
    if previous.get("phase") != "phase6al" or previous.get("status") != "ok":
        raise ValueError("Phase 6AL profile baseline is invalid")
    if adopted.get("phase") != "phase6am" or adopted.get("status") != "ok":
        raise ValueError("Phase 6AM adoption report is invalid")
    if adopted.get("decision", {}).get("adopt_inline_path") is not True:
        raise ValueError("Phase 6AM report did not adopt the inline path")

    internal = phase6aj._median_segments(
        internal_runs,
        "wood_model_internal_segments",
        phase6aj.INTERNAL_LABELS,
    )
    sensible = phase6aj._median_segments(
        sensible_runs,
        "wood_sensible_heat_segments",
        phase6aj.SENSIBLE_LABELS,
    )
    internal_total = sum(item["median_mean_ms"] for item in internal.values())
    sensible_total = sum(item["median_mean_ms"] for item in sensible.values())
    internal_order = sorted(
        internal, key=lambda name: internal[name]["median_mean_ms"], reverse=True
    )
    operation_order = sorted(
        phase6aj.SENSIBLE_OPERATIONS,
        key=lambda name: sensible[name]["median_mean_ms"],
        reverse=True,
    )
    broad_candidate = internal_order[0]
    primary_candidate = (
        operation_order[0] if broad_candidate == "sensible_heat" else broad_candidate
    )
    previous_internal = float(previous["internal_profile"]["median_total_ms"])
    previous_sensible = float(
        previous["internal_profile"]["segments"]["sensible_heat"]["median_mean_ms"]
    )
    previous_capacity = float(
        previous["sensible_detail"]["segments"]["heat_capacity_evaluation"][
            "median_mean_ms"
        ]
    )
    next_audit = {
        "heat_capacity_evaluation": "remaining per-cell mass reads and arithmetic",
        "surface_boundary_update": "surface boundary arithmetic and attribute reads",
        "interior_conduction_update": "interior conduction-only update loop",
        "conduction": "conduction pair traversal and temporary allocations",
        "pyrolysis": "pyrolysis reaction loop and product accounting",
        "evaporation": "evaporation reaction loop",
        "state_finalize": "state finalization clamps",
        "char_oxidation": "char oxidation reaction loop",
    }.get(primary_candidate, f"public-state contract for {primary_candidate}")

    return {
        "schema_version": 1,
        "phase": "phase6an",
        "status": "ok",
        "run_count_per_depth": len(internal_runs),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "constant_heat_capacity_fast_path": True,
            "homogeneous_heat_capacity_fast_path": True,
            "inline_homogeneous_sensible_heat_capacity_fast_path": True,
            "runtime_topology": "dynamic",
            "timing_depths_kept_separate": True,
        },
        "internal_profile": {
            "median_total_ms": internal_total,
            "phase6al_median_total_ms": previous_internal,
            "change_since_phase6al_percent": (
                (internal_total - previous_internal) / previous_internal * 100.0
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
            "sensible_change_since_phase6al_percent": (
                (internal["sensible_heat"]["median_mean_ms"] - previous_sensible)
                / previous_sensible
                * 100.0
            ),
            "heat_capacity_change_since_phase6al_percent": (
                (
                    sensible["heat_capacity_evaluation"]["median_mean_ms"]
                    - previous_capacity
                )
                / previous_capacity
                * 100.0
            ),
        },
        "selection": {
            "broad_candidate": broad_candidate,
            "primary_candidate": primary_candidate,
            "profile_is_for_candidate_selection_not_adoption": True,
            "next_audit": next_audit,
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
            "phase6al": _relative(phase6al_path),
            "phase6am": _relative(phase6am_path),
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
        color = "#fb7185" if index == 0 else "#38bdf8"
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
        color = (
            "#fbbf24"
            if name == report["selection"]["primary_candidate"]
            else "#22c55e"
        )
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
  <title id="title">Phase 6AN adopted inline-path reprofile</title>
  <desc id="desc">Three broad profiles and three detailed sensible-heat profiles rank costs after adopting inline homogeneous sensible heat capacity.</desc>
  <style>.title{{font:750 36px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 16px 'Segoe UI',sans-serif;fill:#fda4af;letter-spacing:2px}}.sub{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 19px 'Segoe UI',sans-serif;fill:#f8fafc}}.label{{font:650 13px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:13px 'Segoe UI',sans-serif;fill:#cbd5e1}}.small{{font:13px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 21px 'Segoe UI',sans-serif;fill:#fde68a}}</style>
  <rect width="1200" height="680" rx="30" fill="#111827"/>
  <text x="58" y="56" class="kicker">PHASE 6AN - ADOPTED INLINE PATH REPROFILE</text>
  <text x="58" y="104" class="title">Re-rank costs after removing the closure</text>
  <text x="58" y="137" class="sub">3 broad + 3 detailed runs - inline path active - exact state, CSV, and ignition</text>
  <rect x="42" y="168" width="620" height="414" rx="20" fill="#142033" stroke="#0ea5e9"/>
  <text x="70" y="194" class="heading">Wood-step internals</text>
  {''.join(internal_rows)}
  <rect x="682" y="168" width="476" height="414" rx="20" fill="#211d15" stroke="#ca8a04"/>
  <text x="710" y="204" class="heading">Sensible-heat detail</text>
  {''.join(sensible_rows)}
  <text x="58" y="620" class="decision">Next audit: {html.escape(selected["label"])} - {selected["median_mean_ms"]:.3f} ms</text>
  <text x="58" y="648" class="small">Selection only. Any trial still needs alternating unprofiled end-to-end improvement and exact outputs.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--sensible-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--phase6al-report", type=Path, default=PHASE6AL_JSON)
    parser.add_argument("--phase6am-report", type=Path, default=PHASE6AM_JSON)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = build_report(
        arguments.internal_summary,
        arguments.sensible_summary,
        arguments.phase6al_report,
        arguments.phase6am_report,
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
