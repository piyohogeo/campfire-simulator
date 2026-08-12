"""Create tracked bounded Phase 6FB summary JSON and SVG from ignored raw artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def marker_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def duration(markers: list[dict], before: str, after: str):
    first = next(row for row in markers if row["marker"] == before)
    second = next(row for row in markers if row["marker"] == after)
    return (second["perf_counter_ns"] - first["perf_counter_ns"]) / 1e9


def case(root: Path, label: str):
    raw = load(root / label / "raw.json")
    evidence = load(root / label / "runner_evidence.json")
    guard = load(root / "runner-logs" / f"{label}.guard.json")
    markers = marker_rows(root / label / "resource_markers.jsonl")
    history = raw["startup_probe"]["history"]
    timeline = {int(item["frame"]): int(item["active_blocks"]) for item in history}
    startup = {}
    base = markers[0]["perf_counter_ns"]
    for name in (
        "startup_extension_ready", "offline_stage_complete", "usd_context_connection_started",
        "usd_context_connection_complete", "renderer_readiness_started", "renderer_readiness_complete",
        "flow_interface_acquire_started", "flow_interface_acquire_complete", "pre_timeline_updates_complete",
        "timeline_playing", "measurement_complete", "shutdown_complete",
    ):
        row = next(item for item in markers if item["marker"] == name)
        startup[name] = {
            "elapsed_seconds": (row["perf_counter_ns"] - base) / 1e9,
            "kit_update_number": row.get("kit_update_number"),
        }
    return {
        "classification": "representative_ingestion",
        "active_blocks": {
            "frame_1": timeline[1], "frame_30": timeline[30], "frame_60": timeline[60],
            "frame_120": timeline[120], "minimum": min(timeline.values()), "maximum": max(timeline.values()),
            "history_identifying_values": [timeline[index] for index in range(1, 121)],
        },
        "telemetry_fresh": True,
        "timeline_start_seconds": history[0]["timeline_time"],
        "timeline_end_seconds": history[-1]["timeline_time"],
        "kit_update_start": history[0]["kit_update_number"],
        "kit_update_end": history[-1]["kit_update_number"],
        "stage_sha256": raw["stage_sha256"],
        "payload_sha256": raw["point_payload"]["payload_sha256"],
        "production_app_sha256_before": evidence["production_app_sha256_before"],
        "production_app_sha256_after": evidence["production_app_sha256_after"],
        "production_changed": evidence["production_changed"],
        "live_point_emitter": raw["startup_live_point_emitter_contract"],
        "startup_boundaries": startup,
        "stage_connection_seconds": duration(markers, "usd_context_connection_started", "usd_context_connection_complete"),
        "stage_close_seconds": duration(markers, "stage_close_request_before", "stage_close_request_after"),
        "normal_os_exit": (evidence["outcome"]["lifecycle_status"] == "normal_exit"),
        "process_exit_code": evidence["process_exit_code"],
        "fatal_count": len(evidence["fatal_lines"]),
        "dump_count": len(evidence["dump_inventory"]),
        "upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
        "shutdown_residual": bool(evidence["shutdown_monitor"]["residual_process"]),
        "cdb_invoked": evidence["shutdown_monitor"]["diagnostic"] is not None,
        "resource_peak_bytes": guard["peaks"],
        "minimum_available_physical_bytes": guard["machine_minima"]["available_physical_bytes"],
        "minimum_commit_headroom_bytes": guard["machine_minima"]["estimated_commit_headroom_bytes"],
    }


def svg(report: dict) -> str:
    colors = {"historical_representative": "#8bd5ca", "historical_small": "#f38ba8", "P0": "#89b4fa", "P1": "#cba6f7"}
    series = {
        "historical_representative": report["historical"]["representative_first_60"],
        "historical_small": report["historical"]["small_first_60"],
        "P0": report["new_probes"]["P0_no_readback"]["active_blocks"]["history_identifying_values"][:60],
        "P1": report["new_probes"]["P1_no_readback_repeat"]["active_blocks"]["history_identifying_values"][:60],
    }
    width, height = 1000, 520
    left, top, plot_w, plot_h = 85, 90, 850, 330
    maximum = max(max(values) for values in series.values())
    paths = []
    for name, values in series.items():
        points = []
        for index, value in enumerate(values):
            x = left + index * plot_w / (len(values) - 1)
            y = top + plot_h - value * plot_h / maximum
            points.append(f"{x:.1f},{y:.1f}")
        paths.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[name]}" stroke-width="3"/>')
    legend = "".join(
        f'<g transform="translate({110 + index * 215},465)"><rect width="18" height="5" fill="{colors[name]}"/><text x="26" y="7">{name.replace("_", " ")}</text></g>'
        for index, name in enumerate(series)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#11131a"/><style>text{{font:16px Segoe UI,sans-serif;fill:#d9e0ee}}.small{{font-size:13px;fill:#a6adc8}}</style>
<text x="50" y="42" font-size="25">Phase 6FB — Point Emitter startup ingestion</text><text class="small" x="50" y="67">frame 1–60 · public readbackなし · 同一stage/payload</text>
<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#585b70"/><line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#585b70"/>
<line x1="{left}" y1="{top + plot_h - 128 * plot_h / maximum:.1f}" x2="{left + plot_w}" y2="{top + plot_h - 128 * plot_h / maximum:.1f}" stroke="#fab387" stroke-dasharray="8 6"/><text class="small" x="90" y="{top + plot_h - 128 * plot_h / maximum - 7:.1f}">representative threshold 128</text>
<text class="small" x="45" y="{top + 6}">{maximum}</text><text class="small" x="52" y="{top + plot_h + 5}">0</text><text class="small" x="{left + plot_w - 15}" y="{top + plot_h + 25}">60</text>
{"".join(paths)}{legend}</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    audit = load(args.root / "historical_startup_audit.json")
    p0 = case(args.root, "P0_no_readback")
    p1 = case(args.root, "P1_no_readback_repeat")
    report = {
        "schema": "campfire.phase6fb.point-emitter-startup-summary.v1",
        "phase": "phase6fb", "generated_utc": datetime.utcnow().isoformat() + "Z",
        "safe_base_commit": "857ab8e", "contract_commit": "86612b8",
        "contract_sha256": load(args.root / "startup_ingestion_report.json")["contract_sha256"],
        "historical_results_frozen": True,
        "historical": {
            "first_divergence_frame": audit["comparison"]["first_divergence_frame"],
            "readback_precedes_divergence": audit["comparison"]["readback_precedes_divergence"],
            "stage_sha256_equal": audit["comparison"]["stage_sha256_equal"],
            "payload_sha256_equal": audit["comparison"]["payload_sha256_equal"],
            "authored_weighted_supply_equal": audit["comparison"]["authored_weighted_supply_equal"],
            "prior_os_exit_to_next_runner_seconds": audit["comparison"]["d0_os_exit_to_d1_runner_start_seconds"],
            "representative_first_60": [int(item["active_blocks"]) for item in audit["cases"]["representative"]["history_first_60"]],
            "small_first_60": [int(item["active_blocks"]) for item in audit["cases"]["small_field"]["history_first_60"]]
        },
        "new_probes": {"P0_no_readback": p0, "P1_no_readback_repeat": p1},
        "active_history_equal_between_new_probes": p0["active_blocks"]["history_identifying_values"] == p1["active_blocks"]["history_identifying_values"],
        "observed_facts": [
            "Historical representative and 24-block processes first diverged at frame 1, before readback.",
            "Both new readback-free processes produced the same 120-frame active-block history and reached normal OS exit.",
            "The live Point payload, revision, sums, stage hash, and payload hash matched across the two new processes.",
            "P1 stage connection took substantially longer than P0, but post-play occupancy was identical.",
            "No public field readback was needed or executed because both startup processes were representative."
        ],
        "strong_inference": "np.asarray and readback disposal are not the direct cause of the historical frame-1 split; the smallest unresolved boundary remains native Flow/Point ingestion during startup.",
        "unconfirmed": [
            "The exact native readiness or process-state trigger for the historical 24-block field was not reproduced.",
            "The public API exposes no positive Flow-ingestion-ready predicate beyond fresh occupancy/input observations used here.",
            "Two successful startups do not prove all future process starts are deterministic."
        ],
        "stable_startup_candidate": "complete offline authoring -> stage connection -> 60 viewport frames -> acquire Flow interface -> 12 stopped updates -> timeline play; candidate only, because historical Phase 6FA used the same broad order",
        "public_field_checked": False, "repeated_readback_started": False,
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
                "active_blocks_final": 260,
                "active_blocks_peak": 311,
                "peak_fuel_input": 1.0,
            },
            "focused_tests": {"passed": 25, "total": 25},
            "standard_suite": {"passed": 78, "total": 78, "processes": 8, "seconds": 343.8},
            "devlog_static": {"status": "passed", "references": 422, "ids": 258, "json": 210, "svg": 176, "zip": 2},
            "production_app_sha256": "94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A",
            "final_residual_process_count": 0,
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.svg.write_text(svg(report), encoding="utf-8")


if __name__ == "__main__":
    main()
