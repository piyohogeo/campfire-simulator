"""Bounded engineering metrics for Phase 6EY Flow dynamic stationarity."""

from __future__ import annotations

import math
import statistics


MIB = 1024 * 1024


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def slope(times: list[float], values: list[float]) -> float | None:
    if len(times) != len(values) or len(times) < 2:
        return None
    mean_x = statistics.fmean(times)
    mean_y = statistics.fmean(values)
    denominator = sum((value - mean_x) ** 2 for value in times)
    if denominator == 0.0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(times, values)) / denominator


def correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = sum((x - mean_left) * (y - mean_right) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - mean_left) ** 2 for x in left) * sum((y - mean_right) ** 2 for y in right)
    )
    return None if denominator == 0.0 else numerator / denominator


def _ratio(later: float, earlier: float) -> float | None:
    return None if earlier == 0.0 else later / earlier


def _summary(values: list[float]) -> dict:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p95": percentile(values, 0.95),
        "maximum": max(values) if values else None,
    }


def _windows(rows: list[dict], count: int) -> list[list[dict]]:
    if not rows:
        return []
    start = float(rows[0]["wall_seconds"])
    end = float(rows[-1]["wall_seconds"])
    duration = max(1e-9, end - start)
    result = [[] for _ in range(count)]
    for row in rows:
        fraction = min(0.999999999, max(0.0, (float(row["wall_seconds"]) - start) / duration))
        result[min(count - 1, int(fraction * count))].append(row)
    return result


