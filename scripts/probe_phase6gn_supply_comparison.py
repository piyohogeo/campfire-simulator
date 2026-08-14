"""Phase 6GN formal comparison with an exact, type-aware wrapper import contract."""

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
from phase6gn_exact_wrapper_contract import audit_export_module, audit_phase6gl_and_shared

PHASE6GL_PATH = (SCRIPT_DIR / "probe_phase6gl_supply_comparison.py").resolve()
SHARED_PATH = (SCRIPT_DIR / "probe_phase6gc_shared_supply_comparison.py").resolve()
EXPORT_PATH = (SCRIPT_DIR / "phase6gm_flow_export_state.py").resolve()
EXPECTED_DESCRIPTOR_DIGEST = "53CDE38FD5B1A5F48AB2E7B896F6EF391DDA4D5F6621B21FDB1B435F34BDA8CE"
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
    # Only actual entry-point functions are passed to the legacy callable loader.
    phase6gl, phase6gl_loader_audit = load_exact_module(
        PHASE6GL_PATH,
        PHASE6GL_PATH,
        module_name="campfire_phase6gn_phase6gl_boundary",
        required_entrypoints=("_qualified_spatial_boundary",),
    )
    shared_contract_audit = audit_phase6gl_and_shared(phase6gl, PHASE6GL_PATH, SHARED_PATH)
    shared = phase6gl.shared
    export_state, export_loader_audit = load_exact_module(
        EXPORT_PATH,
        EXPORT_PATH,
        module_name="campfire_phase6gn_export_state",
        required_entrypoints=("author", "validate", "descriptor_digest", "load_descriptor"),
    )
    export_contract_audit = audit_export_module(export_state, EXPORT_PATH)
    descriptor_digest = export_state.descriptor_digest()
    if descriptor_digest != EXPECTED_DESCRIPTOR_DIGEST:
        raise ImportError(f"immutable export descriptor digest mismatch: {descriptor_digest}")
except BaseException as exc:
    _atomic_json(
        audit_path,
        {
            "schema": "campfire.phase6gn.kit-import-audit.v1",
            "status": "fail",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "wrapper_file": str(Path(__file__).resolve()),
            "process_id": os.getpid(),
        },
    )
    raise

_base_build_stage = shared._build_stage


def _build_stage_with_qualified_exports(arguments):
    stage_path, point_summary, plan = _base_build_stage(arguments)
    stage = shared.Usd.Stage.Open(str(stage_path))
    if stage is None:
        raise RuntimeError("Phase 6GN failed to reopen generated diagnostic stage")
    validation = export_state.author(stage)
    if not validation["pass"]:
        raise RuntimeError(f"Phase 6GN export authoring validation failed: {validation['failures']}")
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Phase 6GN failed to save qualified Flow export state")
    reloaded = shared.Usd.Stage.Open(str(stage_path))
    persisted = export_state.validate(reloaded)
    if not persisted["pass"]:
        raise RuntimeError(f"Phase 6GN persisted export state failed: {persisted['failures']}")
    point_summary["phase6gn_flow_export_state"] = persisted
    return stage_path, point_summary, plan


shared._build_stage = _build_stage_with_qualified_exports
WRAPPER_WIRING_AUDIT = {
    "patch_target": "shared._build_stage",
    "original_callable": callable(_base_build_stage),
    "patched_callable": callable(shared._build_stage),
    "patched_identity_matches": shared._build_stage is _build_stage_with_qualified_exports,
    "original_and_patch_are_distinct": _base_build_stage is not _build_stage_with_qualified_exports,
    "descriptor_digest": descriptor_digest,
}
if not all(
    WRAPPER_WIRING_AUDIT[key]
    for key in ("original_callable", "patched_callable", "patched_identity_matches", "original_and_patch_are_distinct")
):
    raise ImportError("Phase 6GN exact wrapper patch wiring failed")

_atomic_json(
    audit_path,
    {
        "schema": "campfire.phase6gn.kit-import-audit.v1",
        "status": "pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kit_app_ready_exec": True,
        "wrapper_file": str(Path(__file__).resolve()),
        "working_directory": str(Path.cwd()),
        "process_id": os.getpid(),
        "imports": [phase6gl_loader_audit, export_loader_audit],
        "module_contract": shared_contract_audit,
        "export_module_contract": export_contract_audit,
        "wrapper_wiring": WRAPPER_WIRING_AUDIT,
    },
)

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
