"""Phase 6HP app-ready smoke with a junction-aware, fail-closed module gate."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app

SCRIPT_DIR = Path(__file__).absolute().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6hp_junction_module_path import (  # noqa: E402
    collect_module_path_evidence,
    validate_module_path_evidence,
)


def _commit(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


settings = carb.settings.get_settings()
output = Path(settings.get_as_string("/phase6hp/output"))
markers = Path(settings.get_as_string("/phase6hp/markers"))
expected_anim = Path(settings.get_as_string("/phase6hp/expectedAnimPath"))


def marker(name: str, **payload) -> None:
    markers.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "campfire.phase6hp.app-ready-marker.v1",
        "marker": name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with markers.open("ab", buffering=0) as stream:
        stream.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(stream.fileno())


report = {
    "schema": "campfire.phase6hp.app-ready-smoke.v1",
    "status": "failed",
    "stage_created": False,
    "flow_interface_calls": 0,
    "readback_calls": 0,
}
try:
    marker("app_ready")
    app = omni.kit.app.get_app()
    manager = app.get_extension_manager()
    marker("extension_manager_acquired")
    anim_id = manager.get_enabled_extension_id("omni.anim.curve.core")
    campfire_id = manager.get_enabled_extension_id("campfire.app")
    if not anim_id or not campfire_id:
        raise RuntimeError("required_extension_not_enabled")
    anim_path_lexical = Path(manager.get_extension_path(anim_id))
    campfire_path_lexical = Path(manager.get_extension_path(campfire_id))
    if anim_path_lexical.resolve(strict=True) != expected_anim.resolve(strict=True):
        raise RuntimeError("anim_extension_path_mismatch")
    import campfire
    import campfire.app
    module_evidence = collect_module_path_evidence(
        extension_id=campfire_id,
        extension_root=campfire_path_lexical,
        module_name=campfire.app.__name__,
        package_name=campfire.__name__,
        module_file=campfire.app.__file__,
    )
    gate_ok, gate_reason = validate_module_path_evidence(module_evidence)
    report["module_path_evidence"] = module_evidence
    report["module_path_gate"] = {"passed": gate_ok, "reason": gate_reason}
    if not gate_ok:
        raise RuntimeError("junction_module_path_gate:" + gate_reason)
    marker(
        "junction_module_path_gate_complete",
        extension_id=campfire_id,
        junction_reparse_tag=module_evidence["junction_reparse_tag"],
        gate_reason=gate_reason,
    )
    report.update(
        {
            "status": "qualified",
            "kit_app_ready": bool(app.is_running()),
            "anim_extension_id": anim_id,
            "anim_extension_path_lexical": str(anim_path_lexical),
            "campfire_extension_id": campfire_id,
            "campfire_extension_path_lexical": str(campfire_path_lexical),
            "operation_complete": True,
            "shutdown_complete": True,
        }
    )
    marker("operation_complete")
    marker("smoke_complete")
except BaseException as exc:
    report.update(
        {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "operation_complete": False,
            "shutdown_complete": True,
        }
    )
    marker("smoke_failed", error_type=type(exc).__name__)
_commit(output, report)
marker("shutdown_complete")
omni.kit.app.get_app().post_uncancellable_quit(0 if report["status"] == "qualified" else 1)
