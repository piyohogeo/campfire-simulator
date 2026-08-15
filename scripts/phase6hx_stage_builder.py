"""Phase 6HX stage authoring: exact Phase 6HW scene with independent phase identity."""

from __future__ import annotations

from pathlib import Path

import phase6hw_stage_builder as base


TOKEN_OFF = base.TOKEN_OFF
TOKEN_ON = base.TOKEN_ON
TOKEN_COMMON = base.TOKEN_COMMON
sha256 = base.sha256
canonical_json = base.canonical_json
topology = base.topology
settings_common = base.settings_common
settings_descriptor = base.settings_descriptor


def build_stage_bytes(contract: dict, condition: str) -> bytes:
    data = base.build_stage_bytes(contract, condition)
    old = b'string "campfire:phase" = "phase6hw"'
    new = b'string "campfire:phase" = "phase6hx"'
    if data.count(old) != 1:
        raise RuntimeError("Phase 6HX base stage phase identity mismatch")
    return data.replace(old, new)


def normalized_stage_bytes(data: bytes) -> bytes:
    return base.normalized_stage_bytes(data)


def write_stage(path: Path, contract: dict, condition: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_stage_bytes(contract, condition))
