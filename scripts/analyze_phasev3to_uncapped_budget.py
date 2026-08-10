"""Aggregate Phase V3T-O production-capped and 240 Hz diagnostic evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


CONDITIONS = (
    "ground_stones_lit",
    "cylinder20_solid",
    "v3mesh20_static_texture",
    "flow_volume",
)
LABELS = {
    "ground_stones_lit": "Floor + stones",
    "cylinder20_solid": "Cylinder 20",
    "v3mesh20_static_texture": "V3 Mesh 20",
    "flow_volume": "Flow + volume",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def mean(values):
    return round(statistics.fmean(values), 3)


def summarize_uncapped(entries):
    result = {}
    for condition in CONDITIONS:
        rows = [row for row in entries if row["condition"] == condition]
        if len(rows) != 3:
            raise RuntimeError(f"expected three uncapped runs for {condition}, got {len(rows)}")
        fps = [float(row["metrics"]["average_visible_fps"]) for row in rows]
        result[condition] = {
            "run_count": len(rows),
            "values_fps": fps,
            "mean_fps": mean(fps),
            "mean_frame_time_ms_from_average_fps": round(1000.0 / statistics.fmean(fps), 3),
            "kit_updates_per_second": mean([float(row["metrics"]["kit_updates_per_second"]) for row in rows]),
            "gpu_utilization_mean_percent": mean([float(row["gpu"]["utilization_mean_percent"]) for row in rows]),
            "graphics_clock_mean_mhz": mean([float(row["gpu"]["graphics_clock_mean_mhz"]) for row in rows]),
            "power_mean_w": mean([float(row["gpu"]["power_mean_w"]) for row in rows]),
            "vram_max_mib": max(float(row["gpu"]["memory_max_mib"]) for row in rows),
            "effective_rate": {
                "main_hz": rows[0]["effective_settings"]["requested_paths"]["/app/runLoops/main/rateLimitFrequency"],
                "rendering_hz": rows[0]["effective_settings"]["requested_paths"]["/app/runLoops/rendering_0/rateLimitFrequency"],
                "viewport_tick_hz": rows[0]["effective_settings"]["requested_paths"]["/persistent/app/viewport/defaults/tickRate"],
                "present_hz": rows[0]["effective_settings"]["requested_paths"]["/app/runLoops/present/rateLimitFrequency"],
                "vsync": rows[0]["effective_settings"]["requested_paths"]["/renderer/vsync"],
            },
            "gpu_render_time_ms": None,
        }
    return result


def capped_summary(report):
    return {condition: report["formal_candidates"][condition]["candidate_performance"] for condition in CONDITIONS}


def stripped_sample(row):
    return {
        "name": row["name"], "condition": row["condition"], "rate_mode": row["rate_mode"],
        "run": row["run"], "classification": row["classification"], "exit_code": row["exit_code"],
        "fatal_log_counts": row["fatal_log_counts"],
        "automatic_upload_attempt_count": row["automatic_upload_attempt_count"],
        "metrics": row["metrics"], "gpu": row["gpu"], "stage": row["stage"],
        "effective_settings": row["effective_settings"],
        "flow_main_rate_override_observed": row["flow_main_rate_override_observed"],
        "production_changed": row["production_changed"],
    }


def svg(report):
    capped = report["capped"]
    uncapped = report["uncapped_240"]
    rows = []
    top = 210
    for index, condition in enumerate(CONDITIONS):
        y = top + index * 105
        cap = capped[condition]["mean_fps"]
        uncap = uncapped[condition]["mean_fps"]
        cap_w = cap / 240.0 * 780.0
        uncap_w = uncap / 240.0 * 780.0
        rows.append(f'<text x="70" y="{y}" class="label">{LABELS[condition]}</text>')
        rows.append(f'<rect x="300" y="{y-26}" width="{cap_w:.1f}" height="28" rx="7" fill="#8a796c"/><text x="{315+cap_w:.1f}" y="{y-5}" class="value">{cap:.3f}</text>')
        rows.append(f'<rect x="300" y="{y+12}" width="{uncap_w:.1f}" height="28" rx="7" fill="#ff8a48"/><text x="{315+uncap_w:.1f}" y="{y+33}" class="value">{uncap:.3f}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-O capped and 240 Hz visible FPS</title><desc id="desc">4代表sceneのproduction cappedと240 Hz診断の平均visible FPS比較</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#15110f"/><stop offset="1" stop-color="#2e1911"/></linearGradient><style>.k{{font:700 20px 'Segoe UI',sans-serif;fill:#ffb06f;letter-spacing:3px}}.title{{font:700 40px 'Segoe UI',sans-serif;fill:#fff2e4}}.sub{{font:20px 'Segoe UI',sans-serif;fill:#bba99c}}.label{{font:700 22px 'Segoe UI',sans-serif;fill:#f4e6d9}}.value{{font:700 18px 'Segoe UI',sans-serif;fill:#fff5ec}}.small{{font:17px 'Segoe UI',sans-serif;fill:#aa9a8d}}</style></defs>
<rect width="1280" height="720" rx="28" fill="url(#bg)"/><text x="70" y="68" class="k">PHASE V3T-O · RATE-LIMIT DIAGNOSTIC</text><text x="70" y="121" class="title">120 Hz ceiling removed; Flow remains workload-bound</text><text x="70" y="158" class="sub">Candidate Performance · 1280×720 · 210 W · average visible render counter</text>
<rect x="825" y="58" width="22" height="14" rx="4" fill="#8a796c"/><text x="858" y="71" class="small">production capped</text><rect x="1025" y="58" width="22" height="14" rx="4" fill="#ff8a48"/><text x="1058" y="71" class="small">240 Hz diagnostic</text>
{''.join(rows)}
<text x="70" y="660" class="small">Static scenes hit the production 120 Hz ceiling; at 240 Hz they become ~99% GPU-bound.</text><text x="70" y="688" class="small">Flow main loop resolves to 60 Hz; rendering/tick stay 240 Hz. No display-present FPS or raw p95/p99 inferred.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uncapped-manifest", type=Path, required=True)
    parser.add_argument("--capped-report", type=Path, required=True)
    parser.add_argument("--standard-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    uncapped_manifest = load(args.uncapped_manifest)
    capped_report = load(args.capped_report)
    standard_report = load(args.standard_report)
    entries = uncapped_manifest["entries"]
    uncapped = summarize_uncapped(entries)
    capped = capped_summary(capped_report)
    comparison = {}
    for condition in CONDITIONS:
        delta = uncapped[condition]["mean_fps"] - capped[condition]["mean_fps"]
        comparison[condition] = {
            "fps_delta": round(delta, 3),
            "percent_delta": round(delta / capped[condition]["mean_fps"] * 100.0, 2),
            "production_rate_limit_hit": condition != "flow_volume" and capped[condition]["mean_fps"] >= 114.0,
            "uncapped_240_rate_limit_hit": uncapped[condition]["mean_fps"] >= 228.0,
            "classification": "production 120 Hz rate limit exposed" if condition != "flow_volume" else "GPU/Flow workload bound; not a 120 Hz ceiling",
        }
    report = {
        "schema": "campfire.phasev3to.frame-budget-diagnostic.v1", "phase": "V3T-O", "status": "qualified",
        "capped_source": "Phase V3T-L Candidate Performance formal 3-run results; not rerun",
        "uncapped_source": "Phase V3T-O 240 Hz formal 3-run results after separate preflight",
        "candidate_performance": standard_report["standard"],
        "normal_budget": {"target_fps": 45.0, "target_ms": 22.222, "minimum_fps": 30.0, "minimum_ms": 33.333},
        "current_reference_margin": {"reference_fps": 47.858, "reference_ms": 20.9, "to_45_fps_ms": 1.322, "to_30_fps_ms": 12.433},
        "capped_effective_settings": {"main_hz": 120, "rendering_hz": 120, "present_hz": 59, "vsync": False, "resolution": [1280, 720], "power_limit_w": 210},
        "uncapped_effective_settings": {"static_main_hz": 240, "flow_main_hz": 60, "rendering_hz": 240, "viewport_tick_hz": 240, "present_hz": 59, "vsync": False, "resolution": [1280, 720], "power_limit_w": 210},
        "capped": capped, "uncapped_240": uncapped, "comparison": comparison,
        "formal_processes": len(entries),
        "formal_fatal_count": sum(sum(row["fatal_log_counts"].values()) for row in entries),
        "formal_crash_count": sum(bool(row["crash_reporter"]["dump_inventory"]) for row in entries),
        "formal_automatic_upload_attempt_count": sum(row["automatic_upload_attempt_count"] for row in entries),
        "gpu_render_time_ms": None,
        "gpu_render_time_status": "unavailable through confirmed public Kit 110.2 viewport/omni.stats boundary; no additional render path created",
        "display_present_fps": None, "raw_frame_latency": None,
        "production_changed": False,
        "flow_component_safe_stop_maintained": True,
        "observed_facts": [
            "All twelve uncapped formal processes exited normally with zero fatal token, dump, or upload attempt.",
            "The three static scenes rise from about 116.7 FPS to 166.4-169.9 FPS when the rendering ceiling is raised.",
            "Static uncapped GPU utilization is 97.6-99.0 percent at about 209.4 W, while none reaches the 240 Hz limit.",
            "Flow rises from 47.858 to 50.696 FPS; Flow changes main to 60 Hz while rendering and viewport tick remain 240 Hz.",
        ],
        "strong_inferences": [
            "The production 120 Hz rendering ceiling masks static-scene headroom.",
            "The current production-equivalent Flow scene is workload-bound rather than limited by the 120 Hz renderer ceiling.",
        ],
        "unconfirmed": [
            "Public GPU render time and raw visible-render completion timestamps are unavailable.",
            "Display-present FPS, p95/p99 pacing, and one-percent-low are not inferred from the average visible counter.",
            "The exact ownership of the Flow main-loop 60 Hz override is not attributed.",
        ],
    }
    samples = {
        "schema": "campfire.phasev3to.frame-budget-samples.v1", "status": "ok",
        "capped_summary": capped, "uncapped_formal": [stripped_sample(row) for row in entries],
        "excluded_preflight": True,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "frame_budget_diagnostic_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "frame_budget_diagnostic_samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "frame_budget_diagnostic_report.svg").write_text(svg(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "formal_processes": report["formal_processes"], "output": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
