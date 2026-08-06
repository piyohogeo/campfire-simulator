"""Validate and visualize the Phase 6AT approximate-sleep trial."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "approximate_sleep_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
APP_CONTRACT_REPORT = ASSETS / "app_scheduler_contract_report.json"
DISTRIBUTED_REPORT = ASSETS / "distributed_wood_update_report.json"
CANDIDATES = ("strict", "balanced", "aggressive")


def _load_prior_context() -> dict:
    app_report = json.loads(APP_CONTRACT_REPORT.read_text(encoding="utf-8"))
    distributed = json.loads(DISTRIBUTED_REPORT.read_text(encoding="utf-8"))
    rotating = next(
        row for row in app_report["pattern_rows"] if row["pattern"] == "rotating5"
    )
    fully_active = next(
        row for row in distributed["activity_rows"] if row["active_log_count"] == 20
    )
    return {
        "phase6as_rotating5_p95_ms": rotating["median_frame_p95_ms"],
        "phase6ar_burning20_p95_ms": fully_active["median_frame_p95_ms"],
    }


def build_report(raw_path: Path) -> dict:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("benchmark") != "approximate_whole_log_sleep" or raw.get("status") != "ok":
        raise ValueError("Approximate-sleep benchmark is invalid")
    if not all(raw["measurement_boundary"].values()):
        raise ValueError("Approximate-sleep measurement boundary is incomplete")
    if tuple(candidate["name"] for candidate in raw["candidates"]) != CANDIDATES:
        raise ValueError("Approximate-sleep candidate matrix changed")
    budgets = raw["error_budgets"]
    accuracy_by_name = {row["candidate"]: row for row in raw["accuracy"]}
    grouped = {name: [] for name in CANDIDATES}
    for run in raw["performance_runs"]:
        grouped[run["candidate"]].append(run)

    rows = []
    for name in CANDIDATES:
        accuracy = accuracy_by_name[name]
        if set(accuracy["error_gates"]) != {
            key for key in budgets if key != "maximum_frame_p95_ms"
        }:
            raise ValueError(f"{name} accuracy gates do not match the budget")
        if accuracy["all_accuracy_budgets_passed"] != all(
            accuracy["error_gates"].values()
        ):
            raise ValueError(f"{name} accuracy summary is inconsistent")
        runs = grouped[name]
        if len(runs) < 3 or {run["order"] for run in runs} != {
            "forward",
            "reverse",
            "rotated",
        }:
            raise ValueError(f"{name} lacks balanced repeated performance runs")
        p95_ms = statistics.median(run["frame_p95_ms"] for run in runs)
        rows.append(
            {
                "candidate": name,
                "parameters": accuracy["candidate_parameters"],
                "maximum_cell_temperature_error_k": accuracy["errors"][
                    "maximum_cell_temperature_error_k"
                ],
                "maximum_surface_temperature_error_k": accuracy["errors"][
                    "maximum_surface_temperature_error_k"
                ],
                "maximum_total_mass_error_kg": accuracy["errors"][
                    "maximum_total_mass_error_kg"
                ],
                "maximum_flow_component_error": accuracy["errors"][
                    "maximum_flow_component_error"
                ],
                "maximum_support_ratio_error": accuracy["errors"][
                    "maximum_support_ratio_error"
                ],
                "maximum_ignition_time_error_s": accuracy["errors"][
                    "maximum_ignition_time_error_s"
                ],
                "all_accuracy_budgets_passed": accuracy[
                    "all_accuracy_budgets_passed"
                ],
                "median_frame_mean_ms": statistics.median(
                    run["frame_mean_ms"] for run in runs
                ),
                "median_frame_p95_ms": p95_ms,
                "median_frame_max_ms": statistics.median(
                    run["frame_max_ms"] for run in runs
                ),
                "median_frames_over_4ms_fraction": statistics.median(
                    run["frames_over_4ms_fraction"] for run in runs
                ),
                "median_approximate_sleep_fraction": statistics.median(
                    run["approximate_sleep_fraction"] for run in runs
                ),
                "median_full_step_fraction": statistics.median(
                    run["full_step_fraction"] for run in runs
                ),
                "median_full_steps_per_tick": statistics.median(
                    run["median_full_steps_per_tick"] for run in runs
                ),
                "final_full_steps_per_tick": int(
                    statistics.median(run["final_full_steps_per_tick"] for run in runs)
                ),
                "meets_frame_p95_budget": p95_ms
                <= budgets["maximum_frame_p95_ms"],
            }
        )

    passing_accuracy = [
        row["candidate"] for row in rows if row["all_accuracy_budgets_passed"]
    ]
    passing_both = [
        row["candidate"]
        for row in rows
        if row["all_accuracy_budgets_passed"] and row["meets_frame_p95_budget"]
    ]
    prior = _load_prior_context()
    return {
        "schema_version": 1,
        "phase": "phase6at",
        "status": "ok",
        "measurement": {
            "runtime": "Kit Python",
            "scope": "isolated whole-log approximate sleep rejection trial",
            "performance_logs": raw["scenario"]["total_logs_performance"],
            "fixed_frame_slots": raw["scenario"]["frame_slots"],
            "performance_pattern": raw["scenario"]["performance_pattern"],
            "runs_per_candidate": len(grouped[CANDIDATES[0]]),
            "measured_frames_per_run": (
                raw["scenario"]["performance_cycles"]
                - raw["scenario"]["warmup_cycles_excluded"]
            )
            * raw["scenario"]["frame_slots"],
            "production_code_unchanged": True,
        },
        "error_budgets": budgets,
        "candidate_rows": rows,
        "prior_context": prior,
        "decision": {
            "adopt_as_production_default": False,
            "accuracy_passing_candidates": passing_accuracy,
            "accuracy_and_performance_passing_candidates": passing_both,
            "approximate_sleep_rejected_for_capacity": not passing_both,
            "native_or_gpu_path_is_next": not passing_both,
            "reason": (
                "no whole-log tolerance candidate both preserves the declared "
                "error budget and restores the four-millisecond p95 under moving heat"
            ),
            "next_step": (
                "prototype a native contiguous-state wood kernel without changing "
                "the authoritative schema or SI equations"
            ),
        },
        "raw_report": str(raw_path.resolve().relative_to(ROOT)),
    }


def render_svg(report: dict) -> str:
    rows = report["candidate_rows"]
    temp_budget = report["error_budgets"]["maximum_cell_temperature_error_k"]
    frame_budget = report["error_budgets"]["maximum_frame_p95_ms"]
    max_temp = max(temp_budget * 1.2, max(row["maximum_cell_temperature_error_k"] for row in rows) * 1.1)
    max_p95 = max(frame_budget * 1.2, max(row["median_frame_p95_ms"] for row in rows) * 1.1)
    temp_scale = 300.0 / max_temp
    p95_scale = 300.0 / max_p95
    temp_budget_x = 220.0 + temp_budget * temp_scale
    p95_budget_x = 760.0 + frame_budget * p95_scale
    labels = {"strict": "Strict", "balanced": "Balanced", "aggressive": "Aggressive"}
    rows_svg = []
    for index, row in enumerate(rows):
        y = 225 + index * 92
        temp_width = row["maximum_cell_temperature_error_k"] * temp_scale
        p95_width = row["median_frame_p95_ms"] * p95_scale
        temp_color = "#22c55e" if row["all_accuracy_budgets_passed"] else "#fb7185"
        p95_color = "#22c55e" if row["meets_frame_p95_budget"] else "#fb7185"
        rows_svg.append(
            f'<text x="58" y="{y + 23}" class="rowtitle">{labels[row["candidate"]]}</text>'
            f'<rect x="220" y="{y}" width="{temp_width:.1f}" height="32" rx="16" fill="{temp_color}"/>'
            f'<text x="{min(535.0, 232.0 + temp_width):.1f}" y="{y + 22}" class="value">ΔT {row["maximum_cell_temperature_error_k"]:.3f} K</text>'
            f'<rect x="760" y="{y}" width="{p95_width:.1f}" height="32" rx="16" fill="{p95_color}"/>'
            f'<text x="{min(1090.0, 772.0 + p95_width):.1f}" y="{y + 22}" class="value">p95 {row["median_frame_p95_ms"]:.3f} ms</text>'
            f'<text x="220" y="{y + 58}" class="small">approx sleep {row["median_approximate_sleep_fraction"] * 100:.2f}% · final full steps {row["final_full_steps_per_tick"]}/20</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AT bounded approximate whole-log sleep trial</title>
  <desc id="desc">Three tolerance candidates compare physical error and moving-heat frame cost against declared budgets.</desc>
  <style>.title{{font:750 34px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 16px 'Segoe UI',sans-serif;fill:#fda4af;letter-spacing:2px}}.sub{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.rowtitle{{font:750 18px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:650 14px 'Segoe UI',sans-serif;fill:#f8fafc}}.small{{font:13px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 20px 'Segoe UI',sans-serif;fill:#fde68a}}</style>
  <rect width="1200" height="680" rx="30" fill="#111827"/>
  <text x="58" y="56" class="kicker">PHASE 6AT - APPROXIMATE SLEEP GATE</text>
  <text x="58" y="102" class="title">Bound the error first; reject if capacity stays short</text>
  <text x="58" y="136" class="sub">whole-log only · 0.25 / 1 / 5 K candidates · 1 / 2 / 5 s max sleep · moving five-log heat</text>
  <rect x="42" y="168" width="1116" height="360" rx="20" fill="#142033" stroke="#334155"/>
  <text x="220" y="198" class="small">maximum cell-temperature error</text>
  <text x="760" y="198" class="small">full app-contract frame p95</text>
  <line x1="{temp_budget_x:.1f}" y1="210" x2="{temp_budget_x:.1f}" y2="495" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <line x1="{p95_budget_x:.1f}" y1="210" x2="{p95_budget_x:.1f}" y2="495" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  {''.join(rows_svg)}
  <text x="58" y="575" class="decision">No candidate may ship unless both error and 4 ms p95 gates pass</text>
  <text x="58" y="608" class="sub">Moving heat is the capacity case; burning 20-log context remains {report["prior_context"]["phase6ar_burning20_p95_ms"]:.3f} ms p95.</text>
  <text x="58" y="640" class="small">Production state, SI equations, USD, Flow, rendering, and PhysX are unchanged by this isolated trial.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.raw)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
