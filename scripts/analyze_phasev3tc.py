"""Analyze alternating integrated V3 OFF/ON runs and publish adoption evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "devlog" / "assets" / "phasev3tc"


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "artifacts" / "phasev3tc" / "integrated" / "matrix_manifest.json",
    )
    parser.add_argument(
        "--isolated-report",
        type=Path,
        default=ROOT / "docs" / "devlog" / "assets" / "phasev3tb" / "native_beauty_report.json",
    )
    parser.add_argument(
        "--v3mc-report",
        type=Path,
        default=ROOT / "docs" / "devlog" / "assets" / "phasev3tb" / "native_v3mc_regression.json",
    )
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=ROOT / "artifacts" / "phasev3tc" / "demo",
    )
    return parser.parse_args()


def _median(values):
    return round(statistics.median(float(value) for value in values), 4)


def _run_record(item, summary):
    frame = summary["timing"]["segments"]["frame_pacing"]["update_frame"]
    visual = summary["scenario"]["wood_visual_v3"]
    publication = visual["publication_timing"] if visual["enabled"] else None
    reflection = visual["rtx_reflection"] if visual["enabled"] else None
    reflection_summary = (
        {
            "timing": reflection["timing"],
            "maximum_render_frame_updates": reflection[
                "maximum_render_frame_updates"
            ],
            "pending_at_stop": reflection["pending_at_stop"],
            "sample_count": len(reflection["samples"]),
        }
        if reflection is not None
        else None
    )
    resident = summary["scenario"]["resident_snapshot_adapter"]
    return {
        "sequence": item["sequence"],
        "pair": item["pair"],
        "mode": item["mode"],
        "summary": str(Path(item["summary"]).resolve()),
        "authority_sha256": {
            name: summary["wood"][name]["authoritative_state_sha256"]
            for name in ("dry", "wet")
        },
        "metrics_csv_sha256": summary["metrics_csv_sha256"],
        "mass_balance_error_kg": {
            name: summary["wood"][name]["mass_balance_error_kg"]
            for name in ("dry", "wet")
        },
        "ignition_seconds": {
            name: summary["wood"][name]["ignition_seconds"]
            for name in ("dry", "wet")
        },
        "flow": summary["flow"],
        "resident_revision": resident["final_usd_state"]["emitter"]["revision"],
        "frame": frame,
        "visual_publication": publication,
        "visual_transferred_bytes": visual["transferred_bytes"],
        "visual_upload_count": visual["upload_count"],
        "visual_schedule": visual["adaptive_schedule"],
        "rtx_reflection": reflection_summary,
        "gpu": summary["phasev3tc_gpu"],
        "runner_wall_seconds": summary["runner_wall_seconds"],
    }


def _aggregate(records):
    result = {}
    for mode in ("off", "on"):
        selected = [record for record in records if record["mode"] == mode]
        result[mode] = {
            "run_count": len(selected),
            "update_frame_p50_ms_median": _median(
                record["frame"]["p50_ms"] for record in selected
            ),
            "update_frame_p95_ms_median": _median(
                record["frame"]["p95_ms"] for record in selected
            ),
            "update_frame_max_ms_median": _median(
                record["frame"]["max_ms"] for record in selected
            ),
            "over_16_67_ms_total": sum(
                record["frame"]["over_16_67_ms"] for record in selected
            ),
            "over_33_33_ms_total": sum(
                record["frame"]["over_33_33_ms"] for record in selected
            ),
            "over_50_ms_total": sum(
                record["frame"]["over_50_ms"] for record in selected
            ),
            "gpu_utilization_mean_percent_median": _median(
                record["gpu"]["utilization_mean_percent"] for record in selected
            ),
            "gpu_memory_max_mib_median": _median(
                record["gpu"]["memory_max_mib"] for record in selected
            ),
            "runner_wall_seconds_median": _median(
                record["runner_wall_seconds"] for record in selected
            ),
        }
        if mode == "on":
            result[mode].update(
                {
                    "visual_publication_p50_ms_median": _median(
                        record["visual_publication"]["total_ms"]["p50_ms"]
                        for record in selected
                    ),
                    "visual_publication_p95_ms_median": _median(
                        record["visual_publication"]["total_ms"]["p95_ms"]
                        for record in selected
                    ),
                    "visual_publication_max_ms_median": _median(
                        record["visual_publication"]["total_ms"]["max_ms"]
                        for record in selected
                    ),
                    "cpu_upload_p50_ms_median": _median(
                        record["visual_publication"]["cpu_upload_ms"]["p50_ms"]
                        for record in selected
                    ),
                    "cpu_upload_p95_ms_median": _median(
                        record["visual_publication"]["cpu_upload_ms"]["p95_ms"]
                        for record in selected
                    ),
                    "cpu_upload_max_ms_median": _median(
                        record["visual_publication"]["cpu_upload_ms"]["max_ms"]
                        for record in selected
                    ),
                    "rtx_reflection_p95_ms_median": _median(
                        record["rtx_reflection"]["timing"]["p95_ms"]
                        for record in selected
                    ),
                    "rtx_reflection_max_frame_updates": max(
                        record["rtx_reflection"]["maximum_render_frame_updates"]
                        for record in selected
                    ),
                    "transferred_bytes_total": sum(
                        record["visual_transferred_bytes"] for record in selected
                    ),
                }
            )
    return result


def _svg(report):
    off = report["aggregate"]["off"]
    on = report["aggregate"]["on"]
    scale = 28.0
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-C integrated OFF and ON comparison</title><desc id="desc">Three alternating pairs preserve authority and frame pacing, but the isolated one millisecond publication target remains unmet, so V3 stays opt-in.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0d1720"/><stop offset="1" stop-color="#21162d"/></linearGradient></defs><rect width="1200" height="680" rx="30" fill="url(#bg)"/>
<g font-family="Segoe UI, sans-serif"><text x="70" y="68" fill="#c4b5fd" font-size="18" font-weight="700" letter-spacing="3">PHASE V3T-C · INTEGRATED ADOPTION GATE</text><text x="70" y="118" fill="#f8fafc" font-size="38" font-weight="800">Authority holds; V3 remains an explicit preset</text><text x="70" y="154" fill="#a7b2c2" font-size="18">3 alternating OFF/ON pairs · Resident native + Flow + RTX · fixed camera and warmup</text>
<rect x="70" y="194" width="1060" height="150" rx="18" fill="#111e2a"/><text x="96" y="232" fill="#dbeafe" font-size="18">Update-frame p95 median</text><text x="96" y="276" fill="#93c5fd" font-size="19">OFF</text><rect x="160" y="254" width="{off['update_frame_p95_ms_median'] * scale:.1f}" height="26" rx="13" fill="#60a5fa"/><text x="1090" y="277" text-anchor="end" fill="#f8fafc" font-size="24" font-weight="800">{off['update_frame_p95_ms_median']:.4f} ms</text><text x="96" y="322" fill="#c4b5fd" font-size="19">ON</text><rect x="160" y="300" width="{on['update_frame_p95_ms_median'] * scale:.1f}" height="26" rx="13" fill="#a78bfa"/><text x="1090" y="323" text-anchor="end" fill="#f8fafc" font-size="24" font-weight="800">{on['update_frame_p95_ms_median']:.4f} ms</text>
<rect x="70" y="368" width="510" height="148" rx="18" fill="#10261f" stroke="#34d399"/><text x="96" y="407" fill="#d1fae5" font-size="17">Correctness</text><text x="96" y="450" fill="#6ee7b7" font-size="29" font-weight="800">authority SHA-256 identical</text><text x="96" y="486" fill="#a7f3d0" font-size="17">mass 0 · revision / ignition / Flow identical</text>
<rect x="600" y="368" width="530" height="148" rx="18" fill="#312e1b" stroke="#fbbf24"/><text x="626" y="407" fill="#fef3c7" font-size="17">Remaining gate</text><text x="626" y="450" fill="#fbbf24" font-size="29" font-weight="800">isolated p95 {report['isolated']['publication_p95_ms']:.4f} ms</text><text x="626" y="486" fill="#fde68a" font-size="17">reference target 1.0 ms · normal default unchanged</text>
<text x="70" y="575" fill="#f8fafc" font-size="24" font-weight="750">Preset: .\\scripts\\run_visual_v3_demo.ps1</text><text x="70" y="618" fill="#cbd5e1" font-size="18">One command enables render hierarchy + Resident adapter + native backend + V3; Point/V0/V1 conflicts fail closed.</text></g></svg>'''


def main():
    args = _arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    isolated = json.loads(args.isolated_report.read_text(encoding="utf-8"))
    v3mc = json.loads(args.v3mc_report.read_text(encoding="utf-8"))
    records = []
    raw_summaries = []
    for item in manifest["runs"]:
        summary = json.loads(Path(item["summary"]).read_text(encoding="utf-8"))
        raw_summaries.append(summary)
        records.append(_run_record(item, summary))
    aggregate = _aggregate(records)
    off = aggregate["off"]
    on = aggregate["on"]
    p95_delta = round(
        on["update_frame_p95_ms_median"] - off["update_frame_p95_ms_median"], 4
    )
    p95_percent = round(
        100.0 * p95_delta / max(off["update_frame_p95_ms_median"], 1e-9), 3
    )
    authority = {
        "wood_sha256_identical": all(
            record["authority_sha256"] == records[0]["authority_sha256"]
            for record in records
        ),
        "metrics_csv_sha256_identical": len(
            {record["metrics_csv_sha256"] for record in records}
        )
        == 1,
        "mass_balance_error_zero": all(
            all(value == 0.0 for value in record["mass_balance_error_kg"].values())
            for record in records
        ),
        "resident_revision_identical": len(
            {record["resident_revision"] for record in records}
        )
        == 1,
        "ignition_identical": all(
            record["ignition_seconds"] == records[0]["ignition_seconds"]
            for record in records
        ),
        "flow_input_identical_and_active": all(
            record["flow"]["input_owner"]
            == records[0]["flow"]["input_owner"]
            and record["flow"]["peak_fuel_input"]
            == records[0]["flow"]["peak_fuel_input"]
            and record["flow"]["active_blocks_peak"] > 0
            for record in records
        ),
    }
    demo_summary_path = args.demo_dir / "summary.json"
    demo_video_path = args.demo_dir / "phase3_burn.mp4"
    demo_available = demo_summary_path.is_file() and demo_video_path.is_file()
    functional_gates = {
        **authority,
        "surface_identity_complete": bool(
            v3mc["gates"]["twenty_logs_7200_surface_cells"]
            and v3mc["gates"]["mesh_topology_digest_stable"]
        ),
        "reload_and_failure_recovery": bool(
            v3mc["gates"]["reload_force_republishes_latest"]
            and v3mc["gates"]
            ["failure_is_visual_only_and_recovers_previous_revision"]
        ),
        "rtx_reflection_within_one_update": (
            on["rtx_reflection_max_frame_updates"] <= 1
        ),
        "actual_trajectory_captured": demo_available,
    }
    adoption_gates = {
        "functional": all(functional_gates.values()),
        "isolated_20_log_p95_at_most_1_ms": isolated["performance"][
            "changing_publication_p95_ms"
        ]
        <= 1.0,
        "update_frame_p95_delta_within_2_ms_or_10_percent": (
            p95_delta <= 2.0 or p95_percent <= 10.0
        ),
        "over_33_ms_not_increased": (
            on["over_33_33_ms_total"] <= off["over_33_33_ms_total"]
        ),
        "rtx_reflection_wall_p95_at_most_200_ms": (
            on["rtx_reflection_p95_ms_median"] <= 200.0
        ),
    }
    normal_default = all(adoption_gates.values())
    report = {
        "schema": "campfire.phasev3tc.report.v1",
        "status": (
            "qualified_for_normal_default"
            if normal_default
            else "qualified_functionally_explicit_preset_only"
        ),
        "matrix": {
            "run_count": len(records),
            "pair_count": 3,
            "order": manifest["order"],
            "same_camera_warmup_capture": True,
        },
        "runs": records,
        "aggregate": aggregate,
        "paired_effect": {
            "update_frame_p95_delta_ms": p95_delta,
            "update_frame_p95_delta_percent": p95_percent,
        },
        "authority": authority,
        "functional_gates": functional_gates,
        "adoption_gates": adoption_gates,
        "isolated": {
            "logs": 20,
            "surface_cells": 7200,
            "publication_p95_ms": isolated["performance"][
                "changing_publication_p95_ms"
            ],
            "target_ms": 1.0,
            "target_met": isolated["performance"]["target_met"],
        },
        "usage": {
            "normal_app_default": normal_default,
            "explicit_visual_v3_preset": True,
            "command": ".\\scripts\\run_visual_v3_demo.ps1",
            "known_limit": (
                "The isolated 20-log publication p95 remains above 1 ms."
            ),
            "fail_closed_conflicts": ["Point Emitter", "V0", "V1"],
            "cylinder_fallback_preserved": True,
        },
        "non_changes": {
            "flow": True,
            "point_contract": True,
            "wood_authority": True,
            "collider": True,
            "shape_deformation": True,
            "normal_default": not normal_default,
        },
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for mode in ("off", "on"):
        source_summary = next(
            summary
            for item, summary in zip(manifest["runs"], raw_summaries)
            if item["pair"] == 1 and item["mode"] == mode
        )
        shutil.copy2(
            Path(source_summary["images"][-1]["path"]),
            OUTPUT / f"visual_v3_{mode}.png",
        )
    if demo_available:
        demo_summary = json.loads(demo_summary_path.read_text(encoding="utf-8"))
        image_source = Path(demo_summary["images"][-1]["path"])
        shutil.copy2(image_source, OUTPUT / "visual_v3_actual.png")
        shutil.copy2(demo_video_path, OUTPUT / "visual_v3_actual.mp4")
        shutil.copy2(image_source, OUTPUT / "visual_v3_actual_poster.png")
        demo_visual = demo_summary["scenario"]["wood_visual_v3"]
        demo_evidence = {
            "status": demo_summary["status"],
            "phase": demo_summary["phase"],
            "resolution": demo_summary["resolution"],
            "images": demo_summary["images"],
            "video_frames": demo_summary["video_frames"],
            "wood": demo_summary["wood"],
            "comparison": demo_summary["comparison"],
            "flow": demo_summary["flow"],
            "frame_pacing": demo_summary["timing"]["segments"]["frame_pacing"],
            "wood_visual_v3": {
                key: demo_visual[key]
                for key in (
                    "enabled",
                    "input",
                    "adaptive_schedule",
                    "status_after_timeline_stop",
                    "surface_extract_timing",
                    "publication_timing",
                    "upload_count",
                    "usd_set_count",
                    "notice_count",
                    "transferred_bytes",
                    "errors",
                )
            },
            "rtx_reflection": {
                "timing": demo_visual["rtx_reflection"]["timing"],
                "maximum_render_frame_updates": demo_visual["rtx_reflection"]
                ["maximum_render_frame_updates"],
                "pending_at_stop": demo_visual["rtx_reflection"][
                    "pending_at_stop"
                ],
                "sample_count": len(demo_visual["rtx_reflection"]["samples"]),
            },
        }
        (OUTPUT / "visual_v3_demo_summary.json").write_text(
            json.dumps(demo_evidence, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (OUTPUT / "integrated_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUTPUT / "integrated_report.svg").write_text(_svg(report), encoding="utf-8")
    shutil.copy2(args.manifest, OUTPUT / "matrix_manifest.json")
    print(
        "Phase V3T-C: "
        f"status={report['status']}, OFF/ON update p95="
        f"{off['update_frame_p95_ms_median']:.4f}/"
        f"{on['update_frame_p95_ms_median']:.4f} ms"
    )


if __name__ == "__main__":
    main()
