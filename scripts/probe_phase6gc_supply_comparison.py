"""Phase 6GC deterministic Kit wrapper for the frozen Phase 6FO physics probe."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import carb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module

SHARED_PATH = (SCRIPT_DIR / "probe_phase6gc_shared_supply_comparison.py").resolve()
settings = carb.settings.get_settings()
audit_path = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()


def _write_audit(payload: dict) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = audit_path.with_suffix(audit_path.suffix + ".partial")
    with temporary.open("wb") as stream:
        stream.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(audit_path)


try:
    shared, import_audit = load_exact_module(
        SHARED_PATH,
        SHARED_PATH,
        module_name="campfire_phase6gc_shared_supply_probe",
        required_entrypoints=("_run", "_append_resource_marker"),
    )
    _write_audit({
        "schema": "campfire.phase6gc.kit-import-audit.v1",
        "status": "pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "wrapper_file": str(Path(__file__).resolve()),
        "working_directory": str(Path.cwd()),
        "kit_app_ready_exec": True,
        "import": import_audit,
    })
except BaseException as exc:
    _write_audit({
        "schema": "campfire.phase6gc.kit-import-audit.v1",
        "status": "fail",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "wrapper_file": str(Path(__file__).resolve()),
        "working_directory": str(Path.cwd()),
        "error_type": type(exc).__name__,
        "error": str(exc),
    })
    raise

_original_append = shared._append_resource_marker


def _synchronized_append(path, marker, *args, **kwargs):
    _original_append(path, marker, *args, **kwargs)
    if marker != "measurement_complete":
        return
    acknowledgement = Path(settings.get_as_string("/phase6fz/measurementCommitAck")).resolve()
    failure = Path(settings.get_as_string("/phase6fz/measurementCommitFailure")).resolve()
    timeout = float(settings.get_as_float("/phase6fz/measurementCommitTimeoutSeconds") or 60.0)
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if acknowledgement.is_file():
            return
        if failure.is_file():
            raise RuntimeError("Phase 6GC pre-close measurement committer failed")
        time.sleep(0.05)
    raise TimeoutError("Phase 6GC pre-close measurement commit acknowledgement timed out")


shared._append_resource_marker = _synchronized_append

if __name__ == "__main__":
    asyncio.ensure_future(shared._run())
