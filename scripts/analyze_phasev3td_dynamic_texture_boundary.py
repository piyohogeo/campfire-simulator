"""Aggregate Phase V3T-D raw samples and render the committed report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "devlog" / "assets" / "phasev3td"


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def _percentile(values, q):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _stats(values):
    values = [float(value) for value in values]
    return {
        "count": len(values),
        "p50_ms": round(_percentile(values, 0.50), 4),
        "mean_ms": round(statistics.fmean(values), 4),
        "p95_ms": round(_percentile(values, 0.95), 4),
        "p99_ms": round(_percentile(values, 0.99), 4),
        "max_ms": round(max(values), 4),
        "over_5_ms": sum(value > 5.0 for value in values),
        "over_16_67_ms": sum(value > 16.67 for value in values),
        "over_33_33_ms": sum(value > 33.33 for value in values),
        "over_50_ms": sum(value > 50.0 for value in values),
        "near_16_67ms_multiple": sum(
            value >= 8.0 and abs(value / 16.67 - round(value / 16.67)) <= 0.08
            for value in values
        ),
    }


def _gpu_summary(path):
    if not path or not Path(path).is_file():
        return {"available": False}
    utilization, memory = [], []
    with Path(path).open(encoding="utf-8") as stream:
        for row in csv.reader(stream):
            if len(row) >= 3:
                try:
                    utilization.append(float(row[1].strip()))
                    memory.append(float(row[2].strip()))
                except ValueError:
                    pass
    return {
        "available": bool(utilization),
        "sample_count": len(utilization),
        "utilization_mean_percent": round(statistics.fmean(utilization), 3) if utilization else None,
        "utilization_max_percent": max(utilization) if utilization else None,
        "memory_mean_mib": round(statistics.fmean(memory), 3) if memory else None,
        "memory_max_mib": max(memory) if memory else None,
        "scope": "whole GPU process observation; not provider-owned allocation",
    }


def _median_metric(rows, field, metric):
    return round(statistics.median(row[field][metric] for row in rows), 4)


def _svg(report):
    rows = [row for row in report["aggregate"] if row["case"] == "both_changing"]
    palette = ["#60a5fa", "#a78bfa", "#34d399", "#f59e0b", "#fb7185", "#22d3ee", "#facc15"]
    bars = []
    y = 190
    scale = 10.0
    for index, row in enumerate(rows):
        value = row["provider_setter"]["p95_ms_median"]
        width = min(760.0, value * scale)
        label = f"{row['mode']}  {row['atlas']}"
        bars.append(f'<text x="70" y="{y + 19}" fill="#dbeafe" font-size="14">{label}</text><rect x="390" y="{y}" width="{width:.1f}" height="24" rx="12" fill="{palette[index % len(palette)]}"/><text x="1170" y="{y + 19}" text-anchor="end" fill="#f8fafc" font-size="15">{value:.4f} ms</text>')
        y += 34
    height = max(640, y + 90)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="{height}" viewBox="0 0 1240 {height}" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-D DynamicTextureProvider boundary</title><desc id="desc">Median-of-three p95 provider setter time for both changing RGBA8 atlases across disconnected, RTX, Flow, and GPU-source conditions.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0b1624"/><stop offset="1" stop-color="#24152b"/></linearGradient></defs><rect width="1240" height="{height}" rx="28" fill="url(#bg)"/>
<g font-family="Segoe UI, sans-serif"><text x="70" y="62" fill="#c4b5fd" font-size="17" font-weight="700" letter-spacing="3">PHASE V3T-D · PUBLICATION BOUNDARY</text><text x="70" y="108" fill="#f8fafc" font-size="36" font-weight="800">Dynamic texture setter tail by environment</text><text x="70" y="145" fill="#a7b2c2" font-size="17">both textures changing · p95 median across independent runs · 96×15 and 120×60 RGBA8</text>{''.join(bars)}<text x="70" y="{height - 38}" fill="#94a3b8" font-size="15">Setter time excludes source preparation, explicit CPU→GPU staging, USD revision Set, capture, and file I/O.</text></g></svg>'''


def main():
    args = _arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    raw_runs = []
    grouped = defaultdict(list)
    api = None
    for item in manifest["runs"]:
        raw = json.loads(Path(item["samples"]).read_text(encoding="utf-8"))
        api = api or raw["api"]
        gpu = _gpu_summary(item.get("gpu_samples"))
        raw_runs.append({"matrix": item, "gpu": gpu, "probe": raw})
        by_case = defaultdict(list)
        for sample in raw["samples"]:
            by_case[sample["case"]].append(sample)
        for case, samples in by_case.items():
            grouped[(raw["mode"], f'{raw["atlas"]["width"]}x{raw["atlas"]["height"]}', case)].append(
                {
                    "provider_setter": _stats(sample["provider_setter_ms"] for sample in samples),
                    "source_prepare": _stats(sample["source_prepare_ms"] for sample in samples),
                    "cpu_to_gpu_staging": _stats(sample["cpu_to_gpu_staging_ms"] for sample in samples),
                    "publication_to_next_render": _stats(sample["publication_to_next_render_ms"] for sample in samples if sample["publication_to_next_render_ms"] is not None) if raw["environment"]["rtx"] else None,
                    "bytes_per_publication": samples[0]["bytes"],
                    "api_calls_per_publication": samples[0]["api_calls"],
                    "gpu": gpu,
                }
            )
    aggregate = []
    for (mode, atlas, case), rows in sorted(grouped.items()):
        item = {
            "mode": mode,
            "atlas": atlas,
            "case": case,
            "run_count": len(rows),
            "provider_setter": {metric + "_median": _median_metric(rows, "provider_setter", metric) for metric in ("p50_ms", "mean_ms", "p95_ms", "p99_ms", "max_ms", "over_5_ms", "over_16_67_ms", "over_33_33_ms", "over_50_ms", "near_16_67ms_multiple")},
            "source_prepare": {metric + "_median": _median_metric(rows, "source_prepare", metric) for metric in ("p50_ms", "mean_ms", "p95_ms", "p99_ms", "max_ms")},
            "cpu_to_gpu_staging": {metric + "_median": _median_metric(rows, "cpu_to_gpu_staging", metric) for metric in ("p50_ms", "mean_ms", "p95_ms", "p99_ms", "max_ms")},
            "publication_to_next_render": None,
            "bytes_per_publication": rows[0]["bytes_per_publication"],
            "api_calls_per_publication": rows[0]["api_calls_per_publication"],
            "whole_gpu": {
                "available": all(row["gpu"].get("available") for row in rows),
                "sample_count_total": sum(row["gpu"].get("sample_count", 0) for row in rows),
                "utilization_mean_percent_median": round(statistics.median(row["gpu"]["utilization_mean_percent"] for row in rows), 3),
                "utilization_max_percent_median": round(statistics.median(row["gpu"]["utilization_max_percent"] for row in rows), 3),
                "memory_mean_mib_median": round(statistics.median(row["gpu"]["memory_mean_mib"] for row in rows), 3),
                "memory_max_mib_median": round(statistics.median(row["gpu"]["memory_max_mib"] for row in rows), 3),
                "scope": "whole GPU process observation; not provider-owned allocation",
            },
        }
        item["provider_setter"].update(
            {
                metric + "_total": sum(row["provider_setter"][metric] for row in rows)
                for metric in (
                    "over_5_ms",
                    "over_16_67_ms",
                    "over_33_33_ms",
                    "over_50_ms",
                    "near_16_67ms_multiple",
                )
            }
        )
        if rows[0]["publication_to_next_render"]:
            item["publication_to_next_render"] = {metric + "_median": _median_metric(rows, "publication_to_next_render", metric) for metric in ("p50_ms", "mean_ms", "p95_ms", "p99_ms", "max_ms")}
        aggregate.append(item)

    def find(mode, atlas="120x60", case="both_changing"):
        return next((row for row in aggregate if row["mode"] == mode and row["atlas"] == atlas and row["case"] == case), None)

    disconnected = find("cpu_unconnected_changing")
    rtx_off = find("cpu_rtx_flow_off")
    flow_on = find("cpu_rtx_flow_on")
    gpu_off = find("gpu_rtx_flow_off")
    small = find("cpu_rtx_flow_off", "96x15")
    classifications = {
        "provider_or_resource_manager_candidate": bool(disconnected and disconnected["provider_setter"]["p95_ms_median"] > 16.67),
        "renderer_resource_sync_candidate": bool(disconnected and rtx_off and rtx_off["provider_setter"]["p95_ms_median"] > max(5.0, disconnected["provider_setter"]["p95_ms_median"] * 1.5)),
        "flow_gpu_or_scheduler_contention_candidate": bool(rtx_off and flow_on and flow_on["provider_setter"]["p95_ms_median"] > max(5.0, rtx_off["provider_setter"]["p95_ms_median"] * 1.5)),
        "cpu_source_path_primary_candidate": bool(gpu_off and rtx_off and gpu_off["provider_setter"]["p95_ms_median"] < rtx_off["provider_setter"]["p95_ms_median"] * 0.5),
        "destination_or_renderer_fence_candidate": bool(gpu_off and gpu_off["provider_setter"]["p95_ms_median"] > 16.67),
        "bandwidth_dominant_not_supported": bool(small and rtx_off and abs(rtx_off["provider_setter"]["p95_ms_median"] - small["provider_setter"]["p95_ms_median"]) <= max(2.0, rtx_off["provider_setter"]["p95_ms_median"] * 0.2)),
        "frame_quantization_candidate": bool(rtx_off and rtx_off["provider_setter"]["near_16_67ms_multiple_median"] >= manifest["samples_per_case"] * 0.25),
    }
    gpu_probe = next(run["probe"] for run in raw_runs if run["probe"]["source"] == "gpu")
    conclusion_table = []
    for mode in (
        "cpu_unconnected_changing",
        "cpu_connected_no_rtx",
        "cpu_rtx_flow_off",
        "cpu_rtx_flow_on",
        "gpu_rtx_flow_off",
        "gpu_rtx_flow_on",
    ):
        row = find(mode)
        conclusion_table.append(
            {
                "mode": mode,
                "source": "gpu" if mode.startswith("gpu_") else "cpu_raw_pointer",
                "rtx": "_rtx_flow_" in mode,
                "flow": mode.endswith("flow_on"),
                "provider_setter_p95_ms": row["provider_setter"]["p95_ms_median"],
                "cpu_to_gpu_staging_p95_ms": row["cpu_to_gpu_staging"]["p95_ms_median"],
                "publication_to_next_requested_rtx_frame_p95_ms": (
                    row["publication_to_next_render"]["p95_ms_median"]
                    if row["publication_to_next_render"]
                    else None
                ),
                "render_updates_per_sample": 1 if "_rtx_flow_" in mode else 0,
                "interpretation": (
                    "reflection timing is completion of the next explicitly requested viewport frame; per-sample pixel identity was not read back"
                    if "_rtx_flow_" in mode
                    else "no Hydra/RTX viewport in the provider-only Kit root"
                ),
            }
        )
    report = {
        "schema": "campfire.phasev3td.report.v1",
        "status": "measurement_complete_no_production_change",
        "matrix": {
            **{key: manifest[key] for key in ("warmup_per_case", "samples_per_case", "independent_runs", "same_gpu")},
            "process_count": len(raw_runs),
            "measured_sample_count": sum(len(run["probe"]["samples"]) for run in raw_runs),
            "provider_only_no_rtx_processes": sum(not run["probe"]["environment"]["rtx"] for run in raw_runs),
            "editor_rtx_processes": sum(run["probe"]["environment"]["rtx"] for run in raw_runs),
            "measurement_topology_stable_processes": sum(run["probe"]["stage_contract"]["topology_unchanged_during_measurement"] for run in raw_runs),
            "flow_active_processes": sum((run["probe"]["flow_state"]["active_blocks"] or 0) > 0 for run in raw_runs),
        },
        "api": api,
        "gpu_source_contract": gpu_probe["gpu_owner"],
        "aggregate": aggregate,
        "conclusion_table": conclusion_table,
        "classifications": classifications,
        "interpretation_guardrails": {
            "observed": "timings, thresholds, atlas byte counts, runtime API/docstrings, and whole-GPU telemetry",
            "strong_inference": "classification booleans are boundary candidates, not internal implementation proof",
            "unconfirmed": "provider internals, exact renderer fences, and provider-owned memory",
            "v3tc_cpu_upload_ms_reading": "DynamicTextureProvider CPU-source publication call; not a measured raw memcpy bandwidth",
        },
        "production": {"modified": False, "v3_integrated": False, "defaults_changed": False},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dynamic_texture_boundary_samples.json").write_text(json.dumps({"schema": "campfire.phasev3td.all_samples.v1", "runs": raw_runs}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (OUTPUT / "dynamic_texture_boundary_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "dynamic_texture_boundary_report.svg").write_text(_svg(report), encoding="utf-8")
    print(f"Phase V3T-D: {len(raw_runs)} processes, {sum(len(run['probe']['samples']) for run in raw_runs)} measured samples")


if __name__ == "__main__":
    main()
