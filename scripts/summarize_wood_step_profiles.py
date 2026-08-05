"""Summarize repeated opt-in WoodThermalModel.step profiles as JSON and SVG."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


CONFIGURATION_FIELDS = (
    "benchmark",
    "steps",
    "warmup_steps_excluded",
    "model_duration_seconds",
    "combined_cell_count",
    "dt_seconds",
    "external_heat_flux_w_m2",
)
INVARIANT_FIELDS = (
    "ignition_seconds",
    "dry_mass_balance_error_kg",
    "wet_mass_balance_error_kg",
    "dry_state_sha256",
    "wet_state_sha256",
)
SEGMENT_LABELS = {
    "sensible_heat": "Sensible heat",
    "state_finalize": "Clamp + phase",
    "conduction": "Conduction",
    "evaporation": "Evaporation",
    "pyrolysis": "Pyrolysis",
    "char_oxidation": "Char oxidation",
    "input_validation": "Input validation",
    "result_aggregation": "Result aggregation",
}


def _load(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema_version") != 1:
        raise ValueError(f"Unsupported benchmark schema: {path}")
    return result


def _validate_runs(runs: list[dict], reference: dict, require_profile: bool) -> None:
    for run in runs:
        for field in CONFIGURATION_FIELDS + INVARIANT_FIELDS:
            if run.get(field) != reference.get(field):
                raise ValueError(f"Benchmark field differs: {field}")
        if require_profile and not run.get("internal_timing"):
            raise ValueError("Profile run has no internal_timing data")
        if abs(run["dry_mass_balance_error_kg"]) > 1.0e-9:
            raise ValueError("Dry mass balance exceeded 1e-9 kg")
        if abs(run["wet_mass_balance_error_kg"]) > 1.0e-9:
            raise ValueError("Wet mass balance exceeded 1e-9 kg")


def summarize(
    before_profiles: list[dict],
    after_profiles: list[dict],
    baseline: dict,
    optimized_runs: list[dict],
) -> dict:
    reference = before_profiles[0]
    _validate_runs(before_profiles, reference, True)
    _validate_runs(after_profiles, reference, True)
    _validate_runs([baseline], reference, False)
    _validate_runs(optimized_runs, reference, False)

    segments = set(before_profiles[0]["internal_timing"])
    if segments != set(SEGMENT_LABELS):
        raise ValueError(f"Unexpected timing segments: {sorted(segments)}")
    if any(set(run["internal_timing"]) != segments for run in before_profiles + after_profiles):
        raise ValueError("Profile timing segment sets differ")

    segment_measurements = {}
    for segment in SEGMENT_LABELS:
        before_ms = statistics.median(
            run["internal_timing"][segment]["mean_ms"] for run in before_profiles
        )
        after_ms = statistics.median(
            run["internal_timing"][segment]["mean_ms"] for run in after_profiles
        )
        segment_measurements[segment] = {
            "label": SEGMENT_LABELS[segment],
            "before_median_mean_ms": before_ms,
            "after_median_mean_ms": after_ms,
            "improvement_fraction": (before_ms - after_ms) / before_ms,
        }

    before_total_ms = statistics.median(
        run["internal_timing_total_mean_ms"] for run in before_profiles
    )
    after_total_ms = statistics.median(
        run["internal_timing_total_mean_ms"] for run in after_profiles
    )
    for measurement in segment_measurements.values():
        measurement["after_share_fraction"] = (
            measurement["after_median_mean_ms"] / after_total_ms
        )

    unprofiled_fields = (
        "two_log_step_mean_ms",
        "two_log_step_p95_ms",
        "wall_seconds",
    )
    unprofiled = {}
    for field in unprofiled_fields:
        before = baseline[field]
        after = statistics.median(run[field] for run in optimized_runs)
        unprofiled[field] = {
            "before": before,
            "after_median": after,
            "improvement_fraction": (before - after) / before,
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "configuration": {field: reference[field] for field in CONFIGURATION_FIELDS},
        "run_counts": {
            "before_profiles": len(before_profiles),
            "after_profiles": len(after_profiles),
            "unprofiled_baseline": 1,
            "unprofiled_optimized": len(optimized_runs),
        },
        "internal_total": {
            "before_median_mean_ms": before_total_ms,
            "after_median_mean_ms": after_total_ms,
            "improvement_fraction": (before_total_ms - after_total_ms)
            / before_total_ms,
        },
        "segments": segment_measurements,
        "unprofiled": unprofiled,
        "invariants": {
            field: reference[field] for field in INVARIANT_FIELDS
        },
        "boundary": {
            "timings_are_cpu_only": True,
            "physics_equations_changed": False,
            "grid_or_dt_changed": False,
            "gpu_utilization_measured": False,
        },
    }


def write_svg(summary: dict, destination: Path) -> None:
    ordered_segments = sorted(
        summary["segments"].items(),
        key=lambda item: item[1]["after_median_mean_ms"],
        reverse=True,
    )
    maximum = max(
        max(value["before_median_mean_ms"], value["after_median_mean_ms"])
        for _, value in ordered_segments
    )
    rows = []
    for row_index, (_, measurement) in enumerate(ordered_segments):
        y = 154 + row_index * 48
        before_width = 330 * measurement["before_median_mean_ms"] / maximum
        after_width = 330 * measurement["after_median_mean_ms"] / maximum
        label = html.escape(measurement["label"])
        rows.append(
            f'''<text x="76" y="{y}" class="label">{label}</text>
  <rect x="250" y="{y - 15}" width="{before_width:.2f}" height="11" rx="3" fill="#d7b982"/>
  <rect x="250" y="{y + 2}" width="{after_width:.2f}" height="11" rx="3" fill="#58b889"/>
  <text x="600" y="{y - 5}" class="value">{measurement["before_median_mean_ms"]:.3f} → {measurement["after_median_mean_ms"]:.3f} ms</text>
  <text x="790" y="{y + 10}" class="share">{measurement["after_share_fraction"] * 100:.1f}% after</text>'''
        )

    total = summary["internal_total"]
    unprofiled = summary["unprofiled"]
    step = unprofiled["two_log_step_mean_ms"]
    p95 = unprofiled["two_log_step_p95_ms"]
    wall = unprofiled["wall_seconds"]
    dry_ignition = summary["invariants"]["ignition_seconds"]["dry"]
    runs = summary["run_counts"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 14px; fill: #d7b982; }}
    .label {{ font-size: 13px; font-weight: 600; }}
    .value {{ font-size: 12px; fill: #ded2c0; }}
    .share {{ font-size: 11px; fill: #82d8aa; }}
    .heading {{ font-size: 16px; font-weight: 700; }}
    .big {{ font-size: 24px; font-weight: 700; fill: #82d8aa; }}
    .small {{ font-size: 12px; fill: #bcae9a; }}
  </style>
  <text x="60" y="50" class="title">Phase 6T · CPU wood step internals</text>
  <text x="60" y="78" class="subtitle">{summary["configuration"]["combined_cell_count"]:,} cells · 400 steps · profile medians of {runs["before_profiles"]} before + {runs["after_profiles"]} after runs · CPU only</text>
  <rect x="54" y="102" width="856" height="438" rx="10" fill="#1b211d" stroke="#4f966b"/>
  <text x="250" y="124" class="small">BEFORE / AFTER</text>
  {''.join(rows)}
  <rect x="934" y="102" width="212" height="438" rx="10" fill="#211817" stroke="#a77a38"/>
  <text x="954" y="136" class="heading">MEASURED RESULT</text>
  <text x="954" y="178" class="small">Profiled internal total</text>
  <text x="954" y="207" class="big">−{total["improvement_fraction"] * 100:.1f}%</text>
  <text x="954" y="230" class="small">{total["before_median_mean_ms"]:.3f} → {total["after_median_mean_ms"]:.3f} ms</text>
  <text x="954" y="274" class="small">Unprofiled step mean</text>
  <text x="954" y="303" class="big">−{step["improvement_fraction"] * 100:.1f}%</text>
  <text x="954" y="326" class="small">{step["before"]:.3f} → {step["after_median"]:.3f} ms</text>
  <text x="954" y="368" class="small">Step p95 −{p95["improvement_fraction"] * 100:.1f}%</text>
  <text x="954" y="392" class="small">80 s wall −{wall["improvement_fraction"] * 100:.1f}%</text>
  <text x="954" y="440" class="small">No GPU utilization claim</text>
  <text x="954" y="464" class="small">No grid or dt change</text>
  <text x="954" y="488" class="small">Opt-in timing dictionary</text>
  <rect x="54" y="566" width="1092" height="64" rx="9" fill="#1c2820" stroke="#58b889" stroke-width="2"/>
  <text x="78" y="594" class="heading">STATE IDENTICAL · dry ignition {dry_ignition:.1f} s · wet not ignited by 80 s</text>
  <text x="78" y="617" class="small">Dry/wet authoritative JSON SHA-256 unchanged · mass-balance error ≤ 1e−9 kg · equations unchanged.</text>
  <text x="60" y="658" class="small">Before/after segment bars share one scale. Profile timing changes execution shape slightly; production result uses unprofiled runs.</text>
</svg>'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-profile", type=Path, action="append", required=True)
    parser.add_argument("--after-profile", type=Path, action="append", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--optimized", type=Path, action="append", required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    arguments = parser.parse_args()

    summary = summarize(
        [_load(path) for path in arguments.before_profile],
        [_load(path) for path in arguments.after_profile],
        _load(arguments.baseline),
        [_load(path) for path in arguments.optimized],
    )
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_svg(summary, arguments.svg)
    print(json.dumps(summary["internal_total"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
