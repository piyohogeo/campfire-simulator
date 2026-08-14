"""Build the bounded Phase 6GG color-slot diagnostic safe-stop summary."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build_summary(root: Path) -> dict:
    condition = root / "C0-baseline" / "metadata_baseline_attempt01"
    case = condition / "S93_support_clear"
    guard_path = condition / "runner-logs" / "S93_support_clear.guard.json"
    raw_path = case / "raw.json"
    evidence_path = case / "runner_evidence.json"
    outcome_path = case / "shutdown_outcome.json"
    plan_path = root / "diagnostic_plan.json"
    contract_path = root / "frozen_contract.json"

    raw = _load(raw_path)
    guard = _load(guard_path)
    evidence = _load(evidence_path)
    outcome = _load(outcome_path)
    plan = _load(plan_path)
    startup = raw["startup_liveness_gate"]
    cleanup = guard["observed_process_cleanup"]
    peaks = guard["peaks"]
    limits = guard["limits"]
    minima = guard["machine_minima"]

    return {
        "schema": "campfire.phase6gg.color-slot-safe-stop-summary.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "phase6gg",
        "status": "safe_stop",
        "history": {
            "phase6gd_frozen": True,
            "phase6ge_pre_kit_safe_stop_frozen": True,
            "phase6gf_outer_exit_propagation_safe_stop_frozen": True,
            "phase6gg_root_reused": False,
        },
        "contract": {
            "schema": _load(contract_path)["schema"],
            "sha256": _sha256(contract_path),
            "diagnostic_only": True,
            "normal_formal_kit_tree_limits_unchanged_bytes": [
                16 * 1024**3,
                17 * 1024**3,
            ],
        },
        "population": {
            "planned": ["C0", "C1", "C2"],
            "started": ["C0"],
            "completed_functionally": [],
            "not_started": ["C1", "C2"],
            "formal_s93_s100_population_started": bool(
                plan["formal_s93_s100_population_started"]
            ),
        },
        "active_condition": {
            "name": "C0",
            "export_enable_state": {"rgba": False, "rgb": False},
            "failure_boundary": "startup_liveness_gate_before_public_readback",
            "probe_status": raw["status"],
            "error": raw["error"],
            "startup": {
                "classification": startup["classification"],
                "readback_permitted": startup["readback_permitted"],
                "gate_frame": startup["gate_frame"],
                "sample_count": startup["sample_count"],
                "minimum_active_blocks": startup["minimum_active_blocks"],
                "maximum_active_blocks": startup["maximum_active_blocks"],
                "first_representative_frame": startup["first_representative_frame"],
                "source_ok": startup["source_ok"],
                "telemetry_fresh": startup["telemetry_fresh"],
                "identity_and_exact_source_pass": startup[
                    "identity_and_exact_source"
                ]["pass"],
                "canonical_payload_sha256": startup["identity_and_exact_source"][
                    "payload_native_validation"
                ]["observed_payload_sha256"],
            },
            "readback_call_count": 0,
            "bounded_handle_metadata_committed": False,
            "process_exit_code": evidence["process_exit_code"],
            "last_lifecycle_marker": evidence["lifecycle_marker"],
            "physical_process_exit_observed": evidence["shutdown_monitor"][
                "exited_within_shutdown_grace"
            ],
            "contract_outcome": outcome,
        },
        "resource": {
            "duration_seconds": guard["duration_seconds"],
            "sample_count": guard["sample_count"],
            "peaks_bytes": peaks,
            "limits_bytes": limits,
            "minimum_available_physical_bytes": minima["available_physical_bytes"],
            "minimum_commit_headroom_bytes": minima[
                "estimated_commit_headroom_bytes"
            ],
            "kit_margin_to_20_gib_bytes": limits["kit_private_bytes"]
            - peaks["kit"],
            "tree_margin_to_21_gib_bytes": limits["tree_private_bytes"]
            - peaks["tree"],
            "large_output_buffered_in_parent": guard[
                "large_output_buffered_in_parent"
            ],
            "resource_limit_triggered": guard["stop_reason"] is not None,
        },
        "lifecycle_and_cleanup": {
            "stage_close_complete": raw["completion_contract"]["stage_closed"],
            "shutdown_complete_marker": evidence["lifecycle_marker"]
            == "shutdown_complete",
            "cdb_invoked": evidence["shutdown_monitor"]["diagnostic"] is not None,
            "fatal_count": len(evidence["fatal_lines"]),
            "dump_count": len(evidence["dump_inventory"]),
            "automatic_upload_attempt_count": len(
                evidence["automatic_upload_attempt_lines"]
            ),
            "residual_process": evidence["shutdown_monitor"]["residual_process"],
            "exact_cleanup": {
                "observed_identity_count": cleanup["observed_identity_count"],
                "all_matching_absent": cleanup["all_matching_absent"],
                "all_observed_absent": cleanup["all_observed_absent"],
                "matching_remaining": cleanup["matching_remaining"],
                "final_unknown": cleanup["final_unknown"],
            },
        },
        "mapping_result": {
            "handle_6": "unknown",
            "rgba_and_rgb_slot_relationship": "unavailable",
            "reason": "C0 failed the frozen representative-startup prerequisite before readback; C1 and C2 were not permitted to start.",
            "candidate_schema_created": False,
            "offline_schema_fixture_started": False,
            "formal_channel_preflight_started": False,
        },
        "production": {
            "changed": evidence["production_changed"],
            "sha256_before": evidence["production_app_sha256_before"],
            "sha256_after": evidence["production_app_sha256_after"],
            "defaults_changed": False,
            "latest_demo_changed": False,
        },
        "verification": {
            "release_build": "pass",
            "phase0_rtx": {"status": "pass", "summary_status": "ok"},
            "phase3": {
                "status": "pass",
                "dry_mass_balance_error_kg": 0.0,
                "wet_mass_balance_error_kg": 0.0,
                "flow_input_owner": "wood thermal model",
                "active_blocks_peak": 384,
                "peak_fuel_input": 1.0,
            },
            "focused_phase6f": {"passed": 212, "total": 212},
            "focused_phase6g": {"passed": 32, "total": 32},
            "standard_suite": {
                "processes_passed": 8,
                "processes_total": 8,
                "tests_passed": 78,
                "tests_total": 78,
                "automatic_upload": False,
            },
            "devlog_validation": {
                "status": "pass",
                "references": 481,
                "ids": 287,
                "json": 239,
                "svg": 177,
                "zip": 2,
            },
            "production_app_sha256": "94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A",
            "latest_demo_manifest_sha256": "1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285",
            "final_residual_counts": {
                "kit": 0,
                "cdb": 0,
                "nvidia_smi": 0,
                "nvngx_update": 0,
            },
        },
        "source_artifacts": {
            "root": str(root),
            "raw_sha256": _sha256(raw_path),
            "runner_evidence_sha256": _sha256(evidence_path),
            "shutdown_outcome_sha256": _sha256(outcome_path),
            "guard_sha256": _sha256(guard_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_summary(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "pass", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
