"""Validate and visualize the Phase 6AS app scheduler contract trial."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "app_scheduler_contract_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
PATTERNS = ("fixed5", "fixed12", "rotating5")
WOOD_BUDGET_MS = 4.0


def build_report(raw_path: Path) -> dict:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("benchmark") != "app_wood_scheduler_contract" or raw.get("status") != "ok":
        raise ValueError("App scheduler contract benchmark is invalid")
    scenario = raw["scenario"]
    if tuple(scenario["patterns"]) != PATTERNS or scenario["total_logs"] != 20:
        raise ValueError("App scheduler benchmark has an unexpected pattern matrix")
    if scenario["frame_slots_per_logical_tick"] != 12:
        raise ValueError("App scheduler benchmark does not use twelve frame slots")
    if not all(raw["measurement_boundary"].values()):
        raise ValueError("App scheduler measurement boundary is incomplete")
    if not all(
        (
            raw["equivalence"]["exact_reference_states_all_runs"],
            raw["equivalence"]["exact_reference_outputs_all_runs"],
            raw["equivalence"]["maximum_mass_balance_error_kg"] <= 1.0e-9,
        )
    ):
        raise ValueError("App scheduler equivalence gate failed")

    grouped = {pattern: [] for pattern in PATTERNS}
    for run in raw["runs"]:
        pattern = run["pattern"]
        if pattern not in grouped:
            raise ValueError(f"Unexpected activity pattern: {pattern}")
        if not run["exact_reference_states"] or not run["exact_reference_outputs"]:
            raise ValueError(f"{pattern} failed synchronous equivalence")
        if run["maximum_output_latency_frames"] != 11:
            raise ValueError(f"{pattern} violated the eleven-frame latency contract")
        if run["maximum_consumer_tick_staleness"] > 1:
            raise ValueError(f"{pattern} exposed an over-stale consumer record")
        grouped[pattern].append(run)

    rows = []
    for pattern in PATTERNS:
        runs = grouped[pattern]
        if len(runs) < 3 or {run["order"] for run in runs} != {
            "forward",
            "reverse",
            "rotated",
        }:
            raise ValueError(f"{pattern} lacks balanced repeated runs")
        p95_ms = statistics.median(run["frame_p95_ms"] for run in runs)
        rows.append(
            {
                "pattern": pattern,
                "requested_active_count": int(
                    statistics.median(run["requested_active_count"] for run in runs)
                ),
                "median_scheduler_active_count": statistics.median(
                    run["scheduler_active_count_median"] for run in runs
                ),
                "final_scheduler_active_count": int(
                    statistics.median(
                        run["scheduler_active_count_final"] for run in runs
                    )
                ),
                "first_all_awake_model_seconds": statistics.median(
                    run["first_all_awake_model_seconds"]
                    for run in runs
                    if run["first_all_awake_model_seconds"] is not None
                )
                if any(run["first_all_awake_model_seconds"] is not None for run in runs)
                else None,
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
                "median_input_snapshot_p95_ms": statistics.median(
                    run["input_snapshot_p95_ms"] for run in runs
                ),
                "median_scheduled_update_and_output_mean_ms": statistics.median(
                    run["scheduled_update_and_output_mean_ms"] for run in runs
                ),
                "median_consumer_read_mean_ms": statistics.median(
                    run["consumer_read_mean_ms"] for run in runs
                ),
                "meets_p95_budget": p95_ms <= WOOD_BUDGET_MS,
            }
        )

    fixed5, fixed12, rotating5 = rows
    if fixed5["final_scheduler_active_count"] != 5:
        raise ValueError("Fixed-five workload did not preserve five active solvers")
    if fixed12["final_scheduler_active_count"] != 12:
        raise ValueError("Fixed-twelve workload did not preserve twelve active solvers")
    if rotating5["final_scheduler_active_count"] != 20:
        raise ValueError("Rotating-five workload did not expose cumulative wake-up")

    decision = {
        "adopt_as_production_default": False,
        "input_output_contract_succeeded": True,
        "maximum_output_latency_frames": 11,
        "maximum_output_latency_ms_at_60fps": 11 / 60.0 * 1000.0,
        "exact_dormancy_is_stable_capacity_control": False,
        "rotating_requested_active_fraction": rotating5["requested_active_count"] / 20.0,
        "rotating_final_scheduler_active_fraction": (
            rotating5["final_scheduler_active_count"] / 20.0
        ),
        "rotating_all_awake_model_seconds": rotating5[
            "first_all_awake_model_seconds"
        ],
        "fixed12_meets_p95_budget": fixed12["meets_p95_budget"],
        "rotating5_meets_p95_budget": rotating5["meets_p95_budget"],
        "next_step": (
            "choose and validate an explicit approximate sleep tolerance or move the "
            "all-awake path to native/GPU execution before production integration"
        ),
    }
    return {
        "schema_version": 1,
        "phase": "phase6as",
        "status": "ok",
        "measurement": {
            "runtime": "Kit Python",
            "scope": "headless app-equivalent wood input/output contract",
            "total_logs": 20,
            "fixed_frame_slots": 12,
            "wood_update_hz": scenario["wood_update_hz"],
            "runs_per_pattern": len(grouped[PATTERNS[0]]),
            "measured_frames_per_run": (
                scenario["cycles_per_run"] - scenario["warmup_cycles_excluded"]
            )
            * scenario["frame_slots_per_logical_tick"],
            "input_snapshot_in_first_frame": True,
            "usd_flow_render_physx_excluded": True,
        },
        "budget_ms": WOOD_BUDGET_MS,
        "pattern_rows": rows,
        "contract": raw["contract"],
        "equivalence": raw["equivalence"],
        "decision": decision,
        "raw_report": str(raw_path.resolve().relative_to(ROOT)),
    }


def render_svg(report: dict) -> str:
    labels = {
        "fixed5": "Fixed 5",
        "fixed12": "Fixed 12",
        "rotating5": "Rotating 5",
    }
    maximum_p95 = max(row["median_frame_p95_ms"] for row in report["pattern_rows"])
    p95_scale = 310.0 / max(maximum_p95 * 1.12, WOOD_BUDGET_MS * 1.2)
    budget_x = 785.0 + WOOD_BUDGET_MS * p95_scale
    rows_svg = []
    for index, row in enumerate(report["pattern_rows"]):
        y = 235 + index * 92
        requested_width = row["requested_active_count"] / 20.0 * 300.0
        scheduler_width = row["final_scheduler_active_count"] / 20.0 * 300.0
        p95_width = row["median_frame_p95_ms"] * p95_scale
        color = "#22c55e" if row["meets_p95_budget"] else "#fb7185"
        rows_svg.append(
            f'<text x="60" y="{y + 20}" class="rowtitle">{labels[row["pattern"]]}</text>'
            f'<rect x="210" y="{y}" width="300" height="22" rx="11" fill="#293548"/>'
            f'<rect x="210" y="{y}" width="{requested_width:.1f}" height="22" rx="11" fill="#38bdf8"/>'
            f'<rect x="210" y="{y + 31}" width="300" height="22" rx="11" fill="#293548"/>'
            f'<rect x="210" y="{y + 31}" width="{scheduler_width:.1f}" height="22" rx="11" fill="#f59e0b"/>'
            f'<text x="522" y="{y + 17}" class="value">request {row["requested_active_count"]}/20</text>'
            f'<text x="522" y="{y + 48}" class="value">awake {row["final_scheduler_active_count"]}/20</text>'
            f'<rect x="785" y="{y + 8}" width="{p95_width:.1f}" height="34" rx="17" fill="{color}"/>'
            f'<text x="{min(1110.0, 797.0 + p95_width):.1f}" y="{y + 30}" class="value">p95 {row["median_frame_p95_ms"]:.3f} ms</text>'
        )
    rotating = report["pattern_rows"][-1]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AS app scheduler input and output contract</title>
  <desc id="desc">Fixed and moving heat inputs compare requested activity, accumulated awake solvers, and frame latency cost.</desc>
  <style>.title{{font:750 34px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 16px 'Segoe UI',sans-serif;fill:#fda4af;letter-spacing:2px}}.sub{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.rowtitle{{font:750 18px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:650 14px 'Segoe UI',sans-serif;fill:#f8fafc}}.small{{font:13px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 20px 'Segoe UI',sans-serif;fill:#fde68a}}</style>
  <rect width="1200" height="680" rx="30" fill="#111827"/>
  <text x="58" y="56" class="kicker">PHASE 6AS - APP CONTRACT TRIAL</text>
  <text x="58" y="102" class="title">Moving heat defeats exact-equilibrium capacity</text>
  <text x="58" y="136" class="sub">20 logs · snapshot heat + oxygen · 12 publish slots · coherent emitter / visual / support revisions</text>
  <rect x="42" y="170" width="1116" height="360" rx="20" fill="#142033" stroke="#334155"/>
  <text x="210" y="205" class="small">requested heat / final awake solver count</text>
  <text x="785" y="205" class="small">full app-contract frame cost</text>
  <line x1="{budget_x:.1f}" y1="215" x2="{budget_x:.1f}" y2="500" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  {''.join(rows_svg)}
  <text x="58" y="578" class="decision">Rotating 5 wakes all 20 in {rotating["first_all_awake_model_seconds"]:.1f} model seconds</text>
  <text x="58" y="611" class="sub">Only 25% receives heat per tick, but exact sleep cannot reclaim a previously warmed log.</text>
  <text x="58" y="642" class="small">State and published outputs match the synchronous reference; maximum publish latency is 11 frames (183.3 ms at 60 fps).</text>
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
