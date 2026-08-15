"""Validate the frozen Phase 6HW stage and geometry descriptors."""

from __future__ import annotations

from pathlib import Path

from phase6hw_stage_builder import (
    TOKEN_OFF,
    TOKEN_ON,
    canonical_json,
    normalized_stage_bytes,
    settings_common,
    settings_descriptor,
    sha256,
    topology,
)


def validate_stage_bytes(data: bytes, contract: dict, condition: str) -> dict:
    authored = contract["stage_authoring"]
    expected_token = TOKEN_ON if condition == "collision_on" else TOKEN_OFF
    other_token = TOKEN_OFF if condition == "collision_on" else TOKEN_ON
    descriptor = settings_descriptor(contract, condition)
    scene = contract["fixed_scene"]
    points, counts, indices = topology(scene["diagnostic_log_length_m"], scene["log_radius_m"])
    evidence = {
        "condition": condition,
        "stage_sha256": sha256(data),
        "normalized_common_stage_sha256": sha256(normalized_stage_bytes(data)),
        "settings_sha256": sha256(canonical_json(descriptor)),
        "settings_common_sha256": sha256(canonical_json(settings_common(contract))),
        "expected_token_count": data.count(expected_token),
        "other_token_count": data.count(other_token),
        "topology": [len(points), len(counts), len(indices)],
        "source_surface_gap_m": scene["source_surface_gap_m"],
        "gap_in_velocity_voxels": scene["gap_in_velocity_voxels"],
        "source_to_nearest_end_clearance_m": scene["source_to_nearest_end_clearance_m"],
        "end_clearance_in_velocity_voxels": scene["end_clearance_in_velocity_voxels"],
    }
    gates = {
        "stage_sha256": evidence["stage_sha256"] == authored["expected_stage_sha256"][condition],
        "normalized_common_stage_sha256": evidence["normalized_common_stage_sha256"] == authored["normalized_common_stage_sha256"],
        "settings_sha256": evidence["settings_sha256"] == authored["settings_sha256"][condition],
        "settings_common_sha256": evidence["settings_common_sha256"] == authored["settings_common_sha256"],
        "exact_collision_token": evidence["expected_token_count"] == 1 and evidence["other_token_count"] == 0,
        "topology_26_36_120": evidence["topology"] == [26, 36, 120],
        "gap_at_least_one_velocity_voxel": evidence["gap_in_velocity_voxels"] >= 1.0,
        "end_clearance_at_least_16_velocity_voxels": evidence["end_clearance_in_velocity_voxels"] >= 16.0,
        "no_opaque_render_mesh": b'def Mesh "RenderSurface"' not in data and b'token visibility = "invisible"' in data,
        "single_log_no_stones_or_ground": b'def Xform "Stones"' not in data and b'def Cube "Ground"' not in data,
    }
    return {"passed": all(gates.values()), "gates": gates, "evidence": evidence, "settings": descriptor}


def validate_stage(path: Path, contract: dict, condition: str) -> dict:
    return validate_stage_bytes(path.read_bytes(), contract, condition)
