"""Frozen stage/settings identity checks for Phase 6HV."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


TOKEN_OFF = b"bool physicsCollisionEnabled = 0"
TOKEN_ON = b"bool physicsCollisionEnabled = 1"
TOKEN_COMMON = b"bool physicsCollisionEnabled = <CONDITION>"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def settings_common(contract: dict) -> dict:
    scene = contract["fixed_scene"]
    return {
        "schema": contract["stage_authoring"]["settings_schema"],
        "production_hierarchy": scene["production_hierarchy"],
        "log_path": scene["log_path"],
        "log_world_matrix": scene["log_world_matrix"],
        "proxy_path": scene["proxy_path"],
        "proxy_topology": [scene["proxy_vertices"], scene["proxy_faces"], scene["proxy_indices"]],
        "proxy_closed_outward": scene["proxy_closed_outward"],
        "source_center_m": scene["source_center_m"],
        "source_radius_m": scene["source_radius_m"],
        "source_fuel": scene["source_fuel"],
        "source_temperature": scene["source_temperature"],
        "camera_eye_m": scene["camera_eye_m"],
        "camera_target_m": scene["camera_target_m"],
        "resolution": scene["capture_resolution"],
        "preplay_updates": scene["preplay_updates"],
        "simulation_updates": scene["simulation_updates"],
        "sample_frames": scene["active_block_frames"],
        "renderer_drain_updates": scene["renderer_drain_updates"],
    }


def settings_descriptor(contract: dict, condition: str) -> dict:
    expected = {item["name"]: item["physics_collision_enabled"] for item in contract["condition_order"]}
    if condition not in expected:
        raise ValueError(f"unknown condition: {condition}")
    return {**settings_common(contract), "condition": condition, "physics_collision_enabled": expected[condition]}


def normalized_stage_bytes(data: bytes) -> bytes:
    count = data.count(TOKEN_OFF) + data.count(TOKEN_ON)
    if count != 1:
        raise ValueError(f"physicsCollisionEnabled token count must be one, got {count}")
    return data.replace(TOKEN_OFF, TOKEN_COMMON).replace(TOKEN_ON, TOKEN_COMMON)


def validate_stage_bytes(data: bytes, contract: dict, condition: str) -> dict:
    authored = contract["stage_authoring"]
    expected_token = TOKEN_ON if condition == "collision_on" else TOKEN_OFF
    other_token = TOKEN_OFF if condition == "collision_on" else TOKEN_ON
    descriptor = settings_descriptor(contract, condition)
    evidence = {
        "condition": condition,
        "stage_sha256": sha256(data),
        "normalized_common_stage_sha256": sha256(normalized_stage_bytes(data)),
        "settings_sha256": sha256(canonical_json(descriptor)),
        "settings_common_sha256": sha256(canonical_json(settings_common(contract))),
        "expected_token_count": data.count(expected_token),
        "other_token_count": data.count(other_token),
    }
    gates = {
        "stage_sha256": evidence["stage_sha256"] == authored["expected_stage_sha256"][condition],
        "normalized_common_stage_sha256": evidence["normalized_common_stage_sha256"] == authored["normalized_common_stage_sha256"],
        "settings_sha256": evidence["settings_sha256"] == authored["settings_sha256"][condition],
        "settings_common_sha256": evidence["settings_common_sha256"] == authored["settings_common_sha256"],
        "exact_collision_token": evidence["expected_token_count"] == 1 and evidence["other_token_count"] == 0,
    }
    return {"passed": all(gates.values()), "gates": gates, "evidence": evidence, "settings": descriptor}


def validate_stage(path: Path, contract: dict, condition: str) -> dict:
    return validate_stage_bytes(path.read_bytes(), contract, condition)
