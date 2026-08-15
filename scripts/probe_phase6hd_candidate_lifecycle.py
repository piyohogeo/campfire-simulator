"""Phase 6HD wrapper using the shared canonical counter/report producer."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import carb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module
from phase6hb_candidate_lifecycle_contract import LADDER
from phase6hd_operation_schema import (
    COMPLETE_MARKER,
    FAILURE_MARKER,
    SCHEMA,
    append_checkpoint,
    increment_counter,
    new_runtime_report,
    write_operation_report,
)

HB_PATH = (SCRIPT_DIR / "probe_phase6hb_candidate_lifecycle.py").resolve()
settings = carb.settings.get_settings()
MODE = settings.get_as_string("/phase6go/isolationMode") or "R0"
ROW_BY_MODE = {row["mode"]: row for row in LADDER}
if MODE not in ROW_BY_MODE:
    raise ImportError(f"unsupported Phase 6HD mode: {MODE}")
CONDITION = ROW_BY_MODE[MODE]["name"]
ATTEMPT_ID = settings.get_as_string("/phase6ep/startupProbeLabel") or ""
if ATTEMPT_ID != CONDITION:
    raise ImportError(f"Phase 6HD attempt identity mismatch: {ATTEMPT_ID!r} != {CONDITION!r}")

hb, hb_audit = load_exact_module(
    HB_PATH, HB_PATH, module_name="campfire_phase6hd_phase6hb_base", required_entrypoints=()
)
hb.report = new_runtime_report(
    condition=CONDITION,
    attempt_id=ATTEMPT_ID,
    mode=MODE,
    features=list(ROW_BY_MODE[MODE]["features"]),
)


def checkpoint(name: str, **values) -> None:
    translated = name.replace("phase6hb_", "phase6hd_", 1) if name.startswith("phase6hb_") else name
    if translated == "phase6hd_readback_after":
        increment_counter(hb.report, "readback")
    if translated == COMPLETE_MARKER:
        hb.report["operation_complete"] = True
    elif translated == FAILURE_MARKER:
        hb.report["operation_complete"] = False
    append_checkpoint(hb.report, translated, **values)
    write_operation_report(hb.REPORT_PATH, hb.report)


original_append_resource_marker = hb.shared._append_resource_marker


def append_resource_marker(path, name, *args, **kwargs):
    translated = name.replace("phase6hb_", "phase6hd_", 1) if name.startswith("phase6hb_") else name
    if kwargs.get("phase") == "phase6hb":
        kwargs["phase"] = "phase6hd"
    return original_append_resource_marker(path, translated, *args, **kwargs)


original_save_and_sample = hb.shared._save_and_sample


def save_and_sample(*args, **kwargs):
    channel = args[3] if len(args) > 3 else kwargs.get("channel")
    if channel == "velocity":
        increment_counter(hb.report, "velocity_save")
    return original_save_and_sample(*args, **kwargs)


hb.checkpoint = checkpoint
hb.shared._append_resource_marker = append_resource_marker
hb.shared._save_and_sample = save_and_sample
write_operation_report(hb.REPORT_PATH, hb.report)
hb._atomic_json(hb.AUDIT_PATH, {
    "schema": "campfire.phase6hd.kit-import-audit.v1",
    "status": "pass",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper": str(Path(__file__).resolve()),
    "base_wrapper": str(HB_PATH),
    "base_import": hb_audit,
    "condition": CONDITION,
    "attempt_id": ATTEMPT_ID,
    "canonical_operation_schema": SCHEMA,
    "canonical_counter_factory": "phase6hd_operation_schema.new_runtime_report",
    "canonical_writer": "phase6hd_operation_schema.write_operation_report",
    "marker_namespace_normalized": True,
    "patched": hb.shared._p3_spatial_boundary is hb._phase6hb_boundary,
})

if __name__ == "__main__":
    asyncio.ensure_future(hb.shared._run())
