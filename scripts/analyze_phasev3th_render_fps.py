"""Aggregate Phase V3T-H visible-viewport FPS observations without fabricating frame pacing."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


FATAL_LOG_TOKENS = (
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)",
    "CUDA_ERROR_ILLEGAL_ADDRESS",
    "device lost",
    "invalid pointer",
    "Invoked with: <omni.ui._ui.ImageProvider",
)


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def stats(values):
    if not values:
        return {key: None for key in ("count", "p50", "mean", "p95", "p99", "max")}
    return {
        "count": len(values),
        "p50": percentile(values, 0.50),
        "mean": statistics.fmean(values),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
    }


def analyse_run(entry, payload):
    measurement = payload["measurement"]
    wall = measurement["wall_seconds"]
    initial = measurement["initial_frame_info"]
    final = measurement["final_frame_info"]
    frame_delta = final["frame_number"] - initial["frame_number"]
    swh_delta = final["swh_frame_number"] - initial["swh_frame_number"]
    fps_values = [value for value in measurement["hud_fps_values"] if value > 0.0]
    read_times = measurement["read_timestamps_ns"]
    kit_intervals = [(b - a) / 1e6 for a, b in zip(read_times, read_times[1:])]
    observed_frames = measurement["frame_numbers"]
    observed_deltas = [b - a for a, b in zip(observed_frames, observed_frames[1:])]
    publication_profiles = measurement["publication_profiles"]
    log_text = Path(entry["kit_log"]).read_text(encoding="utf-8-sig", errors="replace")
    fatal_counts = {token: log_text.count(token) for token in FATAL_LOG_TOKENS}
    return {
        "name": entry["name"],
        "group": entry["group"],
        "condition": entry["condition"],
        "run": entry["run"],
        "read_mode": entry["read_mode"],
        "wall_seconds": wall,
        "visible_frame_counter_start": initial["frame_number"],
        "visible_frame_counter_end": final["frame_number"],
        "visible_frame_counter_delta": frame_delta,
        "average_visible_render_fps": frame_delta / wall if wall > 0.0 else 0.0,
        "swh_frame_counter_delta": swh_delta,
        "hud_overlay_fps_readings": {
            "count": len(fps_values),
            "mean": statistics.fmean(fps_values) if fps_values else None,
            "min": min(fps_values) if fps_values else None,
            "max": max(fps_values) if fps_values else None,
        },
        "hud_overlay_frame_time_mean_ms": statistics.fmean(1000.0 / value for value in fps_values) if fps_values else None,
        "kit_update_count": measurement["kit_update_count"],
        "kit_updates_per_second": measurement["kit_update_count"] / wall if wall > 0.0 else 0.0,
        "kit_update_interval_ms": stats(kit_intervals),
        "frame_counter_polling": {
            "duplicate_poll_count": sum(delta == 0 for delta in observed_deltas),
            "multi_frame_gap_count": sum(delta > 1 for delta in observed_deltas),
            "largest_observed_gap": max(observed_deltas) if observed_deltas else None,
            "note": "Polling gaps are not raw render intervals and are not used for frame pacing percentiles.",
        },
        "timeline_sim_wall_ratio": (measurement["timeline_seconds_end"] - measurement["timeline_seconds_start"]) / wall,
        "v3_publication_count": len(publication_profiles),
        "cpu_provider_setter_ms": stats([row["cpu_provider_setter_ms"] for row in publication_profiles]),
        "publication_total_ms": stats([row["total_ms"] for row in publication_profiles]),
        "flow_active_blocks_final": measurement["flow_active_blocks_final"],
        "read_overflow": measurement["read_overflow"],
        "fatal_log_counts": fatal_counts,
        "fatal_log_count": sum(fatal_counts.values()),
        "gpu": entry.get("gpu"),
    }


def aggregate(rows):
    total_wall = sum(row["wall_seconds"] for row in rows)
    total_frames = sum(row["visible_frame_counter_delta"] for row in rows)
    return {
        "runs": len(rows),
        "wall_seconds": total_wall,
        "visible_frame_counter_delta": total_frames,
        "average_visible_render_fps_weighted": total_frames / total_wall if total_wall > 0.0 else 0.0,
        "average_visible_render_fps_per_run": stats([row["average_visible_render_fps"] for row in rows]),
        "hud_overlay_fps_mean_per_run": stats([row["hud_overlay_fps_readings"]["mean"] for row in rows if row["hud_overlay_fps_readings"]["mean"] is not None]),
        "hud_overlay_frame_time_mean_ms_per_run": stats([row["hud_overlay_frame_time_mean_ms"] for row in rows if row["hud_overlay_frame_time_mean_ms"] is not None]),
        "kit_updates_per_second_per_run": stats([row["kit_updates_per_second"] for row in rows]),
        "kit_update_interval_p95_ms_per_run": stats([row["kit_update_interval_ms"]["p95"] for row in rows if row["kit_update_interval_ms"]["p95"] is not None]),
        "timeline_sim_wall_ratio": stats([row["timeline_sim_wall_ratio"] for row in rows]),
        "v3_publications": sum(row["v3_publication_count"] for row in rows),
        "cpu_provider_setter_p95_ms_per_run": stats([row["cpu_provider_setter_ms"]["p95"] for row in rows if row["cpu_provider_setter_ms"]["p95"] is not None]),
        "publication_total_p95_ms_per_run": stats([row["publication_total_ms"]["p95"] for row in rows if row["publication_total_ms"]["p95"] is not None]),
        "active_blocks_final": stats([row["flow_active_blocks_final"] for row in rows]),
        "fatal_log_count": sum(row["fatal_log_count"] for row in rows),
        "read_overflow": sum(row["read_overflow"] for row in rows),
        "gpu_util_mean_percent": stats([row["gpu"]["util_mean"] for row in rows if row.get("gpu") and row["gpu"].get("util_mean") is not None]),
        "gpu_memory_max_mib": stats([row["gpu"]["memory_max_mib"] for row in rows if row.get("gpu") and row["gpu"].get("memory_max_mib") is not None]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    raw = []
    analysed = []
    for entry in manifest["entries"]:
        payload = json.loads(Path(entry["samples"]).read_text(encoding="utf-8-sig"))
        row = analyse_run(entry, payload)
        raw.append({"process": entry, "samples": payload})
        analysed.append(row)
    formal = [row for row in analysed if row["group"] == "formal"]
    invalid = [row["name"] for row in formal if row["fatal_log_count"] or row["read_overflow"] or row["visible_frame_counter_delta"] <= 0]
    if invalid:
        raise RuntimeError(f"invalid formal visible-viewport run(s): {', '.join(invalid)}")
    condition_order = manifest["conditions"]
    conditions = {name: aggregate([row for row in formal if row["condition"] == name]) for name in condition_order}
    overhead = []
    for run in range(1, manifest["runs"] + 1):
        pairs = [row for row in analysed if row["name"].startswith("overhead_") and row["run"] == run]
        if not pairs:
            continue
        on = next(row for row in pairs if row["read_mode"] == "on")
        off = next(row for row in pairs if row["read_mode"] == "off")
        overhead.append({
            "run": run,
            "order": [row["read_mode"] for row in pairs],
            "read_on_updates_per_second": on["kit_updates_per_second"],
            "read_off_updates_per_second": off["kit_updates_per_second"],
            "delta_updates_per_second": on["kit_updates_per_second"] - off["kit_updates_per_second"],
        })
    report = {
        "schema": "campfire.phasev3th.visible-viewport-report.v2",
        "status": "ok",
        "metric_name": "average visible-viewport render FPS",
        "metric_method": "ViewportAPI.frame_info frame_number endpoint delta divided by wall time; no additional render product",
        "hud_overlay_metric": "mean of the public ViewportAPI.fps values used by the upper-right HUD",
        "not_measured": ["display-present FPS", "raw visible-frame completion timestamps", "render frame p50/p95/p99/max", "1% low FPS", "publication versus non-publication render-frame intervals", "16.67/33.33/50/100 ms render-frame threshold counts"],
        "why_not_measured": "Kit 110.2 exposes the visible viewport frame counter and a smoothed HUD FPS value, but no public raw completion timestamp/event mapping for that viewport. Poll timestamps are Kit-update observation times, not render completion times.",
        "omni_stats_inventory": manifest["stats_inventory"],
        "conditions": conditions,
        "runs": formal,
        "viewport_read_overhead": {"pairs": overhead, "update_rate_delta": stats([row["delta_updates_per_second"] for row in overhead])},
        "gpu_ring3_condition": {"measured": False, "reason": manifest["gpu_skip_reason"]},
        "separate_prior_metrics": ["next_update wall", "next_viewport_frame_async requested latency", "publication-to-next-RTX", "unique captured frame count"],
        "production_changed": False,
        "observed_facts": [
            "All public omni.stats scopes and nested nodes were enumerated before the formal run; none matched the visible FPS HUD source.",
            "The bundled ViewportFPS HUD reads public ViewportAPI.fps directly and derives its displayed frame time as 1000/FPS.",
            "No HydraTexture, RenderProduct, PNG/video capture, profiler, or per-frame file write was added to the measured population.",
        ],
        "strong_inference": "Condition deltas bound average visible render throughput and HUD-level responsiveness, not display-present pacing.",
        "unconfirmed": ["display compositor/present timing", "raw visible render-completion intervals", "renderer-internal scheduling and GPU fences"],
    }
    base = args.manifest.parent
    (base / "render_fps_samples.json").write_text(json.dumps({"schema": "campfire.phasev3th.raw.v2", "runs": raw}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (base / "render_fps_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    colors = {"flow_off_v3_off": "#38bdf8", "flow_on_v3_off": "#f59e0b", "flow_on_v3_cpu": "#ef4444"}
    labels = {"flow_off_v3_off": "Flow OFF / V3 OFF", "flow_on_v3_off": "Flow ON / V3 OFF", "flow_on_v3_cpu": "Flow ON / V3 CPU"}
    rows = []
    for index, key in enumerate(condition_order):
        row = conditions[key]
        fps = row["average_visible_render_fps_weighted"]
        hud = row["hud_overlay_fps_mean_per_run"]["mean"]
        y = 225 + index * 125
        rows.append(f'<text x="72" y="{y}" class="label">{labels[key]}</text><text x="72" y="{y+34}" class="fps">{fps:.2f} FPS</text><rect x="365" y="{y-27}" width="{min(650, fps*10):.1f}" height="44" rx="10" fill="{colors[key]}"/><text x="1035" y="{y+4}" class="value">HUD mean {hud:.2f} FPS</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="690" viewBox="0 0 1200 690" role="img"><style>.k{{font:700 17px Segoe UI,sans-serif;fill:#7dd3fc;letter-spacing:2px}}.title{{font:700 36px Segoe UI,sans-serif;fill:#f8fafc}}.sub{{font:16px Segoe UI,sans-serif;fill:#a7b2c2}}.label{{font:700 17px Segoe UI,sans-serif;fill:#f8fafc}}.fps{{font:700 27px Segoe UI,sans-serif;fill:#f8fafc}}.value{{font:15px Segoe UI,sans-serif;fill:#cbd5e1;text-anchor:end}}.note{{font:16px Segoe UI,sans-serif;fill:#fbbf24}}</style><rect width="1200" height="690" rx="28" fill="#0b1625"/><text x="72" y="62" class="k">PHASE V3T-H / VISIBLE VIEWPORT</text><text x="72" y="112" class="title">Average render FPS without an extra render path</text><text x="72" y="148" class="sub">20 logs / 1280 x 720 / 30 s warmup + 60 s measurement / 3 rotated runs</text>{''.join(rows)}<text x="72" y="615" class="note">No raw visible-frame timestamps: render p95/p99 and 1% low are intentionally not reported.</text><text x="72" y="650" class="sub">Frame-counter delta / wall time; HUD mean is the public smoothed FPS source. Display-present FPS remains unmeasured.</text></svg>'''
    (base / "render_fps_report.svg").write_text(svg, encoding="utf-8")
    print(json.dumps({"conditions": {key: value["average_visible_render_fps_weighted"] for key, value in conditions.items()}, "gpu_skipped": True}))


if __name__ == "__main__":
    main()
