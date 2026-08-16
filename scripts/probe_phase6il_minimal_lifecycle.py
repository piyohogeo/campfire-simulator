from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import carb
import omni.kit.app

SCRIPTS = Path(__file__).resolve(strict=True).parent
CONTRACT = SCRIPTS / "phase6il_post_shutdown_contract.json"
SIDECAR = SCRIPTS / "phase6il_post_shutdown_contract.sha256"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_exact(path: Path, expected_hash: str, name: str):
    resolved = path.resolve(strict=True)
    if resolved.parent != SCRIPTS:
        raise ImportError("phase6il_module_root_escape")
    if _sha(resolved) != expected_hash:
        raise ImportError("phase6il_module_hash_mismatch:" + resolved.name)
    if name in sys.modules:
        raise ImportError("phase6il_module_shadowed:" + name)
    spec = importlib.util.spec_from_file_location(name, resolved)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != resolved:
        raise ImportError("phase6il_module_path_mismatch")
    return module


policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
if _sha(CONTRACT) != SIDECAR.read_text(encoding="ascii").split()[0].upper():
    raise ImportError("phase6il_contract_digest_mismatch")
atomic_spec = Path("phase6hu_atomic_report.py")
atomic_hash = _sha(SCRIPTS / atomic_spec)
_load_exact(SCRIPTS / atomic_spec, atomic_hash, "phase6hu_atomic_report")
boundary_spec = policy["modules"]["boundary"]
boundary = _load_exact(SCRIPTS / boundary_spec["path"], boundary_spec["sha256"], "phase6il_boundary_runtime")
settings = carb.settings.get_settings()
attempt_id = settings.get_as_string("/phase6il/attemptId")
marker_path = Path(settings.get_as_string("/phase6il/markers")).resolve()
report_path = Path(settings.get_as_string("/phase6il/report")).resolve()
started = time.monotonic()


def mark(step: str) -> None:
    boundary.append_marker(
        marker_path,
        attempt_id=attempt_id,
        step_id=step,
        actor="child_kit",
        pid=__import__("os").getpid(),
        creation_time_utc_epoch=boundary.process_creation_time_utc_epoch(),
        monotonic_elapsed_seconds=time.monotonic() - started,
    )


# No Stage, Layer, timeline, renderer, Flow, readback, or capture call is made.
mark("process_started")
mark("kit_app_ready")
operation = {
    "schema": "campfire.phase6il.minimal-operation.v1",
    "phase": "phase6il",
    "attempt_id": attempt_id,
    "status": "qualified",
    "operation_complete": True,
    "shutdown_complete": False,
    "stage_calls": 0,
    "timeline_play_calls": 0,
    "flow_calls": 0,
    "readback_calls": 0,
    "renderer_update_calls": 0,
    "capture_calls": 0,
}
boundary.write_report(report_path, operation)
mark("operation_complete")
operation["shutdown_complete"] = True
boundary.write_report(report_path, operation)
mark("shutdown_complete")
omni.kit.app.get_app().post_uncancellable_quit(0)
