from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import carb
import omni.kit.app

WRAPPER = Path(__file__).absolute()
SCRIPTS = WRAPPER.parent
CONTRACT = SCRIPTS / "phase6ik_parent_lifecycle_contract.json"
SIDECAR = SCRIPTS / "phase6ik_parent_lifecycle_contract.sha256"


def _load_exact(path: Path, expected_hash: str, name: str):
    resolved = path.resolve(strict=True)
    if resolved.parent != SCRIPTS.resolve(strict=True):
        raise ImportError("boundary_module_root_escape")
    if hashlib.sha256(resolved.read_bytes()).hexdigest().upper() != expected_hash:
        raise ImportError("boundary_module_hash_mismatch")
    if name in sys.modules:
        raise ImportError("boundary_module_shadowed")
    spec = importlib.util.spec_from_file_location(name, resolved)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != resolved:
        raise ImportError("boundary_module_path_mismatch")
    return module


policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
if hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper() != SIDECAR.read_text().split()[0].upper():
    raise ImportError("contract_digest_mismatch")
_load_exact(SCRIPTS / policy["atomic_module"]["path"], policy["atomic_module"]["sha256"], "phase6hu_atomic_report")
boundary = _load_exact(SCRIPTS / policy["boundary_module"]["path"], policy["boundary_module"]["sha256"], "phase6ik_child_boundary_runtime")
settings = carb.settings.get_settings()
attempt_id = settings.get_as_string("/phase6ik/attemptId")
markers = Path(settings.get_as_string("/phase6ik/markers")).resolve()
report_path = Path(settings.get_as_string("/phase6ik/report")).resolve()
started = time.monotonic()

boundary.append_marker(markers, attempt_id, "kit_app_ready", monotonic_elapsed_seconds=time.monotonic() - started)

operation = {
    "schema": "campfire.phase6ik.minimal-operation.v1",
    "phase": "phase6ik",
    "attempt_id": attempt_id,
    "status": "qualified",
    "kit_app_ready": True,
    "operation_complete": True,
    "shutdown_complete": False,
    "stage_calls": 0,
    "timeline_play_calls": 0,
    "flow_calls": 0,
    "readback_calls": 0,
    "renderer_update_calls": 0,
    "capture_calls": 0,
}
boundary.write_runner_evidence(report_path, operation)
boundary.append_marker(markers, attempt_id, "operation_complete", monotonic_elapsed_seconds=time.monotonic() - started)
operation["shutdown_complete"] = True
boundary.write_runner_evidence(report_path, operation)
boundary.append_marker(markers, attempt_id, "shutdown_complete", monotonic_elapsed_seconds=time.monotonic() - started)
omni.kit.app.get_app().post_uncancellable_quit(0)
