"""Aggregate Phase 6EC control/rotation/collision-off public Flow readback."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path


CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity")
SCALAR_LIMIT = 1.0e-6
VELOCITY_LIMIT = 1.0e-5


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(sample: dict, channel: str, group: str, roi: str) -> dict:
    return sample["channels"][channel][group][roi]


def _maxima(raw: dict, group: str, roi: str) -> dict:
    return {
        channel: max(float(_metric(sample, channel, group, roi)["maximum"]) for sample in raw["samples"])
        for channel in CHANNELS
    }


def _means(raw: dict, group: str, roi: str) -> dict:
    return {
        channel: sum(float(_metric(sample, channel, group, roi)["mean"]) for sample in raw["samples"])
        / len(raw["samples"])
        for channel in CHANNELS
    }


def _ratios(numerator: dict, denominator: dict) -> dict:
    return {
        channel: (numerator[channel] / denominator[channel] if denominator[channel] > 0.0 else None)
        for channel in CHANNELS
    }


def _svg(report: dict) -> str:
    labels = ["axis ON", "Y40 ON", "Y40 OFF"]
    cases = ["axis_on", "rotated_on", "rotated_off"]
    values = [report["cases"][case]["core_maximum"]["temperature"] for case in cases]
    maximum = max(values + [1.0e-9])
    bars = []
    for index, (label, value) in enumerate(zip(labels, values)):
        width = 720.0 * value / maximum
        y = 118 + index * 92
        bars.append(
            f'<text x="34" y="{y + 24}" class="label">{html.escape(label)}</text>'
            f'<rect x="190" y="{y}" width="{width:.2f}" height="36" rx="5" class="bar{index}"/>'
            f'<text x="{max(200.0, 202.0 + width):.2f}" y="{y + 25}" class="value">{value:.6g}</text>'
        )
    ratio = report["comparison"]["rotated_on_over_off_core_maximum"]["temperature"]
    ratio_text = "n/a" if ratio is None else f"{ratio:.3g}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="480" viewBox="0 0 1000 480">
<style>.bg{{fill:#10151d}}.title{{fill:#f6f7fb;font:700 28px sans-serif}}.sub{{fill:#b8c3d4;font:16px sans-serif}}.label{{fill:#e8edf5;font:17px sans-serif}}.value{{fill:#d8e1ed;font:15px monospace}}.bar0{{fill:#4aa3df}}.bar1{{fill:#4fc38b}}.bar2{{fill:#ef9b45}}.gate{{fill:#9ee6ba;font:700 18px sans-serif}}</style>
<rect width="1000" height="480" class="bg"/>
<text x="34" y="45" class="title">Phase 6EC — rotated Mesh collision</text>
<text x="34" y="76" class="sub">Temperature maximum inside the centerline core; four public NanoVDB samples</text>
{''.join(bars)}
<text x="34" y="420" class="gate">Y40 ON / OFF = {html.escape(ratio_text)} · qualified={str(report['qualified']).lower()}</text>
<text x="34" y="452" class="sub">Collision OFF is the positive passage control; ON values below 1e-6 are treated as numerical zero.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    prepared = _load(args.root / "prepared_stages.json")
    paths = {
        "axis_on": args.root / "formal" / "A_axis_on" / "raw.json",
        "rotated_on": args.root / "formal" / "B_rotate_y40_on" / "raw.json",
        "rotated_off": args.root / "formal" / "C_rotate_y40_off" / "raw.json",
    }
    raw = {name: _load(path) for name, path in paths.items()}
    evidence = {
        name: _load(path.parent / "runner_evidence.json") for name, path in paths.items()
    }
    cases = {}
    for name, payload in raw.items():
        cases[name] = {
            "status": payload.get("status"),
            "active_blocks_final": payload.get("active_blocks_final"),
            "sample_frames": [sample["frame"] for sample in payload.get("samples", [])],
            "physics_collision_enabled": payload["effective_stage_audit"]["simulate"]["physicsCollisionEnabled"],
            "emitter_fuel": payload["effective_stage_audit"]["emitter"]["coupleRateFuel"],
            "source_fuel": payload["stage_audit"]["emitter"]["fuel"],
            "local_to_world": payload["local_roi_contract"]["local_to_world"],
            "core_maximum": _maxima(payload, "local_rois", "cylinder_core"),
            "inside_mean": _means(payload, "local_rois", "cylinder_inside"),
            "rotated_only_maximum": (
                None if name == "axis_on" else _maxima(payload, "alignment_rois", "rotated_only")
            ),
            "axis_only_maximum": (
                None if name == "axis_on" else _maxima(payload, "alignment_rois", "axis_only")
            ),
            "lifecycle": evidence[name]["outcome"],
        }

    core_ratio = _ratios(cases["rotated_on"]["core_maximum"], cases["rotated_off"]["core_maximum"])
    rotated_only_ratio = _ratios(
        cases["rotated_on"]["rotated_only_maximum"],
        cases["rotated_off"]["rotated_only_maximum"],
    )
    scalar_channels = ("temperature", "fuel", "burn", "smoke")
    lifecycle_values = [cases[name]["lifecycle"]["lifecycle_status"] for name in cases]
    gates = {
        "prepared_stage_contract": prepared.get("status") == "ok" and all(prepared.get("gates", {}).values()),
        "all_probe_results_complete": all(cases[name]["status"] == "ok" and cases[name]["sample_frames"] == [60, 120, 180, 200] for name in cases),
        "all_functional_classifications_pass": all(cases[name]["lifecycle"]["functional_status"] == "pass" for name in cases),
        "no_unknown_shutdown_failure": all(value in ("normal_exit", "known_ngx_shutdown_residual") for value in lifecycle_values),
        "no_two_consecutive_known_residuals": not any(lifecycle_values[index:index + 2] == ["known_ngx_shutdown_residual"] * 2 for index in range(len(lifecycle_values) - 1)),
        "active_blocks_nonzero": all(int(cases[name]["active_blocks_final"]) > 0 for name in cases),
        "fuel_input_preserved": all(math.isclose(float(cases[name]["source_fuel"]), 0.8, abs_tol=1.0e-6) for name in cases),
        "collision_switch_is_only_control_difference": cases["axis_on"]["physics_collision_enabled"] is True and cases["rotated_on"]["physics_collision_enabled"] is True and cases["rotated_off"]["physics_collision_enabled"] is False,
        "axis_core_velocity_suppressed": cases["axis_on"]["core_maximum"]["velocity"] <= VELOCITY_LIMIT,
        "rotated_core_velocity_suppressed": cases["rotated_on"]["core_maximum"]["velocity"] <= VELOCITY_LIMIT,
        "collision_off_positive_control_scalar_passage": all(cases["rotated_off"]["core_maximum"][channel] > SCALAR_LIMIT for channel in ("temperature", "burn", "smoke")),
        "collision_off_positive_control_velocity": cases["rotated_off"]["core_maximum"]["velocity"] > VELOCITY_LIMIT,
        "rotated_core_scalar_reduced_vs_collision_off": all(
            core_ratio[channel] is not None and core_ratio[channel] < 0.75
            for channel in ("temperature", "burn", "smoke")
        ),
        "rotated_transform_shared_by_on_off": cases["rotated_on"]["local_to_world"] == cases["rotated_off"]["local_to_world"],
        "rotation_differs_from_axis_control": cases["axis_on"]["local_to_world"] != cases["rotated_on"]["local_to_world"],
    }
    report = {
        "schema": "campfire.phase6ec.static-rotated-cylinder-report.v1",
        "phase": "phase6ec",
        "purpose": "qualify one static Y40 closed-Mesh Flow CollisionProxy rotation",
        "noise_thresholds": {"scalar": SCALAR_LIMIT, "velocity_m_s": VELOCITY_LIMIT},
        "cases": cases,
        "comparison": {
            "rotated_on_over_off_core_maximum": core_ratio,
            "rotated_on_over_off_rotated_only_maximum": rotated_only_ratio,
            "interpretation": "The transformed core is the qualification gate; alignment-only ROIs are supporting evidence for stale-position discrimination.",
        },
        "gates": gates,
        "qualified": all(gates.values()),
        "performance_samples": {
            name: cases[name]["lifecycle"]["performance_sample_accepted"] for name in cases
        },
        "production_change": False,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
