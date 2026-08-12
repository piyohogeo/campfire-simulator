"""Render the Phase 6EV L0 lifecycle safe-stop report from immutable artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase6eu-root", type=Path, required=True)
    parser.add_argument("--phase6ev-root", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    eu_case = args.phase6eu_root / "calibration/run01/R0_none"
    ev_case = args.phase6ev_root / "L0_short"
    eu_raw = _json(eu_case / "raw.json")
    eu_guard = _json(args.phase6eu_root / "runner-logs/run01_R0_none.guard.json")
    ev_report = _json(args.phase6ev_root / "r0_lifecycle_report.json")
    ev_guard = _json(args.phase6ev_root / "runner-logs/L0_short.guard.json")
    ev_markers = _jsonl(ev_case / "resource_markers.jsonl")
    marker = {row["marker"]: row for row in ev_markers}
    close_seconds = (_utc(marker["stage_close_request_after"]["timestamp_utc"]) - _utc(marker["stage_close_request_before"]["timestamp_utc"])).total_seconds()
    eu_samples = {int(row["frame"]): row["active_blocks"] for row in eu_raw["samples"]}
    eu_stack = (eu_case / "sensitive-shutdown-diagnostics/cdb-thread-stacks.log").read_text(encoding="utf-8", errors="replace")
    report = {
        "schema": "campfire.phase6ev.r0-lifecycle-safe-stop.v1",
        "phase": "phase6ev",
        "status": "safe_stop",
        "reason": "L0 reached normal OS exit, but required final_sample_complete marker was absent due to a diagnostic branch-placement defect; frozen gate forbids retry",
        "phase6eu_frozen_evidence": {
            "classification": "unknown_shutdown_failure",
            "last_marker": (eu_guard.get("last_diagnostic_marker") or "timeline_stopped"),
            "active_blocks_240_280_320": [eu_samples[240], eu_samples[280], eu_samples[320]],
            "kit_peak_private_bytes": eu_guard["peaks"]["kit"],
            "processes_cleaned": eu_guard["observed_process_cleanup"]["observed_alive_before_cleanup"],
            "cleanup_remaining": eu_guard["observed_process_cleanup"]["remaining"],
            "cdb_observations": {
                "main_thread": "RtlAcquireSRWLockExclusive -> MSVCP140 mtx_do_lock -> omni_ext_plugin carbOnPluginShutdown offsets",
                "usd_loader_thread": "RtlAcquireSRWLockExclusive -> omni_usd UsdContext::loadRenderSettingsFromStage -> UsdContext::closeStage+0x360",
                "profiler_thread": "NtDelayExecution",
                "remaining_threads": "not captured before bounded CDB timeout",
                "known_ngx_five_token_signature": False,
                "access_violation": False,
                "stack_tokens_verified": all(token in eu_stack for token in ("RtlAcquireSRWLockExclusive", "UsdContext::closeStage", "carbOnPluginShutdown")),
            },
        },
        "phase6ev_l0": {
            **ev_report["cases"]["L0_short"],
            "stage_close_seconds": close_seconds,
            "kit_peak_private_bytes": ev_guard["peaks"]["kit"],
            "tree_peak_private_bytes": ev_guard["peaks"]["tree"],
            "runner_peak_private_bytes": ev_guard["peaks"]["runner"],
            "process_cleanup": ev_guard["observed_process_cleanup"],
            "fatal_dump_upload_device_fault": 0,
            "missing_required_marker": "final_sample_complete",
            "marker_defect_corrected_after_safe_stop": True,
            "condition_retried": False,
        },
        "formal_population": {"r0_completed": 0, "r0_required": 3, "r1_started": False},
        "production_changed": False,
        "latest_demo_changed": False,
        "regression": {
            "release_build": "pass",
            "phase0_rtx": "pass",
            "phase3": {
                "status": "pass",
                "dry_mass_balance_error_kg": 0.0,
                "wet_mass_balance_error_kg": 0.0,
                "active_blocks_final": 246,
                "active_blocks_peak": 330,
                "peak_fuel_input": 1.0
            },
            "focused": {"passed": 187, "total": 187, "seconds": 28.807},
            "standard_suite": {"passed": 78, "total": 78, "processes": 8, "seconds": 346.9},
            "devlog": {"references": 402, "ids": 250, "json": 202, "svg": 168, "zip": 2},
            "production_app_sha256": "94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A"
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    gib = 1024**3
    eu_peak = report["phase6eu_frozen_evidence"]["kit_peak_private_bytes"] / gib
    ev_peak = report["phase6ev_l0"]["kit_peak_private_bytes"] / gib
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="650" viewBox="0 0 1200 650">
<rect width="1200" height="650" fill="#111318"/><style>.t{{font:700 30px sans-serif;fill:#f2f4f8}}.s{{font:18px sans-serif;fill:#aeb8c8}}.v{{font:700 25px monospace;fill:#ffb45e}}.ok{{fill:#63d39b}}.warn{{fill:#ffb45e}}</style>
<text x="60" y="70" class="t">Phase 6EV — readback-free R0 lifecycle safe stop</text>
<text x="60" y="108" class="s">Phase 6EU evidence remains frozen; L0 was not retried after a required-marker gate failure.</text>
<rect x="60" y="150" width="500" height="340" rx="18" fill="#1b2029"/><text x="90" y="195" class="t">Phase 6EU</text>
<text x="90" y="235" class="s">frame 320 R0 · readback none</text><text x="90" y="280" class="v">{eu_peak:.3f} GiB peak</text>
<text x="90" y="330" class="s">last durable marker</text><text x="90" y="365" class="v">timeline_stopped</text>
<text x="90" y="415" class="s">CDB: stage-close / plugin-shutdown SRW wait</text><text x="90" y="452" class="warn">unknown shutdown · cleanup 0 residual</text>
<rect x="640" y="150" width="500" height="340" rx="18" fill="#1b2029"/><text x="670" y="195" class="t">Phase 6EV L0</text>
<text x="670" y="235" class="s">frame 60 R0 · readback none</text><text x="670" y="280" class="v">{ev_peak:.3f} GiB peak</text>
<text x="670" y="330" class="s">stage close returned after</text><text x="670" y="365" class="v">{close_seconds:.3f} s</text>
<text x="670" y="415" class="ok">shutdown_complete · extension callback · OS exit 0</text><text x="670" y="452" class="warn">gate failed: final_sample_complete missing</text>
<text x="60" y="550" class="t">R0 0 / 3 qualified · R1 not started</text>
<text x="60" y="595" class="s">Marker placement fixed after the safe stop; a new root and explicit approval are required for rerun.</text>
</svg>'''
    args.svg.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
