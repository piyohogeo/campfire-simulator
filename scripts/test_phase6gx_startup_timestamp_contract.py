"""Exact producer-to-consumer no-Kit fixture for Phase 6GX."""

from __future__ import annotations

import json

from phase6fc_startup_contract import classify_startup


THRESHOLDS = {
    "final_frame": 60, "classification_frame": 60,
    "expected_point_revision": 1, "expected_total_point_count": 1440,
    "expected_active_point_count": 1344, "minimum_fuel_sum": 1000,
    "minimum_temperature_sum": 2600, "minimum_smoke_sum": 100,
    "representative_active_blocks": 128, "small_field_minimum_blocks": 20,
    "small_field_maximum_blocks": 32,
}
SOURCE = {"enabled": True, "revision": 1, "total_point_count": 1440,
          "active_point_count": 1344,
          "source_sums": {"fuel": 1075.2000160217285, "temperature": 2688.0,
                          "smoke": 107.51999759674072}}


def history(key: str) -> list[dict]:
    return [{"frame": frame, key: frame * 100, "kit_update_number": frame + 9000,
             "timeline_time": frame / 60, "timeline_playing": True,
             "active_blocks": 269 + frame * 7} for frame in range(1, 61)]


def rejected(call, exception) -> bool:
    try: call()
    except exception: return True
    return False


def main() -> int:
    cases = []
    def check(name, passed, observed=None): cases.append({"name":name,"passed":bool(passed),"observed":observed})
    current = classify_startup(history("sample_perf_counter_ns"), SOURCE, THRESHOLDS)
    check("exact_current_producer_record", current["classification"] == "representative_ingestion", current)
    legacy = classify_startup(history("perf_counter_ns"), SOURCE, THRESHOLDS)
    check("frozen_legacy_record_compatible", legacy["classification"] == "representative_ingestion", legacy)
    both = history("sample_perf_counter_ns")
    for row in both: row["perf_counter_ns"] = row["sample_perf_counter_ns"]
    check("matching_dual_key_canonical", classify_startup(both, SOURCE, THRESHOLDS)["telemetry_fresh"])
    conflict = history("sample_perf_counter_ns")
    for row in conflict: row["perf_counter_ns"] = row["sample_perf_counter_ns"] + 1
    check("conflicting_dual_key_rejected", rejected(lambda: classify_startup(conflict, SOURCE, THRESHOLDS), ValueError))
    missing = history("sample_perf_counter_ns")
    del missing[10]["sample_perf_counter_ns"]
    check("missing_timestamp_rejected", rejected(lambda: classify_startup(missing, SOURCE, THRESHOLDS), KeyError))
    stale = history("sample_perf_counter_ns")
    stale[10]["sample_perf_counter_ns"] = stale[9]["sample_perf_counter_ns"]
    check("nonmonotonic_current_is_stale", classify_startup(stale, SOURCE, THRESHOLDS)["classification"] == "stale_telemetry")
    report = {"schema":"campfire.phase6gx.startup-timestamp-fixture.v1",
              "passed":all(x["passed"] for x in cases), "case_count":len(cases),
              "kit_started":False, "cases":cases}
    print(json.dumps(report, separators=(",",":")))
    if not report["passed"]: raise SystemExit([x["name"] for x in cases if not x["passed"]])
    return 0


if __name__ == "__main__": raise SystemExit(main())
