"""Aggregate Phase V3T-R production/developer split measurements."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _number_summary(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _condition_summary(rows: list[dict]) -> dict:
    performance = [row["performance"] for row in rows]
    gpu = [row["gpu"] for row in rows]
    return {
        "runs": len(rows),
        "visible_fps": _number_summary(
            [float(item["average_visible_fps"]) for item in performance]
        ),
        "derived_frame_time_ms": _number_summary(
            [float(item["derived_frame_time_ms"]) for item in performance]
        ),
        "kit_updates_per_second": _number_summary(
            [float(item["kit_updates_per_second"]) for item in performance]
        ),
        "timeline_sim_wall_ratio": _number_summary(
            [float(item["timeline_sim_wall_ratio"]) for item in performance]
        ),
        "main_update_interval_ms": {
            name: _number_summary(
                [float(item["main_update_interval"][name]) for item in performance]
            )
            for name in ("mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms")
        },
        "gpu": {
            name: _number_summary(
                [float(item[name]["mean"]) for item in gpu if item.get(name)]
            )
            for name in (
                "utilization_percent",
                "power_w",
                "graphics_clock_mhz",
                "memory_used_mib",
                "power_limit_w",
            )
        },
        "v3": {
            name: _number_summary([float(item[name]) for item in performance])
            for name in (
                "v3_publication_count",
                "v3_upload_count",
                "v3_quantized_skip_count",
                "v3_visual_commit_count",
                "flow_active_blocks_peak",
            )
        },
        "debugpy_listen_observed": [row["debugpy_listen"]["observed"] for row in rows],
        "developer_extension_names": rows[0]["developer_extension_names"],
        "authority": [row["authority"] for row in rows],
    }


def _svg(report: dict) -> str:
    summary = report["formal_summary"]
    labels = (
        ("normal", "Production normal", "#22c55e"),
        ("developer", "Explicit developer", "#f97316"),
        ("benchmark", "Benchmark", "#38bdf8"),
    )
    bars = []
    for index, (key, label, color) in enumerate(labels):
        fps = summary[key]["visible_fps"]["mean"]
        width = fps * 10.0
        y = 235 + index * 112
        bars.append(
            f'<text x="80" y="{y}" class="label">{label}</text>'
            f'<rect x="320" y="{y - 31}" width="{width:.1f}" height="42" rx="8" fill="{color}"/>'
            f'<text x="{335 + width:.1f}" y="{y}" class="value">{fps:.3f} FPS</text>'
        )
    gain = report["effects"]["normal_gain_from_phasev3tq_fps"]
    residual = report["effects"]["normal_minus_benchmark_fps"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="760" viewBox="0 0 1180 760">
<rect width="1180" height="760" rx="30" fill="#08111f"/>
<style>.title{{font:700 38px sans-serif;fill:#f8fafc}}.sub{{font:20px sans-serif;fill:#94a3b8}}.label{{font:600 20px sans-serif;fill:#e2e8f0}}.value{{font:700 20px sans-serif;fill:#f8fafc}}.note{{font:19px sans-serif;fill:#cbd5e1}}.good{{font:700 23px sans-serif;fill:#86efac}}</style>
<text x="70" y="86" class="title">Phase V3T-R - Production / debug split</text>
<text x="70" y="126" class="sub">Candidate Performance - V3 ON - CPU source - 1280x720 - RTX 3090 - 210 W</text>
{''.join(bars)}
<line x1="70" y1="590" x2="1110" y2="590" stroke="#334155"/>
<text x="80" y="640" class="good">Candidate normal recovered +{gain:.3f} FPS from V3T-Q</text>
<text x="80" y="680" class="note">Normal - benchmark: {residual:+.3f} FPS - localhost debugpy only in explicit developer app</text>
<text x="80" y="716" class="note">PROMOTION HELD: native shutdown crash in final regression; production app remains unchanged.</text>
</svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", required=True, type=Path)
    parser.add_argument("--visible", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--regression", type=Path)
    args = parser.parse_args()
    formal = _load(args.formal)
    visible = _load(args.visible)
    regression = _load(args.regression) if args.regression else None
    grouped = {
        condition: [row for row in formal["entries"] if row["condition"] == condition]
        for condition in ("normal", "developer", "benchmark")
    }
    summary = {key: _condition_summary(rows) for key, rows in grouped.items()}
    normal_fps = summary["normal"]["visible_fps"]["mean"]
    developer_fps = summary["developer"]["visible_fps"]["mean"]
    benchmark_fps = summary["benchmark"]["visible_fps"]["mean"]
    normal_extensions = set(grouped["normal"][0]["enabled_extension_ids"])
    developer_extensions = set(grouped["developer"][0]["enabled_extension_ids"])
    benchmark_extensions = set(grouped["benchmark"][0]["enabled_extension_ids"])
    authority_rows = [row["authority"] for row in formal["entries"]]
    dry_hashes = {row["dry_sha256"] for row in authority_rows}
    wet_hashes = {row["wet_sha256"] for row in authority_rows}
    mass_errors = [
        abs(float(row[name]))
        for row in authority_rows
        for name in ("dry_mass_balance_error_kg", "wet_mass_balance_error_kg")
    ]
    report = {
        "schema": "campfire.phasev3tr.debug-split-report.v1",
        "status": "qualified" if normal_fps >= 45.0 else "failed",
        "formal_processes": len(formal["entries"]),
        "formal_summary": summary,
        "effects": {
            "phasev3tq_normal_with_developer_fps": 32.2109,
            "normal_gain_from_phasev3tq_fps": round(normal_fps - 32.2109, 4),
            "normal_minus_benchmark_fps": round(normal_fps - benchmark_fps, 4),
            "developer_minus_normal_fps": round(developer_fps - normal_fps, 4),
        },
        "extension_boundary": {
            "normal_count": len(normal_extensions),
            "developer_count": len(developer_extensions),
            "benchmark_count": len(benchmark_extensions),
            "developer_only_vs_normal": sorted(developer_extensions - normal_extensions),
            "normal_only_vs_benchmark": sorted(normal_extensions - benchmark_extensions),
            "benchmark_only_vs_normal": sorted(benchmark_extensions - normal_extensions),
        },
        "gates": {
            "normal_at_least_45_fps": normal_fps >= 45.0,
            "normal_debugpy_listen_absent": not any(summary["normal"]["debugpy_listen_observed"]),
            "benchmark_debugpy_listen_absent": not any(summary["benchmark"]["debugpy_listen_observed"]),
            "developer_debugpy_listen_present": all(summary["developer"]["debugpy_listen_observed"]),
            "authority_hashes_match": len(dry_hashes) == 1 and len(wet_hashes) == 1,
            "mass_balance_zero": max(mass_errors, default=0.0) == 0.0,
            "v3_default_on": formal["v3_default_on"],
            "app_hashes_recorded": len(formal["app_hashes_after"]) == 3,
            "regression_native_crash_zero": not regression or regression["native_crash_count"] == 0,
            "regression_dump_zero": not regression or regression["dump_count"] == 0,
            "automatic_upload_zero": not regression or regression["automatic_upload_count"] == 0,
        },
        "visible_window_confirmation": visible["entries"],
        "metric_contract": {
            "fps": "ViewportAPI.frame_info visible render counter",
            "display_present_fps": None,
            "gpu_render_time": None,
            "capture_or_encode_in_population": False,
            "additional_render_product": False,
        },
        "regression_incident": regression,
        "decision": "Promote debugger-free normal app; retain explicit localhost developer app.",
    }
    if not all(report["gates"].values()):
        report["status"] = "failed"
        report["decision"] = (
            "Do not promote the candidate split: preserve the measured evidence, retain "
            "the current production app, and investigate the shutdown access violation."
        )
    samples = {"schema": "campfire.phasev3tr.debug-split-samples.v1", "formal": formal, "visible": visible}
    for path in (args.report, args.samples, args.svg):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.samples.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "effects": report["effects"]}, indent=2))


if __name__ == "__main__":
    main()
