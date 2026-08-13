"""Publish bounded Phase 6FD safe-stop evidence without field contents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


MIB = 1024 * 1024
GIB = 1024 * MIB


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def bounded_case(case: dict) -> dict:
    startup = case["startup"]
    boundary = case.get("boundary") or {}
    dynamic = case["dynamic_stationarity"]
    return {
        "startup": {
            "classification": startup["classification"],
            "frame_values": startup["frame_values"],
            "telemetry_fresh": startup["telemetry_fresh"],
            "source_ok": startup["source_ok"],
            "identity_and_exact_source_pass": startup["identity_and_exact_source_pass"],
            "readback_permitted": startup["readback_permitted"],
            "payload_sha256": startup["payload_sha256"],
            "normalized_stage_sha256": startup["normalized_stage_sha256"],
        },
        "condition_gate_pass": case["condition_gate_pass"],
        "condition_gate_failures": case["condition_gate_failures"],
        "normal_os_exit": case["normal_exit"],
        "stage_close_seconds": case["stage_close_seconds"],
        "extension_shutdown_seconds": case["extension_shutdown_seconds"],
        "shutdown_complete_to_os_exit_seconds": case["shutdown_complete_to_os_exit_seconds"],
        "cdb_invoked": case["cdb_invoked"],
        "resource": {
            "kit_peak_private_bytes": case["kit_peak_private_bytes"],
            "kit_peak_private_gib": case["kit_peak_private_bytes"] / GIB,
            "kit_terminal_private_bytes": case["terminal_kit_private_bytes"],
            "tree_peak_private_bytes": case["tree_peak_private_bytes"],
            "runner_peak_private_bytes": case["runner_peak_private_bytes"],
            "diagnostic_peak_private_bytes": case["diagnostic_peak_private_bytes"],
            "minimum_available_physical_bytes": case["minimum_available_physical_bytes"],
            "minimum_commit_headroom_bytes": case["minimum_commit_headroom_bytes"],
            "minimum_kit_ceiling_margin_bytes": case["minimum_kit_ceiling_margin_bytes"],
            "minimum_kit_ceiling_margin_mib": case["minimum_kit_ceiling_margin_bytes"] / MIB,
        },
        "memory_deltas_bytes": case["memory_deltas_bytes"],
        "gpu_deltas_mib": case["gpu_deltas_mib"],
        "dynamic_memory": {
            "gate_pass": dynamic["gate_pass"],
            "checks": dynamic["checks"],
            "sample_count": dynamic["metrics"]["sample_count"],
            "duration_seconds": dynamic["metrics"]["duration_seconds"],
            "active_blocks": dynamic["metrics"]["active_blocks"],
            "private_bytes": dynamic["metrics"]["kit_private_bytes"],
            "private_slope_bytes_per_second": dynamic["metrics"]["private_slope_bytes_per_second"],
            "private_projected_drift_fraction": dynamic["metrics"]["private_projected_drift_fraction"],
            "active_drop_private_increase_fraction": dynamic["metrics"]["active_drop_private_increase_fraction"],
            "private_high_water_recovered_or_flat": dynamic["metrics"]["private_high_water_recovered_or_flat"],
            "last_half_private_slope_bytes_per_second": dynamic["metrics"]["last_half_private_slope_bytes_per_second"],
        },
        "readback_boundary": {
            "returned_type": boundary.get("returned_type"),
            "returned_channel_count": boundary.get("returned_channel_count"),
            "operation_counts": boundary.get("operation_counts"),
            "fuel_array": boundary.get("fuel_array"),
            "observable_copy_contract": boundary.get("observable_copy_contract"),
            "converted_valid_after_source_release": (boundary.get("converted_after_source_alias_release") or {}).get("valid"),
            "converted_weak_reference_alive_after_release": boundary.get("converted_weak_reference_alive_immediately_after_release"),
            "channel_weak_reference_alive_after_scope_count": boundary.get("weak_reference_alive_after_scope_count"),
        },
        "runner_safety": case["runner_safety"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.root / "fuel_alias_lifetime_report.json")
    state = load(args.root / "incremental_state.json")
    c0 = source["cases"]["C0_acquire_discard"]
    c1 = source["cases"]["C1_fuel_alias"]
    report = {
        "schema": "campfire.phase6fd.fuel-alias-lifetime-safe-stop-summary.v1",
        "phase": "phase6fd",
        "status": "safe_stop",
        "contract_sha256": source["contract_sha256"],
        "history_frozen": source["history_frozen"],
        "incremental_state": state,
        "cases": {
            "C0_acquire_discard": bounded_case(c0),
            "C1_fuel_alias": bounded_case(c1),
        },
        "comparison": source["comparison"],
        "decision": {
            "c0_formal_pass": source["c0_gate_pass"],
            "c1_started": source["c1_started"],
            "c1_formal_pass": source["c1_gate_pass"],
            "qualified_boundary": source["qualified_boundary"],
            "safe_stop_reason": state["stop_reason"],
            "startup_recurrence": False,
            "startup_issue_moved_to_monitoring": True,
            "automatic_recovery_implemented": False,
            "one_readback_alias_observation_complete": True,
            "one_readback_alias_lifetime_qualified": False,
            "repeated_readback_ready": False,
            "point_emitter_collision_mainline_resume_condition": "a separately frozen contract must resolve or explicitly replace the failed active-drop memory-response predicate without reclassifying Phase 6FD",
        },
        "observed": [
            "C0 and C1 had identical representative startup frame values 269/505/688/1118 and no 24-block or delayed ingestion",
            "C0 passed; C1 exited normally but failed only the frozen dynamic-stationarity active-drop memory-response check",
            "fuel np.asarray returned the same object, shared memory, and allocated no new data buffer",
            "all observable channel weak references were dead after scope and no fatal, dump, upload, CDB, or cleanup residual occurred"
        ],
        "strong_inference": [
            "the zero-byte adjacent np.asarray delta is consistent with an alias operation rather than a fuel data copy",
            "overall memory recovered below the pre-readback marker, but the predeclared local active-drop response threshold still makes the formal qualification fail"
        ],
        "unconfirmed": [
            "internal provider/readback copy count and ownership below the public Python objects",
            "repeated readback accumulation",
            "the low-frequency native startup trigger and safe automatic recovery",
            "the owner of historical native shutdown waits"
        ],
        "regression": {
            "release_build": "pass (6.56 seconds)",
            "phase0_rtx": "pass",
            "phase3": {
                "status": "pass",
                "dry_authority_sha256": "0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10",
                "wet_authority_sha256": "148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9",
                "dry_mass_balance_error_kg": 0.0,
                "wet_mass_balance_error_kg": 0.0,
                "flow_active_blocks_final": 289,
                "flow_active_blocks_peak": 315,
                "peak_fuel_input": 1.0
            },
            "focused_contracts": {"passed": 90, "total": 90},
            "standard_suite": {"passed": 78, "total": 78, "processes": 8, "seconds": 320.9},
            "devlog_validation": {"status": "pass", "references": 427, "ids": 260, "json": 212, "svg": 177, "zip": 2},
            "production_app_sha256": "94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A",
            "residual_process_count": 0
        },
        "production_changed": False,
        "video_created": False,
        "latest_demo_changed": False
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
