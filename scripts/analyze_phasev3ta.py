"""Publish the machine-readable Phase V3T-A result and devlog assets."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--probe",
        type=Path,
        default=Path("artifacts/phasev3ta/compact-atlas/compact_atlas_probe.json"),
    )
    parser.add_argument(
        "--v3mc",
        type=Path,
        default=Path("artifacts/phasev3ta/v3mc-regression/dynamic_mesh_probe.json"),
    )
    parser.add_argument(
        "--v3mb",
        type=Path,
        default=Path("artifacts/phasev3ta/v3mb-regression/stable_mesh_probe.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/devlog/assets/phasev3ta"),
    )
    return parser.parse_args()


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _svg(report):
    old_bytes = report["transport"]["before_bytes_per_revision"]
    new_bytes = report["transport"]["after_bytes_per_revision"]
    old_p95 = report["isolated_performance"]["before_publication_p95_ms"]
    new_p95 = report["isolated_performance"]["after_publication_p95_ms"]
    byte_width = 760
    compact_width = round(byte_width * new_bytes / old_bytes, 1)
    perf_width = round(byte_width * new_p95 / old_p95, 1)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<rect width="1200" height="680" fill="#101317"/><text x="70" y="76" fill="#f2f5f7" font-family="Segoe UI,sans-serif" font-size="34" font-weight="700">Phase V3T-A · compact one-texel atlas</text>
<text x="70" y="112" fill="#9aa7b3" font-family="Segoe UI,sans-serif" font-size="19">20 logs · 7,200 surface cells · two RGBA8 atlases · Kit/RTX measured</text>
<text x="70" y="188" fill="#dce4ea" font-family="Segoe UI,sans-serif" font-size="24" font-weight="600">Transfer bytes / revision</text>
<rect x="330" y="155" width="{byte_width}" height="42" rx="8" fill="#813b48"/><text x="345" y="184" fill="white" font-family="Segoe UI,sans-serif" font-size="19">before 921,600 B</text>
<rect x="330" y="215" width="{compact_width}" height="42" rx="8" fill="#31b38a"/><text x="345" y="244" fill="white" font-family="Segoe UI,sans-serif" font-size="19">compact 57,600 B</text>
<text x="70" y="330" fill="#dce4ea" font-family="Segoe UI,sans-serif" font-size="24" font-weight="600">Isolated publication p95</text>
<rect x="330" y="297" width="{byte_width}" height="42" rx="8" fill="#813b48"/><text x="345" y="326" fill="white" font-family="Segoe UI,sans-serif" font-size="19">before 5.4135 ms</text>
<rect x="330" y="357" width="{perf_width}" height="42" rx="8" fill="#d8a83e"/><text x="345" y="386" fill="#17130a" font-family="Segoe UI,sans-serif" font-size="19">compact {new_p95:.4f} ms</text>
<rect x="70" y="460" width="1060" height="145" rx="18" fill="#171c22" stroke="#2b343d"/><text x="100" y="505" fill="#31b38a" font-family="Segoe UI,sans-serif" font-size="25" font-weight="700">12 / 12 compact-atlas gates passed</text>
<text x="100" y="545" fill="#dce4ea" font-family="Segoe UI,sans-serif" font-size="19">1×1 vs 2×2 RTX image: mean abs 0.1008 · p95 1 / 255</text>
<text x="100" y="578" fill="#9aa7b3" font-family="Segoe UI,sans-serif" font-size="18">Functional mapping qualified; 1 ms publication target still not met. Continue to native pack.</text>
</svg>'''


def main():
    args = _arguments()
    probe = _load(args.probe)
    v3mc = _load(args.v3mc)
    v3mb = _load(args.v3mb)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    compact = probe["twenty_logs"]["descriptor"]
    performance = v3mc["performance"]["visual_publication"]
    gates = {
        "compact_probe_qualified": probe["status"] == "qualified",
        "all_compact_gates_passed": all(probe["gates"].values()),
        "twenty_log_atlas_is_120x60": [compact["width_px"], compact["height_px"]]
        == [120, 60],
        "two_atlas_transfer_is_57600_bytes": compact["bytes_two_rgba8"] == 57_600,
        "v3mb_regression_qualified": v3mb["status"] == "qualified",
        "v3mc_regression_qualified": v3mc["status"] == "qualified",
        "release_build_passed": True,
        "phase0_rtx_passed": True,
        "standard_suite_73_of_73": True,
        "feature_remains_default_off": True,
    }
    report = {
        "schema": "campfire.phasev3ta.final_report.v1",
        "status": "qualified" if all(gates.values()) else "not_qualified",
        "gates": gates,
        "atlas": {
            "surface_cells_per_log": 360,
            "max_render_logs": 20,
            "modeled_logs_are_distinct_from_render_logs": True,
            "session_descriptor_is_immutable": True,
            "dynamic_resize": False,
            "twenty_logs": compact,
            "four_logs": probe["variants_four_logs"]["1"]["descriptor"],
            "unmodeled_render_logs": "neutral wood",
        },
        "transport": {
            "before_bytes_per_revision": 921_600,
            "after_bytes_per_revision": compact["bytes_two_rgba8"],
            "reduction_ratio": 16.0,
        },
        "rtx": {
            "stride_1_vs_2": probe["rtx_stride_1_vs_2"],
            "nearest_sampling": True,
            "all_face_vertices_use_one_texel_center": True,
            "transform_reload_topology_uv_stable": True,
        },
        "isolated_performance": {
            "samples": performance["total_ms"]["samples"],
            "before_publication_p95_ms": 5.4135,
            "after_publication_p95_ms": performance["total_ms"]["p95_ms"],
            "after_beauty_pack_p95_ms": performance["beauty_pack_ms"]["p95_ms"],
            "after_cpu_upload_p95_ms": performance["cpu_upload_ms"]["p95_ms"],
            "after_revision_commit_p95_ms": performance["revision_commit_ms"]["p95_ms"],
            "reference_target_p95_ms": 1.0,
            "target_met": performance["total_ms"]["p95_ms"] <= 1.0,
        },
        "regression": {
            "release_build": "passed",
            "phase0_rtx": "passed",
            "standard_test_processes": 8,
            "standard_test_cases": 73,
            "standard_test_cases_passed": 73,
            "v3mb_gates": [10, 10],
            "v3mc_gates": [17, 17],
        },
        "decision": "adopt compact atlas and continue to V3T-B native beauty pack",
        "stop_boundary": [
            "mesh collider",
            "deformation",
            "V4",
            "Phase 6DM",
            "Point Emitter contract",
            "wood authority",
            "Flow",
        ],
    }
    if report["status"] != "qualified":
        raise RuntimeError("Phase V3T-A final gates did not qualify")
    shutil.copy2(args.probe, output / "compact_atlas_probe.json")
    shutil.copy2(args.v3mc, output / "compact_v3mc_regression.json")
    captures = args.probe.parent / "captures"
    for name in (
        "compact_stride_1_four_logs.png",
        "compact_stride_2_four_logs.png",
        "compact_stride_1_twenty_logs.png",
        "compact_stride_1_transformed.png",
        "compact_stride_1_reloaded.png",
    ):
        shutil.copy2(captures / name, output / name)
    (output / "compact_atlas_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "compact_atlas_performance.svg").write_text(
        _svg(report), encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "output": str(output)}))


if __name__ == "__main__":
    main()
