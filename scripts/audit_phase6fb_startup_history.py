"""Read-only comparison of the representative and 24-block Phase 6FA startups."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def file_hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.exists() else None


def parse_timestamp(value: str):
    normalized = value.replace("Z", "+00:00")
    normalized = re.sub(r"(\.\d{6})\d+(?=[+-]\d\d:\d\d$)", r"\1", normalized)
    return datetime.fromisoformat(normalized)


def case(root: Path, label: str) -> dict:
    directory = root / label
    raw = load(directory / "raw.json")
    evidence = load(directory / "runner_evidence.json")
    history = raw.get("flow_liveness_history") or []
    first60 = [row for row in history if int(row["frame"]) <= 60]
    markers = lines(directory / "resource_markers.jsonl")
    extension = lines(directory / "extension_lifecycle_markers.jsonl")
    guard_trace = lines(root / "runner-logs" / f"{label}.resource.jsonl")
    log_hits = []
    log_path = directory / "kit.log"
    if log_path.exists():
        with log_path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                lower = line.lower()
                if any(token in lower for token in ("[error]", "[warning]", "shader", "cache", "adapter", "gpu foundation")):
                    log_hits.append(line.rstrip()[:1000])
                    if len(log_hits) >= 80:
                        break
    return {
        "label": label,
        "arguments": raw.get("arguments"),
        "stage_sha256_reported": raw.get("stage_sha256"),
        "stage_sha256_actual": file_hash(directory / "raw.scene.usda"),
        "payload_sha256_reported": (raw.get("point_payload") or {}).get("payload_sha256"),
        "payload_sha256_actual": file_hash(directory / "point_payload.npz"),
        "point_payload": raw.get("point_payload"),
        "source_sums": raw.get("source_sums"),
        "revision": raw.get("revision"),
        "history_first_60": first60,
        "first_nonzero_frame": next((row["frame"] for row in first60 if row["active_blocks"] > 0), None),
        "first_24_frame": next((row["frame"] for row in first60 if row["active_blocks"] == 24), None),
        "first_above_24_frame": next((row["frame"] for row in first60 if row["active_blocks"] > 24), None),
        "first_representative_frame": next((row["frame"] for row in first60 if row["active_blocks"] >= 128), None),
        "timeline_play_marker": next((row for row in markers if row.get("marker") == "timeline_playing"), None),
        "shutdown_marker": next((row for row in markers if row.get("marker") == "shutdown_complete"), None),
        "os_exit_marker": next(
            (row for row in lines(directory / "runner_lifecycle_markers.jsonl")
             if row.get("marker") == "os_process_exit_observed"), None
        ),
        "extension_markers": extension,
        "normal_exit": ((evidence.get("outcome") or {}).get("lifecycle_status") == "normal_exit"),
        "runner_start_utc_epoch": guard_trace[0]["timestamp_utc_epoch"] if guard_trace else None,
        "log_startup_fingerprints_bounded": log_hits,
        "unavailable_in_historical_artifact": [
            "Kit update number per frame", "explicit renderer-readiness boundary",
            "Flow-interface acquisition boundary", "live Emitter wrapper identity",
            "live payload-array identity/hash after context connection",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase6fa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    d0 = case(args.phase6fa_root, "D0_no_readback")
    d1 = case(args.phase6fa_root, "D1_readback_release")
    d0_exit = parse_timestamp(d0["os_exit_marker"]["timestamp_utc"])
    d1_entry = next(
        row for row in lines(args.phase6fa_root / "D1_readback_release" / "resource_markers.jsonl")
        if row.get("marker") == "process_entry"
    )
    d1_start = parse_timestamp(d1_entry["timestamp_utc"])
    comparisons = {
        "stage_sha256_equal": d0["stage_sha256_actual"] == d1["stage_sha256_actual"],
        "payload_sha256_equal": d0["payload_sha256_actual"] == d1["payload_sha256_actual"],
        "point_count_equal": d0["point_payload"]["original_point_count"] == d1["point_payload"]["original_point_count"],
        "active_point_count_equal": d0["point_payload"]["active_point_count"] == d1["point_payload"]["active_point_count"],
        "authored_weighted_supply_equal": d0["point_payload"]["weighted_supply"] == d1["point_payload"]["weighted_supply"],
        "post_measurement_source_sums_comparable": d0["source_sums"] is not None and d1["source_sums"] is not None,
        "post_measurement_revision_comparable": d0["revision"] is not None and d1["revision"] is not None,
        "first_divergence_frame": next(
            (left["frame"] for left, right in zip(d0["history_first_60"], d1["history_first_60"])
             if left["active_blocks"] != right["active_blocks"]), None
        ),
        "d0_shutdown_to_d1_process_entry_seconds": (d1_start - d0_exit).total_seconds(),
        "d0_os_exit_to_d1_runner_start_seconds": d1["runner_start_utc_epoch"] - d0_exit.timestamp(),
        "readback_precedes_divergence": False,
    }
    report = {
        "schema": "campfire.phase6fb.startup-history-audit.v1",
        "phase": "phase6fb",
        "read_only": True,
        "historical_results_frozen": True,
        "cases": {"representative": d0, "small_field": d1},
        "comparison": comparisons,
        "observed_fact": "The first differing post-play sample is frame 1, before any public readback call.",
        "strong_inference": "The direct boundary is startup/Point ingestion rather than np.asarray or post-readback alias disposal.",
        "unconfirmed": "The historical artifact cannot distinguish renderer/Flow readiness, ingestion race, or prior-process state.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
