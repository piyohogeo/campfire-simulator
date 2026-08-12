"""Phase 6FA occupancy-aware non-divergence qualification.

This module does not modify the frozen Phase 6EY evaluator.  It classifies
fresh observations as dynamic or constant occupancy and applies the matching
predeclared memory/liveness contract.
"""

from __future__ import annotations

from phase6ey_dynamic_stationarity import evaluate as evaluate_dynamic


def evaluate(rows: list[dict], thresholds: dict, functional: dict) -> dict:
    rows = sorted(rows, key=lambda row: float(row["wall_seconds"]))
    active = [float(row["active_blocks"]) for row in rows]
    occupancy_range = max(active) - min(active) if active else None
    classification = (
        "constant_occupancy"
        if occupancy_range is not None and occupancy_range <= float(thresholds["constant_maximum_range_blocks"])
        else "dynamic_occupancy"
    )
    base = evaluate_dynamic(rows, thresholds["dynamic_thresholds"])
    metrics = base["metrics"]
    common = {
        "minimum_samples": base["checks"]["minimum_samples"],
        "minimum_duration": base["checks"]["minimum_duration"],
        "window_samples": base["checks"]["window_samples"],
        "active_maximum": base["checks"]["active_maximum"],
        "private_slope": base["checks"]["private_slope"],
        "private_projected_drift": base["checks"]["private_projected_drift"],
        "normalized_private_drift": base["checks"]["normalized_private_drift"],
        "half_private_mean_ratio": base["checks"]["half_private_mean_ratio"],
        "private_high_water_recovery_or_plateau": base["checks"]["private_high_water_recovery_or_plateau"],
        "telemetry_fresh": functional.get("telemetry_fresh") is True,
        "timeline_advanced": functional.get("timeline_advanced") is True,
        "timeline_playing": functional.get("timeline_playing") is True,
        "emitter_input_positive": functional.get("emitter_input_positive") is True,
        "point_revision_expected": functional.get("point_revision_expected") is True,
        "stage_identity_unchanged": functional.get("stage_identity_unchanged") is True,
        "flow_identity_unchanged": functional.get("flow_identity_unchanged") is True,
        "meaningful_flow_field": functional.get("meaningful_flow_field") is True,
        "minimum_representative_occupancy": bool(
            active and max(active) >= float(thresholds["minimum_representative_active_blocks"])
        ),
    }
    if classification == "dynamic_occupancy":
        branch = {
            name: base["checks"][name]
            for name in (
                "active_projected_drift", "half_active_mean_ratio", "half_active_median_ratio",
                "window_active_mean_ratio", "window_active_median_ratio", "final_window_mean_return",
                "final_window_median_return", "increase_fraction", "decrease_fraction",
                "late_new_high_fraction", "consecutive_new_highs", "active_drop_memory_response",
            )
        }
    else:
        branch = {
            "constant_active_range": occupancy_range is not None and occupancy_range <= float(
                thresholds["constant_maximum_range_blocks"]
            ),
            "constant_private_slope": metrics["private_slope_bytes_per_second"] is not None
            and metrics["private_slope_bytes_per_second"] <= float(
                thresholds["constant_maximum_private_slope_bytes_per_second"]
            ),
            "constant_private_projected_drift": metrics["private_projected_drift_fraction"] is not None
            and metrics["private_projected_drift_fraction"] <= float(
                thresholds["constant_maximum_private_projected_drift_fraction"]
            ),
            "constant_normalized_private_drift": metrics["private_per_block_projected_drift_fraction"] is not None
            and metrics["private_per_block_projected_drift_fraction"] <= float(
                thresholds["constant_maximum_private_per_block_projected_drift_fraction"]
            ),
        }
    checks = {**common, **branch}
    return {
        "classification": classification,
        "occupancy_range_blocks": occupancy_range,
        "functional_liveness": functional,
        "metrics": metrics,
        "checks": checks,
        "gate_pass": all(checks.values()),
        "frozen_phase6ey_gate_reused": False,
    }

