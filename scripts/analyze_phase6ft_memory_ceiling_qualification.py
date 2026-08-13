"""Analyze the Phase 6FT release-after-close memory-ceiling qualification."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import statistics

from analyze_phase6fq_stage_close_lifecycle import _attempt, _json, _jsonl


RESOURCE_MARKERS = [
    "startup_liveness_confirmed",
    "timeline_stop_request_before", "timeline_stop_request_after", "timeline_stop_confirmed",
    "renderer_drain_started", "renderer_update_started", "renderer_update_complete", "renderer_drain_complete",
    "reference_release_order_selected", "owned_reference_retained", "ownership_container_complete",
    "stage_close_request_before", "stage_close_request_after", "stage_close_complete",
    "usd_context_disconnected", "post_close_renderer_update_started", "post_close_renderer_update_complete",
    "references_retained_through_post_close",
    "capture_related_objects_release_started", "capture_related_objects_release_complete",
    "flow_references_release_started", "flow_references_release_complete",
    "provider_readback_references_release_started", "provider_readback_references_release_complete",
    "stage_viewport_references_release_started", "stage_viewport_references_release_complete",
    "ownership_container_released", "app_close_requested", "shutdown_complete",
]
EXTENSION_MARKERS = ["extension_on_startup", "extension_on_shutdown_begin", "extension_on_shutdown_end"]
RUNNER_MARKERS = ["os_process_exit_observed"]
OWNERSHIP_SLOTS = [
    "stage", "viewport", "capture_provider_alias", "flow_interface", "volume_provider",
    "emitter_prim", "collectors", "collectors_by_index",
]
REQUIRED_PRESENT = [
    "stage", "viewport", "flow_interface", "volume_provider", "emitter_prim",
    "collectors", "collectors_by_index",
]


def _ordered(names: list[str], required: list[str]) -> bool:
    cursor = -1
    for name in required:
        try:
            cursor = names.index(name, cursor + 1)
        except ValueError:
            return False
    return True


def _duration(rows: list[dict], first: str, last: str):
    start = next((row for row in rows if row.get("marker") == first), None)
    end = next((row for row in rows if row.get("marker") == last), None)
    if not start or not end:
        return None
    if start.get("perf_counter_ns") is not None and end.get("perf_counter_ns") is not None:
        return (int(end["perf_counter_ns"]) - int(start["perf_counter_ns"])) / 1e9
    try:
        return (datetime.fromisoformat(end["timestamp_utc"]) - datetime.fromisoformat(start["timestamp_utc"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None


def _role_value(sample: dict, role: str, key: str = "private_bytes"):
    values = [int(row.get(key) or 0) for row in sample.get("processes", []) if row.get("role") == role]
    return max(values) if values else None


def _trace_summary(path: Path, raw: dict, contract: dict) -> dict:
    rows = _jsonl(path)
    kit = []
    for sample in rows:
        value = _role_value(sample, "kit")
        if value is not None:
            kit.append(
                {
                    "timestamp_utc_epoch": sample.get("timestamp_utc_epoch"),
                    "private_bytes": value,
                    "working_set_bytes": _role_value(sample, "kit", "working_set_bytes"),
                    "tree_private_bytes": sample.get("tree_private_bytes"),
                    "runner_private_bytes": _role_value(sample, "runner"),
                    "diagnostic_private_bytes": _role_value(sample, "diagnostic"),
                    "available_physical_bytes": (sample.get("machine") or {}).get("available_physical_bytes"),
                    "commit_headroom_bytes": (sample.get("machine") or {}).get("estimated_commit_headroom_bytes"),
                    "lifecycle_marker": sample.get("lifecycle_marker"),
                    "execution_section": sample.get("current_execution_section"),
                }
            )
    values = [row["private_bytes"] for row in kit]
    final = kit[-10:]
    monotonic = len(final) == 10 and all(
        final[index]["private_bytes"] >= final[index - 1]["private_bytes"]
        for index in range(1, len(final))
    )
    total_rise = (final[-1]["private_bytes"] - final[0]["private_bytes"]) if len(final) == 10 else None
    samples = raw.get("samples") or []
    active_growth = len(samples) >= 2 and int(samples[-1].get("active_blocks") or 0) > int(samples[-2].get("active_blocks") or 0)
    rule = contract["boundedness"]["persistent_unexplained_accumulation"]
    persistent = bool(
        monotonic
        and total_rise is not None
        and total_rise >= int(rule["minimum_total_rise_bytes"])
        and not active_growth
    )
    return {
        "sample_count": len(rows),
        "kit_sample_count": len(kit),
        "kit_private_peak_bytes": max(values) if values else None,
        "kit_private_terminal_bytes": values[-1] if values else None,
        "kit_working_set_peak_bytes": max((row["working_set_bytes"] or 0 for row in kit), default=None),
        "tree_private_peak_bytes": max((row["tree_private_bytes"] or 0 for row in kit), default=None),
        "runner_private_peak_bytes": max((row["runner_private_bytes"] or 0 for row in kit), default=None),
        "diagnostic_private_peak_bytes": max((row["diagnostic_private_bytes"] or 0 for row in kit), default=None),
        "available_physical_minimum_bytes": min((row["available_physical_bytes"] for row in kit if row["available_physical_bytes"] is not None), default=None),
        "commit_headroom_minimum_bytes": min((row["commit_headroom_bytes"] for row in kit if row["commit_headroom_bytes"] is not None), default=None),
        "peak_recovery_to_terminal_bytes": (max(values) - values[-1]) if values else None,
        "final_window": {
            "samples": len(final),
            "monotonic_non_decreasing": monotonic,
            "total_rise_bytes": total_rise,
            "active_block_growth_between_final_physics_markers": active_growth,
            "persistent_unexplained_accumulation": persistent,
        },
    }


def _gpu_summary(path: Path) -> dict:
    dedicated = []
    rows = 0
    if path.is_file():
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.reader(stream):
                if len(row) < 5:
                    continue
                rows += 1
                try:
                    dedicated.append(int(float(row[4].strip())) * 1024 * 1024)
                except ValueError:
                    pass
    return {
        "sample_rows": rows,
        "dedicated_memory_peak_bytes": max(dedicated) if dedicated else None,
        "shared_memory_bytes": None,
        "shared_memory_status": "unavailable_from_existing_bounded_public_telemetry",
    }


def _cache_activity(path: Path) -> dict:
    counts = {"shader": 0, "cache": 0, "compile": 0, "rtx": 0}
    examples = []
    if path.is_file():
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                lower = line.lower()
                matched = False
                for token in counts:
                    if token in lower:
                        counts[token] += 1
                        matched = True
                if matched and len(examples) < 5:
                    examples.append(line.strip()[:300])
    return {
        "bounded_counts": counts,
        "bounded_examples": examples,
        "classification": "activity_observed" if any(counts.values()) else "not_observed",
        "cold_warm_inference": "not_inferred",
    }


def _mean(values):
    return statistics.fmean(values) if values else None


def _median(values):
    return statistics.median(values) if values else None


def _pearson(xs, ys):
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = _mean(xs), _mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denominator = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    return (sum(a * b for a, b in zip(dx, dy)) / denominator) if denominator else None


def build(root: Path, contract_path: Path) -> dict:
    contract = _json(contract_path)
    if not contract or contract.get("phase") != "phase6ft":
        raise ValueError("invalid Phase 6FT contract")
    base_contract = {"required_markers": RESOURCE_MARKERS}
    by_id = {row["id"]: row for row in contract["conditions"]}
    attempts = []
    for path in sorted((root / "attempts").glob("attempt*")):
        if not path.is_dir():
            continue
        row = _attempt(path, base_contract)
        condition = by_id.get(row.get("condition"))
        case = path / "case"
        raw = _json(case / "raw.json") or {}
        markers = _jsonl(case / "resource_markers.jsonl")
        marker_names = [str(value.get("marker")) for value in markers]
        extensions = [str(value.get("name") or value.get("marker")) for value in _jsonl(case / "extension_lifecycle_markers.jsonl")]
        runner = [str(value.get("marker") or value.get("name")) for value in _jsonl(case / "runner_lifecycle_markers.jsonl")]
        ownership = raw.get("lifecycle_reference_ownership") or {}
        retained = ownership.get("retained") or {}
        released_slots = (ownership.get("released") or {}).get("ownership_container_slots") or {}
        payload = raw.get("point_payload") or {}
        trace = _trace_summary(path / "runner-logs" / "resource.jsonl", raw, contract)
        failures = list(row["failures"])
        if condition is None:
            failures.append("unknown_condition")
        if not _ordered(marker_names, RESOURCE_MARKERS):
            failures.append("resource_marker_order_integrity")
        if marker_names.count("renderer_update_complete") != 8:
            failures.append("renderer_drain_update_count")
        if marker_names.count("post_close_renderer_update_complete") != 4:
            failures.append("post_close_renderer_update_count")
        if not _ordered(extensions, EXTENSION_MARKERS):
            failures.append("extension_marker_order_integrity")
        if not _ordered(runner, RUNNER_MARKERS):
            failures.append("runner_exit_marker_missing")
        if sorted(retained) != sorted(OWNERSHIP_SLOTS):
            failures.append("ownership_slot_set")
        if any(not (retained.get(name) or {}).get("present") for name in REQUIRED_PRESENT):
            failures.append("required_reference_not_retained")
        if (retained.get("capture_provider_alias") or {}).get("present") is not False:
            failures.append("unexpected_capture_provider_alias")
        if ownership.get("python_owned_slots_clear") is not True or any(bool(released_slots.get(name)) for name in OWNERSHIP_SLOTS):
            failures.append("ownership_container_not_clear")
        if str(payload.get("payload_sha256", "")).upper() != contract["physical_fixture"]["payload_sha256"]:
            failures.append("payload_sha256_mismatch")
        if int(payload.get("active_count", payload.get("active_point_count", -1))) != contract["physical_fixture"]["active_points"]:
            failures.append("active_point_count_mismatch")
        if int(payload.get("total_count", payload.get("total_point_count", payload.get("original_point_count", -1)))) != contract["physical_fixture"]["total_points"]:
            failures.append("total_point_count_mismatch")
        if condition:
            observed_frames = {int(value.get("frame")) for value in raw.get("samples") or []}
            if not set(condition["sample_frames"]).issubset(observed_frames):
                failures.append("required_sample_frame_missing")
            arguments = raw.get("arguments") or {}
            if int(arguments.get("allocation_calibration_level", -1)) != int(condition["allocation_level"]):
                failures.append("allocation_level_mismatch")
        allocation = raw.get("allocation_calibration") or {}
        if int(allocation.get("readback_calls", 0)) != 0 or int(row.get("readback_calls") or 0) != 0:
            failures.append("readback_not_zero")
        capture = raw.get("capture_lifecycle_preparation") or {}
        if int(capture.get("capture_calls", 0)) or int(capture.get("pixel_buffer_bytes", 0)) or int(capture.get("video_generation_calls", 0)):
            failures.append("capture_body_created")
        if trace["final_window"]["persistent_unexplained_accumulation"]:
            failures.append("persistent_unexplained_accumulation")
        if (row.get("diagnostic") or {}).get("started"):
            failures.append("unexpected_cdb_invocation")
        failures = list(dict.fromkeys(failures))
        startup_only = failures and all(value.startswith("startup:") for value in failures)
        classification = "representative_pass" if not failures else ("startup_prerequisite_failure" if startup_only else "nonreplaceable_failure")
        active = {str(value.get("frame")): value.get("active_blocks") for value in raw.get("samples") or []}
        row.update(
            {
                "classification": classification,
                "failures": failures,
                "condition_contract": condition,
                "stage_close_seconds": _duration(markers, "stage_close_request_before", "stage_close_request_after"),
                "renderer_drain_update_count": marker_names.count("renderer_update_complete"),
                "post_close_renderer_update_count": marker_names.count("post_close_renderer_update_complete"),
                "payload_sha256": payload.get("payload_sha256"),
                "active_blocks_at_frames": active,
                "resource_trace": trace,
                "gpu": _gpu_summary(path / "runner-logs" / "gpu.csv"),
                "public_field_metadata": {
                    "available": False,
                    "shape": None,
                    "logical_bytes": None,
                    "reason": "unavailable_without_readback",
                    "estimated": False,
                },
                "diagnostic_allocation": allocation,
                "cache_shader_rtx_activity": _cache_activity(case / "kit.log"),
                "legacy_14_gib_crossed": bool(trace["kit_private_peak_bytes"] and trace["kit_private_peak_bytes"] >= int(contract["safety"]["legacy_kit_evaluation_threshold_bytes"])),
            }
        )
        attempts.append(row)

    planned = int(contract["population"]["required_representative_processes"])
    passed = [row for row in attempts if row["classification"] == "representative_pass"]
    failed = [row for row in attempts if row["classification"] == "nonreplaceable_failure"]
    startup = [row for row in attempts if row["classification"] == "startup_prerequisite_failure"]
    groups = {}
    for condition_id in by_id:
        rows = [row for row in passed if row["condition"] == condition_id]
        peaks = [row["resource_trace"]["kit_private_peak_bytes"] for row in rows]
        groups[condition_id] = {
            "runs": len(rows),
            "kit_peak_bytes": peaks,
            "kit_peak_minimum_bytes": min(peaks) if peaks else None,
            "kit_peak_median_bytes": _median(peaks),
            "kit_peak_maximum_bytes": max(peaks) if peaks else None,
            "stage_close_seconds": [row["stage_close_seconds"] for row in rows],
            "active_blocks_terminal": [int(row["active_blocks_at_frames"].get(str(by_id[condition_id]["terminal_frame"])) or 0) for row in rows],
        }
    peaks = [row["resource_trace"]["kit_private_peak_bytes"] for row in passed]
    max_peak = max(peaks) if peaks else None
    legacy_crossings = sum(row["legacy_14_gib_crossed"] for row in passed)
    legacy_margin = int(contract["safety"]["legacy_kit_evaluation_threshold_bytes"]) - max_peak if max_peak is not None else None
    legacy_too_strict = bool(
        legacy_crossings >= 2
        or (legacy_margin is not None and legacy_margin < int(contract["decision"]["legacy_small_margin_bytes"]))
    )
    complete = len(passed) == planned and not failed
    candidate = bool(
        complete
        and max_peak is not None
        and max_peak <= int(contract["safety"]["candidate_peak_maximum_bytes"])
        and all(not row["resource_trace"]["final_window"]["persistent_unexplained_accumulation"] for row in passed)
    )
    closes = [row["stage_close_seconds"] for row in passed if row["stage_close_seconds"] is not None]
    return {
        "schema": "campfire.phase6ft.memory-ceiling-qualification-report.v1",
        "phase": "phase6ft",
        "contract_sha256": (root / "frozen_contract.sha256").read_text(encoding="utf-8").split()[0],
        "phase6fs_reclassified": False,
        "phase6fo_restarted": False,
        "production_changed": False,
        "population": {
            "planned": planned,
            "launched": len(attempts),
            "representative_pass": len(passed),
            "startup_prerequisite_failure": len(startup),
            "nonreplaceable_failure": len(failed),
        },
        "qualification_complete": complete,
        "candidate_16_gib_qualified": candidate,
        "legacy_14_gib": {
            "threshold_bytes": int(contract["safety"]["legacy_kit_evaluation_threshold_bytes"]),
            "normal_crossings": legacy_crossings,
            "minimum_margin_bytes": legacy_margin,
            "too_strict_as_anomaly_ceiling": legacy_too_strict,
        },
        "candidate_16_gib": {
            "limit_bytes": int(contract["safety"]["kit_provisional_hard_limit_bytes"]),
            "required_fixed_headroom_bytes": int(contract["safety"]["minimum_candidate_headroom_bytes"]),
            "normal_maximum_peak_bytes": max_peak,
            "observed_fixed_headroom_bytes": (int(contract["safety"]["kit_provisional_hard_limit_bytes"]) - max_peak) if max_peak is not None else None,
        },
        "candidate_unique_tree_limit_bytes": int(contract["safety"]["unique_tree_provisional_hard_limit_bytes"]),
        "phase6fo_restart_ready": candidate and complete,
        "safe_stop": failed[0] if failed else None,
        "attempts": attempts,
        "conditions": groups,
        "distribution": {
            "kit_peak_bytes": peaks,
            "run_range_bytes": (max(peaks) - min(peaks)) if peaks else None,
            "stage_close_seconds": closes,
            "stage_close_vs_kit_peak_pearson": _pearson(peaks, closes) if len(peaks) == len(closes) else None,
        },
        "cdb_invocations": sum(bool((row.get("diagnostic") or {}).get("started")) for row in attempts),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root.resolve(), args.contract.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
