"""Phase 6FG three-layer safety and repetition-candidate policy."""

from __future__ import annotations


def evaluate_hard_gate(evidence: dict, safety: dict) -> dict:
    failures: list[str] = []
    if evidence.get("guard_status") != "ok" or evidence.get("guard_exit_code") != 0:
        failures.append("resource_guard")
    if evidence.get("process_absent") is not True or evidence.get("cleanup_residual_count") != 0:
        failures.append("cleanup")
    limits = {
        "runner_peak_bytes": "runner_private_limit_bytes",
        "diagnostic_peak_bytes": "diagnostic_private_limit_bytes",
        "kit_peak_bytes": "kit_private_limit_bytes",
        "tree_peak_bytes": "unique_tree_private_limit_bytes",
    }
    for measured, limit in limits.items():
        value = evidence.get(measured)
        if value is None or int(value) > int(safety[limit]):
            failures.append(measured[:-6] if measured.endswith("_bytes") else measured)
    if evidence.get("minimum_available_physical_bytes") is None or int(evidence["minimum_available_physical_bytes"]) < int(safety["physical_memory_floor_bytes"]):
        failures.append("physical_memory_floor")
    if evidence.get("minimum_commit_headroom_bytes") is None or int(evidence["minimum_commit_headroom_bytes"]) < int(safety["commit_headroom_floor_bytes"]):
        failures.append("commit_headroom_floor")
    for name in ("fatal_count", "access_violation_count", "dump_count", "upload_attempt_count"):
        if int(evidence.get(name, -1)) != 0:
            failures.append(name)
    if evidence.get("lifecycle_complete") is not True or evidence.get("normal_os_exit") is not True:
        failures.append("lifecycle")
    return {"gate_pass": not failures, "failures": sorted(set(failures))}


def evaluate_repetition_candidate(settled_baselines: list[int], contract: dict) -> dict:
    cfg = contract["repetition_candidate"]
    if len(settled_baselines) < int(cfg["synthetic_settled_baseline_count"]):
        return {"gate_pass": False, "classification": "insufficient_iterations", "increments": []}
    values = [int(value) for value in settled_baselines]
    increments = [right - left for left, right in zip(values, values[1:])]
    threshold = int(cfg["staircase_minimum_increment_bytes"])
    longest = current = 0
    for delta in increments:
        current = current + 1 if delta >= threshold else 0
        longest = max(longest, current)
    staircase = longest >= int(cfg["staircase_minimum_consecutive_increases"])
    tail = values[1:]
    tail_range = max(tail) - min(tail) if tail else 0
    plateau = tail_range <= int(cfg["first_cache_then_plateau_maximum_tail_range_bytes"])
    return {
        "gate_pass": bool(plateau and not staircase),
        "classification": "first_cache_then_plateau" if plateau and not staircase else "staircase_accumulation",
        "increments": increments,
        "longest_material_increase_run": longest,
        "tail_range_bytes": tail_range,
    }
