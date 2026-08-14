"""Phase 6GM formal comparison with Phase 6GK-matched export authoring."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import carb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module

PHASE6GL_PATH = (SCRIPT_DIR / "probe_phase6gl_supply_comparison.py").resolve()
EXPORT_PATH = (SCRIPT_DIR / "phase6gm_flow_export_state.py").resolve()
settings = carb.settings.get_settings()
audit_path = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


try:
    phase6gl, phase6gl_audit = load_exact_module(
        PHASE6GL_PATH, PHASE6GL_PATH, module_name="campfire_phase6gm_phase6gl_boundary",
        required_entrypoints=("_qualified_spatial_boundary", "shared"),
    )
    export_state, export_audit = load_exact_module(
        EXPORT_PATH, EXPORT_PATH, module_name="campfire_phase6gm_export_state",
        required_entrypoints=("author", "validate", "descriptor_digest"),
    )
    _atomic_json(audit_path, {
        "schema": "campfire.phase6gm.kit-import-audit.v1", "status": "pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "kit_app_ready_exec": True,
        "wrapper_file": str(Path(__file__).resolve()), "working_directory": str(Path.cwd()),
        "imports": [phase6gl_audit, export_audit],
    })
except BaseException as exc:
    _atomic_json(audit_path, {
        "schema": "campfire.phase6gm.kit-import-audit.v1", "status": "fail",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "error_type": type(exc).__name__,
        "error": str(exc), "wrapper_file": str(Path(__file__).resolve()),
    })
    raise

shared = phase6gl.shared
_base_build_stage = shared._build_stage


def _build_stage_with_qualified_exports(arguments):
    stage_path, point_summary, plan = _base_build_stage(arguments)
    stage = shared.Usd.Stage.Open(str(stage_path))
    if stage is None:
        raise RuntimeError("Phase 6GM failed to reopen generated diagnostic stage")
    validation = export_state.author(stage)
    if not validation["pass"]:
        raise RuntimeError(f"Phase 6GM export authoring validation failed: {validation['failures']}")
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Phase 6GM failed to save qualified Flow export state")
    reloaded = shared.Usd.Stage.Open(str(stage_path))
    persisted = export_state.validate(reloaded)
    if not persisted["pass"]:
        raise RuntimeError(f"Phase 6GM persisted export state failed: {persisted['failures']}")
    point_summary["phase6gm_flow_export_state"] = persisted
    return stage_path, point_summary, plan


shared._build_stage = _build_stage_with_qualified_exports

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
