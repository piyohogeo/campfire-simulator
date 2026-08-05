"""Validate the Phase 6U backend benchmark and render its browser SVG."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROWS = (
    ("python_aos", "Python AoS", "production-shaped CPU baseline"),
    ("numpy_aos_roundtrip", "NumPy roundtrip", "AoS convert + compute + writeback"),
    ("warp_aos_roundtrip", "Warp roundtrip", "AoS + H2D + kernel + D2H"),
    ("numpy_resident", "NumPy resident", "one boundary crossing per 400 steps"),
    (
        "warp_resident_sync_each_step",
        "Warp resident · sync/step",
        "GPU state resident, CPU waits every step",
    ),
    (
        "warp_resident_sync_every_5_steps",
        "Warp resident · sync/5",
        "GPU state resident, CPU waits every 5 steps",
    ),
    ("warp_resident_final_sync", "Warp resident · final sync", "architectural lower bound"),
)


def load_and_validate(source: Path) -> dict:
    result = json.loads(source.read_text(encoding="utf-8"))
    if result.get("schema_version") != 1:
        raise ValueError("Unsupported benchmark schema")
    if result.get("benchmark") != "isolated_sensible_heat_and_state_finalize":
        raise ValueError("Unexpected benchmark kind")
    if result.get("runs", 0) < 3 or result.get("steps", 0) < 400:
        raise ValueError("Phase 6U report requires at least 3 runs of 400 steps")
    measurements = result.get("measurements", {})
    if set(measurements) != {key for key, _, _ in ROWS}:
        raise ValueError("Backend measurement set differs")
    for measurement in measurements.values():
        for field in (
            "total_ms_min",
            "total_ms_median",
            "total_ms_max",
            "per_step_ms_median",
            "relative_to_python",
        ):
            value = measurement[field]
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"Invalid measurement: {field}")
    comparisons = result.get("candidate_comparisons", {})
    if any(
        not comparison.get("within_candidate_tolerance")
        or not comparison.get("exact_state_sha256_match")
        for comparison in comparisons.values()
    ):
        raise ValueError("A backend changed the isolated authoritative state")
    python_ms = measurements["python_aos"]["per_step_ms_median"]
    numpy_roundtrip_ms = measurements["numpy_aos_roundtrip"]["per_step_ms_median"]
    warp_roundtrip_ms = measurements["warp_aos_roundtrip"]["per_step_ms_median"]
    if numpy_roundtrip_ms >= python_ms:
        raise ValueError("NumPy roundtrip did not improve on Python AoS")
    if warp_roundtrip_ms <= python_ms:
        raise ValueError("Expected per-step Warp transfer penalty was not observed")
    result["decision"] = {
        "prototype_next": "numpy_aos_roundtrip",
        "reject_now": "warp_aos_roundtrip",
        "numpy_roundtrip_improvement_fraction": (
            python_ms - numpy_roundtrip_ms
        )
        / python_ms,
        "warp_roundtrip_regression_fraction": (warp_roundtrip_ms - python_ms)
        / python_ms,
        "resident_results_are_architectural_lower_bounds": True,
        "gpu_utilization_measured": False,
    }
    return result


def write_svg(result: dict, destination: Path) -> None:
    measurements = result["measurements"]
    maximum = max(value["per_step_ms_median"] for value in measurements.values())
    rows = []
    for row_index, (key, label, detail) in enumerate(ROWS):
        measurement = measurements[key]
        value = measurement["per_step_ms_median"]
        width = 350.0 * value / maximum
        y = 143 + row_index * 54
        if key == "numpy_aos_roundtrip":
            color = "#58b889"
        elif key == "warp_aos_roundtrip":
            color = "#cf765f"
        elif "resident" in key:
            color = "#699fd1"
        else:
            color = "#d7b982"
        rows.append(
            f'''<text x="72" y="{y}" class="label">{label}</text>
  <text x="72" y="{y + 17}" class="detail">{detail}</text>
  <rect x="360" y="{y - 15}" width="{width:.2f}" height="18" rx="4" fill="{color}"/>
  <text x="728" y="{y}" class="value">{value:.4f} ms/step</text>'''
        )

    decision = result["decision"]
    numpy_gain = decision["numpy_roundtrip_improvement_fraction"] * 100.0
    warp_loss = decision["warp_roundtrip_regression_fraction"] * 100.0
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#15120f"/>
  <style>
    text {{ font-family: "Segoe UI", Arial, sans-serif; fill: #fff7e9; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 14px; fill: #d7b982; }}
    .label {{ font-size: 14px; font-weight: 700; }}
    .detail {{ font-size: 10px; fill: #a99c89; }}
    .value {{ font-size: 13px; fill: #ded2c0; }}
    .heading {{ font-size: 16px; font-weight: 700; }}
    .big {{ font-size: 24px; font-weight: 700; }}
    .good {{ fill: #82d8aa; }}
    .bad {{ fill: #ef9a81; }}
    .small {{ font-size: 12px; fill: #bcae9a; }}
  </style>
  <text x="56" y="48" class="title">Phase 6U · Array backend transfer boundary</text>
  <text x="56" y="76" class="subtitle">{result["cell_count"]:,} cells · {result["steps"]} steps × {result["runs"]} runs · sensible heat + state finalize only · RTX 3090</text>
  <rect x="52" y="100" width="832" height="438" rx="10" fill="#1b211d" stroke="#4f966b"/>
  {''.join(rows)}
  <rect x="908" y="100" width="238" height="438" rx="10" fill="#211817" stroke="#a77a38"/>
  <text x="930" y="136" class="heading">DECISION</text>
  <text x="930" y="178" class="small">Prototype next</text>
  <text x="930" y="207" class="big good">NumPy</text>
  <text x="930" y="232" class="small">AoS roundtrip −{numpy_gain:.1f}%</text>
  <text x="930" y="278" class="small">Reject now</text>
  <text x="930" y="307" class="big bad">Warp roundtrip</text>
  <text x="930" y="332" class="small">per-step transfer +{warp_loss:.1f}%</text>
  <text x="930" y="380" class="small">Resident GPU is a lower bound</text>
  <text x="930" y="404" class="small">not a production result</text>
  <text x="930" y="448" class="small">GPU kernels executed</text>
  <text x="930" y="472" class="small">utilization not sampled</text>
  <text x="930" y="506" class="small">No production code changed</text>
  <rect x="52" y="564" width="1094" height="66" rx="9" fill="#1c2820" stroke="#58b889" stroke-width="2"/>
  <text x="76" y="592" class="heading">EXACT ISOLATED STATE MATCH · all six candidates match Python SHA-256</text>
  <text x="76" y="616" class="small">Float64 · zero temperature/mass error · zero phase mismatch · Warp compilation excluded.</text>
  <text x="56" y="658" class="small">Excluded: conduction, evaporation, pyrolysis, char oxidation, metrics, Flow/USD. Resident paths include one initial upload and final download.</text>
</svg>'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    arguments = parser.parse_args()
    result = load_and_validate(arguments.source)
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_svg(result, arguments.svg)
    print(json.dumps(result["decision"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
