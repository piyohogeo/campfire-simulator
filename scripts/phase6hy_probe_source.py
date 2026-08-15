"""Exact Phase 6HY probe builder; nested import is intentionally audited."""

from pathlib import Path

from phase6hx_probe_source import build_probe_source as _build_frozen_source


def build_probe_source(base_path: Path) -> str:
    return _build_frozen_source(base_path)

