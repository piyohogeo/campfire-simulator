"""Validate and visualize the Phase 6AR distributed-update trial."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "distributed_wood_update_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
WOOD_BUDGET_MS = 4.0


def build_report(raw_path: Path) -> dict:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("benchmark") != "distributed_5hz_wood_updates" or raw.get("status") != "ok":
        raise ValueError("Distributed-update benchmark is invalid")
    scenario = raw["scenario"]
    expected_counts = [2, 5, 10, 12, 20]
    if scenario["active_counts"] != expected_counts or scenario["total_logs"] != 20:
        raise ValueError("Distributed benchmark has an unexpected activity matrix")
    if scenario["frame_slots_per_logical_tick"] != 12 or scenario["wood_update_hz"] != 5:
        raise ValueError("Distributed benchmark does not represent 5 Hz at 60 fps")
    if not all(raw["measurement_boundary"].values()):
        raise ValueError("Distributed measurement boundary is incomplete")
    if not all(raw["gate_contract"].values()):
        raise ValueError("Dormant gate audit failed")
    if (
        not raw["equivalence"]["exact_reference_states_all_runs"]
        or raw["equivalence"]["maximum_mass_balance_error_kg"] > 1.0e-9
    ):
        raise ValueError("Distributed exact-state gate failed")

    grouped = {count: [] for count in expected_counts}
    for run in raw["runs"]:
        grouped[run["active_log_count"]].append(run)
    rows = []
    for count in expected_counts:
        runs = grouped[count]
        if len(runs) < 3 or {run["order"] for run in runs} != {"ascending", "descending"}:
            raise ValueError(f"Activity {count} lacks balanced repeated runs")
        mean_ms = statistics.median(run["frame_mean_ms"] for run in runs)
        p95_ms = statistics.median(run["frame_p95_ms"] for run in runs)
        over_fraction = statistics.median(
            run["frames_over_4ms_fraction"] for run in runs
        )
        rows.append(
            {
                "active_log_count": count,
                "sleeping_log_count": 20 - count,
                "active_fraction": count / 20.0,
                "median_frame_mean_ms": mean_ms,
                "median_frame_p95_ms": p95_ms,
                "median_frame_max_ms": statistics.median(
                    run["frame_max_ms"] for run in runs
                ),
                "median_cycle_mean_ms": statistics.median(
                    run["cycle_mean_ms"] for run in runs
                ),
                "median_frames_over_4ms_fraction": over_fraction,
                "meets_mean_budget": mean_ms <= WOOD_BUDGET_MS,
                "meets_p95_budget": p95_ms <= WOOD_BUDGET_MS,
            }
        )

    passing = [row for row in rows if row["meets_p95_budget"]]
    maximum_active = max(
        (row["active_log_count"] for row in passing), default=0
    )
    fully_active = rows[-1]
    decision = {
        "adopt_as_production_default": False,
        "exact_fixed_input_trial_succeeded": True,
        "maximum_active_logs_meeting_p95_budget": maximum_active,
        "maximum_active_fraction_meeting_p95_budget": maximum_active / 20.0,
        "fully_active_meets_mean_budget": fully_active["meets_mean_budget"],
        "fully_active_meets_p95_budget": fully_active["meets_p95_budget"],
        "next_step": (
            "validate snapshotted time-varying app inputs, output-latency semantics, "
            "and real activity ratios before production integration"
        ),
        "native_or_gpu_required_if_all_20_must_remain_active": (
            not fully_active["meets_p95_budget"]
        ),
    }
    return {
        "schema_version": 1,
        "phase": "phase6ar",
        "status": "ok",
        "measurement": {
            "runtime": "Kit Python",
            "scope": "isolated authoritative CPU wood scheduler",
            "total_logs": 20,
            "fixed_frame_slots": 12,
            "wood_update_hz": 5,
            "runs_per_activity": len(grouped[expected_counts[0]]),
            "measured_frames_per_run": (
                scenario["cycles_per_run"] - scenario["warmup_cycles_excluded"]
            )
            * scenario["frame_slots_per_logical_tick"],
            "input_snapshot_before_timed_frames": True,
        },
        "budget_ms": WOOD_BUDGET_MS,
        "activity_rows": rows,
        "dormant_gate_contract": raw["gate_contract"],
        "equivalence": raw["equivalence"],
        "decision": decision,
        "raw_report": str(raw_path.resolve().relative_to(ROOT)),
    }


def render_svg(report: dict) -> str:
    rows = report["activity_rows"]
    maximum = max(row["median_frame_p95_ms"] for row in rows) * 1.12
    scale = 660.0 / maximum
    budget_x = 370.0 + report["budget_ms"] * scale
    bars = []
    for index, row in enumerate(rows):
        y = 205 + index * 68
        mean_width = row["median_frame_mean_ms"] * scale
        p95_width = row["median_frame_p95_ms"] * scale
        color = "#22c55e" if row["meets_p95_budget"] else "#fb7185"
        bars.append(
            f'<text x="70" y="{y + 19}" class="count">{row["active_log_count"]} active</text>'
            f'<text x="184" y="{y + 19}" class="sleep">{row["sleeping_log_count"]} sleeping</text>'
            f'<rect x="370" y="{y}" width="{p95_width:.1f}" height="28" rx="14" fill="#334155"/>'
            f'<rect x="370" y="{y + 5}" width="{mean_width:.1f}" height="18" rx="9" fill="{color}"/>'
            f'<text x="{min(1060.0, 382.0 + p95_width):.1f}" y="{y + 19}" class="value">mean {row["median_frame_mean_ms"]:.3f} · p95 {row["median_frame_p95_ms"]:.3f} ms</text>'
        )
    maximum_active = report["decision"]["maximum_active_logs_meeting_p95_budget"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AR distributed five-hertz wood-update trial</title>
  <desc id="desc">Twenty logs are assigned to twelve deterministic frame slots while exact dormant logs skip full solver work.</desc>
  <style>.title{{font:750 34px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 16px 'Segoe UI',sans-serif;fill:#fda4af;letter-spacing:2px}}.sub{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.count{{font:750 18px 'Segoe UI',sans-serif;fill:#f8fafc}}.sleep{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.value{{font:650 14px 'Segoe UI',sans-serif;fill:#f8fafc}}.small{{font:13px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 20px 'Segoe UI',sans-serif;fill:#fde68a}}</style>
  <rect width="1200" height="680" rx="30" fill="#111827"/>
  <text x="58" y="56" class="kicker">PHASE 6AR - DISTRIBUTED 5 HZ TRIAL</text>
  <text x="58" y="102" class="title">Spread fixed steps; sleep only exact equilibrium</text>
  <text x="58" y="136" class="sub">20 logs · 12 deterministic frame slots · 3 balanced runs/activity · exact snapshotted inputs</text>
  <rect x="42" y="164" width="1116" height="390" rx="20" fill="#142033" stroke="#334155"/>
  <line x1="{budget_x:.1f}" y1="184" x2="{budget_x:.1f}" y2="525" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 7"/>
  <text x="{min(1010.0, budget_x + 10):.1f}" y="181" class="value">4 ms p95 budget</text>
  {''.join(bars)}
  <text x="58" y="598" class="decision">Measured p95 capacity: {maximum_active} active + {20 - maximum_active} exact-sleeping logs</text>
  <text x="58" y="630" class="sub">Every final state matches the synchronous reference; production adoption remains blocked on app input/output latency.</text>
  <text x="58" y="657" class="small">Colored bar = mean; dark bar = p95. Full 20-log activity still requires native/GPU work or a finer scheduling boundary.</text>
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
