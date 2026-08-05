"""Compare two isolated wood CPU benchmarks and render a browser SVG."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


MATCHED_CONFIGURATION_FIELDS = (
    "benchmark",
    "steps",
    "warmup_steps_excluded",
    "model_duration_seconds",
    "cell_count_per_log",
    "combined_cell_count",
    "dt_seconds",
    "external_heat_flux_w_m2",
)
METRICS = (
    ("two_log_step_mean_ms", "Two-log step mean"),
    ("two_log_step_p95_ms", "Two-log step p95"),
    ("two_log_metrics_mean_ms", "Metrics mean"),
    ("wall_seconds", "80 s model wall time"),
)


def _load(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema_version") != 1:
        raise ValueError(f"Unsupported benchmark schema: {path}")
    return result


def compare(before: dict, after: dict) -> dict:
    changed = tuple(
        field
        for field in MATCHED_CONFIGURATION_FIELDS
        if before.get(field) != after.get(field)
    )
    if changed:
        raise ValueError(f"Benchmark configurations differ: {changed}")
    if before["ignition_seconds"] != after["ignition_seconds"]:
        raise ValueError("Ignition behavior changed during performance comparison")
    for field in ("dry_state_sha256", "wet_state_sha256"):
        if field in before and field in after and before[field] != after[field]:
            raise ValueError(f"Authoritative wood state changed: {field}")
    mass_error_limit_kg = 1.0e-9
    if any(
        abs(result[field]) > mass_error_limit_kg
        for result in (before, after)
        for field in ("dry_mass_balance_error_kg", "wet_mass_balance_error_kg")
    ):
        raise ValueError("Benchmark violated the mass-balance tolerance")
    for key, _ in METRICS:
        values = (before[key], after[key])
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError(f"Benchmark metric must be finite and positive: {key}")
        if after[key] >= before[key]:
            raise ValueError(f"Benchmark metric did not improve: {key}")
    measurements = {
        key: {
            "before": before[key],
            "after": after[key],
            "improvement_fraction": (before[key] - after[key]) / before[key],
        }
        for key, _ in METRICS
    }
    return {
        "schema_version": 1,
        "status": "ok",
        "configuration": {
            field: before[field] for field in MATCHED_CONFIGURATION_FIELDS
        },
        "measurements": measurements,
        "invariants": {
            "ignition_seconds": before["ignition_seconds"],
            "mass_balance_limit_kg": mass_error_limit_kg,
            "dry_mass_balance_error_kg": after["dry_mass_balance_error_kg"],
            "wet_mass_balance_error_kg": after["wet_mass_balance_error_kg"],
        },
    }


def write_svg(comparison: dict, destination: Path) -> None:
    rows = []
    for row_index, (key, label) in enumerate(METRICS):
        measurement = comparison["measurements"][key]
        before = measurement["before"]
        after = measurement["after"]
        improvement = measurement["improvement_fraction"] * 100.0
        maximum = max(before, after)
        before_width = 340.0 * before / maximum
        after_width = 340.0 * after / maximum
        y = 166 + row_index * 92
        unit = "s" if key == "wall_seconds" else "ms"
        rows.append(
            f'''<text x="84" y="{y}" class="label">{label}</text>
  <rect x="310" y="{y - 22}" width="{before_width:.2f}" height="18" rx="4" fill="#d7b982"/>
  <rect x="310" y="{y + 8}" width="{after_width:.2f}" height="18" rx="4" fill="#58b889"/>
  <text x="670" y="{y - 7}" class="value">{before:.3f} {unit}</text>
  <text x="670" y="{y + 23}" class="value">{after:.3f} {unit}</text>
  <text x="842" y="{y + 8}" class="gain">−{improvement:.1f}%</text>'''
        )
    invariant = comparison["invariants"]
    configuration = comparison["configuration"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 15px; fill: #d7b982; }}
    .label {{ font-size: 15px; font-weight: 600; }}
    .value {{ font-size: 13px; fill: #ded2c0; }}
    .gain {{ font-size: 18px; font-weight: 700; fill: #7ed7a7; }}
    .small {{ font-size: 12px; fill: #bcae9a; }}
    .heading {{ font-size: 16px; font-weight: 700; }}
  </style>
  <text x="60" y="52" class="title">Phase 6R · Wood CPU hot-path</text>
  <text x="60" y="82" class="subtitle">{configuration["combined_cell_count"]:,} cells · {configuration["steps"]} steps · isolated from Kit, Flow, USD, and rendering</text>
  <rect x="60" y="112" width="920" height="428" rx="10" fill="#1b211d" stroke="#4f966b"/>
  <text x="310" y="130" class="small">BEFORE</text>
  <text x="390" y="130" class="small">AFTER</text>
  {''.join(rows)}
  <rect x="1004" y="112" width="136" height="428" rx="10" fill="#211817" stroke="#a77a38"/>
  <text x="1022" y="150" class="heading">BOUNDARY</text>
  <text x="1022" y="184" class="small">CPU only</text>
  <text x="1022" y="208" class="small">No GPU claim</text>
  <text x="1022" y="248" class="small">Same physics</text>
  <text x="1022" y="272" class="small">Same inputs</text>
  <text x="1022" y="312" class="small">No grid change</text>
  <text x="1022" y="336" class="small">No dt change</text>
  <text x="1022" y="376" class="small">Python</text>
  <text x="1022" y="400" class="small">microbench</text>
  <text x="1022" y="456" class="small">End-to-end</text>
  <text x="1022" y="480" class="small">measured</text>
  <text x="1022" y="504" class="small">separately</text>
  <rect x="60" y="566" width="1080" height="64" rx="9" fill="#1c2820" stroke="#58b889" stroke-width="2"/>
  <text x="84" y="594" class="heading">INVARIANTS PASS · dry ignition {invariant["ignition_seconds"]["dry"]:.1f} s · wet not ignited by 80 s</text>
  <text x="84" y="616" class="small">Mass-balance error ≤ {invariant["mass_balance_limit_kg"]:.0e} kg · arithmetic and aggregation optimized; model equations unchanged.</text>
  <text x="60" y="658" class="small">Bars use a per-row scale. Values are the evidence; bar length is only a visual aid.</text>
</svg>'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    arguments = parser.parse_args()
    comparison = compare(_load(arguments.before), _load(arguments.after))
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_svg(comparison, arguments.svg)
    print(json.dumps(comparison["measurements"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
