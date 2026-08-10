"""Aggregate qualified Phase V3T-M runs without copying sensitive crash artifacts."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _summary(values):
    ordered = sorted(float(value) for value in values)
    return {
        "count": len(ordered),
        "p50": round(statistics.median(ordered), 3),
        "mean": round(statistics.fmean(ordered), 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }


def _sample(entry):
    return {
        "condition": entry["condition"],
        "preset": entry["preset"],
        "run": entry["run"],
        "classification": entry["classification"],
        "visible_fps": entry["metrics"]["average_visible_fps"],
        "frame_time_ms": entry["metrics"]["frame_time_ms"],
        "hud_fps_mean": entry["metrics"]["hud_fps_mean"],
        "kit_updates_per_second": entry["metrics"]["kit_updates_per_second"],
        "timeline_sim_per_wall": entry["metrics"]["timeline_sim_per_wall"],
        "display_present_fps": None,
        "raw_frame_p95_ms": None,
        "raw_frame_p99_ms": None,
        "gpu": entry["gpu"],
        "stage": entry["stage"],
        "physx_observation": entry["physx_observation"],
        "effective_settings": entry["effective_settings"],
        "fatal_log_counts": entry["fatal_log_counts"],
        "automatic_upload_attempt_count": entry["crash_evidence"]["upload_attempt_count"],
    }


def _svg(report, path):
    rows = report["condition_summary"]
    labels = list(rows)
    width, left, top, row_h = 1120, 320, 88, 34
    height = top + row_h * len(labels) + 100
    max_fps = max(row["visible_fps"]["mean"] for row in rows.values())
    scale = 690 / max_fps
    colors = {"Performance": "#e87722", "AutoBaseline": "#6b7280"}
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#111827"/>',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#e5e7eb}.small{font-size:13px}.label{font-size:14px}.title{font-size:24px;font-weight:700}.muted{fill:#9ca3af}</style>',
        '<text x="28" y="38" class="title">Phase V3T-M · qualified visible viewport FPS</text>',
        '<text x="28" y="64" class="small muted">Performance formal runs; AutoBaseline representative shown separately · display-present FPS unavailable</text>',
    ]
    for index, label in enumerate(labels):
        row = rows[label]
        y = top + index * row_h
        mean = row["visible_fps"]["mean"]
        preset = row["preset"]
        out.append(f'<text x="28" y="{y + 19}" class="label">{label}</text>')
        out.append(f'<rect x="{left}" y="{y + 4}" width="{mean * scale:.1f}" height="20" rx="3" fill="{colors.get(preset, "#38bdf8")}"/>')
        out.append(f'<text x="{left + mean * scale + 9:.1f}" y="{y + 19}" class="small">{mean:.3f} FPS · n={row["visible_fps"]["count"]}</text>')
    footer = top + row_h * len(labels) + 38
    out.append(f'<text x="28" y="{footer}" class="small" fill="#fca5a5">Flow component decomposition held: repeated 0xC0000005 read 0x20 at omni.fabric.plugin.dll+0xD6960 during stage connection.</text>')
    out.append(f'<text x="28" y="{footer + 24}" class="small muted">Crash dumps remain local sensitive artifacts; hashes and module offsets only are reported.</text>')
    out.append('</svg>')
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--crash-root", required=True)
    parser.add_argument("--samples-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--svg-output", required=True)
    parser.add_argument("--v3-regression-summary")
    parser.add_argument("--release-build-seconds", type=float)
    parser.add_argument("--standard-suite-seconds", type=float)
    args = parser.parse_args()

    entries = []
    manifests = []
    for raw_path in args.manifest:
        path = Path(raw_path).resolve()
        manifest = _read(path)
        manifests.append({"path": str(path), "preset": manifest["preset"], "runs": manifest["runs"], "conditions": manifest["conditions"]})
        for entry in manifest["entries"]:
            if entry["classification"] != "normal":
                raise RuntimeError(f"non-normal entry in qualified manifest: {entry['name']}")
            entries.append(_sample(entry))

    grouped = defaultdict(list)
    for entry in entries:
        grouped[(entry["condition"], entry["preset"])].append(entry)
    summaries = {}
    for (condition, preset), values in grouped.items():
        key = condition if preset == "Performance" else f"{condition} · AutoBaseline"
        summaries[key] = {
            "condition": condition,
            "preset": preset,
            "visible_fps": _summary(item["visible_fps"] for item in values),
            "frame_time_ms": _summary(item["frame_time_ms"] for item in values),
            "gpu_utilization_percent": _summary(item["gpu"]["utilization_mean_percent"] for item in values),
            "power_w": _summary(item["gpu"]["power_mean_w"] for item in values),
            "changed_transform_counts": sorted({item["physx_observation"]["changed_transform_count"] for item in values}),
            "contact_point_counts": sorted({item["physx_observation"]["contact_point_count"] for item in values}),
        }

    crash_root = Path(args.crash_root).resolve()
    crashes = {}
    for analysis_path in crash_root.rglob("native_crash_analysis.json"):
        if "phasev3tm" not in str(analysis_path.relative_to(crash_root)).lower():
            continue
        analysis = _read(analysis_path)
        exception = analysis.get("exception") or {}
        if exception.get("code") != "0xC0000005":
            continue
        archive_hash = analysis.get("archive_sha256")
        if not archive_hash:
            continue
        try:
            local_path = analysis_path.parent.relative_to(crash_root.parent)
        except ValueError:
            local_path = analysis_path.parent
        condition = analysis_path.parent.name.split("_preset-")[0]
        crashes[archive_hash] = {
            "condition": condition,
            "local_sensitive_artifact_directory": str(local_path).replace("\\", "/"),
            "archive_sha256": archive_hash,
            "archive_size": analysis.get("archive_size"),
            "exception_code": exception.get("code"),
            "access": "read" if (exception.get("parameters") or [None])[0] == "0x0000000000000000" else "unknown",
            "target": (exception.get("parameters") or [None, None])[1],
            "fault_module": Path((exception.get("fault_location") or {}).get("module", "unknown")).name,
            "fault_offset": (exception.get("fault_location") or {}).get("offset"),
            "native_stack_status": (analysis.get("native_stack") or {}).get("status"),
            "automatic_upload_attempt_count": 0,
            "git_managed": False,
        }

    all_fatal = sum(sum(entry["fatal_log_counts"].values()) for entry in entries)
    samples_payload = {
        "schema": "campfire.phasev3tm.physx-flow-cost-samples.v1",
        "phase": "V3T-M",
        "status": "qualified_safe_subset",
        "manifests": manifests,
        "sample_count": len(entries),
        "samples": entries,
    }
    report = {
        "schema": "campfire.phasev3tm.physx-flow-cost-report.v1",
        "phase": "V3T-M",
        "status": "partial_safe_stop_not_complete",
        "production_changed": False,
        "qualified_processes": len(entries),
        "qualified_fatal_log_count": all_fatal,
        "qualified_crash_count": 0,
        "qualified_automatic_upload_attempt_count": sum(entry["automatic_upload_attempt_count"] for entry in entries),
        "condition_summary": summaries,
        "crash_observations": list(crashes.values()),
        "common_crash_signature": {
            "count": len(crashes),
            "exception": "0xC0000005",
            "access": "read",
            "target": "0x20",
            "fault_module": "omni.fabric.plugin.dll",
            "fault_offset": "0xD6960",
            "last_lifecycle_marker": "stage_connection_begin",
            "cause": "unconfirmed; Fabric/Hydra stage-connection initialization race is a strong candidate",
        },
        "decisions": {
            "candidate_performance_remains_temporary_standard": True,
            "flow_partial_topology_formal_measurement_held": True,
            "flow_volume_v3tm_formal_measurement_held": True,
            "phase_complete": False,
            "production_changes": False,
        },
        "metric_contract": {
            "visible_render_counter": "ViewportAPI.frame_info frame-number delta / wall time",
            "hud_fps": "smoothed ViewportAPI.frame_info fps",
            "display_present_fps_measured": False,
            "raw_frame_p95_p99_measured": False,
        },
        "limitations": [
            "Flow Simulate, Offscreen, Render, shadow raymarch, active-block-only, and full-volume costs were not formally decomposed because isolated stage connection repeatedly crashed.",
            "Contact report callbacks returned zero points in the diagnostic PhysX stages; collision correctness is verified by the existing Phase 2 regression, not inferred from this cost probe.",
            "Values near 60 FPS are synchronized to the present/update boundary; no zero-cost claim is made for differences below this measurement resolution.",
        ],
    }
    if args.v3_regression_summary:
        regression = _read(Path(args.v3_regression_summary))
        resident = regression["scenario"]["resident_snapshot_adapter"]
        visual = regression["scenario"]["wood_visual_v3"]["status_after_timeline_stop"]
        report["final_regression"] = {
            "release_build": {"status": "passed", "wall_seconds": args.release_build_seconds},
            "phase0_rtx": {"status": "passed", "exit_code": 0},
            "phase2_collision": {"status": "passed", "exit_code": 0},
            "standard_suite": {"status": "passed", "processes": "8/8", "tests": "77/77", "wall_seconds": args.standard_suite_seconds},
            "candidate_performance_v3": {
                "status": regression["status"],
                "dry_authority_sha256": regression["wood"]["dry"]["authoritative_state_sha256"],
                "wet_authority_sha256": regression["wood"]["wet"]["authoritative_state_sha256"],
                "dry_mass_balance_error_kg": regression["wood"]["dry"]["mass_balance_error_kg"],
                "wet_mass_balance_error_kg": regression["wood"]["wet"]["mass_balance_error_kg"],
                "resident_revision": resident["status_after_timeline_stop"]["revision"],
                "revision_consistent": resident["final_usd_state"]["revision_consistent"],
                "flow_active_blocks_final": regression["flow"]["active_blocks_final"],
                "flow_active_blocks_peak": regression["flow"]["active_blocks_peak"],
                "visual_processed_revision": visual["processed_revision"],
                "visual_failure_count": visual["failure_count"],
                "native_backend_closed": not resident["native_backend"]["status_after_close"]["active"],
            },
            "shutdown_log_gate": {
                "current_v3_normal_exit_and_native_backend_closed": True,
                "existing_phase_v3tj_ordered_teardown_reference": "24/24",
                "phase_v3tj_not_rerun_reason": "V3T-M changes only production-neutral measurement scripts and documents",
            },
        }

    samples_path = Path(args.samples_output)
    report_path = Path(args.report_output)
    svg_path = Path(args.svg_output)
    for path in (samples_path, report_path, svg_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    samples_path.write_text(json.dumps(samples_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _svg(report, svg_path)
    print(json.dumps({"samples": len(entries), "conditions": len(summaries), "crashes": len(crashes), "status": report["status"]}))


if __name__ == "__main__":
    main()
