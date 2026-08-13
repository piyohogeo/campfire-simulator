"""Lag-aware Flow occupancy and CPU-memory response qualification for Phase 6FE."""

from __future__ import annotations

import statistics

try:
    from .phase6ey_dynamic_stationarity import evaluate as evaluate_phase6ey
except ImportError:
    from phase6ey_dynamic_stationarity import evaluate as evaluate_phase6ey


def _event(rows: list[dict], index: int, contract: dict) -> dict:
    response = contract["lagged_occupancy_response"]
    lag_count = int(response["lag_samples"])
    before = rows[index]
    after = rows[index + 1]
    window = rows[index + 1:index + 1 + lag_count]
    base_private = int(before["kit_private_bytes"])
    base_active = int(before["active_blocks"])
    post_active = int(after["active_blocks"])
    drop = base_active - post_active
    private_deltas = [int(row["kit_private_bytes"]) - base_private for row in window]
    active_deltas = [int(row["active_blocks"]) - base_active for row in window]
    lag_seconds = [float(row["wall_seconds"]) - float(before["wall_seconds"]) for row in window]
    reclaim = int(response["material_reclaim_bytes"])
    rebound_target = post_active + drop * float(response["active_rebound_fraction"])
    rebound_sample = next(
        (offset + 1 for offset, row in enumerate(window) if float(row["active_blocks"]) >= rebound_target),
        None,
    )
    reclaim_sample = next(
        (offset + 1 for offset, delta in enumerate(private_deltas) if delta <= -reclaim),
        None,
    )
    positive_steps = sum(
        int(right["kit_private_bytes"]) > int(left["kit_private_bytes"])
        for left, right in zip([before] + window[:-1], window)
    )
    terminal_delta = private_deltas[-1]
    maximum_delta = max(private_deltas)
    if reclaim_sample == 1:
        classification = "immediate_reclaim"
    elif reclaim_sample is not None:
        classification = "delayed_reclaim"
    elif rebound_sample is not None:
        classification = "active_rebound_overlap"
    elif (
        terminal_delta >= int(response["continued_growth_terminal_bytes"])
        and positive_steps >= int(response["continued_growth_positive_steps"])
    ):
        classification = "post_drop_continued_growth"
    else:
        classification = "bounded_cache_retention"
    return {
        "drop_from_index": index,
        "drop_to_index": index + 1,
        "timestamp_utc": after.get("timestamp_utc"),
        "timeline_frame": after.get("timeline_frame"),
        "active_before": base_active,
        "active_after": post_active,
        "active_drop": drop,
        "private_before_bytes": base_private,
        "private_after_bytes": int(after["kit_private_bytes"]),
        "same_sample_private_delta_bytes": private_deltas[0],
        "lag_private_deltas_bytes": private_deltas,
        "lag_active_deltas": active_deltas,
        "lag_seconds": lag_seconds,
        "minimum_private_delta_bytes": min(private_deltas),
        "maximum_private_delta_bytes": maximum_delta,
        "terminal_private_delta_bytes": terminal_delta,
        "reclaim_sample": reclaim_sample,
        "reclaim_seconds": None if reclaim_sample is None else lag_seconds[reclaim_sample - 1],
        "active_rebound_sample": rebound_sample,
        "active_rebound_seconds": None if rebound_sample is None else lag_seconds[rebound_sample - 1],
        "positive_private_steps": positive_steps,
        "classification": classification,
        "overlaps_readback_or_alias_boundary": any(
            str(row.get("marker", "")).startswith(("readback_", "fuel_", "original_", "converted_"))
            for row in window
        ),
    }


def evaluate(rows: list[dict], contract: dict) -> dict:
    """Evaluate global boundedness plus a finite lag response without a same-sample invariant."""
    rows = sorted(rows, key=lambda row: float(row["wall_seconds"]))
    legacy = evaluate_phase6ey(rows, contract["global_boundedness_thresholds"])
    global_checks = {
        key: value for key, value in legacy["checks"].items()
        if key != "active_drop_memory_response"
    }
    response = contract["lagged_occupancy_response"]
    lag_count = int(response["lag_samples"])
    minimum_drop = int(response["minimum_active_block_drop"])
    events = [
        _event(rows, index, contract)
        for index in range(max(0, len(rows) - lag_count))
        if int(rows[index]["active_blocks"]) - int(rows[index + 1]["active_blocks"]) >= minimum_drop
    ]
    counts = {
        name: sum(event["classification"] == name for event in events)
        for name in (
            "immediate_reclaim", "delayed_reclaim", "active_rebound_overlap",
            "bounded_cache_retention", "post_drop_continued_growth",
        )
    }
    continued = [event for event in events if event["classification"] == "post_drop_continued_growth"]
    longest = current = 0
    previous_index = None
    for event in continued:
        adjacent = previous_index is not None and event["drop_from_index"] - previous_index <= lag_count
        current = current + 1 if adjacent else 1
        longest = max(longest, current)
        previous_index = event["drop_from_index"]
    maximum_event_growth = max((event["maximum_private_delta_bytes"] for event in events), default=0)
    duration = float(rows[-1]["wall_seconds"]) - float(rows[0]["wall_seconds"]) if len(rows) > 1 else 0.0
    median_interval = statistics.median(
        float(right["wall_seconds"]) - float(left["wall_seconds"])
        for left, right in zip(rows, rows[1:])
    ) if len(rows) > 1 else None
    event_fraction = len(continued) / len(events) if events else 0.0
    dynamic_occupancy = bool(events)
    if not dynamic_occupancy:
        # Constant occupancy is valid when telemetry is fresh and memory is bounded;
        # increase/decrease fractions are not meaningful in that branch.
        global_checks.pop("increase_fraction", None)
        global_checks.pop("decrease_fraction", None)
    lag_checks = {
        "lag_window_is_finite": (
            median_interval is not None
            and lag_count * median_interval <= float(response["maximum_lag_window_seconds"])
        ),
        "minimum_drop_event_coverage": (
            not dynamic_occupancy
            or len(events) >= int(response["minimum_drop_events_for_dynamic_occupancy"])
        ),
        "continued_growth_fraction": event_fraction <= float(response["maximum_continued_growth_event_fraction"]),
        "continued_growth_run_length": longest <= int(response["maximum_consecutive_continued_growth_events"]),
        "single_event_growth_bound": maximum_event_growth <= int(response["maximum_event_growth_bytes"]),
    }
    checks = {**global_checks, **lag_checks}
    return {
        "schema": "campfire.phase6fe.lagged-memory-response-evaluation.v1",
        "gate_pass": all(checks.values()),
        "checks": checks,
        "global_boundedness": {
            "gate_pass_without_legacy_same_sample_check": all(global_checks.values()),
            "checks": global_checks,
            "metrics": legacy["metrics"],
            "legacy_same_sample_check": legacy["checks"].get("active_drop_memory_response"),
        },
        "lagged_response": {
            "dynamic_occupancy": dynamic_occupancy,
            "event_count": len(events),
            "classification_counts": counts,
            "continued_growth_event_fraction": event_fraction,
            "longest_consecutive_continued_growth_events": longest,
            "maximum_event_growth_bytes": maximum_event_growth,
            "median_sample_interval_seconds": median_interval,
            "observed_duration_seconds": duration,
            "events": events,
        },
    }
