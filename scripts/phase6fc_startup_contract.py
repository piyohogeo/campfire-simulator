"""Pure Phase 6FC startup classification helpers."""

from __future__ import annotations


def classify_startup(history: list[dict], source: dict, thresholds: dict) -> dict:
    final_frame = int(thresholds["final_frame"])
    classification_frame = int(thresholds["classification_frame"])
    sums = source.get("source_sums") or {}
    source_ok = bool(
        source.get("enabled") is True
        and int(source.get("revision", -1)) == int(thresholds["expected_point_revision"])
        and int(source.get("total_point_count", 0)) == int(thresholds["expected_total_point_count"])
        and int(source.get("active_point_count", 0)) == int(thresholds["expected_active_point_count"])
        and float(sums.get("fuel", 0.0)) >= float(thresholds["minimum_fuel_sum"])
        and float(sums.get("temperature", 0.0)) >= float(thresholds["minimum_temperature_sum"])
        and float(sums.get("smoke", 0.0)) >= float(thresholds["minimum_smoke_sum"])
    )
    if not source_ok:
        return {"classification": "no_source", "source_ok": False, "telemetry_fresh": False}

    rows = sorted(history, key=lambda item: int(item.get("frame", -1)))
    complete = bool(rows and int(rows[0].get("frame", -1)) == 1 and int(rows[-1].get("frame", -1)) >= final_frame)
    fresh = bool(
        complete
        and bool(rows[0].get("timeline_playing"))
        and all(
            int(right["frame"]) == int(left["frame"]) + 1
            and int(right["perf_counter_ns"]) > int(left["perf_counter_ns"])
            and int(right["kit_update_number"]) > int(left["kit_update_number"])
            and float(right["timeline_time"]) > float(left["timeline_time"])
            and bool(right.get("timeline_playing"))
            for left, right in zip(rows, rows[1:])
        )
    )
    if not complete:
        return {"classification": "lifecycle_failure", "source_ok": True, "telemetry_fresh": False, "history_complete": False}
    if not fresh:
        return {"classification": "stale_telemetry", "source_ok": True, "telemetry_fresh": False, "history_complete": True}

    threshold = int(thresholds["representative_active_blocks"])
    first_representative = next((int(item["frame"]) for item in rows if int(item["active_blocks"]) >= threshold), None)
    early = [item for item in rows if int(item["frame"]) <= classification_frame]
    small_min = int(thresholds["small_field_minimum_blocks"])
    small_max = int(thresholds["small_field_maximum_blocks"])
    if first_representative is not None and first_representative <= classification_frame:
        classification = "representative_ingestion"
    elif first_representative is not None and first_representative <= final_frame:
        classification = "delayed_ingestion"
    elif early and all(small_min <= int(item["active_blocks"]) <= small_max for item in early):
        classification = "small_field_ingestion"
    else:
        classification = "indeterminate_startup"
    return {
        "classification": classification,
        "source_ok": True,
        "telemetry_fresh": True,
        "history_complete": True,
        "sample_count": len(rows),
        "minimum_active_blocks": min(int(item["active_blocks"]) for item in rows),
        "maximum_active_blocks": max(int(item["active_blocks"]) for item in rows),
        "first_24_frame": next((int(item["frame"]) for item in rows if int(item["active_blocks"]) == 24), None),
        "first_above_24_frame": next((int(item["frame"]) for item in rows if int(item["active_blocks"]) > 24), None),
        "first_representative_frame": first_representative,
    }
