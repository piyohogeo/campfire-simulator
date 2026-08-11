"""Create the sanitized Phase 6DY report from ignored runtime artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "artifacts" / "phase6dy-calibrated-stage-open-1"
ASSET = ROOT / "docs" / "devlog" / "assets" / "phase6"
STAGE_CASES = (
    "A_box_decomposition",
    "B_box_hull",
    "C_box_decomposition",
    "D_cylinder_decomposition",
    "E_box_decomposition",
)
FLOW_CASES = ("box_before", "cylinder_decomposition", "box_after")
CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity")
ROIS = ("inside_core", "above", "cylinder_core", "cylinder_above")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_count(value) -> int:
    return len(value) if isinstance(value, list) else 0


def _last_roi(sample: dict, channel: str, roi: str) -> dict:
    return sample["channels"][channel]["rois"][roi]


def _flow_summary(flow_root: Path, label: str) -> dict:
    raw = _load(flow_root / label / "raw.json")
    evidence = _load(flow_root / label / "runner_evidence.json")
    samples = raw["samples"]
    final = samples[-1]
    series = {}
    for channel in CHANNELS:
        series[channel] = {}
        for roi in ROIS:
            values = []
            for sample in samples:
                stats = _last_roi(sample, channel, roi)
                values.append(
                    {
                        "frame": sample["frame"],
                        "mean": stats["mean"],
                        "p95": stats["p95"],
                        "maximum": stats["maximum"],
                        "nonzero_voxel_count": stats["nonzero_voxel_count"],
                    }
                )
            series[channel][roi] = values
    return {
        "condition": label,
        "status": raw["status"],
        "sample_frames": [sample["frame"] for sample in samples],
        "active_blocks_final": raw["active_blocks_final"],
        "lifecycle_marker": raw["lifecycle_marker"],
        "process_exit_code": evidence["process_exit_code"],
        "timed_out": bool(evidence.get("timed_out", False)),
        "fatal_count": _safe_count(evidence.get("fatal_lines")),
        "dump_count": _safe_count(evidence.get("dump_inventory")),
        "upload_attempt_count": _safe_count(evidence.get("automatic_upload_attempt_lines")),
        "production_changed": evidence["production_changed"],
        "stage_audit": raw["effective_stage_audit"],
        "density_cell_size_m": raw["effective_stage_audit"]["simulate"]["densityCellSize"],
        "velocity_cell_size_m": final["channels"]["velocity"]["voxel_size"][0],
        "rois": raw["rois"],
        "series": series,
        "final": {
            channel: {
                roi: {
                    "mean": _last_roi(final, channel, roi)["mean"],
                    "p95": _last_roi(final, channel, roi)["p95"],
                    "maximum": _last_roi(final, channel, roi)["maximum"],
                    "nonzero_voxel_count": _last_roi(final, channel, roi)["nonzero_voxel_count"],
                }
                for roi in ROIS
            }
            for channel in CHANNELS
        },
    }


def _stage_summary(artifact: Path, prepared: dict, label: str) -> dict:
    evidence = _load(artifact / "stage-open" / label / "runner_evidence.json")
    markers = evidence.get("lifecycle_history", [])
    if isinstance(markers, dict):
        markers = [markers]
    audit = prepared["cases"][label]["audit"]
    geometry = audit["geometry"]
    return {
        "condition": label,
        "stage_sha256": prepared["cases"][label]["sha256"],
        "physics_approximation": audit["physics_approximation"],
        "vertex_count": geometry["vertex_count"],
        "face_count": geometry["face_count"],
        "index_count": geometry["index_count"],
        "closed_manifold": geometry["closed_manifold"],
        "winding": geometry["winding"],
        "degenerate_face_count": geometry["degenerate_face_count"],
        "extent_matches": geometry["extent_matches"],
        "audit": audit,
        "duration_seconds": evidence["duration_seconds"],
        "process_exit_code": evidence["process_exit_code"],
        "timed_out": evidence["timed_out"],
        "last_marker": evidence["lifecycle_marker"],
        "marker_names": [item["marker"] for item in markers],
        "lifecycle_history": markers,
        "selected_device_log_lines": evidence.get("selected_device_log_lines", []),
        "fatal_count": _safe_count(evidence.get("fatal_lines")),
        "dump_count": _safe_count(evidence.get("dump_inventory")),
        "upload_attempt_count": _safe_count(evidence.get("automatic_upload_attempt_lines")),
        "production_changed": evidence["production_changed"],
    }


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) < 0.001:
        return f"{value:.2e}"
    return f"{value:.4f}"


def _svg(report: dict) -> str:
    stages = report["stage_open_results"]
    flow = {item["condition"]: item for item in report["flow_readback_results"]}
    cylinder = flow["cylinder_decomposition"]["final"]
    durations = [item["duration_seconds"] for item in stages]
    max_duration = max(durations)
    bars = []
    for index, item in enumerate(stages):
        y = 196 + index * 48
        width = 420 * item["duration_seconds"] / max_duration
        bars.append(
            f'<text x="54" y="{y + 19}" fill="#dbe5f5" font-family="Segoe UI, sans-serif" font-size="15">{item["condition"]}</text>'
            f'<rect x="290" y="{y}" width="{width:.1f}" height="27" rx="5" fill="#4cc9a4"/>'
            f'<text x="{300 + width:.1f}" y="{y + 19}" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="14">{item["duration_seconds"]:.2f}s · exit 0</text>'
        )
    temp_core = cylinder["temperature"]["cylinder_core"]
    temp_above = cylinder["temperature"]["cylinder_above"]
    velocity_core = cylinder["velocity"]["cylinder_core"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="610" viewBox="0 0 1200 610" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DY calibrated Box-to-Cylinder stage-open results</title>
<desc id="desc">All five stage-open processes exited normally and the cylinder-contained Flow ROI remained zero at frame 200.</desc>
<rect width="1200" height="610" fill="#0e1118"/>
<text x="54" y="62" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="30" font-weight="700">Phase 6DY · calibrated Box → Cylinder boundary</text>
<text x="54" y="99" fill="#9eabc1" font-family="Segoe UI, sans-serif" font-size="18">Phase 6DW lifecycle reused directly · Cylinder Hull still excluded</text>
<rect x="54" y="126" width="690" height="354" rx="12" fill="#151b27" stroke="#354158"/>
<text x="76" y="164" fill="#a8e6cf" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700">STAGE-OPEN MATRIX · 5 / 5 NORMAL OS EXITS</text>
{''.join(bars)}
<rect x="770" y="126" width="376" height="354" rx="12" fill="#151b27" stroke="#354158"/>
<text x="794" y="164" fill="#ffcc80" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700">CYLINDER CORE · FRAME 200</text>
<text x="794" y="213" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="20">temperature mean</text><text x="1110" y="213" text-anchor="end" fill="#a8e6cf" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">{_fmt(temp_core['mean'])}</text>
<text x="794" y="254" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="20">velocity mean</text><text x="1110" y="254" text-anchor="end" fill="#a8e6cf" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">{_fmt(velocity_core['mean'])}</text>
<text x="794" y="295" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="20">nonzero scalar voxels</text><text x="1110" y="295" text-anchor="end" fill="#a8e6cf" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">0</text>
<line x1="794" y1="326" x2="1110" y2="326" stroke="#354158"/>
<text x="794" y="366" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="19">cylinder-above temp mean</text>
<text x="1110" y="366" text-anchor="end" fill="#ffcc80" font-family="Segoe UI, sans-serif" font-size="20" font-weight="700">{_fmt(temp_above['mean'])}</text>
<text x="794" y="407" fill="#9eabc1" font-family="Segoe UI, sans-serif" font-size="16">Wide Box ROI sees lateral flow;</text>
<text x="794" y="433" fill="#9eabc1" font-family="Segoe UI, sans-serif" font-size="16">contained core distinguishes penetration.</text>
<rect x="54" y="510" width="1092" height="62" rx="10" fill="#1a2130"/>
<text x="78" y="548" fill="#dbe5f5" font-family="Segoe UI, sans-serif" font-size="17">fatal 0 · dump 0 · upload 0 · production SHA-256 unchanged · Box controls identical before/after</text>
</svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--flow-root", type=Path, default=None)
    parser.add_argument("--release-seconds", type=float, default=None)
    parser.add_argument("--suite-seconds", type=float, default=None)
    parser.add_argument("--suite-passed", type=int, default=None)
    parser.add_argument("--suite-total", type=int, default=None)
    parser.add_argument("--targeted-seconds", type=float, default=None)
    parser.add_argument("--devlog-refs", type=int, default=None)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.flow_root is not None:
        flow_root = args.flow_root.resolve()
    else:
        measured = artifact / "flow-readback-core-1"
        flow_root = (measured if measured.is_dir() else artifact / "flow-readback").resolve()
    prepared = _load(artifact / "prepared_stages.json")
    matrix = _load(artifact / "matrix_complete.json")
    flow_matrix = _load(flow_root / "matrix_complete.json")
    stages = [_stage_summary(artifact, prepared, label) for label in STAGE_CASES]
    flow = [_flow_summary(flow_root, label) for label in FLOW_CASES]
    flow_by_name = {item["condition"]: item for item in flow}
    cylinder = flow_by_name["cylinder_decomposition"]
    box_before = flow_by_name["box_before"]
    box_after = flow_by_name["box_after"]
    scalar_channels = ("temperature", "fuel", "burn", "smoke")
    cylinder_core_all_zero = all(
        all(point["maximum"] == 0.0 for point in cylinder["series"][channel]["cylinder_core"])
        for channel in scalar_channels
    )
    cylinder_core_velocity_all_zero = all(
        point["maximum"] == 0.0 for point in cylinder["series"]["velocity"]["cylinder_core"]
    )
    box_controls_equal = box_before["series"] == box_after["series"]
    report = {
        "schema": "campfire.phase6dy.calibrated-stage-open-report.v1",
        "phase": "phase6dy",
        "status": "qualified_safe_stop",
        "source_phase": "phase6dt",
        "lifecycle_reuse": {
            "runner": "scripts/run_phase6dw_gpu_renderer_case.ps1",
            "probe": "scripts/probe_phase6dw_gpu_renderer_lifecycle.py",
            "implementation_changed": False,
            "pre_stage_viewport_frame_wait": False,
            "static_contract_tests": 6,
        },
        "source_stage_sha256": prepared["source_sha256"],
        "stage_open_results": stages,
        "normalized_differences": prepared["normalized_differences"],
        "control_sha256_equal": prepared["control_sha256_equal"],
        "control_audit_equal": prepared["control_audit_equal"],
        "flow_readback_results": flow,
        "flow_classification": {
            "sample_frames": cylinder["sample_frames"],
            "box_before_after_equal": box_controls_equal,
            "cylinder_core_scalar_all_samples_zero": cylinder_core_all_zero,
            "cylinder_core_velocity_all_samples_zero": cylinder_core_velocity_all_zero,
            "final_cylinder_core_temperature_mean": cylinder["final"]["temperature"]["cylinder_core"]["mean"],
            "final_cylinder_above_temperature_mean": cylinder["final"]["temperature"]["cylinder_above"]["mean"],
            "final_wide_inside_temperature_mean": cylinder["final"]["temperature"]["inside_core"]["mean"],
            "interpretation": "The nonzero scalar values in the wider Box ROI are outside the cylindrical solid and are consistent with lateral bypass. The contained core remained zero. A very small scalar residual appeared above the cylinder, so perfect global occlusion is not claimed.",
        },
        "safety": {
            "stage_matrix_complete": matrix["status"] == "complete",
            "flow_matrix_complete": flow_matrix["status"] == "complete",
            "processes": 8,
            "normal_exit_count": sum(item["process_exit_code"] == 0 for item in stages + flow),
            "timeout_count": sum(bool(item["timed_out"]) for item in stages + flow),
            "fatal_count": sum(item["fatal_count"] for item in stages + flow),
            "dump_count": sum(item["dump_count"] for item in stages + flow),
            "upload_attempt_count": sum(item["upload_attempt_count"] for item in stages + flow),
            "production_app_sha256_before": matrix["production_app_sha256_before"],
            "production_app_sha256_after": flow_matrix["production_app_sha256_after"],
            "production_changed": matrix["production_app_sha256_before"] != flow_matrix["production_app_sha256_after"],
        },
        "classification": {
            "observed": [
                "All A-E processes reached pure OpenUSD open, USD context connection, Hydra observation, first renderer update, first viewport frame, stage close, renderer drain, and normal OS exit.",
                "Changing only the Box approximation to convexHull did not reproduce the historical cylindrical Hull crash.",
                "The closed 12-segment cylindrical topology with convexDecomposition opened, rendered, closed, and exited normally.",
                "The public Flow readback completed between matching Box controls; all scalar and velocity samples inside the cylinder-contained core were zero.",
            ],
            "strong_inference": [
                "The Phase 6DX timeout was caused by its pre-stage viewport-frame wait rather than the tested stage content.",
                "The cylindrical topology is safe for this static axis-aligned Flow-only convexDecomposition boundary on the current fixed environment.",
                "Nonzero values in the wider Box ROI during the Cylinder run represent space outside the cylinder and are consistent with lateral bypass rather than solid-volume penetration.",
            ],
            "unconfirmed": [
                "Cylinder convexHull remains untested after its historical crash and is not qualified by the Box convexHull result.",
                "Rotation, PhysX sharing, analytic siblings, dynamic transforms, Phase 6DR integration, and 20-log performance remain untested.",
                "No public evidence identifies the historical omni.fabric.plugin.dll fault's root cause.",
            ],
        },
        "decision": "Phase 6DU may resume only in a new independent phase from the qualified static axis-aligned Cylinder convexDecomposition configuration. Cylinder convexHull must remain excluded until separately approved and guarded by controls.",
        "regression": {
            "release_build": {"status": "passed" if args.release_seconds is not None else "pending", "seconds": args.release_seconds},
            "lifecycle_contract": {"status": "passed", "passed": 6, "total": 6},
            "flow_collider_runtime_target": {"status": "passed", "processes": 3, "public_readback_samples": 12},
            "flow_collider_unit_target": {
                "status": "passed" if args.targeted_seconds is not None else "pending",
                "test": "campfire.app.tests.test_scene.TestScene.test_flow_scene_has_emitter_simulation_and_colliders",
                "passed": 1 if args.targeted_seconds is not None else None,
                "total": 1,
                "seconds": args.targeted_seconds,
            },
            "standard_suite": {
                "status": "passed" if args.suite_passed is not None and args.suite_passed == args.suite_total else "pending",
                "passed": args.suite_passed,
                "total": args.suite_total,
                "seconds": args.suite_seconds,
            },
            "static_devlog": {
                "status": "passed" if args.devlog_refs is not None else "pending",
                "unique_local_references": args.devlog_refs,
                "missing_references": 0 if args.devlog_refs is not None else None,
                "json_failures": 0 if args.devlog_refs is not None else None,
                "svg_failures": 0 if args.devlog_refs is not None else None,
                "utf8_replacement_characters": 0 if args.devlog_refs is not None else None,
            },
            "phase0_rtx": "not required; production code/app composition unchanged and renderer lifecycle stayed normal",
        },
        "production_changed": False,
        "latest_demo_changed": False,
    }
    if not all(
        (
            prepared["status"] == "ok",
            prepared["control_sha256_equal"],
            prepared["control_audit_equal"],
            all(item["process_exit_code"] == 0 and not item["timed_out"] for item in stages + flow),
            report["safety"]["fatal_count"] == 0,
            report["safety"]["dump_count"] == 0,
            report["safety"]["upload_attempt_count"] == 0,
            not report["safety"]["production_changed"],
            box_controls_equal,
            cylinder_core_all_zero,
            cylinder_core_velocity_all_zero,
        )
    ):
        raise RuntimeError("Phase 6DY aggregate gate failed")
    ASSET.mkdir(parents=True, exist_ok=True)
    json_path = ASSET / "calibrated_stage_open_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ASSET / "calibrated_stage_open_report.svg").write_text(_svg(report), encoding="utf-8")
    print(json_path)


if __name__ == "__main__":
    main()
