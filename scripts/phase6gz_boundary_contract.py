"""Pure contract helpers for the Phase 6GZ post-readback boundary ladder."""

from __future__ import annotations

from pathlib import Path


LADDER = (
    ("control_r2", "control", "R2", -1),
    ("candidate_temperature_front", "candidate", "R0", 0),
    ("candidate_temperature_volume", "candidate", "R1", 1),
    ("candidate_temperature_volume_metadata", "candidate", "R2", 2),
    ("candidate_temperature_save", "candidate", "R3", 3),
    ("candidate_temperature_typed_read", "candidate", "R4", 4),
    ("candidate_temperature_sampling", "candidate", "R5", 5),
    ("candidate_temperature_collector", "candidate", "R6", 6),
)

LEVEL_NAMES = (
    "temperature_front",
    "temperature_volume",
    "temperature_volume_metadata",
    "temperature_save",
    "temperature_typed_read",
    "temperature_sampling",
    "temperature_collector",
)

MODE_TO_LEVEL = {mode: level for _, kind, mode, level in LADDER if kind == "candidate"}

ALLOWED_TEMPORARY_NAMES = {
    *(f"handle_{index}.nvdb" for index in range(7)),
    "p3_f0180_velocity.nvdb",
    "p3_f0180_temperature.nvdb",
}

REQUIRED_BOUNDARY_MARKERS = (
    "phase6gz_readback_before",
    "phase6gz_readback_after",
    "phase6gz_list_count_check_after",
    "phase6gz_handle_array_metadata_before",
    "phase6gz_handle_array_metadata_after",
    "phase6gz_schema_buffer_to_volume_before",
    "phase6gz_schema_buffer_to_volume_after",
    "phase6gz_schema_volume_metadata_before",
    "phase6gz_schema_volume_metadata_after",
    "phase6gz_schema_save_before",
    "phase6gz_schema_save_after",
    "phase6gz_schema_file_durable",
    "phase6gz_schema_validation_before",
    "phase6gz_schema_validation_after",
    "phase6gz_temperature_entry",
    "phase6gz_temperature_buffer_to_volume_before",
    "phase6gz_temperature_buffer_to_volume_after",
    "phase6gz_temperature_save_before",
    "phase6gz_temperature_save_after",
    "phase6gz_temperature_file_durable",
    "phase6gz_temperature_sampling_before",
    "phase6gz_temperature_sampling_after",
    "phase6gz_temperature_collector_before",
    "phase6gz_temperature_collector_after",
    "phase6gz_release_before",
    "phase6gz_release_after",
)


def candidate_level(mode: str) -> int:
    if mode not in MODE_TO_LEVEL:
        raise ValueError(f"unsupported Phase 6GZ candidate mode: {mode}")
    return MODE_TO_LEVEL[mode]


def validate_ladder(rows: list[dict]) -> dict:
    expected = [name for name, _, _, _ in LADDER]
    names = [row.get("name") for row in rows]
    reasons = []
    if names != expected:
        reasons.append("ladder_order_mismatch")
    levels = [row.get("level") for row in rows if row.get("kind") == "candidate"]
    if levels != list(range(len(LEVEL_NAMES))):
        reasons.append("candidate_levels_not_single_step_prefixes")
    if len(set(names)) != len(names):
        reasons.append("duplicate_condition")
    return {"pass": not reasons, "reasons": reasons, "expected_order": expected}


def classify_boundary(marker_names: list[str], process_exit_code: int | None, timed_out: bool) -> dict:
    last = marker_names[-1] if marker_names else None
    if process_exit_code in (3221225477, -1073741819):
        classification = "windows_native_exception"
    elif timed_out:
        classification = "timeout"
    elif process_exit_code == 0:
        classification = "normal_exit"
    else:
        classification = "operation_failure"
    return {"classification": classification, "last_marker": last}


def validate_temporary_path(attempt_root: Path, candidate: Path) -> dict:
    """Validate an exact Phase 6GZ temporary-file target without touching it."""

    root = attempt_root.resolve()
    target = candidate.resolve()
    reasons = []
    try:
        target.relative_to(root)
    except ValueError:
        reasons.append("outside_attempt_root")
    if target.name not in ALLOWED_TEMPORARY_NAMES:
        reasons.append("name_not_allowlisted")
    return {"pass": not reasons, "reasons": reasons, "path": str(target)}


def classify_historical_candidate(phase: str, sequence: int) -> str:
    if phase == "phase6gy" and int(sequence) == 23:
        return "user-intervention-contaminated"
    return "primary-unintervened"
