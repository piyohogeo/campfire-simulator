"""Aggregate Phase 6EV lifecycle and readback-free plateau evidence."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _jsonl(path: Path):
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def _slope(points):
    if len(points) < 2:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denominator = sum((value - mx) ** 2 for value in xs)
    return None if denominator == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator


def _case(root: Path, relative: str, prefix: str, contract: dict):
    case_dir = root / relative
    raw = _json(case_dir / "raw.json") or {}
    evidence = _json(case_dir / "runner_evidence.json") or {}
    guard = _json(root / "runner-logs" / f"{prefix}.guard.json") or {}
    markers = _jsonl(case_dir / "resource_markers.jsonl")
    extension = _jsonl(case_dir / "extension_lifecycle_markers.jsonl")
    runner = _jsonl(case_dir / "runner_lifecycle_markers.jsonl")
    trace = _jsonl(root / "runner-logs" / f"{prefix}.resource.jsonl")
    marker_names = [row.get("marker") for row in markers]
    extension_names = [row.get("name") for row in extension]
    runner_names = [row.get("marker") for row in runner]
    normal_exit = bool(
        raw.get("status") == "ok"
        and raw.get("lifecycle_marker") == "shutdown_complete"
        and (evidence.get("outcome") or {}).get("lifecycle_status") == "normal_exit"
        and guard.get("status") == "ok"
        and guard.get("exit_code") == 0
        and guard.get("process_absent") is True
    )
    markers_complete = all(value in marker_names for value in contract["required_probe_markers"])
    extension_complete = all(value in extension_names for value in contract["required_extension_markers"])
    runner_complete = all(value in runner_names for value in contract["required_runner_markers"])
    memory_valid = all(
        not row.get("process_memory") or row["process_memory"].get("available") is True
        for row in markers
    )
    sample_blocks = {int(row["frame"]): int(row["active_blocks"]) for row in raw.get("samples", [])}
    stability_frames = contract["plateau_contract"]["stability_frames"]
    blocks = [sample_blocks.get(frame) for frame in stability_frames]
    blocks_complete = all(value is not None and value > 0 for value in blocks)
    block_range_fraction = None
    if blocks_complete:
        block_range_fraction = (max(blocks) - min(blocks)) / max(1.0, sum(blocks) / len(blocks))
    frame_markers = {int(row["frame"]): _epoch(row["timestamp_utc"]) for row in markers if row.get("marker") == "sample_started" and "frame" in row}
    stability_rows = []
    if all(frame in frame_markers for frame in stability_frames):
        start, end = frame_markers[stability_frames[0]], frame_markers[stability_frames[-1]]
        for row in trace:
            timestamp = float(row.get("timestamp_utc_epoch", 0.0))
            if not start <= timestamp <= end:
                continue
            for process in row.get("processes", []):
                if process.get("role") == "kit":
                    stability_rows.append((timestamp, int(process["private_bytes"])))
                    break
    slope = _slope(stability_rows)
    private_values = [value for _, value in stability_rows]
    non_monotonic = any(right <= left for left, right in zip(private_values, private_values[1:]))
    plateau = bool(
        blocks_complete
        and block_range_fraction <= contract["plateau_contract"]["maximum_active_block_range_fraction"]
        and len(stability_rows) >= contract["plateau_contract"]["minimum_resource_samples_in_stability_interval"]
        and slope is not None
        and slope <= contract["plateau_contract"]["maximum_private_growth_bytes_per_second"]
        and non_monotonic
    )
    return {
        "path": relative.replace("\\", "/"),
        "normal_exit": normal_exit,
        "probe_markers_complete": markers_complete,
        "extension_markers_complete": extension_complete,
        "runner_markers_complete": runner_complete,
        "synchronous_memory_valid": memory_valid,
        "active_blocks": sample_blocks,
        "stability_active_block_range_fraction": block_range_fraction,
        "stability_resource_sample_count": len(stability_rows),
        "stability_private_slope_bytes_per_second": slope,
        "stability_private_non_monotonic_or_flat": non_monotonic,
        "plateau": plateau,
        "kit_peak_private_bytes": ((guard.get("peaks") or {}).get("kit")),
        "last_probe_marker": marker_names[-1] if marker_names else None,
        "last_extension_marker": extension_names[-1] if extension_names else None,
        "last_runner_marker": runner_names[-1] if runner_names else None,
        "cdb_invoked": bool(((evidence.get("shutdown_monitor") or {}).get("diagnostic"))),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    candidates = [("L0_short", "L0_short", "L0_short")]
    candidates += [(f"R0_run{run:02d}", f"calibration/run{run:02d}/R0_none", f"run{run:02d}_R0_none") for run in range(1, 4)]
    candidates += [("R1_acquire_discard", "R1_acquire_discard", "R1_acquire_discard")]
    for key, relative, prefix in candidates:
        if (args.root / relative).exists():
            cases[key] = _case(args.root, relative, prefix, contract)
    r0 = [cases.get(f"R0_run{run:02d}") for run in range(1, 4)]
    r0_complete = all(item is not None for item in r0)
    r0_gate = bool(r0_complete and all(
        item["normal_exit"] and item["probe_markers_complete"] and item["extension_markers_complete"]
        and item["runner_markers_complete"] and item["synchronous_memory_valid"] and item["plateau"]
        for item in r0
    ))
    report = {
        "schema": "campfire.phase6ev.r0-lifecycle-report.v1",
        "phase": "phase6ev",
        "cases": cases,
        "r0_completed_runs": sum(item is not None for item in r0),
        "r0_normal_exit_runs": sum(bool(item and item["normal_exit"]) for item in r0),
        "r0_plateau_runs": sum(bool(item and item["plateau"]) for item in r0),
        "r0_gate_pass": r0_gate,
        "r1_started": "R1_acquire_discard" in cases,
        "r1_gate_pass": bool(
            cases.get("R1_acquire_discard", {}).get("normal_exit")
            and cases.get("R1_acquire_discard", {}).get("probe_markers_complete")
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
