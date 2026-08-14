"""Offline gate for the Phase 6GO strictly increasing operation ladder."""

from __future__ import annotations

STAGES = (
    "R0", "R1", "R2_temperature", "R2_fuel", "R2_burn", "R2_smoke",
    "R2_velocity", "R2_divergence", "R3_temperature", "R4_temperature",
    "R5_temperature", "R6_temperature", "R7_temperature_velocity",
)


def next_stage(completed: list[str], outcome: str) -> dict:
    expected = STAGES[len(completed)] if len(completed) < len(STAGES) else None
    if outcome != "pass":
        return {"proceed": False, "next": None, "classification": "safe_stop_first_failure"}
    if expected is None:
        return {"proceed": False, "next": None, "classification": "qualified_complete"}
    return {
        "proceed": True,
        "next": STAGES[len(completed) + 1] if len(completed) + 1 < len(STAGES) else None,
        "classification": "continue" if len(completed) + 1 < len(STAGES) else "qualified_complete",
    }


def validate_marker_order(markers: list[str], required: list[str]) -> dict:
    positions, cursor = {}, -1
    failures = []
    for name in required:
        try:
            index = markers.index(name, cursor + 1)
        except ValueError:
            failures.append(f"missing:{name}")
            continue
        if index <= cursor:
            failures.append(f"reversed:{name}")
        positions[name] = index
        cursor = index
    return {"pass": not failures, "failures": failures, "positions": positions}
