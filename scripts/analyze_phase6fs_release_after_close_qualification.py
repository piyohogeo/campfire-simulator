"""Aggregate the Phase 6FS B-first release-after-close qualification."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from analyze_phase6fq_stage_close_lifecycle import _attempt, _json, _jsonl


def _ordered(rows: list[dict], names: list[str]) -> bool:
    cursor = -1
    markers = [str(row.get("marker")) for row in rows]
    for name in names:
        try:
            cursor = markers.index(name, cursor + 1)
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


def _extension_names(path: Path) -> list[str]:
    return [str(row.get("name") or row.get("marker")) for row in _jsonl(path)]


def _runner_names(path: Path) -> list[str]:
    return [str(row.get("marker") or row.get("name")) for row in _jsonl(path)]


def build(root: Path, contract_path: Path) -> dict:
    contract = _json(contract_path)
    if not contract or contract.get("phase") != "phase6fs":
        raise ValueError("invalid Phase 6FS contract")
    attempts = []
    base_contract = dict(contract)
    base_contract["required_markers"] = list(contract["required_resource_markers_in_order"])
    for path in sorted((root / "attempts").glob("attempt*")):
        if not path.is_dir():
            continue
        row = _attempt(path, base_contract)
        case = path / "case"
        raw = _json(case / "raw.json") or {}
        markers = _jsonl(case / "resource_markers.jsonl")
        marker_names = [str(value.get("marker")) for value in markers]
        extensions = _extension_names(case / "extension_lifecycle_markers.jsonl")
        runner = _runner_names(case / "runner_lifecycle_markers.jsonl")
        ownership = raw.get("lifecycle_reference_ownership") or {}
        retained = ownership.get("retained") or {}
        released = ownership.get("released") or {}
        required_present = contract["ownership"]["required_present_before_close"]
        required_slots = contract["ownership"]["required_slots"]

        failures = list(row["failures"])
        if row.get("condition") != contract["condition"]["id"]:
            failures.append("condition_not_B_release_after_close")
        if not _ordered(markers, contract["required_resource_markers_in_order"]):
            failures.append("resource_marker_order_integrity")
        if sum(name == "renderer_update_complete" for name in marker_names) != 8:
            failures.append("renderer_drain_update_count")
        if sum(name == "post_close_renderer_update_complete" for name in marker_names) != 4:
            failures.append("post_close_renderer_update_count")
        if not _ordered([{"marker": name} for name in extensions], contract["required_extension_markers_in_order"]):
            failures.append("extension_marker_order_integrity")
        if not _ordered([{"marker": name} for name in runner], contract["required_runner_markers_in_order"]):
            failures.append("runner_exit_marker_missing")
        if sorted(retained) != sorted(required_slots):
            failures.append("ownership_slot_set")
        if any(not (retained.get(name) or {}).get("present") for name in required_present):
            failures.append("required_reference_not_retained")
        if (retained.get("capture_provider_alias") or {}).get("present") is not False:
            failures.append("unexpected_capture_provider_alias")
        released_slots = released.get("ownership_container_slots") or {}
        if ownership.get("python_owned_slots_clear") is not True:
            failures.append("python_owned_slots_not_clear")
        if any(bool(released_slots.get(name)) for name in required_slots):
            failures.append("ownership_container_not_empty")
        payload = raw.get("point_payload") or {}
        if str(payload.get("payload_sha256", "")).upper() != contract["physical_fixture"]["payload_sha256"]:
            failures.append("payload_sha256_mismatch")
        if int(payload.get("active_count", payload.get("active_point_count", -1))) != contract["physical_fixture"]["active_points"]:
            failures.append("active_point_count_mismatch")
        if int(payload.get("total_count", payload.get("total_point_count", payload.get("original_point_count", -1)))) != contract["physical_fixture"]["total_points"]:
            failures.append("total_point_count_mismatch")
        diagnostic = row.get("diagnostic") or {}
        if diagnostic.get("started"):
            failures.append("unexpected_cdb_invocation")

        row["failures"] = list(dict.fromkeys(failures))
        row["classification"] = "representative_pass" if not row["failures"] else "nonreplaceable_failure"
        startup_only = row["failures"] and all(value.startswith("startup:") for value in row["failures"])
        if startup_only:
            row["classification"] = "startup_prerequisite_failure"
        row.update(
            {
                "resource_marker_order_integrity": "resource_marker_order_integrity" not in row["failures"],
                "renderer_drain_update_count": sum(name == "renderer_update_complete" for name in marker_names),
                "post_close_renderer_update_count": sum(name == "post_close_renderer_update_complete" for name in marker_names),
                "ownership": ownership,
                "extension_markers": extensions,
                "runner_markers": runner,
                "payload_sha256": payload.get("payload_sha256"),
                "active_blocks_at_frames": {
                    str(sample.get("frame")): sample.get("active_blocks")
                    for sample in (raw.get("startup_probe") or {}).get("history", [])
                    if sample.get("frame") in (60, 96)
                },
                "post_close_seconds": _duration(markers, "stage_close_complete", "ownership_container_released"),
            }
        )
        attempts.append(row)

    planned = contract["population"]["independent_processes"]
    passed = [row for row in attempts if row["classification"] == "representative_pass"]
    failures = [row for row in attempts if row["classification"] == "nonreplaceable_failure"]
    startup = [row for row in attempts if row["classification"] == "startup_prerequisite_failure"]
    complete = len(passed) == planned and not failures
    return {
        "schema": "campfire.phase6fs.release-after-close-qualification-report.v1",
        "phase": "phase6fs",
        "contract_sha256": (root / "frozen_contract.sha256").read_text(encoding="utf-8").split()[0],
        "phase6fr_reclassified": False,
        "phase6fo_restarted": False,
        "production_shutdown_order_changed": False,
        "population": {
            "planned": planned,
            "launched": len(attempts),
            "representative_pass": len(passed),
            "startup_prerequisite_failure": len(startup),
            "nonreplaceable_failure": len(failures),
        },
        "qualification_complete": complete,
        "release_after_close_candidate": complete,
        "memory_ceiling_qualification_ready": complete,
        "safe_stop": failures[0] if failures else None,
        "attempts": attempts,
        "stage_close_seconds": [row.get("stage_close_seconds") for row in passed],
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
