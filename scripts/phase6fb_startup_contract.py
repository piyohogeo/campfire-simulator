"""Pure Phase 6FB startup-ingestion classification helpers."""

from __future__ import annotations


def classify_startup(history: list[dict], source: dict, thresholds: dict) -> dict:
    required_frames = int(thresholds["classification_frame"])
    final_frame = int(thresholds["final_frame"])
    expected_revision = int(thresholds["expected_point_revision"])
    source_ok = bool(
        source.get("enabled") is True
        and int(source.get("revision", -1)) == expected_revision
        and int(source.get("total_point_count", 0)) == int(thresholds["expected_total_point_count"])
        and int(source.get("active_point_count", 0)) == int(thresholds["expected_active_point_count"])
        and float((source.get("source_sums") or {}).get("fuel", 0.0))
        >= float(thresholds["minimum_fuel_sum"])
    )
    if not source_ok:
        return {"classification": "no_source", "source_ok": False, "telemetry_fresh": False}

    rows = sorted(history, key=lambda row: int(row.get("frame", -1)))
    complete = bool(rows and rows[0].get("frame") == 1 and rows[-1].get("frame") >= final_frame)
    fresh = bool(
        complete
        and all(
            int(right["frame"]) == int(left["frame"]) + 1
            and int(right["perf_counter_ns"]) > int(left["perf_counter_ns"])
            and int(right["kit_update_number"]) > int(left["kit_update_number"])
            and float(right["timeline_time"]) > float(left["timeline_time"])
            for left, right in zip(rows, rows[1:])
        )
    )
    if not complete:
        return {"classification": "indeterminate", "source_ok": True, "telemetry_fresh": fresh}
    if not fresh:
        return {"classification": "stale_telemetry", "source_ok": True, "telemetry_fresh": False}

    early = [row for row in rows if int(row["frame"]) <= required_frames]
    representative_threshold = int(thresholds["representative_active_blocks"])
    small_min = int(thresholds["small_field_minimum_blocks"])
    small_max = int(thresholds["small_field_maximum_blocks"])
    first_representative = next(
        (int(row["frame"]) for row in rows if int(row["active_blocks"]) >= representative_threshold), None
    )
    classification = "indeterminate"
    if first_representative is not None and first_representative <= required_frames:
        classification = "representative_ingestion"
    elif early and all(small_min <= int(row["active_blocks"]) <= small_max for row in early):
        classification = "small_field_ingestion"
    return {
        "classification": classification,
        "source_ok": True,
        "telemetry_fresh": True,
        "history_complete": True,
        "sample_count": len(rows),
        "minimum_active_blocks": min(int(row["active_blocks"]) for row in rows),
        "maximum_active_blocks": max(int(row["active_blocks"]) for row in rows),
        "first_24_frame": next((int(row["frame"]) for row in rows if int(row["active_blocks"]) == 24), None),
        "first_above_24_frame": next((int(row["frame"]) for row in rows if int(row["active_blocks"]) > 24), None),
        "first_representative_frame": first_representative,
    }
