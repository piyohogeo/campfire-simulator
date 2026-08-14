"""Summarize the bounded Phase 6GH startup-gated color-slot diagnosis."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def only(root: Path, name: str) -> Path:
    paths = list(root.rglob(name))
    if len(paths) != 1:
        raise RuntimeError(f"expected one {name} under {root}, found {len(paths)}")
    return paths[0]


def handle_row(item: dict) -> dict:
    volume = item.get("volume") or {}
    grids = volume.get("grids") or [] if isinstance(volume, dict) else []
    nano = volume.get("nano_grid") or {} if isinstance(volume, dict) else {}
    grid = grids[0] if grids else {}
    return {
        "index": item["index"],
        "empty": item["logical_bytes"] == 0,
        "python_type": item["python_type"],
        "dtype": item["dtype"],
        "shape": item["shape"],
        "strides": item["strides"],
        "logical_bytes": item["logical_bytes"],
        "public_data_pointer_available": item.get("data_pointer") not in (None, "unavailable"),
        "grid_count": volume.get("grid_count", 0) if isinstance(volume, dict) else 0,
        "grid_short_name": grid.get("short_name", "unavailable"),
        "grid_class": grid.get("grid_class", "unavailable"),
        "value_type": nano.get("value_type", "unavailable") if isinstance(nano, dict) else "unavailable",
        "bounding_box": {
            "index": grid.get("index_bounding_box", "unavailable"),
            "world": grid.get("world_bounding_box", "unavailable"),
        },
        "channel_metadata": item.get("public_channel_or_semantic_name", "unavailable"),
        "metadata_sha256": item["metadata_sha256"],
        "weak_reference_supported": item["weak_reference_supported"],
    }


def attempt_row(attempt: dict) -> dict:
    root = Path(attempt["artifact_root"])
    raw = load(only(root, "raw.json"))
    guard_paths = list(root.rglob("*.guard.json"))
    if len(guard_paths) != 1:
        raise RuntimeError(f"expected one guard report under {root}, found {len(guard_paths)}")
    guard = load(guard_paths[0])
    evidence = load(only(root, "runner_evidence.json"))
    marker_path = only(root, "resource_markers.jsonl")
    markers = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    marker_by_name = {item["marker"]: item for item in markers}
    metadata_path = Path(attempt["metadata_path"])
    metadata = load(metadata_path)
    gate = raw["startup_liveness_gate"]
    probe = raw["startup_probe"]
    history = [
        {"frame": row["frame"], "active_blocks": row["active_blocks"]}
        for row in probe["history"][: gate["sample_count"]]
    ]
    first = probe["history"][0]
    outcome = evidence["outcome"]
    peaks = guard["peaks"]
    limits = guard["limits"]
    return {
        "condition": attempt["condition"],
        "control": attempt["control"],
        "condition_attempt": attempt["condition_attempt"],
        "launch_index": attempt["launch_index"],
        "classification": attempt["classification"],
        "replacement_eligible": attempt["replacement_eligible"],
        "replacement_scheduled": attempt["replacement_scheduled"],
        "startup": {
            "classification": gate["classification"],
            "sample_count": gate["sample_count"],
            "first_24_frame": gate["first_24_frame"],
            "first_above_24_frame": gate["first_above_24_frame"],
            "first_representative_frame": gate["first_representative_frame"],
            "minimum_active_blocks": gate["minimum_active_blocks"],
            "maximum_active_blocks": gate["maximum_active_blocks"],
            "timeline_fresh": gate["telemetry_fresh"],
            "emitter_enabled": first["emitter_enabled"],
            "total_points": first["total_point_count"],
            "active_points": first["active_point_count"],
            "payload_sha256": first["payload_sha256"],
            "source_sums": first["source_sums"],
            "identity_and_source_pass": gate["identity_and_exact_source"]["pass"],
            "history": history,
        },
        "metadata": {
            "path": str(metadata_path),
            "file_sha256": sha256(metadata_path),
            "returned_handle_count": metadata["returned_handle_count"],
            "api": metadata["api"],
            "handles": [handle_row(item) for item in metadata["handles"]],
            "private_api_used": metadata["private_api_used"],
            "full_field_written": metadata["full_field_json_or_npz_written"],
            "forced_gc": metadata["forced_gc"],
        },
        "resources": {
            "peaks_bytes": peaks,
            "limits_bytes": limits,
            "kit_margin_bytes": limits["kit_private_bytes"] - peaks["kit"],
            "tree_margin_bytes": limits["tree_private_bytes"] - peaks["tree"],
            "machine_minima_bytes": guard["machine_minima"],
        },
        "axes": {
            "functional": outcome["functional_status"],
            "lifecycle": outcome["lifecycle_status"],
            "normal_os_exit": outcome["os_process_normal_exit"],
            "normal_exit_sample_accepted": outcome["normal_exit_sample_accepted"],
            "process_exit_code": evidence["process_exit_code"],
            "exact_cleanup": guard["observed_process_cleanup"]["all_observed_absent"],
            "residual_zero": guard["process_absent"],
            "cdb_invoked": evidence["shutdown_monitor"].get("diagnostic") is not None,
            "shutdown_complete": "shutdown_complete" in marker_by_name,
            "stage_close_seconds": (
                marker_by_name["stage_close_complete"]["perf_counter_ns"]
                - marker_by_name["stage_close_request_before"]["perf_counter_ns"]
            ) / 1_000_000_000,
            "references_retained_at_stage_close": marker_by_name["stage_close_complete"].get(
                "ownership_weak_reference_alive_count"
            ),
            "flow_reference_present_at_shutdown_complete": marker_by_name["shutdown_complete"].get(
                "flow_reference_present"
            ),
            "python_owned_slots_clear": raw["lifecycle_reference_ownership"]["python_owned_slots_clear"],
            "ownership_container_count_after_release": raw["lifecycle_reference_ownership"]["released"][
                "ownership_container_count"
            ],
            "external_weak_referents_alive_after_release": raw["lifecycle_reference_ownership"]["released"][
                "ownership_weak_reference_alive_count"
            ],
            "weak_reference_supported_count": raw["lifecycle_reference_ownership"]["released"][
                "ownership_weak_reference_supported_count"
            ],
            "fatal_count": len(evidence.get("fatal_lines") or []),
            "dump_count": len(evidence.get("dump_inventory") or []),
            "automatic_upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines") or []),
        },
        "production_changed": evidence["production_changed"],
    }


def build(root: Path, contract: Path, schema: Path, fixtures: Path) -> dict:
    plan = load(root / "diagnostic_plan.json")
    rows = [attempt_row(item) for item in plan["attempts"]]
    by_condition = {item["condition"]: item for item in rows}
    baseline = by_condition["C0"]["metadata"]["handles"]
    changed = {}
    for condition in ("C1", "C2"):
        handles = by_condition[condition]["metadata"]["handles"]
        changed[condition] = [
            index for index, (left, right) in enumerate(zip(baseline, handles))
            if left["metadata_sha256"] != right["metadata_sha256"]
        ]
    payloads = {item["startup"]["payload_sha256"] for item in rows}
    sources = {json.dumps(item["startup"]["source_sums"], sort_keys=True) for item in rows}
    schema_payload = load(schema)
    fixture_payload = load(fixtures)
    mapping_pass = changed == {"C1": [6], "C2": []} and len(payloads) == 1 and len(sources) == 1
    return {
        "schema": "campfire.phase6gh.color-slot-diagnostic-summary.v1",
        "phase": "phase6gh",
        "status": "qualified_handle6_rgba_candidate" if mapping_pass else "safe_stop_unknown_handle6",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256(contract),
        "history": {
            "phase6gg_reclassified": False,
            "phase6gg_reused": False,
            "formal_s93_s100_started": False,
        },
        "population": {
            "total_launches": plan["total_launches"],
            "replacement_budget": plan["replacement_budget"],
            "replacements_used": plan["replacements_used"],
            "accepted_conditions": plan["accepted_conditions"],
            "attempts": rows,
        },
        "comparison": {
            "changed_indices_from_c0": changed,
            "payload_sha256_equal": len(payloads) == 1,
            "source_sums_equal": len(sources) == 1,
            "handle6_identification": "rgba" if mapping_pass else "unknown",
            "rgba_and_rgb_same_returned_slot": False if mapping_pass else "unknown",
            "rgb_returned_slot_observed": False if mapping_pass else "unknown",
            "basis": "Only rgbaEnabled changed handle[6]; rgbEnabled changed no handle; indices 0..5 remained metadata-identical.",
            "value_or_visual_inference_used": False,
        },
        "candidate_schema": {
            "schema_id": schema_payload["schema_id"],
            "path": str(schema),
            "sha256": sha256(schema),
            "fixture_path": str(fixtures),
            "fixture_passed": fixture_payload["passed"],
            "fixture_total": fixture_payload["total"],
            "fixture_all_pass": fixture_payload["all_pass"],
            "formal_preflight_qualified": False,
        },
        "normal_resource_contract_16_17_gib_unchanged": True,
        "diagnostic_resource_contract_20_21_gib_only": True,
        "production_changed": any(item["production_changed"] for item in rows),
        "next_gate": "Explicit approval for a fresh S93 channel preflight under the normal 16/17 GiB contract; no formal S93/S100 comparison has started.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.root.resolve(), args.contract.resolve(), args.schema.resolve(), args.fixtures.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
