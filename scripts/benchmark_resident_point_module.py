"""Run the Resident recovery scenario with production Point module types."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import carb


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_BENCHMARK = ROOT / "scripts" / "benchmark_resident_stage_orchestrator.py"


def _load_orchestrator_module():
    spec = importlib.util.spec_from_file_location(
        "campfire_phase6cg_orchestrator", ORCHESTRATOR_BENCHMARK
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load benchmark: {ORCHESTRATOR_BENCHMARK}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase6cf = _load_orchestrator_module()


def _settings():
    settings = carb.settings.get_settings()
    return {
        "native_library": Path(settings.get_as_string("/phase6cg/nativeLibrary")),
        "output": Path(settings.get_as_string("/phase6cg/output")),
        "video_frames": Path(settings.get_as_string("/phase6cg/videoFrames")),
    }


def main():
    asyncio.ensure_future(phase6cf._run(_settings(), phase="phase6cg"))


if __name__ == "__main__":
    main()
