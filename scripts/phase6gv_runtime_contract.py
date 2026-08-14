"""Frozen, no-Kit runtime constants for the Phase 6GV repetition harness."""

from __future__ import annotations

from pathlib import Path


CANONICAL_TEMPORARY_FILENAME = "slot0_temperature_temporary_once.nvdb"


def canonical_temporary_path(artifact_directory: Path) -> Path:
    root = Path(artifact_directory).resolve()
    path = (root / CANONICAL_TEMPORARY_FILENAME).resolve()
    if path.parent != root or path.name != CANONICAL_TEMPORARY_FILENAME:
        raise ValueError("temporary path escaped its process artifact directory")
    return path
