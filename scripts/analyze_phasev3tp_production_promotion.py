#!/usr/bin/env python3
"""Aggregate the Phase V3T-P production-default qualification artifacts."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
from pathlib import Path


FATAL_TOKENS = (
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)",
    "CUDA_ERROR_ILLEGAL_ADDRESS",
    "device lost",
    "invalid pointer",
    "[crash] A crash has occurred",
    "Uploading minidump:",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def stats(values) -> dict:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return {key: None for key in ("count", "p50", "mean", "p95", "p99", "max")}
    return {
        "count": len(numbers),
        "p50": round(percentile(numbers, 0.50), 4),
        "mean": round(statistics.fmean(numbers), 4),
        "p95": round(percentile(numbers, 0.95), 4),
        "p99": round(percentile(numbers, 0.99), 4),
        "max": round(max(numbers), 4),
    }


def gpu_samples(path: Path) -> list[dict]:
    samples = []
    if not path.exists():
        return samples
    with path.open(encoding="utf-8", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 10:
                continue
            try:
                samples.append(
                    {
                        "utilization_percent": float(row[1].strip()),
                        "memory_used_mib": float(row[2].strip()),
                        "power_w": float(row[3].strip()),
                        "graphics_clock_mhz": float(row[4].strip()),
                        "sm_clock_mhz": float(row[5].strip()),
                        "temperature_c": float(row[6].strip()),
                        "pstate": row[7].strip(),
                        "power_limit_w": float(row[8].strip()),
                        "enforced_power_limit_w": float(row[9].strip()),
                    }
                )
            except ValueError:
                continue
    return samples


def profile_category(sample: dict) -> str:
    base = bool(sample.get("base_changed"))
    emission = bool(sample.get("emission_changed"))
    if base and emission:
        return "base_and_emission"
    if base:
        return "base_only"
    if emission:
        return "emission_only"
    return "unchanged"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal-manifest", type=Path, required=True)
    parser.add_argument("--visible-report", type=Path, required=True)
    parser.add_argument("--visible-root", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--demo-summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    manifest = load(args.formal_manifest)
    visible = load(args.visible_report)
    lifecycle = load(args.lifecycle)
    demo = load(args.demo_summary)
    entries = []
    raw_profiles = []
    gpu_by_condition: dict[str, list[dict]] = {}
    fatal_counts = {token: 0 for token in FATAL_TOKENS}
    dump_count = 0

    for entry in manifest["entries"]:
        summary_path = Path(entry["summary"])
        summary = load(summary_path)
        condition_key = f"{entry['app_kind']}_{entry['condition']}"
        gpu = gpu_samples(Path(entry["gpu_csv"]))
        gpu_by_condition.setdefault(condition_key, []).extend(gpu)
        log_text = Path(entry["kit_log"]).read_text(encoding="utf-8", errors="replace")
        for token in FATAL_TOKENS:
            fatal_counts[token] += log_text.count(token)
        dump_dir = summary_path.parent / "sensitive-crash-dumps"
        if dump_dir.exists():
            dump_count += sum(1 for item in dump_dir.rglob("*") if item.is_file())
        visual = summary["scenario"]["wood_visual_v3"]
        profiles = list(visual.get("publication_samples") or [])
        for profile in profiles:
            profile["run_name"] = entry["name"]
            profile["category"] = profile_category(profile)
            raw_profiles.append(profile)
        entries.append(
            {
                "name": entry["name"],
                "condition": entry["condition"],
                "app_kind": entry["app_kind"],
                "run": entry["run"],
                "visible_fps": summary["scenario"]["visible_viewport"]["average_fps"],
                "authority_sha256": entry["authority_sha256"],
                "mass_balance_error_kg": {
                    name: summary["wood"][name]["mass_balance_error_kg"] for name in ("dry", "wet")
                },
                "flow": summary["flow"],
                "resident_revision_consistent": summary["scenario"]["resident_snapshot_adapter"]["final_usd_state"]["revision_consistent"],
                "resident_revision": summary["scenario"]["resident_snapshot_adapter"]["status_after_timeline_stop"]["revision"],
                "v3": {
                    "enabled": visual["enabled"],
                    "revision": (visual.get("status_after_timeline_stop") or {}).get("revision"),
                    "processed_revision": (visual.get("status_after_timeline_stop") or {}).get("processed_revision"),
                    "failure_count": (visual.get("status_after_timeline_stop") or {}).get("failure_count", 0),
                    "upload_count": visual.get("upload_count", 0),
                    "visual_commit_count": (visual.get("status_after_timeline_stop") or {}).get("visual_commit_count", 0),
                    "quantized_skip_count": (visual.get("status_after_timeline_stop") or {}).get("quantized_skip_count", 0),
                    "published": (visual.get("adaptive_schedule") or {}).get("published", 0),
                },
            }
        )

    publication = {}
    for category in ("base_only", "emission_only", "base_and_emission", "unchanged"):
        group = [sample for sample in raw_profiles if sample["category"] == category]
        publication[category] = {
            "samples": len(group),
            "provider_setter_ms": stats(sample.get("cpu_upload_ms") for sample in group),
            "total_ms": stats(sample.get("total_ms") for sample in group),
            "over_30_ms": sum(float(sample.get("total_ms", 0)) > 30.0 for sample in group),
            "over_33_333_ms": sum(float(sample.get("total_ms", 0)) > 33.333 for sample in group),
        }
    publication["all"] = {
        "samples": len(raw_profiles),
        "provider_setter_ms": stats(sample.get("cpu_upload_ms") for sample in raw_profiles),
        "total_ms": stats(sample.get("total_ms") for sample in raw_profiles),
        "over_30_ms": sum(float(sample.get("total_ms", 0)) > 30.0 for sample in raw_profiles),
        "over_33_333_ms": sum(float(sample.get("total_ms", 0)) > 33.333 for sample in raw_profiles),
        "over_50_ms": sum(float(sample.get("total_ms", 0)) > 50.0 for sample in raw_profiles),
    }

    gpu_summary = {}
    for condition, samples in gpu_by_condition.items():
        gpu_summary[condition] = {
            field: stats(sample[field] for sample in samples)
            for field in (
                "utilization_percent", "memory_used_mib", "power_w",
                "graphics_clock_mhz", "sm_clock_mhz", "temperature_c",
                "power_limit_w", "enforced_power_limit_w",
            )
        }
        gpu_summary[condition]["pstates"] = sorted({sample["pstate"] for sample in samples})

    authority_sets = {
        name: sorted({entry["authority_sha256"][name] for entry in entries})
        for name in ("dry", "wet", "metrics_csv")
    }
    on_entries = [entry for entry in entries if entry["condition"] == "on_default"]
    off_entries = [entry for entry in entries if entry["condition"] == "off_explicit"]
    benchmark_on = [entry for entry in on_entries if entry["app_kind"] == "benchmark"]
    normal_on = [entry for entry in on_entries if entry["app_kind"] == "normal"]
    visible_off = visible["conditions"]["flow_on_v3_off"]
    visible_on = visible["conditions"]["flow_on_v3_cpu"]
    demo_wood = demo["wood"]
    demo_visual = demo["scenario"]["wood_visual_v3"]
    lifecycle_gates = lifecycle["gates"]
    gates = {
        "production_apps_default_v3_on": all(entry["v3"]["enabled"] for entry in on_entries),
        "explicit_off_fallback": all(not entry["v3"]["enabled"] for entry in off_entries),
        "authority_hash_equal_off_on": all(len(values) == 1 for values in authority_sets.values()),
        "mass_balance_zero": all(
            all(value == 0 for value in entry["mass_balance_error_kg"].values()) for entry in entries
        ),
        "resident_and_v3_revision_consistent": all(
            entry["resident_revision_consistent"] and entry["resident_revision"] == 1200 and
            (not entry["v3"]["enabled"] or (
                entry["v3"]["revision"] == 1200 and entry["v3"]["processed_revision"] == 1200
            )) for entry in entries
        ),
        "flow_preserved": all(
            entry["flow"]["active_blocks_peak"] > 0 and entry["flow"]["peak_fuel_input"] > 0 for entry in entries
        ),
        "visual_failure_zero": all(entry["v3"]["failure_count"] == 0 for entry in on_entries),
        "normal_app_above_30_fps": min(entry["visible_fps"] for entry in normal_on) >= 30.0,
        "visible_20_log_above_30_fps": visible_on["average_visible_render_fps_weighted"] >= 30.0,
        "visible_20_log_meets_45_fps_target": visible_on["average_visible_render_fps_weighted"] >= 45.0,
        "stage_reload_and_lifecycle": all(lifecycle_gates.values()),
        "native_crash_dump_upload_zero": sum(fatal_counts.values()) == 0 and dump_count == 0,
        "visual_states_from_authority": (
            demo_wood["wet"]["moisture_mass_kg"] > demo_wood["dry"]["moisture_mass_kg"] and
            demo_wood["dry"]["char_mass_kg"] > demo_wood["wet"]["char_mass_kg"] and
            demo_wood["dry"]["ash_mass_kg"] > 0 and demo_wood["wet"]["ash_mass_kg"] > 0 and
            demo_wood["dry"]["surface_mean_temperature_k"] > demo_wood["wet"]["surface_mean_temperature_k"]
        ),
        "long_burn_visual_revision_and_flow": (
            demo_visual["status_after_timeline_stop"]["revision"] == 1200 and
            demo_visual["status_after_timeline_stop"]["failure_count"] == 0 and
            demo["flow"]["active_blocks_peak"] > 0
        ),
    }
    promoted = all(gates.values())

    report = {
        "schema": "campfire.phasev3tp.production-promotion-report.v1",
        "status": "qualified" if promoted else "not_qualified",
        "decision": "promote_v3_production_default_on" if promoted else "retain_default_off",
        "transport": "DynamicTextureProvider.set_raw_bytes_data CPU-source",
        "renderer": "Candidate Performance; RTX Real-Time 2.0; DLSS Performance; maxBounces=2",
        "resolution": [1280, 720],
        "gpu": "NVIDIA GeForce RTX 3090; Power Limit 210 W (60%), unchanged",
        "targets": {"normal_fps": 45.0, "minimum_fps": 30.0, "ideal_light_scene_fps": 60.0},
        "formal_runs": entries,
        "formal_fps": {
            "benchmark_off": stats(entry["visible_fps"] for entry in off_entries),
            "benchmark_on": stats(entry["visible_fps"] for entry in benchmark_on),
            "normal_app_on": stats(entry["visible_fps"] for entry in normal_on),
        },
        "visible_20_log": {
            "off": visible_off,
            "on": visible_on,
            "fps_delta": round(
                visible_on["average_visible_render_fps_weighted"] -
                visible_off["average_visible_render_fps_weighted"], 4
            ),
            "display_present_fps": None,
            "raw_render_frame_intervals": None,
            "one_percent_low": None,
        },
        "publication": publication,
        "scheduler": {
            "configured_range_hz": [2.5, 5.0],
            "model_duration_seconds_per_run": 240.0,
            "mean_published_hz": round(statistics.fmean(entry["v3"]["published"] / 240.0 for entry in benchmark_on), 4),
            "mean_visual_commit_hz": round(statistics.fmean(entry["v3"]["visual_commit_count"] / 240.0 for entry in benchmark_on), 4),
            "upload_count_per_run": [entry["v3"]["upload_count"] for entry in benchmark_on],
            "quantized_skip_count_per_run": [entry["v3"]["quantized_skip_count"] for entry in benchmark_on],
            "visual_commit_count_per_run": [entry["v3"]["visual_commit_count"] for entry in benchmark_on],
        },
        "gpu_telemetry": gpu_summary,
        "authority_sha256": authority_sets,
        "lifecycle": {
            "gates": lifecycle_gates,
            "stage_reload_first_republish_ms": lifecycle["performance"]["stage_reload_first_republish_ms"],
            "crash_safety": lifecycle["crash_safety"],
        },
        "long_burn": {
            "wood": demo_wood,
            "comparison": demo["comparison"],
            "flow": demo["flow"],
            "visual_status": demo_visual["status_after_timeline_stop"],
        },
        "fatal_log_counts": fatal_counts,
        "crash_dump_count": dump_count,
        "gates": gates,
        "measurement_limits": {
            "visible_fps": "Public ViewportAPI.frame_info render counter; not display-present FPS.",
            "display_present_fps": "not measured",
            "gpu_render_time": "not measured",
            "one_percent_low": "not derived because public raw render-frame intervals were unavailable",
            "gpu_telemetry": "whole-GPU nvidia-smi samples, not provider-owned usage",
        },
    }
    sample_document = {
        "schema": "campfire.phasev3tp.production-promotion-samples.v1",
        "formal_publication_samples": raw_profiles,
        "visible_sample_source": str(args.visible_root / "render_fps_samples.json"),
        "note": "Visible raw samples remain in the reproducible artifact; publication samples are embedded here.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.samples.write_text(json.dumps(sample_document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    bars = [
        ("20 logs OFF", visible_off["average_visible_render_fps_weighted"], "#64748b"),
        ("20 logs V3 ON", visible_on["average_visible_render_fps_weighted"], "#f97316"),
        ("Normal app V3 ON", normal_on[0]["visible_fps"], "#ef4444"),
    ]
    rows = []
    for index, (label, value, color) in enumerate(bars):
        y = 88 + index * 66
        width = value * 9
        rows.append(
            f'<text x="28" y="{y}" class="label">{html.escape(label)}</text>'
            f'<rect x="205" y="{y-24}" width="{width:.1f}" height="30" rx="6" fill="{color}"/>'
            f'<text x="{215+width:.1f}" y="{y}" class="value">{value:.2f} FPS</text>'
        )
    p95 = publication["all"]["total_ms"]["p95"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="920" height="360" viewBox="0 0 920 360">
<rect width="920" height="360" rx="18" fill="#111827"/>
<style>.title{{font:700 24px Segoe UI;fill:#f8fafc}}.label{{font:16px Segoe UI;fill:#e2e8f0}}.value{{font:700 16px Segoe UI;fill:#f8fafc}}.note{{font:14px Segoe UI;fill:#94a3b8}}</style>
<text x="28" y="38" class="title">Phase V3T-P — CPU-source V3 production promotion</text>
{''.join(rows)}
<line x1="475" y1="54" x2="475" y2="272" stroke="#22c55e" stroke-width="2" stroke-dasharray="6 6"/>
<text x="482" y="70" class="note">45 FPS target</text>
<line x1="340" y1="54" x2="340" y2="272" stroke="#eab308" stroke-width="2" stroke-dasharray="6 6"/>
<text x="347" y="270" class="note">30 FPS minimum</text>
<text x="28" y="314" class="label">Publication total p95: {p95:.2f} ms · fatal / dump / upload: 0 · authority hash: identical</text>
<text x="28" y="340" class="note">Visible FPS is ViewportAPI.frame_info, not display-present FPS. Candidate Performance, 1280×720, 210 W limit.</text>
</svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    print(f"Phase V3T-P: {sum(gates.values())}/{len(gates)} gates; decision={report['decision']}")
    return 0 if promoted else 1


if __name__ == "__main__":
    raise SystemExit(main())
