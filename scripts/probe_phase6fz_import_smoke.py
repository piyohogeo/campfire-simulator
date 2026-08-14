"""App-ready Kit --exec import smoke for the Phase 6FZ shared probe."""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from phase6fz_import_contract import load_exact_module


def _commit(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with partial.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


settings = carb.settings.get_settings()
report_path = Path(settings.get_as_string("/phase6fz/importSmokeReport")).resolve()
target = settings.get_as_string("/phase6fz/importTarget")
expected = settings.get_as_string("/phase6fz/importExpected")
expectation = settings.get_as_string("/phase6fz/importExpectation") or "success"
report = {
    "schema": "campfire.phase6fz.app-ready-import-smoke.v1",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "expectation": expectation,
    "target": target,
    "expected": expected,
    "wrapper_file": str(Path(__file__).resolve()),
    "working_directory": str(Path.cwd()),
    "kit_app_ready": bool(omni.kit.app.get_app().is_running()),
    "sys_path_at_exec": list(sys.path),
}
try:
    module, audit = load_exact_module(
        target,
        expected,
        module_name="campfire_phase6fz_import_smoke_target",
        required_entrypoints=("_run", "_append_resource_marker"),
    )
    report.update(status="pass" if expectation == "success" else "unexpected_success", import_audit=audit)
except BaseException as exc:
    expected_failure = expectation in {"missing", "wrong_path"}
    report.update(
        status="expected_failure" if expected_failure else "fail",
        error_type=type(exc).__name__,
        error=str(exc),
        traceback=traceback.format_exc(limit=8),
    )

_commit(report_path, report)
exit_code = 0 if report["status"] in {"pass", "expected_failure"} else 12
omni.kit.app.get_app().post_uncancellable_quit(exit_code)
