"""Multi-window memory boundedness evaluation for Phase 6FF."""

from __future__ import annotations

import math
import statistics


def slope(times: list[float], values: list[float]) -> float | None:
    if len(times) != len(values) or len(times) < 2:
        return None
    mx = statistics.fmean(times)
    my = statistics.fmean(values)
    denominator = sum((value - mx) ** 2 for value in times)
    if denominator == 0.0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(times, values)) / denominator


def summary(values: list[float]) -> dict:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _equal_windows(rows: list[dict], count: int) -> list[list[dict]]:
    result = [[] for _ in range(count)]
    start = float(rows[0]["wall_seconds"])
    duration = max(1.0e-9, float(rows[-1]["wall_seconds"]) - start)
    for row in rows:
        fraction = min(0.999999999, max(0.0, (float(row["wall_seconds"]) - start) / duration))
        result[min(count - 1, int(fraction * count))].append(row)
    return result


def _window_record(rows: list[dict], index: int) -> dict:
    times = [float(row["wall_seconds"]) for row in rows]
    private = [float(row["kit_private_bytes"]) for row in rows]
    active = [float(row["active_blocks"]) for row in rows]
    representative_floor = max(128.0, statistics.median(active) * 0.25)
    normalized_pairs = [
        (time, memory / blocks) for time, memory, blocks in zip(times, private, active)
        if blocks >= representative_floor
    ]
    normalized_times = [item[0] for item in normalized_pairs]
    normalized = [item[1] for item in normalized_pairs]
    return {
        "index": index,
        "sample_count": len(rows),
        "start_seconds": times[0] if rows else None,
        "end_seconds": times[-1] if rows else None,
        "private": summary(private),
        "active": summary(active),
        "private_slope_bytes_per_second": slope(times, private),
        "normalized_slope_bytes_per_block_per_second": slope(normalized_times, normalized),
    }


def _rolling(rows: list[dict], seconds: float, stride: float, minimum_samples: int) -> list[dict]:
    start = float(rows[0]["wall_seconds"])
    end = float(rows[-1]["wall_seconds"])
    result = []
    cursor = start
    index = 0
    while cursor + seconds <= end + 1.0e-6:
        selected = [row for row in rows if cursor <= float(row["wall_seconds"]) <= cursor + seconds]
        if len(selected) >= minimum_samples:
            result.append(_window_record(selected, index))
        cursor += stride
        index += 1
    return result


