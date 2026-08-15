"""Phase 6HC wrapper: canonical operation evidence over the frozen HB ladder."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import carb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module
from phase6hb_candidate_lifecycle_contract import LADDER
from phase6hc_operation_evidence import COMPLETE_MARKER, FAILURE_MARKER, SCHEMA

HB_PATH = (SCRIPT_DIR / "probe_phase6hb_candidate_lifecycle.py").resolve()
settings = carb.settings.get_settings()
MODE = settings.get_as_string("/phase6go/isolationMode") or "R0"
CONDITION_BY_MODE = {row["mode"]: row["name"] for row in LADDER}
if MODE not in CONDITION_BY_MODE:
    raise ImportError(f"unsupported Phase 6HC mode: {MODE}")
CONDITION = CONDITION_BY_MODE[MODE]
ATTEMPT_ID = settings.get_as_string("/phase6ep/startupProbeLabel") or ""
if ATTEMPT_ID != CONDITION:
    raise ImportError(f"Phase 6HC attempt identity mismatch: {ATTEMPT_ID!r} != {CONDITION!r}")

hb, hb_audit = load_exact_module(
    HB_PATH, HB_PATH, module_name="campfire_phase6hc_phase6hb_base", required_entrypoints=()
)


def checkpoint(name: str, **values) -> None:
    translated = name.replace("phase6hb_", "phase6hc_", 1) if name.startswith("phase6hb_") else name
    hb.report["last_operation_marker"] = translated
    if translated == COMPLETE_MARKER:
        hb.report["operation_complete"] = True
    elif translated == FAILURE_MARKER:
        hb.report["operation_complete"] = False
    hb.report["checkpoints"].append({
        "name": translated,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **values,
    })
    hb._atomic_json(hb.REPORT_PATH, hb.report)


original_append_resource_marker = hb.shared._append_resource_marker


def append_resource_marker(path, name, *args, **kwargs):
    translated = name.replace("phase6hb_", "phase6hc_", 1) if name.startswith("phase6hb_") else name
    if kwargs.get("phase") == "phase6hb":
        kwargs["phase"] = "phase6hc"
    return original_append_resource_marker(path, translated, *args, **kwargs)


hb.checkpoint = checkpoint
hb.shared._append_resource_marker = append_resource_marker
hb.report.update({
    "schema": SCHEMA,
    "phase": "phase6hc",
    "condition": CONDITION,
    "attempt_identity": {"attempt_id": ATTEMPT_ID, "condition": CONDITION, "mode": MODE},
    "operation_complete": False,
    "canonical_operation_evidence": True,
})
hb._atomic_json(hb.REPORT_PATH, hb.report)
hb._atomic_json(hb.AUDIT_PATH, {
    "schema": "campfire.phase6hc.kit-import-audit.v1",
    "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper": str(Path(__file__).resolve()),
    "base_wrapper": str(HB_PATH),
    "base_import": hb_audit,
    "condition": CONDITION,
    "attempt_id": ATTEMPT_ID,
    "canonical_operation_schema": SCHEMA,
    "marker_namespace_normalized": True,
    "patched": hb.shared._p3_spatial_boundary is hb._phase6hb_boundary,
})

if __name__ == "__main__":
    asyncio.ensure_future(hb.shared._run())
