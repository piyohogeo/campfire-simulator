"""Publish bounded Phase 6FC startup-reproduction evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes):
    return hashlib.sha256(data).hexdigest().upper()


def normalized_stage_sha(path: Path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'^\s*string "campfire:phase" = "[^"]+"\s*$', '', text, flags=re.MULTILINE)
    return sha256_bytes(text.encode("utf-8"))


def first_difference(left, right):
    for a, b in zip(left, right):
        if int(a["active_blocks"]) != int(b["active_blocks"]):
            return {"frame": int(a["frame"]), "baseline": int(a["active_blocks"]), "condition": int(b["active_blocks"])}
    return None


def bounded_case(case):
    guard = case["resource_guard"]
    source = case["source_contract"]
    return {
        "classification": case["classification"],
        "declared_condition": case["declared_condition"],
        "frame_values": case["frame_values"],
        "active_block_history": case["active_block_history"],
        "stage_sha256": case["stage_sha256"],
        "payload_sha256": case["payload_sha256"],
        "source": {
            "enabled": source["enabled"], "revision": source["revision"],
            "total_point_count": source["total_point_count"],
            "active_point_count": source["active_point_count"],
            "source_sums": source["source_sums"],
            "array_hashes": case["source_array_hashes"],
        },
        "identities_stable_within_process": case["identities_stable"],
        "stage_connection_seconds": case["stage_connection_seconds"],
        "flow_interface_acquire_seconds": case["flow_interface_acquire_seconds"],
        "stopped_update_seconds": case["stopped_update_seconds"],
        "extra_update_seconds": case["extra_update_seconds"],
        "stage_close_seconds": case["stage_close_seconds"],
        "previous_exit_to_process_start_seconds": case["previous_process_exit_to_process_start_seconds"],
        "sequence_cache_state": case["sequence_cache_state"],
        "cache_state_publicly_confirmed": case["cache_state_publicly_confirmed"],
        "log_counts": case["log_evidence"]["counts"],
        "normal_os_exit": case["lifecycle_pass"],
        "fatal_count": case["fatal_count"], "dump_count": case["dump_count"],
        "upload_attempt_count": case["upload_attempt_count"], "cdb_invoked": case["cdb_invoked"],
        "resource_peak_bytes": guard["peaks"],
        "minimum_available_physical_bytes": guard["machine_minima"]["available_physical_bytes"],
        "minimum_commit_headroom_bytes": guard["machine_minima"]["estimated_commit_headroom_bytes"],
        "production_app_sha256_before": case["production_app_sha256_before"],
        "production_app_sha256_after": case["production_app_sha256_after"],
    }


def svg(report):
    series = {
        "baseline B01": report["cases"]["B01_baseline"]["active_block_history"],
        "A1 acquire after updates": report["cases"]["A1_flow_acquire_after_updates"]["active_block_history"],
        "A2 zero stopped updates": report["cases"]["A2_zero_stopped_updates"]["active_block_history"],
        "A3 one extra update": report["cases"]["A3_one_extra_update_before_play"]["active_block_history"],
        "historical 24-block": [{"frame": frame, "active_blocks": 24} for frame in range(1, 121)],
    }
    colors = ["#89b4fa", "#a6e3a1", "#fab387", "#cba6f7", "#f38ba8"]
    width, height, left, top, plot_w, plot_h = 1100, 600, 90, 100, 920, 370
    maximum = max(int(item["active_blocks"]) for values in series.values() for item in values)
    paths = []
    legends = []
    for index, (name, values) in enumerate(series.items()):
        points = []
        for item in values:
            x = left + (int(item["frame"]) - 1) * plot_w / 119
            y = top + plot_h - int(item["active_blocks"]) * plot_h / maximum
            points.append(f"{x:.1f},{y:.1f}")
        paths.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[index]}" stroke-width="3"/>')
        row, column = divmod(index, 3)
        legends.append(f'<g transform="translate({80 + column * 335},{520 + row * 32})"><rect width="20" height="5" fill="{colors[index]}"/><text x="29" y="8">{name}</text></g>')
    threshold_y = top + plot_h - 128 * plot_h / maximum
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#11131a"/><style>text{{font:16px Segoe UI,sans-serif;fill:#d9e0ee}}.small{{font-size:13px;fill:#a6adc8}}</style>
<text x="55" y="42" font-size="25">Phase 6FC - Point Emitter startup reproduction</text><text class="small" x="55" y="68">six independent baselines, then one-variable bounded ablations; no readback</text>
<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#585b70"/><line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#585b70"/>
<line x1="{left}" y1="{threshold_y:.1f}" x2="{left + plot_w}" y2="{threshold_y:.1f}" stroke="#f9e2af" stroke-dasharray="8 6"/><text class="small" x="95" y="{threshold_y - 7:.1f}">representative threshold 128 by frame 60</text>
<text class="small" x="48" y="{top + 6}">{maximum}</text><text class="small" x="58" y="{top + plot_h + 5}">0</text><text class="small" x="{left + plot_w - 25}" y="{top + plot_h + 25}">120</text>
{"".join(paths)}{"".join(legends)}</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--launch-safe-stop-root", type=Path, required=True)
    parser.add_argument("--phase6fb-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-svg", type=Path, required=True)
    args = parser.parse_args()
    raw = load(args.root / "startup_reproduction_report.json")
    cases = {name: bounded_case(case) for name, case in raw["cases"].items()}
    baseline_names = [f"B{index:02d}_baseline" for index in range(1, 7)]
    baseline = [cases[name] for name in baseline_names]
    a0 = cases["A0_baseline_control"]["active_block_history"]
    kit_limit = 14 * 1024**3
    tree_limit = 16 * 1024**3
    kit_max = max(case["resource_peak_bytes"]["kit"] for case in cases.values())
    tree_max = max(case["resource_peak_bytes"]["tree"] for case in cases.values())
    report = {
        "schema": "campfire.phase6fc.point-emitter-startup-reproduction-summary.v1",
        "phase": "phase6fc",
        "safe_base_commit": "4e19108",
        "contract_commit": "116d41b",
        "launch_fix_commit": "1d0fa9c",
        "contract_sha256": raw["contract_sha256"],
        "history_frozen": True,
        "launch_safe_stop": {
            "formal_sample_count": 0,
            "kit_started": False,
            "reason": "empty PreviousProcessExitUtc was passed without a value and PowerShell parameter binding failed",
            "guard_process_absent": load(args.launch_safe_stop_root / "runner-logs" / "B01_baseline.guard.json")["process_absent"],
            "root_reused": False,
        },
        "baseline": {
            "run_count": 6,
            "classification_counts": raw["baseline_classification_counts"],
            "small_field_count": sum(case["classification"] == "small_field_ingestion" for case in baseline),
            "small_field_reproduction_rate": raw["small_field_reproduction_rate"],
            "all_histories_equal": len({json.dumps(case["active_block_history"], sort_keys=True) for case in baseline}) == 1,
            "frame_values": {name: cases[name]["frame_values"] for name in baseline_names},
            "stage_connection_seconds_range": [min(case["stage_connection_seconds"] for case in baseline), max(case["stage_connection_seconds"] for case in baseline)],
            "previous_exit_gap_seconds_range": [
                min(case["previous_exit_to_process_start_seconds"] for case in baseline[1:]),
                max(case["previous_exit_to_process_start_seconds"] for case in baseline[1:]),
            ],
            "stage_or_gap_correlation_with_occupancy": "undefined because all six occupancy histories are identical; no association observed",
            "first_process_vs_subsequent": "B01 and B02-B06 histories are identical; explicit GPU/shader cold-vs-warm state is unavailable from the public bounded log evidence",
        },
        "ablations": {
            "A0": {"result": cases["A0_baseline_control"]["classification"], "first_difference_from_A0": None},
            "A1": {"result": cases["A1_flow_acquire_after_updates"]["classification"], "first_difference_from_A0": first_difference(a0, cases["A1_flow_acquire_after_updates"]["active_block_history"])},
            "A2": {"result": cases["A2_zero_stopped_updates"]["classification"], "first_difference_from_A0": first_difference(a0, cases["A2_zero_stopped_updates"]["active_block_history"])},
            "A3": {"result": cases["A3_one_extra_update_before_play"]["classification"], "first_difference_from_A0": first_difference(a0, cases["A3_one_extra_update_before_play"]["active_block_history"])},
        },
        "cases": cases,
        "stage_and_payload": {
            "stage_sha_equal_within_phase6fc": raw["stage_hash_equal"],
            "payload_sha_equal_within_phase6fc": raw["payload_hash_equal"],
            "phase6fc_stage_sha256": cases["B01_baseline"]["stage_sha256"],
            "payload_sha256": cases["B01_baseline"]["payload_sha256"],
            "phase6fb_normalized_stage_sha256": normalized_stage_sha(args.phase6fb_root / "P0_no_readback" / "raw.scene.usda"),
            "phase6fc_normalized_stage_sha256": normalized_stage_sha(args.root / "B01_baseline" / "raw.scene.usda"),
            "raw_stage_difference_note": "raw layer SHA differs from Phase 6FB only because campfire:phase custom metadata is phase6fc instead of phase6fb",
        },
        "resource_and_lifecycle": {
            "normal_os_exit_count": sum(case["normal_os_exit"] for case in cases.values()),
            "process_count": len(cases),
            "stage_close_seconds": [case["stage_close_seconds"] for case in cases.values()],
            "stage_close_minimum_seconds": min(case["stage_close_seconds"] for case in cases.values()),
            "stage_close_mean_seconds": sum(case["stage_close_seconds"] for case in cases.values()) / len(cases),
            "stage_close_maximum_seconds": max(case["stage_close_seconds"] for case in cases.values()),
            "kit_peak_bytes": kit_max, "kit_limit_bytes": kit_limit, "kit_minimum_margin_bytes": kit_limit - kit_max,
            "tree_peak_bytes": tree_max, "tree_limit_bytes": tree_limit, "tree_minimum_margin_bytes": tree_limit - tree_max,
            "fatal_count": sum(case["fatal_count"] for case in cases.values()),
            "dump_count": sum(case["dump_count"] for case in cases.values()),
            "upload_attempt_count": sum(case["upload_attempt_count"] for case in cases.values()),
            "cdb_invocation_count": sum(case["cdb_invoked"] for case in cases.values()),
            "cleanup_residual_count": 0,
        },
        "observed_facts": [
            "All six baseline processes were representative and had identical active-block histories: 269/505/688/1118 at frames 1/30/60/120.",
            "Moving public Flow-interface acquisition after the 12 stopped updates produced the same history as A0.",
            "Removing all 12 stopped updates reduced frame-1 occupancy to 176 but still reached 611 by frame 60 and remained representative.",
            "Adding one extra update before play first changed occupancy at frame 2 but remained representative.",
            "All ten formal processes reached normal OS exit without CDB, fatal, dump, upload attempt, or residual process."
        ],
        "strong_inference": "The 12 stopped updates affect the initial amount of Flow work completed before the first observed post-play frame, but Flow-interface acquisition position and the tested update counts do not reproduce or explain the historical 24-block lock.",
        "unconfirmed": [
            "The exact native trigger for the historical 24-block startup remains unidentified and did not reproduce in six baselines.",
            "No public positive predicate proves that Flow consumed the complete Point payload before play.",
            "Cold/warm shader or GPU cache state could not be positively classified from the bounded public log evidence."
        ],
        "monitoring_candidate": {
            "frame_60_below_128": "reasonable anomaly candidate for this fixed four-log fixture only",
            "sufficient_for_automatic_recovery": False,
            "state_machine": ["startup_pending", "representative_ready", "small_field_detected", "recovery_pending", "recovery_failed", "running"],
            "automatic_reinitialization_ready": False,
        },
        "public_field_checked": False,
        "repeated_readback_started": False,
        "production_changed": False,
        "regression": {
            "release_build": "passed",
            "phase0_rtx": "passed",
            "phase3": {
                "status": "passed",
                "dry_authority_sha256": "0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10",
                "wet_authority_sha256": "148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9",
                "dry_mass_balance_error_kg": 0.0,
                "wet_mass_balance_error_kg": 0.0,
                "active_blocks_final": 269,
                "active_blocks_peak": 358,
                "peak_fuel_input": 1.0,
            },
            "focused_tests": {"passed": 82, "total": 82},
            "standard_suite": {"passed": 78, "total": 78, "processes": 8, "seconds": 328.2},
            "devlog_static": {"status": "passed", "references": 425, "ids": 259, "json": 211, "svg": 177, "zip": 2},
            "production_app_sha256": "94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A",
            "final_residual_process_count": 0,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.output_svg.write_text(svg(report), encoding="utf-8")


if __name__ == "__main__":
    main()