def evaluate(rows: list[dict], contract: dict) -> dict:
    """Separate absolute safety, bounded transient, and sustained growth gates."""
    thresholds = contract["boundedness"]
    rows = sorted(rows, key=lambda row: float(row["wall_seconds"]))
    if not rows:
        return {"gate_pass": False, "checks": {"samples_present": False}, "metrics": {}}
    times = [float(row["wall_seconds"]) for row in rows]
    origin = times[0]
    times = [value - origin for value in times]
    private = [float(row["kit_private_bytes"]) for row in rows]
    working = [float(row["kit_working_set_bytes"]) for row in rows]
    tree = [float(row["tree_private_bytes"]) for row in rows]
    active = [float(row["active_blocks"]) for row in rows]
    gpu = [float(row["gpu_dedicated_memory_mib"]) for row in rows if row.get("gpu_dedicated_memory_mib") is not None]
    representative_floor = max(128.0, statistics.median(active) * 0.25)
    normalized_pairs = [
        (time, memory / blocks) for time, memory, blocks in zip(times, private, active)
        if blocks >= representative_floor
    ]
    normalized_times = [item[0] for item in normalized_pairs]
    normalized = [item[1] for item in normalized_pairs]
    duration = times[-1] if len(times) > 1 else 0.0
    midpoint = len(rows) // 2
    equal = [_window_record(window, index) for index, window in enumerate(
        _equal_windows(rows, int(thresholds["window_count"]))
    )]
    rolling = _rolling(
        rows,
        float(thresholds["rolling_window_seconds"]),
        float(thresholds["rolling_stride_seconds"]),
        int(thresholds["minimum_samples_per_rolling_window"]),
    )
    diagnostic_limit = float(thresholds["diagnostic_local_slope_bytes_per_second"])
    above = [
        item["private_slope_bytes_per_second"] > diagnostic_limit
        for item in rolling if item["start_seconds"] >= duration / 3.0
    ]
    longest = current = 0
    for value in above:
        current = current + 1 if value else 0
        longest = max(longest, current)
    window_floors = [item["private"]["minimum"] for item in equal]
    window_midpoints = [statistics.fmean([item["start_seconds"], item["end_seconds"]]) for item in equal]
    overall_slope = slope(times, private)
    last_half_slope = slope(times[midpoint:], private[midpoint:])
    final_window_slope = equal[-1]["private_slope_bytes_per_second"]
    late_window_count = max(3, len(equal) // 2)
    floor_slope = slope(window_midpoints[-late_window_count:], window_floors[-late_window_count:])
    normalized_slope = slope(normalized_times, normalized)
    private_mean = statistics.fmean(private)
    normalized_mean = statistics.fmean(normalized) if normalized else None
    projected = None if overall_slope is None else abs(overall_slope) * duration / private_mean
    normalized_projected = (
        None if normalized_slope is None or not normalized_mean
        else abs(normalized_slope) * duration / normalized_mean
    )
    peak = max(private)
    peak_index = private.index(peak)
    terminal = private[-1]
    recovery_amount = peak - terminal
    recovery_target = float(thresholds["material_high_water_recovery_bytes"])
    recovery_index = next(
        (index for index in range(peak_index + 1, len(private)) if private[index] <= peak - recovery_target),
        None,
    )
    recovery_seconds = None if recovery_index is None else times[recovery_index] - times[peak_index]
    terminal_residual = terminal - private[0]
    transient_growth = peak - min(private[:peak_index + 1])
    final_plateau = final_window_slope is not None and final_window_slope <= float(
        thresholds["maximum_final_window_private_slope_bytes_per_second"]
    )
    recovered = recovery_amount >= recovery_target and (
        recovery_seconds is not None
        and recovery_seconds <= float(thresholds["maximum_high_water_recovery_seconds"])
    )
    checks = {
        "minimum_samples": len(rows) >= int(thresholds["minimum_samples"]),
        "minimum_duration": duration >= float(thresholds["minimum_observation_seconds"]),
        "window_coverage": all(item["sample_count"] >= int(thresholds["minimum_samples_per_equal_window"]) for item in equal),
        "rolling_window_coverage": len(rolling) >= int(thresholds["minimum_rolling_windows"]),
        "kit_absolute_limit": peak <= float(contract["safety"]["kit_private_limit_bytes"]),
        "tree_absolute_limit": max(tree) <= float(contract["safety"]["unique_tree_private_limit_bytes"]),
        "transient_size": transient_growth <= float(thresholds["maximum_transient_growth_bytes"]),
        "transient_recovery_or_final_plateau": recovered or final_plateau,
        "persistent_local_growth": longest <= int(thresholds["maximum_consecutive_rolling_windows_above_diagnostic_slope"]),
        "last_half_slope": last_half_slope is not None and (
            last_half_slope <= float(thresholds["maximum_last_half_private_slope_bytes_per_second"])
            or (recovered and normalized_projected is not None and normalized_projected <= 0.05)
        ),
        "final_window_slope": final_plateau,
        "window_floor_slope": floor_slope is not None and (
            floor_slope <= float(thresholds["maximum_window_floor_slope_bytes_per_second"])
            or (recovered and normalized_projected is not None and normalized_projected <= 0.05)
        ),
        "projected_drift": projected is not None and projected <= float(thresholds["maximum_projected_private_drift_fraction"]),
        "normalized_projected_drift": normalized_projected is not None and normalized_projected <= float(thresholds["maximum_normalized_projected_drift_fraction"]),
        "terminal_residual": terminal_residual <= float(thresholds["maximum_terminal_residual_bytes"]),
    }
    return {
        "schema": "campfire.phase6ff.memory-boundedness-evaluation.v1",
        "gate_pass": all(checks.values()),
        "checks": checks,
        "metrics": {
            "sample_count": len(rows),
            "duration_seconds": duration,
            "kit_private_bytes": summary(private),
            "kit_working_set_bytes": summary(working),
            "tree_private_bytes": summary(tree),
            "gpu_dedicated_memory_mib": summary(gpu),
            "active_blocks": summary(active),
            "private_bytes_per_active_block": summary(normalized),
            "overall_private_slope_bytes_per_second": overall_slope,
            "last_half_private_slope_bytes_per_second": last_half_slope,
            "final_window_private_slope_bytes_per_second": final_window_slope,
            "window_floor_slope_bytes_per_second": floor_slope,
            "normalized_slope_bytes_per_block_per_second": normalized_slope,
            "projected_private_drift_fraction": projected,
            "normalized_projected_drift_fraction": normalized_projected,
            "initial_private_bytes": private[0],
            "terminal_private_bytes": terminal,
            "terminal_residual_bytes": terminal_residual,
            "private_high_water_bytes": peak,
            "high_water_recovery_bytes": recovery_amount,
            "high_water_recovery_seconds": recovery_seconds,
            "maximum_transient_growth_bytes": transient_growth,
            "late_rolling_windows_above_8mib_per_second": sum(above),
            "longest_consecutive_late_rolling_windows_above_8mib_per_second": longest,
            "equal_windows": equal,
            "rolling_windows": rolling,
        },
    }
