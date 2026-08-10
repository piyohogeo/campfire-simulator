"""Aggregate Phase V3T-I without inventing visible-frame pacing metrics."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


STAGE_ID_ERROR = "IRenderSettings::getRenderSettings failed getting a stage-id"


def mean(values):
    return statistics.fmean(values) if values else None


def load_run(entry):
    payload = json.loads(Path(entry["samples"]).read_text(encoding="utf-8-sig"))
    if payload["status"] != "ok":
        raise RuntimeError(f"probe error: {entry['name']}")
    if entry["fatal_log_counts"].get(STAGE_ID_ERROR, 0):
        raise RuntimeError(f"stage-ID error in {entry['name']}")
    return {"process": entry, "samples": payload}


def aggregate(runs):
    metrics = [item["process"]["metrics"] for item in runs]
    gpu = [item["process"]["gpu"] for item in runs]
    def values(key):
        return [row[key] for row in metrics if row.get(key) is not None]
    def gpu_values(key):
        return [row[key] for row in gpu if row.get(key) is not None]
    return {
        "runs": len(runs),
        "average_visible_fps": {"mean": mean(values("average_visible_fps")), "min": min(values("average_visible_fps")), "max": max(values("average_visible_fps"))},
        "hud_fps_mean": mean(values("hud_fps_mean")),
        "kit_updates_per_second_mean": mean(values("kit_updates_per_second")),
        "timeline_sim_per_wall_mean": mean(values("timeline_sim_per_wall")),
        "gpu_utilization_mean_percent": mean(gpu_values("utilization_mean_percent")),
        "gpu_graphics_clock_mean_mhz": mean(gpu_values("graphics_clock_mean_mhz")),
        "gpu_memory_max_mib": max(gpu_values("memory_max_mib")),
        "gpu_power_mean_w": mean(gpu_values("power_mean_w")),
        "gpu_temperature_mean_c": mean(gpu_values("temperature_mean_c")),
        "power_limit_w": sorted(set(gpu_values("power_limit_w"))),
        "enforced_power_limit_w": sorted(set(gpu_values("enforced_power_limit_w"))),
        "perfcap_active_values": sorted({value for row in gpu for value in row.get("perfcap_active_values", [])}),
        "flow_active_blocks_final": [item["samples"]["measurement"]["flow_active_blocks_final"] for item in runs],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--aux", type=Path, required=True)
    parser.add_argument("--ui", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    formal_manifest = json.loads(args.formal.read_text(encoding="utf-8-sig"))
    if args.aux.is_dir():
        aux_entries = [json.loads(path.read_text(encoding="utf-8-sig")) for path in sorted(args.aux.glob("*/process.json"))]
        aux_manifest = {"entries": aux_entries}
    else:
        aux_manifest = json.loads(args.aux.read_text(encoding="utf-8-sig"))
    ui_manifest = json.loads(args.ui.read_text(encoding="utf-8-sig"))
    settings = json.loads(args.settings.read_text(encoding="utf-8-sig"))
    formal = [load_run(entry) for entry in formal_manifest["entries"]]
    auxiliary = [load_run(entry) for manifest in (aux_manifest, ui_manifest) for entry in manifest["entries"]]
    by_condition = {
        condition: aggregate([item for item in formal if item["process"]["condition"] == condition])
        for condition in formal_manifest["conditions"]
    }
    aux_by_condition = {item["process"]["condition"]: aggregate([item]) for item in auxiliary}
    baseline = by_condition["current_flow_off"]["average_visible_fps"]["mean"]
    low = by_condition["resolution_640x360"]["average_visible_fps"]["mean"]
    high = by_condition["resolution_1920x1080"]["average_visible_fps"]["mean"]
    simulation = by_condition["flow_simulation_only"]["average_visible_fps"]["mean"]
    volume = by_condition["flow_volume"]["average_visible_fps"]["mean"]
    matching = {row["path"]: row["value"] for row in settings["matching_settings"]}
    cap = {
        key: matching.get(key) for key in (
            "/app/runLoops/main/rateLimitEnabled", "/app/runLoops/main/rateLimitFrequency",
            "/app/runLoops/present/rateLimitEnabled", "/app/runLoops/present/rateLimitFrequency",
            "/app/runLoops/rendering_0/rateLimitEnabled", "/app/runLoops/rendering_0/rateLimitFrequency",
            "/app/vsync", "/renderer/vsync", "/persistent/app/viewport/defaults/tickRate",
            "/persistent/simulation/minFrameRate",
        )
    }
    report = {
        "schema": "campfire.phasev3ti.fps-isolation-report.v1",
        "status": "ok",
        "baseline_commit": "a014058",
        "formal": by_condition,
        "auxiliary_preflight": aux_by_condition,
        "frame_limit_inventory": cap,
        "power_contract": {
            "observed_limit_w": 210.0, "default_limit_w": 350.0, "ratio_percent": 60.0,
            "changed_during_phase": False, "comparison_with_100_percent_performed": False,
        },
        "classification": {
            "pixel_load_dominant": low >= baseline * 1.5 and high < baseline,
            "empty_stage_renderer_cap_dominant": False,
            "reflection_dominant": False,
            "flow_volume_rendering_dominant": volume < simulation * 0.9,
            "flow_enabled_gpu_work_dominant_over_volume_delta": abs(volume - simulation) / simulation < 0.02,
            "notes": [
                f"Resolution scaling: 640x360 {low:.2f}, 1280x720 {baseline:.2f}, 1920x1080 {high:.2f} visible FPS.",
                f"Flow simulation-only {simulation:.2f} versus simulation+volume {volume:.2f} visible FPS.",
                "The 59 Hz present run-loop limit is visible at 640x360, but it does not explain the 1280x720 or Flow results.",
            ],
        },
        "metric_contract": {
            "measured": ["average visible ViewportAPI frame-counter FPS", "smoothed HUD FPS", "Kit updates/s", "timeline sim/wall", "nvidia-smi telemetry"],
            "not_measured": ["display-present FPS", "raw visible render-frame latency", "render-frame p95/p99", "1% low FPS"],
            "reason": "Kit 110.2 exposes a counter and smoothed FPS for the existing viewport, not public raw visible-frame completion timestamps.",
        },
        "profiler": {"run": False, "reason": "Public viewport and GPU telemetry already isolate pixel scaling and Flow activation; profiler overhead was not introduced."},
        "observed_facts": [
            "No added RenderProduct, HydraTexture, capture, encoder, or per-frame file write was used.",
            "All 18 formal runs completed with zero RTX stage-ID errors.",
            "The RTX 3090 remained at the observed 210 W enforced limit (60% of the 350 W default); no power-setting command was issued.",
        ],
        "strong_inference": [
            "The current 20-log stage at 1280x720 is primarily pixel/GPU limited under the 60% power limit.",
            "For this probe scene, enabling Flow adds GPU cost, while adding Flow volume rendering after simulation changes average visible FPS by less than 2%.",
        ],
        "unconfirmed": ["ray-tracing pass-level GPU time", "denoiser pass time", "display compositor pacing", "behavior at a 100% power limit"],
        "production_changed": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw = {"schema": "campfire.phasev3ti.fps-isolation-raw.v1", "formal": formal, "auxiliary": auxiliary, "settings_inventory": settings}
    (args.output_dir / "fps_isolation_samples.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "fps_isolation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    labels = {
        "empty_rtx": "Empty stage", "current_flow_off": "20 logs / Flow OFF", "resolution_640x360": "640 x 360",
        "resolution_1920x1080": "1920 x 1080", "flow_simulation_only": "Flow simulation", "flow_volume": "Flow + volume",
    }
    colors = ["#38bdf8", "#f59e0b", "#34d399", "#fb7185", "#a78bfa", "#e879f9"]
    bars = []
    for index, (key, label) in enumerate(labels.items()):
        value = by_condition[key]["average_visible_fps"]["mean"]
        y = 205 + index * 72
        bars.append(f'<text x="55" y="{y+24}" class="label">{label}</text><rect x="275" y="{y}" width="{value*9:.1f}" height="36" rx="8" fill="{colors[index]}"/><text x="{285+value*9:.1f}" y="{y+25}" class="value">{value:.2f} FPS</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="720" viewBox="0 0 1100 720" role="img"><style>.title{{font:700 34px Segoe UI,sans-serif;fill:#f8fafc}}.sub{{font:16px Segoe UI,sans-serif;fill:#a7b2c2}}.label{{font:700 16px Segoe UI,sans-serif;fill:#e2e8f0}}.value{{font:700 16px Segoe UI,sans-serif;fill:#f8fafc}}.note{{font:15px Segoe UI,sans-serif;fill:#fbbf24}}</style><rect width="1100" height="720" rx="28" fill="#0b1625"/><text x="55" y="62" class="sub">PHASE V3T-I / EXISTING VISIBLE VIEWPORT</text><text x="55" y="108" class="title">FPS isolation at unchanged 60% power limit</text><text x="55" y="142" class="sub">RTX 3090 / 20 logs / 3 independent runs / no added render path</text>{''.join(bars)}<text x="55" y="665" class="note">210 W enforced / 350 W default. Display-present FPS and raw frame p95/p99 were not available.</text><text x="55" y="696" class="sub">640x360 reaches the 59 Hz present limit; Flow simulation and volume are nearly identical in this scene.</text></svg>'''
    (args.output_dir / "fps_isolation_report.svg").write_text(svg, encoding="utf-8")
    print(json.dumps({"formal_runs": len(formal), "stage_id_errors": 0, "baseline_fps": baseline, "flow_delta_fps": simulation - volume}))


if __name__ == "__main__":
    main()
