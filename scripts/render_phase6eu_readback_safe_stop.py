"""Publish the bounded Phase 6EU safe-stop summary and SVG from an artifact root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


GIB = 1024 ** 3


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-svg", type=Path, required=True)
    args = parser.parse_args()
    report = _load(args.root / "readback_lifetime_report.json")
    state = _load(args.root / "incremental_state.json")
    row = report["rows"][0]
    evidence = _load(args.root / "calibration/run01/R0_none/runner_evidence.json")
    guard = _load(args.root / "runner-logs/run01_R0_none.guard.json")
    marker = row["marker_summary"]
    diagnostic = (evidence.get("shutdown_monitor") or {}).get("diagnostic") or {}
    public = {
        "schema": "campfire.phase6eu.nanovdb-readback-safe-stop.v1",
        "phase": "phase6eu",
        "status": "safe_stop",
        "phase6es_frozen": True,
        "phase6et_frozen": True,
        "contract_sha256": report["contract_sha256"],
        "production_app_sha256_before": state["production_app_sha256_before"],
        "production_app_sha256_after": state["production_app_sha256_current"],
        "production_changed": state["production_changed"],
        "formal_population": {"attempted": 1, "normal_exit": 0, "expected": 27},
        "active_condition": "baseline/run01/R0_none",
        "stop_reason": guard["stop_reason"],
        "last_probe_marker": evidence["lifecycle_marker"],
        "probe_status": evidence["probe_status"],
        "lifecycle_status": evidence["outcome"]["lifecycle_status"],
        "normal_os_exit": False,
        "known_ngx_signature_matched": bool((evidence.get("shutdown_monitor") or {}).get("known_signature_matched")),
        "cdb_all_thread_stack_observed": bool((diagnostic.get("debugger") or {}).get("all_thread_stack_observed")),
        "resource": {
            "kit_peak_bytes": row["kit_peak_bytes"],
            "kit_peak_gib": row["kit_peak_gib"],
            "tree_peak_bytes": row["tree_peak_bytes"],
            "runner_peak_bytes": row["runner_peak_bytes"],
            "diagnostic_peak_bytes": row["diagnostic_peak_bytes"],
            "minimum_available_physical_bytes": guard["machine_minima"]["available_physical_bytes"],
            "minimum_commit_headroom_bytes": guard["machine_minima"]["estimated_commit_headroom_bytes"],
            "fixed_kit_limit_bytes": guard["limits"]["kit_private_bytes"],
            "fixed_tree_limit_bytes": guard["limits"]["tree_private_bytes"],
        },
        "flow": {
            "frames": [sample["frame"] for sample in row["samples"]],
            "active_blocks": [sample["active_blocks"] for sample in row["samples"]],
            "stability_frames": marker["stability_frames"],
            "stability_active_blocks": marker["stability_active_blocks"],
            "active_block_range_fraction": marker["active_block_range_fraction"],
            "stability_private_bytes": marker["stability_private_bytes"],
            "private_growth_bytes_per_second": marker["private_growth_bytes_per_second"],
            "private_decrease_interval_count": marker["private_decrease_interval_count"],
            "active_blocks_stable": marker["active_blocks_stable"],
            "private_memory_stable": marker["private_memory_stable"],
            "stability_resource_sample_count": marker["stability_resource_sample_count"],
            "frozen_minimum_resource_samples": 20,
            "plateau_pass": marker["plateau_pass"],
            "no_readback_performed": True,
        },
        "synchronous_marker_probe": {
            "status": "invalid_ctypes_signature_in_run; corrected after safe stop and verified with a small fixture only",
            "run_retried": False,
            "outer_guard_fallback_used_for_partial_memory_series": True,
        },
        "cleanup": guard["observed_process_cleanup"],
        "safety": {
            "fatal_count": len(evidence["fatal_lines"]),
            "dump_count": len(evidence["dump_inventory"]),
            "automatic_upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
            "device_lost_or_tdr_count": 0,
            "residual_after_cleanup": len(guard["observed_process_cleanup"]["remaining"]),
        },
        "classification": {
            "observed_fact": "readback-free four-log Flow reached all ten sample frames, then did not complete stage-close/shutdown and was cleaned up fail closed",
            "strong_inference": "frames 240-320 show stable active-block count and decreasing nearest-guard Private Bytes, but the frozen 20-sample stability population and normal-exit gate were not met",
            "unconfirmed": "NanoVDB acquisition, conversion, Python retention, and persistence remain unmeasured because R1-R6 were never started",
        },
        "decision": {
            "kit_limit_raised": False,
            "r1_to_r6_started": False,
            "supply_comparison_started": False,
            "video_generated": False,
            "latest_demo_changed": False,
            "restart_requires_new_root_and_explicit_approval": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    values = public["flow"]["stability_private_bytes"]
    active = public["flow"]["stability_active_blocks"]
    ys = [215, 295, 375]
    bars = []
    for frame, blocks, value, y in zip(public["flow"]["stability_frames"], active, values, ys):
        width = 690 * (value / (14 * GIB))
        bars.append(
            f'<text x="250" y="{y + 24}" text-anchor="end" class="label">frame {frame} / {blocks} blocks</text>'
            f'<rect x="275" y="{y}" width="{width:.1f}" height="35" rx="8" fill="#38bdf8"/>'
            f'<text x="{287 + width:.1f}" y="{y + 25}" class="value">{value/GIB:.3f} GiB</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<style>.title{{font:700 34px system-ui;fill:#f8fafc}}.sub{{font:18px system-ui;fill:#cbd5e1}}.label{{font:17px system-ui;fill:#e2e8f0}}.value{{font:700 17px ui-monospace,monospace;fill:#f8fafc}}.small{{font:16px system-ui;fill:#cbd5e1}}.strong{{font:700 19px system-ui;fill:#f8fafc}}</style>
<rect width="1200" height="680" rx="28" fill="#101827"/>
<text x="70" y="70" class="title">Phase 6EU - Readback-free baseline lifecycle safe stop</text>
<text x="70" y="108" class="sub">Phase 6ES / 6ET frozen - unchanged 14 GiB guard - no NanoVDB readback called</text>
<line x1="965" y1="175" x2="965" y2="435" stroke="#fda4af" stroke-width="3" stroke-dasharray="10 8"/>
<text x="950" y="166" text-anchor="end" class="small">fixed Kit limit 14.000 GiB</text>
{''.join(bars)}
<rect x="70" y="475" width="1060" height="135" rx="18" fill="#1e293b"/>
<text x="95" y="515" class="strong">Flow samples complete; normal OS exit not established</text>
<text x="95" y="550" class="small">Kit peak {public['resource']['kit_peak_gib']:.3f} GiB. Stability frames: active blocks vary {100*public['flow']['active_block_range_fraction']:.2f}%.</text>
<text x="95" y="580" class="small">Nearest guard memory decreases across 240/280/320, but only {public['flow']['stability_resource_sample_count']} of 20 frozen samples were available.</text>
<text x="70" y="650" class="small">Safe stop: observed descendant residual, unknown shutdown signature, exact PID cleanup complete. R1-R6 not started.</text>
</svg>'''
    args.output_svg.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
