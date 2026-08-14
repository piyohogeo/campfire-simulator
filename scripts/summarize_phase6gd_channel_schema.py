"""Build the bounded Phase 6GD public-channel discovery safe-stop summary."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _metadata_rows(path: Path) -> list[dict]:
    payload = _load(path)
    rows = []
    for item in payload["handles"]:
        volume = item.get("volume") or {}
        grids = volume.get("grids") or [] if isinstance(volume, dict) else []
        nano = volume.get("nano_grid") or {} if isinstance(volume, dict) else {}
        rows.append(
            {
                "index": int(item["index"]),
                "label": item["label"],
                "python_type": item["python_type"],
                "native_type": item["native_type"],
                "object_identity": item["object_identity"],
                "weak_reference_supported": item["weak_reference_supported"],
                "is_numpy_array": item["is_numpy_array"],
                "dtype": item["dtype"],
                "shape": item["shape"],
                "strides": item["strides"],
                "c_contiguous": item["c_contiguous"],
                "f_contiguous": item["f_contiguous"],
                "writable": item["writable"],
                "logical_bytes": item["logical_bytes"],
                "data_pointer": item.get("data_pointer", "unavailable"),
                "grid_count": volume.get("grid_count", 0) if isinstance(volume, dict) else 0,
                "public_short_grid_name": grids[0].get("short_name", "unavailable") if grids else "unavailable",
                "grid_name": nano.get("grid_name", "unavailable") if isinstance(nano, dict) else "unavailable",
                "grid_class": grids[0].get("grid_class", "unavailable") if grids else "unavailable",
                "value_type": nano.get("value_type", "unavailable") if isinstance(nano, dict) else "unavailable",
                "grid_type": grids[0].get("grid_type", "unavailable") if grids else "unavailable",
                "index_bounding_box": grids[0].get("index_bounding_box", "unavailable") if grids else "unavailable",
                "world_bounding_box": grids[0].get("world_bounding_box", "unavailable") if grids else "unavailable",
                "voxel_size": nano.get("voxel_size", "unavailable") if isinstance(nano, dict) else "unavailable",
                "active_voxel_count": nano.get("active_voxel_count", "unavailable") if isinstance(nano, dict) else "unavailable",
                "background_value": nano.get("background_value", "unavailable") if isinstance(nano, dict) else "unavailable",
                "metadata_keys": nano.get("metadata_keys", "unavailable") if isinstance(nano, dict) else "unavailable",
                "public_channel_or_semantic_name": item["public_channel_or_semantic_name"],
                "metadata_sha256": item["metadata_sha256"],
            }
        )
    return rows


def build_summary(baseline_root: Path, divergence_root: Path, rgba_root: Path) -> dict:
    baseline_meta = baseline_root / "metadata_attempt01/S93_support_clear/channel-schema-metadata/bounded_handle_metadata.json"
    divergence_meta = divergence_root / "metadata_divergence_attempt01/S93_support_clear/channel-schema-metadata/bounded_handle_metadata.json"
    baseline_payload = _load(baseline_meta)
    divergence_payload = _load(divergence_meta)
    baseline_guard = _load(baseline_root / "metadata_attempt01/runner-logs/S93_support_clear.guard.json")
    divergence_guard = _load(divergence_root / "metadata_divergence_attempt01/runner-logs/S93_support_clear.guard.json")
    rgba_guard = _load(rgba_root / "metadata_rgba_attempt01/runner-logs/S93_support_clear.guard.json")
    baseline_evidence = _load(baseline_root / "metadata_attempt01/S93_support_clear/runner_evidence.json")
    divergence_evidence = _load(divergence_root / "metadata_divergence_attempt01/S93_support_clear/runner_evidence.json")
    divergence_diagnostic = divergence_evidence["shutdown_monitor"]["diagnostic"]
    divergence_debugger = divergence_diagnostic["debugger"]
    baseline = _metadata_rows(baseline_meta)
    divergence = _metadata_rows(divergence_meta)
    changed = [
        row["index"]
        for row, control in zip(baseline, divergence)
        if row["metadata_sha256"] != control["metadata_sha256"]
    ]
    return {
        "schema": "campfire.phase6gd.public-channel-schema-safe-stop-summary.v1",
        "phase": "phase6gd",
        "status": "safe_stop_unknown_seventh_handle",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "history": {
            "phase6gc_reclassified": False,
            "phase6gc_retried": False,
            "formal_population_started": False,
            "channel_preflight_qualified": False,
            "divergence_lifecycle_reclassified": False,
            "rgba_retried": False,
        },
        "baseline": {
            "artifact_root": str(baseline_root),
            "metadata_sha256": _sha256(baseline_meta),
            "returned_handle_count": len(baseline),
            "handle_order": baseline_payload["handle_order"],
            "api": baseline_payload["api"],
            "handles": baseline,
            "kit_peak_bytes": baseline_guard["peaks"]["kit"],
            "tree_peak_bytes": baseline_guard["peaks"]["tree"],
            "functional_status": baseline_evidence["outcome"]["functional_status"],
            "lifecycle_status": baseline_evidence["outcome"]["lifecycle_status"],
            "normal_exit": baseline_evidence["outcome"]["normal_exit_sample_accepted"],
            "process_exit_code": baseline_evidence["process_exit_code"],
            "cleanup_residual_zero": baseline_guard["observed_process_cleanup"]["all_observed_absent"],
        },
        "divergence_control": {
            "artifact_root": str(divergence_root),
            "metadata_sha256": _sha256(divergence_meta),
            "returned_handle_count": len(divergence),
            "handle_order": divergence_payload["handle_order"],
            "changed_indices_from_baseline": changed,
            "identified_mapping": {"index": 5, "channel": "divergence"} if changed == [5] else None,
            "handles": divergence,
            "kit_peak_bytes": divergence_guard["peaks"]["kit"],
            "tree_peak_bytes": divergence_guard["peaks"]["tree"],
            "metadata_operation_complete": True,
            "stage_close_complete": divergence_diagnostic["completion_contract"]["stage_closed"],
            "functional_status": divergence_evidence["outcome"]["functional_status"],
            "lifecycle_status": divergence_evidence["outcome"]["lifecycle_status"],
            "normal_exit": divergence_evidence["outcome"]["normal_exit_sample_accepted"],
            "process_exit_code": divergence_evidence["process_exit_code"],
            "outer_runner_terminated_target": divergence_evidence["shutdown_monitor"]["terminated_by_outer_runner"],
            "diagnostic_stack_fingerprint": divergence_diagnostic["stack_fingerprint"],
            "frozen_classifier_known_signature_matched": divergence_evidence["shutdown_monitor"]["known_signature_matched"],
            "cdb": {
                "invoked": True,
                "timed_out": divergence_debugger["timed_out"],
                "all_thread_stack_observed": divergence_debugger["all_thread_stack_observed"],
                "native_frames_observed": divergence_debugger["native_frames_observed"],
                "loaded_modules_observed": divergence_debugger["loaded_modules_observed"],
                "detach_observed": divergence_debugger["detach_observed"],
                "process_absent": divergence_debugger["process_absent"],
            },
            "cleanup_residual_zero": divergence_guard["observed_process_cleanup"]["all_observed_absent"],
        },
        "rgba_control": {
            "artifact_root": str(rgba_root),
            "readback_called": False,
            "bounded_metadata_complete": False,
            "guard_status": rgba_guard["status"],
            "guard_stop_reason": rgba_guard["stop_reason"],
            "guard_exit_code": rgba_guard["exit_code"],
            "kit_peak_bytes": rgba_guard["peaks"]["kit"],
            "tree_peak_bytes": rgba_guard["peaks"]["tree"],
            "kit_limit_bytes": rgba_guard["limits"]["kit_private_bytes"],
            "kit_limit_excess_bytes": rgba_guard["peaks"]["kit"] - rgba_guard["limits"]["kit_private_bytes"],
            "cleanup_residual_zero": rgba_guard["observed_process_cleanup"]["all_observed_absent"],
            "replacement_or_retry": False,
        },
        "mapping": {
            "legacy_public_ogn_order": ["temperature", "fuel", "burn", "smoke", "velocity", "divergence"],
            "legacy_order_mechanically_extended": False,
            "confirmed": {"handle[5]": "divergence"},
            "unconfirmed": {"handle[6]": "unknown"},
            "seventh_handle_formal_meaning": "unavailable",
            "operational_schema_id": "unavailable",
            "reason": "RGBA control reached the unchanged 16 GiB Kit hard limit before readback; RGB control was not started after the nonreplaceable resource failure.",
        },
        "harness_correction": {
            "defect": "The Phase 6GD parent metadata runner accepted raw shutdown_complete and its guard exit without propagating runner_evidence lifecycle and OS-exit axes.",
            "effect": "The frozen divergence result remained unknown_shutdown_failure, but the RGBA control was launched before the defect was discovered.",
            "correction": "Future metadata controls require functional pass, lifecycle normal_exit, accepted normal-exit sample, and process exit code zero.",
            "existing_artifacts_reclassified": False,
            "kit_conditions_rerun": False,
        },
        "next_gate": "A new pre-runtime contract must safely identify handle[6] without changing production or exceeding the qualified resource limits; only then may an operational schema fixture and S93 channel preflight start.",
        "production_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--divergence-root", type=Path, required=True)
    parser.add_argument("--rgba-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    summary = build_summary(arguments.baseline_root.resolve(), arguments.divergence_root.resolve(), arguments.rgba_root.resolve())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(arguments.output.suffix + ".partial")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(arguments.output)


if __name__ == "__main__":
    main()
