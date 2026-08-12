"""Aggregate the frozen Phase 6EW L0/R0/R1 lifecycle qualification."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

try:
    from .analyze_phase6ev_r0_lifecycle import _case as _base_case
    from .analyze_phase6ev_r0_lifecycle import _json, _jsonl
except ImportError:
    from analyze_phase6ev_r0_lifecycle import _case as _base_case
    from analyze_phase6ev_r0_lifecycle import _json, _jsonl


def _time(text: str) -> float:
    normalized = text.replace("Z", "+00:00")
    match = re.match(r"^(.*\.)(\d+)([+-]\d\d:\d\d)$", normalized)
    if match and len(match.group(2)) > 6:
        normalized = f"{match.group(1)}{match.group(2)[:6]}{match.group(3)}"
    return datetime.fromisoformat(normalized).timestamp()


def _range_fraction(values: list[float]) -> float | None:
    return None if not values else (max(values) - min(values)) / max(1.0, sum(values) / len(values))


def _nearest_kit_private(trace: list[dict], epoch: float) -> int | None:
    candidates = []
    for row in trace:
        for process in row.get("processes", []):
            if process.get("role") == "kit":
                candidates.append((abs(float(row["timestamp_utc_epoch"]) - epoch), int(process["private_bytes"])))
                break
    return min(candidates)[1] if candidates else None


def _gpu_peak_mib(path: Path) -> int | None:
    if not path.is_file():
        return None
    values = []
    with path.open(encoding="utf-8", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) >= 5 and row[1].strip() == "0":
                try:
                    values.append(int(row[4].strip()))
                except ValueError:
                    pass
    return max(values) if values else None


def _duration(marker: dict[str, dict], start: str, end: str) -> float | None:
    if start not in marker or end not in marker:
        return None
    return _time(marker[end]["timestamp_utc"]) - _time(marker[start]["timestamp_utc"])


def _extension_duration(rows: list[dict]) -> float | None:
    by_name = {row["name"]: row for row in rows}
    if not all(name in by_name for name in ("extension_on_shutdown_begin", "extension_on_shutdown_end")):
        return None
    return (int(by_name["extension_on_shutdown_end"]["wall_ns"]) - int(by_name["extension_on_shutdown_begin"]["wall_ns"])) / 1e9


def _case(root: Path, relative: str, prefix: str, contract: dict) -> dict:
    result = _base_case(root, relative, prefix, contract)
    case_dir = root / relative
    rows = _jsonl(case_dir / "resource_markers.jsonl")
    marker = {row["marker"]: row for row in rows}
    extension = _jsonl(case_dir / "extension_lifecycle_markers.jsonl")
    runner = _jsonl(case_dir / "runner_lifecycle_markers.jsonl")
    trace = _jsonl(root / "runner-logs" / f"{prefix}.resource.jsonl")
    guard = _json(root / "runner-logs" / f"{prefix}.guard.json") or {}

    final_epoch = _time(marker["final_sample_complete"]["timestamp_utc"]) if "final_sample_complete" in marker else None
    terminal_private = _nearest_kit_private(trace, final_epoch) if final_epoch is not None else None
    minimum_available = min((int(row["machine"]["available_physical_bytes"]) for row in trace if row.get("machine")), default=None)
    minimum_commit = min((int(row["machine"]["estimated_commit_headroom_bytes"]) for row in trace if row.get("machine")), default=None)
    result.update({
        "stage_close_seconds": _duration(marker, "stage_close_request_before", "stage_close_request_after"),
        "pre_close_renderer_drain_seconds": _duration(marker, "renderer_drain_started", "renderer_drain_complete"),
        "extension_shutdown_seconds": _extension_duration(extension),
        "shutdown_complete_to_os_exit_seconds": (
            _time(runner[-1]["timestamp_utc"]) - _time(marker["shutdown_complete"]["timestamp_utc"])
            if runner and "shutdown_complete" in marker else None
        ),
        "terminal_kit_private_bytes": terminal_private,
        "runner_peak_private_bytes": (guard.get("peaks") or {}).get("runner"),
        "diagnostic_peak_private_bytes": (guard.get("peaks") or {}).get("diagnostic"),
        "tree_peak_private_bytes": (guard.get("peaks") or {}).get("tree"),
        "kit_peak_working_set_bytes": (((guard.get("peak_evidence") or {}).get("kit") or {}).get("peak_working_set_bytes")),
        "minimum_available_physical_bytes": minimum_available,
        "minimum_commit_headroom_bytes": minimum_commit,
        "gpu0_peak_dedicated_memory_mib": _gpu_peak_mib(root / "runner-logs" / f"{prefix}.gpu.csv"),
        "resource_trace_samples": len(trace),
        "stage_close_timeout_marker": "stage_close_timeout" in marker,
    })

    before = marker.get("readback_call_before", {}).get("process_memory", {}).get("private_bytes")
    after = marker.get("readback_call_after", {}).get("process_memory", {}).get("private_bytes")
    released = marker.get("python_references_released", {}).get("process_memory", {}).get("private_bytes")
    next_frame = marker.get("next_frame_started", {}).get("process_memory", {}).get("private_bytes")
    result["acquire_private_bytes"] = {
        "before": before,
        "after": after,
        "after_minus_before": None if before is None or after is None else after - before,
        "references_released": released,
        "released_minus_before": None if before is None or released is None else released - before,
        "next_frame": next_frame,
        "next_frame_minus_before": None if before is None or next_frame is None else next_frame - before,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = _json(args.contract)
    cases = {}
    entries = [("L0_short", "L0_short", "L0_short")]
    entries += [(f"R0_run{run:02d}", f"calibration/run{run:02d}/R0_none", f"run{run:02d}_R0_none") for run in range(1, 4)]
    entries.append(("R1_acquire_discard", "R1_acquire_discard", "R1_acquire_discard"))
    for key, relative, prefix in entries:
        if (args.root / relative).exists():
            cases[key] = _case(args.root, relative, prefix, contract)

    l0 = cases.get("L0_short")
    l0_pass = bool(l0 and l0["normal_exit"] and l0["probe_markers_complete"] and l0["extension_markers_complete"] and l0["runner_markers_complete"] and l0["synchronous_memory_valid"] and not l0["stage_close_timeout_marker"])
    r0 = [cases.get(f"R0_run{run:02d}") for run in range(1, 4)]
    r0_complete = all(item is not None for item in r0)
    peaks = [float(item["kit_peak_private_bytes"]) for item in r0 if item and item["kit_peak_private_bytes"] is not None]
    terminals = [float(item["terminal_kit_private_bytes"]) for item in r0 if item and item["terminal_kit_private_bytes"] is not None]
    close_times = [float(item["stage_close_seconds"]) for item in r0 if item and item["stage_close_seconds"] is not None]
    thresholds = contract["plateau_contract"]
    reproducibility = {
        "peak_private_range_fraction": _range_fraction(peaks),
        "terminal_private_range_fraction": _range_fraction(terminals),
        "stage_close_range_seconds": None if not close_times else max(close_times) - min(close_times),
        "maximum_stage_close_seconds": max(close_times) if close_times else None,
    }
    reproducibility["gate_pass"] = bool(
        len(peaks) == len(terminals) == len(close_times) == 3
        and reproducibility["peak_private_range_fraction"] <= thresholds["maximum_cross_run_peak_private_range_fraction"]
        and reproducibility["terminal_private_range_fraction"] <= thresholds["maximum_cross_run_terminal_private_range_fraction"]
        and reproducibility["stage_close_range_seconds"] <= thresholds["maximum_cross_run_stage_close_range_seconds"]
        and reproducibility["maximum_stage_close_seconds"] <= thresholds["maximum_stage_close_seconds"]
    )
    r0_gate = bool(
        r0_complete and reproducibility["gate_pass"]
        and all(item["normal_exit"] and item["probe_markers_complete"] and item["extension_markers_complete"]
                and item["runner_markers_complete"] and item["synchronous_memory_valid"] and item["plateau"]
                and not item["stage_close_timeout_marker"] for item in r0)
    )
    r1 = cases.get("R1_acquire_discard")
    r1_memory = {} if r1 is None else r1["acquire_private_bytes"]
    r1_gate = bool(
        r1
        and r1["normal_exit"]
        and r1["probe_markers_complete"]
        and r1["extension_markers_complete"]
        and r1["runner_markers_complete"]
        and r1["synchronous_memory_valid"]
        and not r1["stage_close_timeout_marker"]
        and all(r1_memory.get(name) is not None for name in ("before", "after", "references_released", "next_frame"))
    )
    report = {
        "schema": "campfire.phase6ew.r0-lifecycle-qualification-report.v1",
        "phase": "phase6ew",
        "cases": cases,
        "l0_gate_pass": l0_pass,
        "r0_completed_runs": sum(item is not None for item in r0),
        "r0_normal_exit_runs": sum(bool(item and item["normal_exit"]) for item in r0),
        "r0_plateau_runs": sum(bool(item and item["plateau"]) for item in r0),
        "r0_cross_run_reproducibility": reproducibility,
        "r0_gate_pass": r0_gate,
        "r1_started": r1 is not None,
        "r1_gate_pass": r1_gate,
        "r1_vs_r0": {
            "r0_peak_private_bytes": peaks,
            "r1_peak_private_bytes": None if r1 is None else r1["kit_peak_private_bytes"],
            "r0_stage_close_seconds": close_times,
            "r1_stage_close_seconds": None if r1 is None else r1["stage_close_seconds"],
            "r1_acquire_private_bytes": None if r1 is None else r1["acquire_private_bytes"],
            "r0_final_active_blocks": [item.get("active_blocks", {}).get(320) for item in r0 if item],
            "r1_final_active_blocks": None if r1 is None else r1.get("active_blocks", {}).get(320),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
