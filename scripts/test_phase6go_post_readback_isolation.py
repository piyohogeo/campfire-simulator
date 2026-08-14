"""No-Kit fixtures for the Phase 6GO fail-closed ladder and markers."""

from phase6go_post_readback_isolation_policy import STAGES, next_stage, validate_marker_order


def main() -> int:
    results = []
    completed = []
    for stage in STAGES:
        decision = next_stage(completed, "pass")
        results.append(decision["classification"] in ("continue", "qualified_complete"))
        completed.append(stage)
    results.append(next_stage([], "native_crash")["classification"] == "safe_stop_first_failure")
    results.append(next_stage(["R0"], "resource_limit")["proceed"] is False)
    good = ["readback_before", "readback_after", "release_before", "release_after"]
    results.append(validate_marker_order(good, good)["pass"])
    results.append(not validate_marker_order(good[:-1], good)["pass"])
    results.append(not validate_marker_order(list(reversed(good)), good)["pass"])
    if not all(results):
        raise SystemExit("Phase 6GO offline fixture failed")
    print(f"Phase 6GO offline fixtures passed: {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
