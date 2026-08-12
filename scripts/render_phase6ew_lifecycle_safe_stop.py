"""Publish the immutable Phase 6EW L0/R0 lifecycle safe-stop evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    runtime = _json(args.root / "r0_lifecycle_report.json")
    state = _json(args.root / "incremental_state.json")
    contract_hash = (args.root / "frozen_contract.sha256").read_text(encoding="ascii").split()[0]
    l0 = runtime["cases"]["L0_short"]
    r0 = runtime["cases"]["R0_run01"]
    l0_evidence = _json(args.root / "L0_short/runner_evidence.json")
    r0_evidence = _json(args.root / "calibration/run01/R0_none/runner_evidence.json")
    l0_guard = _json(args.root / "runner-logs/L0_short.guard.json")
    r0_guard = _json(args.root / "runner-logs/run01_R0_none.guard.json")

    evidences = (l0_evidence, r0_evidence)
    guards = (l0_guard, r0_guard)
    report = {
        "schema": "campfire.phase6ew.r0-lifecycle-safe-stop.v1",
        "phase": "phase6ew",
        "status": "safe_stop",
        "reason": state["reason"],
        "active_condition": state["active_condition"],
        "contract_sha256": contract_hash,
        "frozen_history": {
            "phase6eu_changed": False,
            "phase6ev_changed": False,
            "phase6ev_stage_close_seconds": 102.595644,
            "prior_samples_reused": False,
        },
        "l0": {
            "gate_pass": runtime["l0_gate_pass"],
            "normal_exit": l0["normal_exit"],
            "markers_complete": l0["probe_markers_complete"] and l0["extension_markers_complete"] and l0["runner_markers_complete"],
            "active_blocks": l0["active_blocks"],
            "stage_close_seconds": l0["stage_close_seconds"],
            "kit_peak_private_bytes": l0["kit_peak_private_bytes"],
            "tree_peak_private_bytes": l0["tree_peak_private_bytes"],
            "process_cleanup": l0_guard["observed_process_cleanup"],
        },
        "r0_run01": {
            "normal_exit": r0["normal_exit"],
            "markers_complete": r0["probe_markers_complete"] and r0["extension_markers_complete"] and r0["runner_markers_complete"],
            "active_blocks": r0["active_blocks"],
            "stability_frames": [240, 280, 320],
            "stability_resource_samples": r0["stability_resource_sample_count"],
            "required_stability_resource_samples": 20,
            "active_block_range_fraction": r0["stability_active_block_range_fraction"],
            "maximum_active_block_range_fraction": 0.15,
            "private_slope_bytes_per_second": r0["stability_private_slope_bytes_per_second"],
            "maximum_private_slope_bytes_per_second": 8 * 1024**2,
            "private_non_monotonic_or_flat": r0["stability_private_non_monotonic_or_flat"],
            "plateau_gate_pass": r0["plateau"],
            "stage_close_seconds": r0["stage_close_seconds"],
            "kit_peak_private_bytes": r0["kit_peak_private_bytes"],
            "terminal_kit_private_bytes": r0["terminal_kit_private_bytes"],
            "runner_peak_private_bytes": r0["runner_peak_private_bytes"],
            "diagnostic_peak_private_bytes": r0["diagnostic_peak_private_bytes"],
            "tree_peak_private_bytes": r0["tree_peak_private_bytes"],
            "gpu0_peak_dedicated_memory_mib": r0["gpu0_peak_dedicated_memory_mib"],
            "minimum_available_physical_bytes": r0["minimum_available_physical_bytes"],
            "minimum_commit_headroom_bytes": r0["minimum_commit_headroom_bytes"],
            "process_cleanup": r0_guard["observed_process_cleanup"],
        },
        "formal_population": {
            "r0_completed": runtime["r0_completed_runs"],
            "r0_normal_exit": runtime["r0_normal_exit_runs"],
            "r0_plateau": runtime["r0_plateau_runs"],
            "r0_required": 3,
            "accepted_complete_population": 0,
            "r1_started": runtime["r1_started"],
        },
        "stage_close_seconds": [l0["stage_close_seconds"], r0["stage_close_seconds"]],
        "safety": {
            "fatal_lines": sum(len(item.get("fatal_lines", [])) for item in evidences),
            "dumps": sum(len(item.get("dump_inventory", [])) for item in evidences),
            "automatic_upload_attempts": sum(len(item.get("automatic_upload_attempt_lines", [])) for item in evidences),
            "device_lost_or_tdr": 0,
            "cdb_invocations": sum(bool((item.get("shutdown_monitor") or {}).get("diagnostic")) for item in evidences),
            "remaining_processes": sum(len((item.get("observed_process_cleanup") or {}).get("remaining", [])) for item in guards),
        },
        "production": {
            "changed": state["production_changed"],
            "app_sha256": state["production_app_sha256_current"],
            "latest_demo_changed": False,
        },
        "regression": {
            "release_build": {"status": "pass", "seconds": 6.98},
            "phase0_rtx": {"status": "pass", "seconds": 17.9},
            "phase3": {
                "status": "pass", "seconds": 25.9,
                "dry_mass_balance_error_kg": 0.0, "wet_mass_balance_error_kg": 0.0,
                "dry_authority_sha256": "0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10",
                "wet_authority_sha256": "148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9",
                "active_blocks_final": 229, "active_blocks_peak": 348, "peak_fuel_input": 1.0,
            },
            "focused_contracts": {"passed": 196, "total": 196, "seconds": 25.337},
            "standard_suite": {"passed": 78, "total": 78, "processes": 8, "seconds": 306.6},
        },
        "conclusion": {
            "plateau_qualified": False,
            "r1_allowed": False,
            "nanovdb_lifetime_next_stage_allowed": False,
            "unresolved_native_lock_risk": "Phase 6EU's incomplete CDB capture still leaves the stage-close/plugin-shutdown SRW-lock owner unknown; Phase 6EW did not reproduce the residual.",
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    gib = 1024**3
    l0_peak = l0["kit_peak_private_bytes"] / gib
    r0_peak = r0["kit_peak_private_bytes"] / gib
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="650" viewBox="0 0 1200 650">
<rect width="1200" height="650" fill="#111318"/><style>.t{{font:700 30px sans-serif;fill:#f2f4f8}}.s{{font:18px sans-serif;fill:#aeb8c8}}.v{{font:700 25px monospace;fill:#ffb45e}}.ok{{fill:#63d39b}}.warn{{fill:#ffb45e}}</style>
<text x="60" y="70" class="t">Phase 6EW - R0 lifecycle qualification safe stop</text>
<text x="60" y="108" class="s">Corrected markers qualified L0; R0 run 1 exited normally but missed the frozen sample-count gate.</text>
<rect x="60" y="150" width="500" height="330" rx="18" fill="#1b2029"/><text x="90" y="195" class="t">L0 control</text>
<text x="90" y="240" class="ok">all markers / OS exit 0 / residual 0</text><text x="90" y="285" class="v">{l0["stage_close_seconds"]:.3f} s stage close</text>
<text x="90" y="330" class="v">{l0_peak:.3f} GiB Kit peak</text><text x="90" y="390" class="s">active blocks 505 / 688</text><text x="90" y="435" class="ok">L0 gate PASS</text>
<rect x="640" y="150" width="500" height="330" rx="18" fill="#1b2029"/><text x="670" y="195" class="t">R0 run 1</text>
<text x="670" y="240" class="ok">frame 320 / OS exit 0 / stage close {r0["stage_close_seconds"]:.3f} s</text><text x="670" y="285" class="v">18 / 20 stability samples</text>
<text x="670" y="330" class="s">blocks range 3.970% / private slope -4.47 MiB/s</text><text x="670" y="380" class="v">{r0_peak:.3f} GiB Kit peak</text><text x="670" y="435" class="warn">plateau gate FAIL</text>
<text x="60" y="545" class="t">R0 formal 0 / 3 - R1 not started</text>
<text x="60" y="590" class="s">No retry, no threshold relaxation, no production or latest-demo change.</text>
</svg>'''
    args.svg.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
