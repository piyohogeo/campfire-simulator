"""Build the exact Phase 6HX probe from the frozen Phase 6HW operation order."""

from __future__ import annotations

from pathlib import Path


def build_probe_source(base_path: Path) -> str:
    source = base_path.read_text(encoding="utf-8")
    replacements = {
        "Phase 6HW": "Phase 6HX",
        "phase6hw_stage_contract": "phase6hx_stage_contract",
        "campfire.phase6hw.single-log-end-on-run.v1": "campfire.phase6hx.single-log-end-on-run.v1",
        '"phase": "phase6hw"': '"phase": "phase6hx"',
    }
    for old, new in replacements.items():
        if old not in source:
            raise RuntimeError(f"Phase 6HX probe source token missing: {old}")
        source = source.replace(old, new)
    if 'settings.get_as_string("/phase6hw/condition")' not in source or 'settings.get_as_string("/phase6hw/stage")' not in source:
        raise RuntimeError("Phase 6HX exact case-runner setting interface changed")
    if '"phase": "phase6hw"' in source or "phase6hw_stage_contract" in source:
        raise RuntimeError("Phase 6HX raw evidence identity transformation incomplete")
    return source
