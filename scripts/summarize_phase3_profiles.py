"""Aggregate repeated Phase 3 profiles into tracked JSON and SVG evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


CONFIGURATION_FIELDS = (
    "model_dt_seconds",
    "flow_update_interval_steps",
    "flow_update_interval_seconds",
    "steps",
    "model_duration_seconds",
    "external_heat_flux_w_m2",
)
DISPLAYED_SEGMENTS = (
    ("wood_model_step", "Wood model", "#e57638"),
    ("wood_metrics", "Metrics", "#d7b982"),
    ("wood_visual_usd", "Wood visual USD", "#8d7bd1"),
    ("kit_flow_render_update", "Kit / Flow / render", "#58b889"),
    ("viewport_capture", "Viewport capture", "#5b8ec9"),
)


def _load(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("status") != "ok" or result.get("phase") != "phase3":
        raise ValueError(f"Not a successful Phase 3 summary: {path}")
    if not result.get("timing", {}).get("segments"):
        raise ValueError(f"Phase 3 summary has no detailed timing segments: {path}")
    return result


def _range(values: list[float]) -> dict[str, float]:
    return {
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def summarize(paths: list[Path]) -> dict:
    if len(paths) < 2:
        raise ValueError("At least two Phase 3 profiles are required")
    runs = [_load(path) for path in paths]
    reference = runs[0]
    configuration = {
        field: reference["scenario"][field] for field in CONFIGURATION_FIELDS
    }
    segment_names = tuple(reference["timing"]["segments"])
    for path, run in zip(paths[1:], runs[1:]):
        candidate = {field: run["scenario"][field] for field in CONFIGURATION_FIELDS}
        if candidate != configuration:
            raise ValueError(f"Phase 3 configurations differ: {path}")
        if tuple(run["timing"]["segments"]) != segment_names:
            raise ValueError(f"Phase 3 timing schemas differ: {path}")
        for name in segment_names:
            if (
                run["timing"]["segments"][name]["sample_count"]
                != reference["timing"]["segments"][name]["sample_count"]
            ):
                raise ValueError(f"Phase 3 timing sample counts differ: {name}")

    ignition_pairs = [
        (run["wood"]["dry"]["ignition_seconds"], run["wood"]["wet"]["ignition_seconds"])
        for run in runs
    ]
    if any(pair != ignition_pairs[0] for pair in ignition_pairs[1:]):
        raise ValueError("Phase 3 ignition behavior changed between profiles")
    mass_error_limit_kg = 1.0e-6
    if any(
        abs(run["wood"][kind]["mass_balance_error_kg"]) > mass_error_limit_kg
        for run in runs
        for kind in ("dry", "wet")
    ):
        raise ValueError("Phase 3 profile violated mass balance")
    if any(run["flow"]["active_blocks_peak"] <= 0 for run in runs):
        raise ValueError("Phase 3 profile did not activate Flow")

    aggregates = {
        "runner_wall_seconds": _range([run["runner_wall_seconds"] for run in runs]),
        "capture_resolution_wait_seconds": _range(
            [run["startup"]["capture_resolution_wait_seconds"] for run in runs]
        ),
        "scenario_wall_seconds": _range(
            [run["scenario"]["simulation_wall_seconds"] for run in runs]
        ),
        "finalization_seconds": _range(
            [run["timing"]["finalization"]["total_seconds"] for run in runs]
        ),
        "segments": {
            name: {
                "total_seconds": _range(
                    [run["timing"]["segments"][name]["total_ms"] / 1000.0 for run in runs]
                ),
                "mean_ms": _range(
                    [run["timing"]["segments"][name]["mean_ms"] for run in runs]
                ),
                "p95_ms": _range(
                    [run["timing"]["segments"][name]["p95_ms"] for run in runs]
                ),
                "sample_count": reference["timing"]["segments"][name]["sample_count"],
            }
            for name in segment_names
        },
    }
    scenario_median = aggregates["scenario_wall_seconds"]["median"]
    model_median = aggregates["segments"]["wood_model_step"]["total_seconds"]["median"]
    runner_median = aggregates["runner_wall_seconds"]["median"]
    readiness_median = aggregates["capture_resolution_wait_seconds"]["median"]
    return {
        "schema_version": 1,
        "status": "ok",
        "profile_count": len(runs),
        "configuration": configuration,
        "aggregates": aggregates,
        "interpretation": {
            "wood_model_share_of_scenario": model_median / scenario_median,
            "capture_readiness_share_of_runner": readiness_median / runner_median,
            "flow_update_cadence_model_seconds": configuration[
                "flow_update_interval_seconds"
            ],
            "gpu_utilization_sampled": False,
        },
        "invariants": {
            "dry_ignition_seconds": ignition_pairs[0][0],
            "wet_ignition_seconds": ignition_pairs[0][1],
            "mass_balance_limit_kg": mass_error_limit_kg,
            "flow_active_in_all_profiles": True,
        },
        "runs": [
            {
                "source": str(path),
                "runner_wall_seconds": run["runner_wall_seconds"],
                "capture_resolution_wait_seconds": run["startup"][
                    "capture_resolution_wait_seconds"
                ],
                "scenario_wall_seconds": run["scenario"]["simulation_wall_seconds"],
                "dry_ignition_seconds": run["wood"]["dry"]["ignition_seconds"],
                "wet_ignition_seconds": run["wood"]["wet"]["ignition_seconds"],
                "flow_active_blocks_peak": run["flow"]["active_blocks_peak"],
            }
            for path, run in zip(paths, runs)
        ],
    }


def _bar_rectangles(parts: list[tuple[str, float, str]], x: float, y: float, width: float) -> str:
    total = sum(value for _, value, _ in parts)
    cursor = x
    rectangles = []
    for _, value, color in parts:
        part_width = width * value / total
        rectangles.append(
            f'<rect x="{cursor:.2f}" y="{y}" width="{part_width:.2f}" height="34" fill="{color}"/>'
        )
        cursor += part_width
    return "".join(rectangles)


def write_svg(summary: dict, destination: Path) -> None:
    aggregate = summary["aggregates"]
    runner = aggregate["runner_wall_seconds"]["median"]
    readiness = aggregate["capture_resolution_wait_seconds"]["median"]
    scenario = aggregate["scenario_wall_seconds"]["median"]
    runner_other = max(0.0, runner - readiness - scenario)
    runner_parts = [
        ("Capture / RTX readiness", readiness, "#a77a38"),
        ("240 s scenario", scenario, "#58b889"),
        ("Other startup / shutdown", runner_other, "#665c57"),
    ]

    scenario_parts = []
    displayed_total = 0.0
    for name, label, color in DISPLAYED_SEGMENTS:
        seconds = aggregate["segments"][name]["total_seconds"]["median"]
        displayed_total += seconds
        scenario_parts.append((label, seconds, color))
    scenario_other = max(0.0, scenario - displayed_total)
    scenario_parts.append(("Warmup + loop overhead", scenario_other, "#665c57"))

    cards = []
    for index, (label, seconds, color) in enumerate(scenario_parts):
        column = index % 3
        row = index // 3
        x = 60 + column * 360
        y = 410 + row * 62
        cards.append(
            f'''<circle cx="{x + 7}" cy="{y - 5}" r="6" fill="{color}"/>
  <text x="{x + 22}" y="{y}" class="label">{label}</text>
  <text x="{x + 22}" y="{y + 22}" class="small">{seconds:.3f} s median</text>'''
        )
    model_share = summary["interpretation"]["wood_model_share_of_scenario"] * 100.0
    readiness_share = summary["interpretation"]["capture_readiness_share_of_runner"] * 100.0
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 15px; fill: #d7b982; }}
    .heading {{ font-size: 17px; font-weight: 700; }}
    .label {{ font-size: 14px; font-weight: 600; }}
    .small {{ font-size: 12px; fill: #bcae9a; }}
    .value {{ font-size: 20px; font-weight: 700; fill: #7ed7a7; }}
  </style>
  <text x="60" y="50" class="title">Phase 6S · Phase 3 time anatomy</text>
  <text x="60" y="78" class="subtitle">{summary["profile_count"]} repeated runs · RTX 3090 active · same 1,200-step physics scenario</text>

  <rect x="60" y="102" width="1080" height="142" rx="10" fill="#1c1a18" stroke="#5b5049"/>
  <text x="82" y="132" class="heading">Runner wall · {runner:.2f} s median</text>
  {_bar_rectangles(runner_parts, 82, 150, 1036)}
  <text x="82" y="207" class="small">Capture / RTX readiness {readiness:.2f} s ({readiness_share:.1f}%)</text>
  <text x="430" y="207" class="small">Scenario {scenario:.2f} s</text>
  <text x="690" y="207" class="small">Other startup / shutdown {runner_other:.2f} s</text>

  <rect x="60" y="264" width="1080" height="278" rx="10" fill="#1b211d" stroke="#4f966b"/>
  <text x="82" y="296" class="heading">Scenario breakdown · wood model owns {model_share:.1f}%</text>
  {_bar_rectangles(scenario_parts, 82, 320, 1036)}
  {''.join(cards)}
  <text x="82" y="526" class="small">Flow is updated every {summary["configuration"]["flow_update_interval_seconds"]:.1f} model s. Segment totals exclude their declared warmup samples; remainder includes warmup and Python loop overhead.</text>

  <rect x="60" y="566" width="1080" height="66" rx="9" fill="#1c2820" stroke="#58b889" stroke-width="2"/>
  <text x="84" y="594" class="heading">INVARIANTS PASS · ignition {summary["invariants"]["dry_ignition_seconds"]:.1f} / {summary["invariants"]["wet_ignition_seconds"]:.1f} s · mass error ≤ {summary["invariants"]["mass_balance_limit_kg"]:.0e} kg</text>
  <text x="84" y="617" class="small">GPU utilization was not sampled. This report separates CPU/API wall intervals; it does not claim GPU kernel occupancy.</text>
  <text x="60" y="660" class="small">Conclusion: optimize the CPU wood step next; investigate the long viewport / RTX readiness wait independently.</text>
</svg>'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profiles", type=Path, nargs="+")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    arguments = parser.parse_args()
    result = summarize(arguments.profiles)
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_svg(result, arguments.svg)
    print(json.dumps(result["interpretation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
