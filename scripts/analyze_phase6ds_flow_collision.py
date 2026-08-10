"""Aggregate the isolated Phase 6DS static Flow-collision measurements."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


CONDITIONS = ("collision_off", "box_aligned", "box_shift_half", "box_shift_one")
CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity")
ROIS = ("below", "inside", "inside_core", "above", "above_far")


def _percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _stats(values):
    values = list(values)
    return {
        "sample_count": len(values),
        "mean": statistics.fmean(values),
        "p95": _percentile(values, 0.95),
        "maximum": max(values),
        "minimum": min(values),
    }


def _aggregate_condition(runs):
    result = {"run_count": len(runs), "channels": {}}
    for channel in CHANNELS:
        channel_result = {}
        for roi in ROIS:
            records = [
                sample["channels"][channel]["rois"][roi]
                for run in runs
                for sample in run["samples"]
                if sample["channels"].get(channel, {}).get("available", False)
            ]
            if not records:
                channel_result[roi] = {"available": False}
                continue
            channel_result[roi] = {
                "available": True,
                "voxel_mean": _stats(record["mean"] for record in records),
                "voxel_p95": _stats(record["p95"] for record in records),
                "voxel_maximum": _stats(record["maximum"] for record in records),
                "nonzero_voxel_count": _stats(record["nonzero_voxel_count"] for record in records),
                "voxel_count": _stats(record["voxel_count"] for record in records),
            }
        result["channels"][channel] = channel_result
    result["active_blocks"] = _stats(
        sample["active_blocks"] for run in runs for sample in run["samples"]
    )
    return result


def _ratio(value, denominator):
    return None if abs(denominator) <= 1.0e-20 else value / denominator


def _svg(report):
    colors = {
        "collision_off": "#ef4444",
        "box_aligned": "#22c55e",
        "box_shift_half": "#38bdf8",
        "box_shift_one": "#a78bfa",
    }
    labels = {
        "collision_off": "OFF",
        "box_aligned": "ON aligned",
        "box_shift_half": "ON +0.5 cell",
        "box_shift_one": "ON +1 cell",
    }
    metrics = []
    for channel in ("temperature", "fuel", "smoke", "burn"):
        for roi in ("inside_core", "above_far"):
            metrics.append((channel, roi))
    width, height = 1400, 860
    chart_left, chart_top, chart_width, row_height = 310, 175, 1020, 72
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Phase 6DS Flow collision occlusion</title>',
        '<desc id="desc">Collision ON channel means in collider core and far-above regions normalized to Collision OFF.</desc>',
        '<rect width="1400" height="860" rx="28" fill="#081521"/>',
        '<style>.k{font:700 17px Segoe UI,sans-serif;fill:#7dd3fc;letter-spacing:2px}.t{font:750 38px Segoe UI,sans-serif;fill:#f8fafc}.s{font:16px Segoe UI,sans-serif;fill:#cbd5e1}.l{font:600 15px Segoe UI,sans-serif;fill:#e2e8f0}.v{font:700 14px Segoe UI,sans-serif;fill:#f8fafc}.m{font:13px Segoe UI,sans-serif;fill:#94a3b8}</style>',
        '<text x="64" y="55" class="k">PHASE 6DS · FLOW COLLISION OCCLUSION PROBE</text>',
        '<text x="64" y="105" class="t">Static Box ROI field ratios</text>',
        '<text x="64" y="139" class="s">Flow 110.0.0 · 0.025 m density cells · public NanoVDB readback · 3 independent runs</text>',
    ]
    for row, (channel, roi) in enumerate(metrics):
        y = chart_top + row * row_height
        lines.append(f'<text x="64" y="{y + 25}" class="l">{channel} · {roi}</text>')
        lines.append(f'<line x1="{chart_left}" y1="{y + 30}" x2="{chart_left + chart_width}" y2="{y + 30}" stroke="#334155"/>')
        for index, condition in enumerate(CONDITIONS):
            ratio = report["off_ratios"][condition][channel][roi]
            shown = 0.0 if ratio is None else min(1.35, ratio)
            bar_width = shown * chart_width / 1.35
            bar_y = y + 4 + index * 13
            lines.append(f'<rect x="{chart_left}" y="{bar_y}" width="{bar_width:.2f}" height="10" rx="5" fill="{colors[condition]}"/>')
            display = "n/a" if ratio is None else f"{ratio:.3f}×"
            lines.append(f'<text x="{chart_left + bar_width + 8:.2f}" y="{bar_y + 9}" class="v">{display}</text>')
    legend_x = 64
    for condition in CONDITIONS:
        lines.append(f'<rect x="{legend_x}" y="790" width="14" height="14" rx="3" fill="{colors[condition]}"/>')
        lines.append(f'<text x="{legend_x + 22}" y="802" class="m">{labels[condition]}</text>')
        legend_x += 245
    lines.append(f'<text x="64" y="835" class="m">Velocity cell {report["effective_velocity_cell_size_m"]:.5f} m · bars capped at 1.35× · no zero-leakage pass threshold imposed</text>')
    lines.append("</svg>")
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    arguments = parser.parse_args()
    runs_by_condition = {}
    evidence = []
    for condition in CONDITIONS:
        runs = []
        for run_index in range(1, 4):
            directory = arguments.input / condition / f"run-{run_index}"
            run = json.loads((directory / "raw.json").read_text(encoding="utf-8"))
            runner = json.loads((directory / "runner_evidence.json").read_text(encoding="utf-8"))
            if run.get("status") != "ok" or runner.get("process_exit_code") != 0:
                raise ValueError(f"Invalid Phase 6DS run: {condition} r{run_index}")
            if runner.get("fatal_lines") or runner.get("dump_inventory") or runner.get("automatic_upload_attempt_lines"):
                raise ValueError(f"Unsafe Phase 6DS evidence: {condition} r{run_index}")
            if runner.get("production_changed") or runner.get("machine_wide_settings_changed"):
                raise ValueError(f"Phase 6DS changed protected state: {condition} r{run_index}")
            runs.append(run)
            evidence.append(runner)
        runs_by_condition[condition] = runs

    raw = {
        "schema": "campfire.phase6ds.flow-collision-raw.v1",
        "phase": "phase6ds",
        "status": "ok",
        "conditions": runs_by_condition,
        "runner_evidence": evidence,
    }
    aggregates = {name: _aggregate_condition(runs) for name, runs in runs_by_condition.items()}
    off_ratios = {}
    for condition in CONDITIONS:
        off_ratios[condition] = {}
        for channel in CHANNELS:
            off_ratios[condition][channel] = {}
            for roi in ROIS:
                numerator = aggregates[condition]["channels"][channel][roi]
                denominator = aggregates["collision_off"]["channels"][channel][roi]
                if not numerator.get("available") or not denominator.get("available"):
                    off_ratios[condition][channel][roi] = None
                else:
                    off_ratios[condition][channel][roi] = _ratio(
                        numerator["voxel_mean"]["mean"], denominator["voxel_mean"]["mean"]
                    )

    velocity_sizes = [
        run["flow_settings"]["velocity_cell_size_m"]
        for runs in runs_by_condition.values()
        for run in runs
    ]
    if max(velocity_sizes) - min(velocity_sizes) > 1.0e-7:
        raise ValueError(f"Velocity-cell size changed across runs: {velocity_sizes}")
    velocity_cell = statistics.fmean(velocity_sizes)
    shift_cells = {
        condition: statistics.fmean(run["collider"]["shift_velocity_cells"] for run in runs)
        for condition, runs in runs_by_condition.items()
    }
    report = {
        "schema": "campfire.phase6ds.flow-collision-report.v1",
        "phase": "phase6ds",
        "status": "ok",
        "default_off": True,
        "production_code_changed": False,
        "flow_version": "110.0.0",
        "run_count": sum(len(runs) for runs in runs_by_condition.values()),
        "effective_velocity_cell_size_m": velocity_cell,
        "shift_velocity_cells": shift_cells,
        "aggregates": aggregates,
        "off_ratios": off_ratios,
        "safety": {
            "fatal_count": sum(len(item["fatal_lines"]) for item in evidence),
            "native_crash_count": sum(bool(item["native_crash"]) for item in evidence),
            "dump_count": sum(len(item["dump_inventory"]) for item in evidence),
            "automatic_upload_attempt_count": sum(len(item["automatic_upload_attempt_lines"]) for item in evidence),
            "all_shutdown_complete": all(item["lifecycle_marker"] == "shutdown_complete" for item in evidence),
            "all_machine_wide_settings_unchanged": all(not item["machine_wide_settings_changed"] for item in evidence),
        },
        "measurement_gates": {
            "three_runs_per_condition": all(len(runs) == 3 for runs in runs_by_condition.values()),
            "all_run_gates_passed": all(all(run["measurement_gates"].values()) for runs in runs_by_condition.values() for run in runs),
            "half_cell_shift_measured": abs(shift_cells["box_shift_half"] - 0.5) <= 1.0e-5,
            "one_cell_shift_measured": abs(shift_cells["box_shift_one"] - 1.0) <= 1.0e-5,
            "safety_clean": all(value == 0 for key, value in {
                "fatal": sum(len(item["fatal_lines"]) for item in evidence),
                "dump": sum(len(item["dump_inventory"]) for item in evidence),
                "upload": sum(len(item["automatic_upload_attempt_lines"]) for item in evidence),
            }.items()),
        },
        "interpretation": {
            "threshold_policy": "Measurement validity is gated; no predeclared zero-leakage threshold is used.",
            "velocity": "Public velocity readback was sampled as magnitude." if all(run["velocity_readback"]["available"] for runs in runs_by_condition.values() for run in runs) else "Velocity unavailable through the public readback in one or more runs; no private API used.",
            "internal_representation": "Not established by this probe; no claim of retained convex geometry or explicit voxel mask.",
        },
    }
    aligned_primary_ratios = {
        channel: {
            roi: off_ratios["box_aligned"][channel][roi]
            for roi in ("inside_core", "above_far")
        }
        for channel in ("temperature", "smoke", "burn", "velocity")
    }
    shifted_values_equal = all(
        off_ratios["box_shift_half"][channel][roi]
        == off_ratios["box_shift_one"][channel][roi]
        for channel in CHANNELS
        for roi in ROIS
    )
    report["decision"] = {
        "classification": "Collision ONでもOFFと同程度に上側へ到達する",
        "aligned_primary_off_ratios": aligned_primary_ratios,
        "half_and_one_cell_aggregate_values_equal": shifted_values_equal,
        "position_shift_response": (
            "0.5-cell and 1-cell aggregate values were identical; no monotonic "
            "occlusion response was observed."
        ),
        "visual_classification": (
            "OFF and aligned-ON captures both show the vertical volume continuing "
            "through and above the opaque Box; numeric and rendered evidence agree."
        ),
        "phase6dr_current_explanation": (
            "The leading explanation is real Flow-field non-occlusion under the "
            "current public PhysX/Flow integration, not a ray-march-only illusion. "
            "The missing ingestion/constraint boundary is not identified."
        ),
        "cylinder_attempted": False,
        "cylinder_reason": (
            "The required axis-aligned static Box did not establish occlusion, so "
            "Cylinder and dynamic-transform tests were not started."
        ),
    }
    report["visual_evidence"] = {
        "comparison_video": "flow_collision_occlusion_comparison.mp4",
        "comparison_poster": "flow_collision_occlusion_comparison.png",
        "off_frame": "flow_collision_occlusion_off.png",
        "aligned_on_frame": "flow_collision_occlusion_on.png",
        "frame_count": 4,
        "unique_source_frame_count": 8,
        "duration_seconds": 8.0,
        "latest_demo_pointer_changed": False,
    }
    if not all(report["measurement_gates"].values()):
        raise ValueError(f"Phase 6DS aggregate gates failed: {report['measurement_gates']}")
    for path in (arguments.raw, arguments.report, arguments.svg):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.raw.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    arguments.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    print(f"Phase 6DS: {report['run_count']} valid runs; velocity cell {velocity_cell:.5f} m")


if __name__ == "__main__":
    main()
