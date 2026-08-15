"""App-ready-only Phase 6HO smoke; no stage, Flow operation, or readback."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app


def _commit(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


settings = carb.settings.get_settings()
output = Path(settings.get_as_string("/phase6ho/output"))
markers = Path(settings.get_as_string("/phase6ho/markers"))
expected_campfire = Path(settings.get_as_string("/phase6ho/expectedCampfirePath"))
expected_anim = Path(settings.get_as_string("/phase6ho/expectedAnimPath"))

def marker(name: str, **payload) -> None:
    markers.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema": "campfire.phase6ho.app-ready-marker.v1", "marker": name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **payload}
    with markers.open("ab", buffering=0) as stream:
        stream.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8")); os.fsync(stream.fileno())

report = {"schema": "campfire.phase6ho.app-ready-smoke.v1", "status": "failed", "stage_created": False, "flow_interface_calls": 0, "readback_calls": 0}
try:
    marker("app_ready")
    app = omni.kit.app.get_app()
    manager = app.get_extension_manager()
    marker("extension_manager_acquired")
    anim_id = manager.get_enabled_extension_id("omni.anim.curve.core")
    campfire_id = manager.get_enabled_extension_id("campfire.app")
    if not anim_id or not campfire_id:
        raise RuntimeError("required_extension_not_enabled")
    anim_path = Path(manager.get_extension_path(anim_id)).resolve()
    campfire_path = Path(manager.get_extension_path(campfire_id)).resolve()
    import campfire
    import campfire.app
    module_path = Path(campfire.app.__file__).resolve()
    if campfire_path != expected_campfire.resolve() or anim_path != expected_anim.resolve():
        raise RuntimeError("resolved_extension_path_mismatch")
    if campfire_path not in module_path.parents:
        raise RuntimeError("campfire_module_path_mismatch")
    marker("extension_resolution_complete", anim_id=anim_id, campfire_id=campfire_id)
    report.update({"status": "qualified", "kit_app_ready": bool(app.is_running()), "anim_extension_id": anim_id,
                   "anim_extension_path": str(anim_path), "campfire_extension_id": campfire_id,
                   "campfire_extension_path": str(campfire_path), "campfire_module_path": str(module_path),
                   "working_directory": str(Path.cwd()), "operation_complete": True,
                   "shutdown_complete": True})
    marker("smoke_complete")
except BaseException as exc:
    report.update({"error_type": type(exc).__name__, "error": str(exc), "operation_complete": False, "shutdown_complete": True})
    marker("smoke_failed", error_type=type(exc).__name__)
_commit(output, report)
marker("shutdown_complete")
omni.kit.app.get_app().post_uncancellable_quit(0 if report["status"] == "qualified" else 1)
