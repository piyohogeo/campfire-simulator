"""Validate and visualize the Phase 6AQ multi-log scaling benchmark."""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "wood_scaling_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
WOOD_BUDGET_MS = 4.0
FRAME_BUDGET_MS = 1000.0 / 30.0


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _linear_fit(points: list[tuple[float, float]]) -> dict:
    x_mean = statistics.fmean(x for x, _ in points)
    y_mean = statistics.fmean(y for _, y in points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator
    intercept = y_mean - slope * x_mean
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    total = sum((y - y_mean) ** 2 for _, y in points)
    r_squared = 1.0 if total == 0.0 else 1.0 - residual / total
    return {
        "intercept_ms": intercept,
        "slope_ms_per_log": slope,
        "r_squared": r_squared,
    }


def build_report(raw_path: Path) -> dict:
    raw = _load(raw_path)
    if raw.get("benchmark") != "adopted_python_wood_scaling" or raw.get("status") != "ok":
        raise ValueError("Scaling benchmark is invalid")
    scenario = raw["scenario"]
    counts = scenario["counts"]
    if counts != [2, 5, 10, 20] or scenario["runs_per_count"] < 3:
        raise ValueError("Scaling benchmark must contain 2/5/10/20 logs and 3 runs")
    if not raw["runtime"].get("kit_python"):
        raise ValueError("Scaling benchmark did not use Kit Python")
    if not all(raw["measurement_boundary"].values()):
        raise ValueError("Scaling measurement boundary is incomplete")
    if not all(raw["adopted_settings"].values()):
        raise ValueError("Scaling benchmark did not use every adopted setting")
    equivalence = raw["equivalence"]
    if (
        not equivalence["exact_per_log_state_across_scales_and_runs"]
        or not equivalence["all_cells_slotted"]
        or equivalence["maximum_mass_balance_error_kg"] > 1.0e-9
    ):
        raise ValueError("Scaling equivalence gate failed")

    grouped = {count: [] for count in counts}
    for run in raw["runs"]:
        grouped[run["log_count"]].append(run)
    rows = []
    for count in counts:
        runs = grouped[count]
        if len(runs) != scenario["runs_per_count"]:
            raise ValueError(f"Unexpected run count for {count} logs")
        if {run["order"] for run in runs} != {"ascending", "descending"}:
            raise ValueError(f"Scale {count} did not use alternating order")
        mean_ms = statistics.median(run["aggregate_step_mean_ms"] for run in runs)
        p95_ms = statistics.median(run["aggregate_step_p95_ms"] for run in runs)
        rows.append(
            {
                "log_count": count,
                "combined_cell_count": count * scenario["cell_count_per_log"],
                "median_step_mean_ms": mean_ms,
                "median_step_p95_ms": p95_ms,
                "median_ms_per_log": statistics.median(
                    run["mean_ms_per_log"] for run in runs
                ),
                "median_ms_per_1000_cells": statistics.median(
                    run["mean_ms_per_1000_cells"] for run in runs
                ),
                "wood_budget_ratio": mean_ms / WOOD_BUDGET_MS,
                "meets_wood_budget": mean_ms <= WOOD_BUDGET_MS,
            }
        )

    fit = _linear_fit(
        [(row["log_count"], row["median_step_mean_ms"]) for row in rows]
    )
    twenty = next(row for row in rows if row["log_count"] == 20)
    reduction = max(
        0.0,
        (twenty["median_step_mean_ms"] - WOOD_BUDGET_MS)
        / twenty["median_step_mean_ms"]
        * 100.0,
    )
    speedup = twenty["median_step_mean_ms"] / WOOD_BUDGET_MS
    spread_frames = max(1, math.ceil(speedup))
    predicted_logs_at_budget = max(
        0.0, (WOOD_BUDGET_MS - fit["intercept_ms"]) / fit["slope_ms_per_log"]
    )
    five_hz_average_ms = twenty["median_step_mean_ms"] / 12.0
    ten_hz_average_ms = twenty["median_step_mean_ms"] / 6.0
    five_hz_reduction = max(
        0.0, (five_hz_average_ms - WOOD_BUDGET_MS) / five_hz_average_ms * 100.0
    )
    ten_hz_reduction = max(
        0.0, (ten_hz_average_ms - WOOD_BUDGET_MS) / ten_hz_average_ms * 100.0
    )
    if twenty["meets_wood_budget"]:
        next_step = "simultaneous_updates_fit; validate inside the full application"
    elif five_hz_reduction <= 12.5:
        next_step = (
            "prototype distributed 5 Hz log updates plus inactive-log and "
            "sleeping-cell gates; retain native/GPU work as a measured contingency"
        )
    else:
        next_step = (
            "distributed scheduling alone is insufficient; prototype native or "
            "resident GPU wood updates"
        )
    return {
        "schema_version": 1,
        "phase": "phase6aq",
        "status": "ok",
        "measurement": {
            "runtime": "Kit Python",
            "scope": "authoritative CPU wood step only",
            "flow_usd_render_metrics_excluded": True,
            "active_combustion_window_model_seconds": [
                scenario["precondition_model_seconds"],
                scenario["precondition_model_seconds"]
                + scenario["measured_model_seconds"],
            ],
            "runs_per_count": scenario["runs_per_count"],
            "samples_per_run": scenario["steps_per_run"]
            - scenario["warmup_steps_excluded"],
            "cell_count_per_log": scenario["cell_count_per_log"],
            "order_balanced": True,
        },
        "budgets": {
            "wood_update_ms": WOOD_BUDGET_MS,
            "frame_at_30_fps_ms": FRAME_BUDGET_MS,
        },
        "scales": rows,
        "linear_fit": fit,
        "mvp_20_log_gap": {
            "median_step_mean_ms": twenty["median_step_mean_ms"],
            "median_step_p95_ms": twenty["median_step_p95_ms"],
            "required_reduction_percent": reduction,
            "required_speedup": speedup,
            "predicted_logs_at_4ms": predicted_logs_at_budget,
            "minimum_spread_frames_from_mean": spread_frames,
            "distributed_frequency_at_60fps_hz": 60.0 / spread_frames,
            "average_ms_if_distributed_at_10hz": ten_hz_average_ms,
            "average_ms_if_distributed_at_5hz": five_hz_average_ms,
            "required_reduction_at_10hz_percent": ten_hz_reduction,
            "required_reduction_at_5hz_percent": five_hz_reduction,
        },
        "equivalence": raw["equivalence"],
        "decision": {
            "twenty_simultaneous_meets_4ms": twenty["meets_wood_budget"],
            "scaling_is_linear_enough_for_planning": fit["r_squared"] >= 0.98,
            "next_step": next_step,
            "native_or_gpu_decision_deferred_until_activity_gating_is_measured": True,
            "scheduling_values_are_capacity_estimates_not_physics_validation": True,
        },
        "raw_report": str(raw_path.resolve().relative_to(ROOT)),
    }


def render_svg(report: dict) -> str:
    rows = report["scales"]
    maximum = max(report["budgets"]["wood_update_ms"], rows[-1]["median_step_mean_ms"])
    scale = 700.0 / (maximum * 1.08)
    budget_x = 350.0 + report["budgets"]["wood_update_ms"] * scale
    bars = []
    for index, row in enumerate(rows):
        y = 230 + index * 82
        width = row["median_step_mean_ms"] * scale
        color = "#22c55e" if row["meets_wood_budget"] else "#fb7185"
        bars.append(
            f'<text x="78" y="{y + 22}" class="count">{row["log_count"]} logs</text>'
            f'<text x="186" y="{y + 22}" class="cells">{row["combined_cell_count"]:,} cells</text>'
            f'<rect x="350" y="{y}" width="{width:.1f}" height="31" rx="15" fill="{color}"/>'
            f'<text x="{min(1080.0, 362.0 + width):.1f}" y="{y + 22}" class="value">{row["median_step_mean_ms"]:.3f} ms</text>'
        )
    gap = report["mvp_20_log_gap"]
    fit = report["linear_fit"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AQ adopted wood-model scaling</title>
  <desc id="desc">Three balanced Kit Python runs measure simultaneous authoritative CPU wood updates for 2, 5, 10, and 20 logs.</desc>
  <style>.title{{font:750 34px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 16px 'Segoe UI',sans-serif;fill:#fda4af;letter-spacing:2px}}.sub{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.count{{font:750 20px 'Segoe UI',sans-serif;fill:#f8fafc}}.cells{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.value{{font:700 15px 'Segoe UI',sans-serif;fill:#f8fafc}}.small{{font:13px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 20px 'Segoe UI',sans-serif;fill:#fde68a}}</style>
  <rect width="1200" height="680" rx="30" fill="#111827"/>
  <text x="58" y="56" class="kicker">PHASE 6AQ - MULTI-LOG CPU SCALING</text>
  <text x="58" y="102" class="title">Measure the MVP gap before choosing an architecture</text>
  <text x="58" y="136" class="sub">Kit Python · active combustion at 180–220 model s · 3 balanced runs · 1,152 cells/log</text>
  <rect x="42" y="166" width="1116" height="390" rx="20" fill="#142033" stroke="#334155"/>
  <line x1="{budget_x:.1f}" y1="198" x2="{budget_x:.1f}" y2="535" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1010.0, budget_x + 10):.1f}" y="194" class="value" fill="#fde68a">4 ms wood budget</text>
  {''.join(bars)}
  <text x="58" y="603" class="decision">20 logs: {gap["median_step_mean_ms"]:.3f} ms · {gap["required_speedup"]:.2f}× speedup required</text>
  <text x="58" y="633" class="sub">Linear fit: {fit["slope_ms_per_log"]:.3f} ms/log · R² {fit["r_squared"]:.4f} · 5 Hz distributed estimate {gap["average_ms_if_distributed_at_5hz"]:.3f} ms/frame</text>
  <text x="58" y="658" class="small">Flow, USD, rendering, metrics, and internal timers excluded. Scheduling estimates still require numerical stability validation.</text>
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