def evaluate(rows: list[dict], thresholds: dict) -> dict:
    """Evaluate aligned active-block/resource samples against a frozen contract."""
    rows = sorted(rows, key=lambda row: float(row["wall_seconds"]))
    times = [float(row["wall_seconds"]) for row in rows]
    if times:
        origin = times[0]
        times = [value - origin for value in times]
    active = [float(row["active_blocks"]) for row in rows]
    private = [float(row["kit_private_bytes"]) for row in rows]
    working = [float(row["kit_working_set_bytes"]) for row in rows]
    tree = [float(row["tree_private_bytes"]) for row in rows]
    gpu = [float(row["gpu_dedicated_memory_mib"]) for row in rows if row.get("gpu_dedicated_memory_mib") is not None]
    normalized = [memory / blocks for memory, blocks in zip(private, active) if blocks > 0.0]
    duration = times[-1] - times[0] if len(times) >= 2 else 0.0

    active_slope = slope(times, active)
    private_slope = slope(times, private)
    normalized_slope = slope(times, normalized) if len(normalized) == len(times) else None
    active_mean = statistics.fmean(active) if active else None
    private_mean = statistics.fmean(private) if private else None
    normalized_mean = statistics.fmean(normalized) if normalized else None
    active_projected = None if not active_mean or active_slope is None else abs(active_slope) * duration / active_mean
    private_projected = None if not private_mean or private_slope is None else abs(private_slope) * duration / private_mean
    normalized_projected = (
        None if not normalized_mean or normalized_slope is None else abs(normalized_slope) * duration / normalized_mean
    )

    midpoint = len(rows) // 2
    first_active, last_active = active[:midpoint], active[midpoint:]
    first_private, last_private = private[:midpoint], private[midpoint:]
    window_rows = _windows(rows, int(thresholds["window_count"]))
    windows = []
    for index, window in enumerate(window_rows):
        window_active = [float(row["active_blocks"]) for row in window]
        window_private = [float(row["kit_private_bytes"]) for row in window]
        windows.append({
            "index": index,
            "sample_count": len(window),
            "start_wall_seconds": float(window[0]["wall_seconds"]) if window else None,
            "end_wall_seconds": float(window[-1]["wall_seconds"]) if window else None,
            "active": _summary(window_active),
            "kit_private_bytes": _summary(window_private),
        })
    window_means = [item["active"]["mean"] for item in windows if item["active"]["mean"] is not None]
    window_medians = [item["active"]["median"] for item in windows if item["active"]["median"] is not None]

    deltas_active = [right - left for left, right in zip(active, active[1:])]
    deltas_private = [right - left for left, right in zip(private, private[1:])]
    increases = sum(value > 0.0 for value in deltas_active)
    decreases = sum(value < 0.0 for value in deltas_active)
    transition_count = len(deltas_active)
    decreasing_indices = [index for index, value in enumerate(deltas_active) if value < 0.0]
    drop_mismatch = (
        None if not decreasing_indices else
        sum(deltas_private[index] > 0.0 for index in decreasing_indices) / len(decreasing_indices)
    )

    running_high = -math.inf
    new_high_flags = []
    consecutive = longest_consecutive = 0
    for value in active:
        is_new = value > running_high
        new_high_flags.append(is_new)
        if is_new:
            running_high = value
            consecutive += 1
            longest_consecutive = max(longest_consecutive, consecutive)
        else:
            consecutive = 0
    final_half_new_high_fraction = (
        sum(new_high_flags[midpoint:]) / len(new_high_flags[midpoint:]) if new_high_flags[midpoint:] else None
    )

    autocorrelations = {}
    maximum_lag = min(int(thresholds["maximum_autocorrelation_lag_samples"]), max(0, len(active) // 3))
    for lag in range(1, maximum_lag + 1):
        autocorrelations[str(lag)] = correlation(active[:-lag], active[lag:])
    positive_cycle = max(
        (value for key, value in autocorrelations.items() if int(key) >= 2 and value is not None), default=None
    )
    lag_correlations = {}
    for lag in range(0, min(int(thresholds["maximum_memory_lag_samples"]), len(active) - 3) + 1):
        lag_correlations[str(lag)] = correlation(active[:len(active) - lag or None], private[lag:])

    peak_private = max(private) if private else None
    peak_index = private.index(peak_private) if peak_private is not None else None
    terminal_private = private[-1] if private else None
    last_half_slope = slope(times[midpoint:], last_private) if len(last_private) >= 2 else None
    high_water_recovered_or_flat = bool(
        peak_private is not None and terminal_private is not None and (
            terminal_private <= peak_private - float(thresholds["private_high_water_recovery_bytes"])
            or (last_half_slope is not None and last_half_slope <= float(thresholds["maximum_last_half_private_slope_bytes_per_second"]))
        )
    )

    metrics = {
        "sample_count": len(rows),
        "duration_seconds": duration,
        "active_blocks": _summary(active),
        "kit_private_bytes": _summary(private),
        "kit_working_set_bytes": _summary(working),
        "tree_private_bytes": _summary(tree),
        "gpu_dedicated_memory_mib": _summary(gpu),
        "private_bytes_per_active_block": _summary(normalized),
        "active_slope_blocks_per_second": active_slope,
        "private_slope_bytes_per_second": private_slope,
        "private_per_block_slope_bytes_per_block_per_second": normalized_slope,
        "active_projected_drift_fraction": active_projected,
        "private_projected_drift_fraction": private_projected,
        "private_per_block_projected_drift_fraction": normalized_projected,
        "later_to_earlier_active_mean_ratio": (
            _ratio(statistics.fmean(last_active), statistics.fmean(first_active)) if first_active and last_active else None
        ),
        "later_to_earlier_active_median_ratio": (
            _ratio(statistics.median(last_active), statistics.median(first_active)) if first_active and last_active else None
        ),
        "later_to_earlier_private_mean_ratio": (
            _ratio(statistics.fmean(last_private), statistics.fmean(first_private)) if first_private and last_private else None
        ),
        "window_active_mean_max_min_ratio": (
            max(window_means) / min(window_means) if window_means and min(window_means) > 0.0 else None
        ),
        "window_active_median_max_min_ratio": (
            max(window_medians) / min(window_medians) if window_medians and min(window_medians) > 0.0 else None
        ),
        "final_to_initial_window_active_mean_ratio": (
            _ratio(window_means[-1], window_means[0]) if len(window_means) >= 2 else None
        ),
        "final_to_initial_window_active_median_ratio": (
            _ratio(window_medians[-1], window_medians[0]) if len(window_medians) >= 2 else None
        ),
        "increase_transition_fraction": increases / transition_count if transition_count else None,
        "decrease_transition_fraction": decreases / transition_count if transition_count else None,
        "final_half_new_high_fraction": final_half_new_high_fraction,
        "longest_consecutive_new_highs": longest_consecutive,
        "active_private_correlation": correlation(active, private),
        "active_private_lag_correlations": lag_correlations,
        "active_autocorrelation": autocorrelations,
        "maximum_positive_cycle_autocorrelation": positive_cycle,
        "active_drop_private_increase_fraction": drop_mismatch,
        "private_peak_index": peak_index,
        "private_high_water_recovered_or_flat": high_water_recovered_or_flat,
        "last_half_private_slope_bytes_per_second": last_half_slope,
        "windows": windows,
    }

    def between(value, lower, upper):
        return value is not None and lower <= value <= upper

    checks = {
        "minimum_samples": len(rows) >= int(thresholds["minimum_aligned_samples"]),
        "minimum_duration": duration >= float(thresholds["minimum_observation_seconds"]),
        "window_samples": len(windows) == int(thresholds["window_count"]) and all(
            item["sample_count"] >= int(thresholds["minimum_samples_per_window"]) for item in windows
        ),
        "active_maximum": bool(active and max(active) <= float(thresholds["maximum_active_blocks"])),
        "active_projected_drift": active_projected is not None and active_projected <= float(thresholds["maximum_active_projected_drift_fraction"]),
        "private_slope": private_slope is not None and private_slope <= float(thresholds["maximum_private_slope_bytes_per_second"]),
        "private_projected_drift": private_projected is not None and private_projected <= float(thresholds["maximum_private_projected_drift_fraction"]),
        "normalized_private_drift": normalized_projected is not None and normalized_projected <= float(thresholds["maximum_private_per_block_projected_drift_fraction"]),
        "half_active_mean_ratio": between(metrics["later_to_earlier_active_mean_ratio"], *thresholds["active_half_ratio_range"]),
        "half_active_median_ratio": between(metrics["later_to_earlier_active_median_ratio"], *thresholds["active_half_ratio_range"]),
        "half_private_mean_ratio": between(metrics["later_to_earlier_private_mean_ratio"], *thresholds["private_half_ratio_range"]),
        "window_active_mean_ratio": metrics["window_active_mean_max_min_ratio"] is not None and metrics["window_active_mean_max_min_ratio"] <= float(thresholds["maximum_window_active_ratio"]),
        "window_active_median_ratio": metrics["window_active_median_max_min_ratio"] is not None and metrics["window_active_median_max_min_ratio"] <= float(thresholds["maximum_window_active_ratio"]),
        "final_window_mean_return": between(metrics["final_to_initial_window_active_mean_ratio"], *thresholds["active_final_window_ratio_range"]),
        "final_window_median_return": between(metrics["final_to_initial_window_active_median_ratio"], *thresholds["active_final_window_ratio_range"]),
        "increase_fraction": metrics["increase_transition_fraction"] is not None and metrics["increase_transition_fraction"] >= float(thresholds["minimum_increase_transition_fraction"]),
        "decrease_fraction": metrics["decrease_transition_fraction"] is not None and metrics["decrease_transition_fraction"] >= float(thresholds["minimum_decrease_transition_fraction"]),
        "late_new_high_fraction": final_half_new_high_fraction is not None and final_half_new_high_fraction <= float(thresholds["maximum_final_half_new_high_fraction"]),
        "consecutive_new_highs": longest_consecutive <= int(thresholds["maximum_consecutive_new_highs"]),
        "active_drop_memory_response": drop_mismatch is not None and drop_mismatch <= float(thresholds["maximum_active_drop_private_increase_fraction"]),
        "private_high_water_recovery_or_plateau": high_water_recovered_or_flat,
    }
    return {"metrics": metrics, "checks": checks, "gate_pass": all(checks.values())}
