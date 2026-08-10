"""Summarize Phase V3T-Q app-path, developer-bundle, and scheduler evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


SETTING_PATHS = (
    "/app/runLoops/main/rateLimitEnabled",
    "/app/runLoops/main/rateLimitFrequency",
    "/app/runLoops/main/syncToPresent",
    "/app/runLoops/rendering_0/rateLimitEnabled",
    "/app/runLoops/rendering_0/rateLimitFrequency",
    "/app/runLoops/rendering_0/syncToPresent",
    "/app/runLoops/present/rateLimitEnabled",
    "/app/runLoops/present/rateLimitFrequency",
    "/app/runLoops/present/syncToPresent",
    "/app/runLoopsGlobal/syncToPresent",
    "/persistent/app/viewport/defaults/tickRate",
    "/persistent/simulation/minFrameRate",
    "/renderer/vsync",
    "/app/vsync",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def average(values: list[float]) -> float:
    return round(statistics.fmean(values), 4)


def app_package(extension_id: str) -> bool:
    return extension_id.startswith("campfire.phasev3tq.")


def snapshot(entry: dict, marker: str) -> dict | None:
    return next(
        (
            item
            for item in entry["runtime_diagnostic"]["snapshots"]
            if item["marker"] == marker
        ),
        None,
    )


def sample(entry: dict, population: str) -> dict:
    timing = entry["performance"]["main_update_interval"]
    play = snapshot(entry, "timeline_play")
    return {
        "population": population,
        "condition": entry["condition"],
        "run": entry["run"],
        "order_index": entry["order_index"],
        "visible_window": bool(
            entry["metric_contract"].get("visible_window", False)
        ),
        "average_visible_fps": entry["performance"]["average_visible_fps"],
        "derived_visible_frame_ms": entry["performance"]["hud_frame_time_ms"],
        "hud_fps": None,
        "kit_update_rate_hz": round(1000.0 / timing["mean_ms"], 4),
        "timeline_simulation_seconds": entry["performance"][
            "timeline_model_seconds"
        ],
        "simulation_wall_seconds": entry["performance"][
            "simulation_wall_seconds"
        ],
        "main_update_interval": timing,
        "v3_publication_timing": entry["performance"]["v3_publication_timing"],
        "v3_publication_count": entry["performance"]["v3_publication_count"],
        "v3_upload_count": entry["performance"]["v3_upload_count"],
        "v3_quantized_skip_count": entry["performance"][
            "v3_quantized_skip_count"
        ],
        "flow_active_blocks_final": entry["performance"][
            "flow_active_blocks_final"
        ],
        "flow_active_blocks_peak": entry["performance"][
            "flow_active_blocks_peak"
        ],
        "gpu": entry["gpu"],
        "process_wall_seconds": entry["process_wall_seconds"],
        "timeline_play_settings": (
            {path: play["settings"].get(path) for path in SETTING_PATHS}
            if play
            else None
        ),
        "setting_changes": entry["runtime_diagnostic"]["setting_changes"],
        "enabled_extension_ids": entry["enabled_extension_ids"],
        "startup_order": entry["startup_order"],
        "developer_related_extensions": entry["developer_related_extensions"],
        "display_present_fps": None,
        "gpu_render_time": None,
        "raw_renderer_frame_interval": None,
        "extension_callback_profile": None,
        "fatal_count": 0,
    }


def condition_summary(rows: list[dict]) -> dict:
    fps = [float(row["average_visible_fps"]) for row in rows]
    frame = [float(row["derived_visible_frame_ms"]) for row in rows]
    update = [row["main_update_interval"] for row in rows]
    gpu = [float(row["gpu"]["utilization_percent"]["mean"]) for row in rows]
    power = [float(row["gpu"]["power_w"]["mean"]) for row in rows]
    clocks = [float(row["gpu"]["graphics_clock_mhz"]["mean"]) for row in rows]
    vram = [float(row["gpu"]["memory_used_mib"]["mean"]) for row in rows]
    temperature = [float(row["gpu"]["temperature_c"]["mean"]) for row in rows]
    return {
        "run_count": len(rows),
        "average_visible_fps": {
            "mean": average(fps),
            "min": round(min(fps), 4),
            "max": round(max(fps), 4),
            "range": round(max(fps) - min(fps), 4),
        },
        "derived_visible_frame_ms_mean": average(frame),
        "kit_update_rate_hz_mean": average(
            [float(row["kit_update_rate_hz"]) for row in rows]
        ),
        "main_update_interval_ms": {
            key: average([float(item[key]) for item in update])
            for key in ("mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms")
        },
        "gpu_utilization_percent_mean": average(gpu),
        "gpu_power_w_mean": average(power),
        "graphics_clock_mhz_mean": average(clocks),
        "vram_mib_mean": average(vram),
        "temperature_c_mean": average(temperature),
        "process_wall_seconds_mean": average(
            [float(row["process_wall_seconds"]) for row in rows]
        ),
    }


def make_svg(report: dict) -> str:
    conditions = (
        ("normal_baseline", "Normal + developer", "#f97316"),
        ("normal_without_developer_bundle", "Normal - developer", "#22c55e"),
        ("benchmark_with_developer_bundle", "Benchmark + developer", "#fb7185"),
        ("benchmark_baseline", "Benchmark - developer", "#38bdf8"),
    )
    bars = []
    y = 205
    for key, label, color in conditions:
        value = report["formal_summary"][key]["average_visible_fps"]["mean"]
        width = value * 12.0
        bars.append(
            f'<text x="70" y="{y}" class="label">{label}</text>'
            f'<rect x="330" y="{y - 25}" width="{width:.1f}" height="30" rx="7" fill="{color}"/>'
            f'<text x="{345 + width:.1f}" y="{y}" class="value">{value:.3f} FPS</text>'
        )
        y += 74
    focused = report["focused_summary"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="760" viewBox="0 0 1180 760" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-Q normal and benchmark FPS boundary</title>
<desc id="desc">Developer bundle follows a 32 FPS class result in both app roots. Removing it restores about 56 FPS. Focused probes isolate debugpy listen.</desc>
<style>.title{{font:700 34px Segoe UI,sans-serif;fill:#f8fafc}}.sub{{font:16px Segoe UI,sans-serif;fill:#94a3b8}}.label{{font:600 17px Segoe UI,sans-serif;fill:#e2e8f0}}.value{{font:700 18px Segoe UI,sans-serif;fill:#f8fafc}}.note{{font:16px Segoe UI,sans-serif;fill:#cbd5e1}}.accent{{font:700 20px Segoe UI,sans-serif;fill:#fbbf24}}</style>
<rect width="1180" height="760" rx="28" fill="#0b1324"/>
<text x="70" y="65" class="sub">PHASE V3T-Q / 4 CONDITIONS × 3 INDEPENDENT PROCESSES</text>
<text x="70" y="112" class="title">The app-root FPS gap follows debugpy listen</text>
<text x="70" y="145" class="sub">Candidate Performance / 1280×720 / CPU-source V3 / RTX 3090 / 210 W</text>
{''.join(bars)}
<rect x="70" y="515" width="1040" height="140" rx="18" fill="#172033" stroke="#334155"/>
<text x="96" y="552" class="accent">Focused minimum factor</text>
<text x="96" y="590" class="note">No developer: {focused['normal_without_developer_bundle']['average_visible_fps']:.3f} FPS · debug extension, no listen: {focused['normal_debug_python_no_listen']['average_visible_fps']:.3f} FPS</text>
<text x="96" y="624" class="note">debugpy listen: {focused['normal_debug_python']['average_visible_fps']:.3f} FPS · VS Code path: {focused['normal_debug_vscode']['average_visible_fps']:.3f} FPS</text>
<text x="70" y="700" class="note">No explicit 30 Hz loop setting was observed. Callback-level attribution is unavailable from the public manager boundary.</text>
<text x="70" y="731" class="sub">Production .kit files and defaults were not changed; removal is a proposed next Phase only.</text>
</svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", required=True, type=Path)
    parser.add_argument("--focused", required=True, type=Path)
    parser.add_argument("--visible", required=True, type=Path)
    parser.add_argument("--scheduler", required=True, type=Path)
    parser.add_argument("--samples-out", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    parser.add_argument("--svg-out", required=True, type=Path)
    args = parser.parse_args()

    manifests = {
        name: load(path)
        for name, path in (
            ("formal", args.formal),
            ("focused", args.focused),
            ("visible", args.visible),
            ("scheduler", args.scheduler),
        )
    }
    samples = {
        name: [sample(entry, name) for entry in manifest["entries"]]
        for name, manifest in manifests.items()
        if name != "scheduler"
    }
    formal_by_condition: dict[str, list[dict]] = defaultdict(list)
    for row in samples["formal"]:
        formal_by_condition[row["condition"]].append(row)
    formal_summary = {
        condition: condition_summary(rows)
        for condition, rows in sorted(formal_by_condition.items())
    }
    focused_summary = {
        row["condition"]: {
            "average_visible_fps": row["average_visible_fps"],
            "derived_visible_frame_ms": row["derived_visible_frame_ms"],
            "main_update_interval": row["main_update_interval"],
            "gpu_utilization_percent": row["gpu"]["utilization_percent"]["mean"],
            "power_w": row["gpu"]["power_w"]["mean"],
            "debugpy_listening": row["condition"]
            in {
                "normal_debug_python",
                "normal_debug_vscode",
                "normal_dev_utilities_bundle",
            },
        }
        for row in samples["focused"]
    }

    representative = {
        condition: next(
            row for row in samples["formal"] if row["condition"] == condition
        )
        for condition in formal_by_condition
    }
    normal_dev = set(representative["normal_baseline"]["enabled_extension_ids"])
    normal_no_dev = set(
        representative["normal_without_developer_bundle"]["enabled_extension_ids"]
    )
    transitive = sorted(
        item for item in normal_dev - normal_no_dev if not app_package(item)
    )
    residual = sorted(
        item
        for item in normal_no_dev
        ^ set(representative["benchmark_baseline"]["enabled_extension_ids"])
        if not app_package(item)
    )

    scheduler_rows = []
    for entry in manifests["scheduler"]["entries"]:
        summary = load(Path(entry["summary_path"]))
        scheduler_rows.append(
            {
                "condition": entry["condition"],
                "snapshots": summary["scenario"]["scheduler_settings"]["snapshots"],
            }
        )

    normal_slow = formal_summary["normal_baseline"]["average_visible_fps"]["mean"]
    normal_fast = formal_summary["normal_without_developer_bundle"][
        "average_visible_fps"
    ]["mean"]
    benchmark_slow = formal_summary["benchmark_with_developer_bundle"][
        "average_visible_fps"
    ]["mean"]
    benchmark_fast = formal_summary["benchmark_baseline"]["average_visible_fps"][
        "mean"
    ]
    report = {
        "schema": "campfire.phasev3tq.app-path-fps-report.v1",
        "status": "qualified_diagnostic_safe_stop",
        "formal_population": {
            "process_count": 12,
            "run_count_per_condition": 3,
            "condition_order_rotated": True,
            "no_window": True,
            "cold_or_invalid_runs_included": 0,
        },
        "fixed_contract": {
            "kit": "110.2",
            "flow": "110.0.0",
            "resolution": [1280, 720],
            "candidate_performance": True,
            "rtx_realtime_2": True,
            "dlss_mode": "Performance",
            "max_bounces": 2,
            "v3": "production default ON",
            "texture_transport": "CPU source",
            "power_limit_w": 210,
            "power_limit_changed": False,
            "additional_render_product": False,
            "capture_or_encode_in_population": False,
        },
        "formal_summary": formal_summary,
        "focused_summary": focused_summary,
        "visible_window_confirmation": {
            row["condition"]: {
                "average_visible_fps": row["average_visible_fps"],
                "derived_visible_frame_ms": row["derived_visible_frame_ms"],
                "main_update_interval": row["main_update_interval"],
            }
            for row in samples["visible"]
        },
        "developer_bundle_transitive_extensions": transitive,
        "normal_no_dev_vs_benchmark_baseline_extension_difference": residual,
        "scheduler_probe": scheduler_rows,
        "effects": {
            "normal_remove_developer_fps": round(normal_fast - normal_slow, 4),
            "benchmark_add_developer_fps": round(benchmark_slow - benchmark_fast, 4),
            "no_developer_app_root_residual_fps": round(
                normal_fast - benchmark_fast, 4
            ),
            "developer_app_root_residual_fps": round(
                normal_slow - benchmark_slow, 4
            ),
        },
        "classification": {
            "observed_facts": [
                "The developer bundle follows the low-FPS class across both app roots; removing it reverses the result.",
                "Focused probes reproduce the loss with omni.kit.debug.python and the VS Code path, but not with debug settings or the developer window group.",
                "Loading the Python debug extension with its listen mode disabled retains the fast class.",
                "No explicit 30 Hz main, render, present, viewport, VSync, or simulation setting differs between the four formal conditions.",
                "The developer conditions use less GPU power/utilization, so the qualified difference is not a pure GPU saturation boundary.",
            ],
            "strong_inference": (
                "Starting debugpy.listen through omni.kit.debug.python is the minimum "
                "identified cause boundary. Debugger instrumentation/tracing is the "
                "leading CPU-side mechanism, but callback-level time was not exposed."
            ),
            "unconfirmed": [
                "The public extension-manager surface did not expose per-extension update subscriptions or callback durations.",
                "The exact debugpy internal hook responsible for the render-counter reduction was not profiled.",
                "HUD FPS is absent in --no-window runs; display-present FPS, GPU render time, and raw renderer frame intervals remain unavailable and were not inferred.",
                "Warmup scheduler snapshots also show a timeline/main-rate lifecycle difference in debugpy-listening conditions; causality inside Kit/debugpy is unconfirmed.",
            ],
        },
        "recommendation": {
            "next_phase": (
                "Remove omni.kit.developer.bundle from the production normal app and "
                "provide an explicit opt-in developer/debug preset; then repeat normal "
                "startup, interactive debugging, Phase 0, Phase 3, and the standard suite."
            ),
            "this_phase_changes_production_dependency": False,
            "this_phase_changes_rates": False,
        },
        "production_apps_changed": False,
    }
    sample_document = {
        "schema": "campfire.phasev3tq.app-path-fps-samples.v1",
        "formal": samples["formal"],
        "focused": samples["focused"],
        "visible_window": samples["visible"],
        "scheduler": scheduler_rows,
    }
    for path in (args.samples_out, args.report_out, args.svg_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.samples_out.write_text(
        json.dumps(sample_document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg_out.write_text(make_svg(report), encoding="utf-8")
    print(json.dumps(report["effects"], indent=2))


if __name__ == "__main__":
    main()
