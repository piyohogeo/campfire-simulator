from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import carb
import omni.kit.app

SCRIPTS = Path(__file__).resolve(strict=True).parent
CONTRACT = SCRIPTS / "phase6in_post_shutdown_contract.json"
SIDECAR = SCRIPTS / "phase6in_post_shutdown_contract.sha256"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_exact(path: Path, expected_sha256: str, name: str):
    path = path.resolve(strict=True)
    if path.parent != SCRIPTS or _sha(path) != expected_sha256 or name in sys.modules:
        raise ImportError("phase6in_exact_module_identity_invalid:" + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != path:
        raise ImportError("phase6in_loaded_module_path_invalid:" + name)
    return module


policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
if _sha(CONTRACT) != SIDECAR.read_text(encoding="ascii").split()[0].upper():
    raise ImportError("phase6in_contract_digest_mismatch")
atomic = SCRIPTS / "phase6hu_atomic_report.py"
_load_exact(atomic, _sha(atomic), "phase6hu_atomic_report")
helper_spec = policy["dependencies"]["phase6im_helper"]
helper = _load_exact(SCRIPTS / helper_spec["path"], helper_spec["sha256"], "phase6im_identity_runtime")
boundary_spec = policy["modules"]["boundary"]
boundary = _load_exact(SCRIPTS / boundary_spec["path"], boundary_spec["sha256"], "phase6in_boundary_runtime")

settings = carb.settings.get_settings()
attempt_id = settings.get_as_string("/phase6in/attemptId")
markers = Path(settings.get_as_string("/phase6in/childMarkers")).resolve()
report_path = Path(settings.get_as_string("/phase6in/operationReport")).resolve()
expected_kit = Path(settings.get_as_string("/phase6in/expectedKitPath")).resolve(strict=True)
started = time.monotonic()

# Phase 6IM is the sole process-identity implementation and is intentionally
# called unchanged. This probe creates no Stage, Layer, timeline, Flow,
# renderer, camera, capture, readback, or diagnostic attachment.
helper_report = helper.produce_helper_report(attempt_id=attempt_id, pid=os.getpid(), expected_path=expected_kit)
identity = helper_report["identities"][0]


def mark(step: str, details: dict | None = None) -> None:
    boundary.append_marker(
        markers, attempt_id=attempt_id, step_id=step, actor="child_kit",
        pid=identity["pid"], creation_ticks=identity["creation_time_filetime_ticks"],
        executable_path=identity["executable_path"], elapsed=time.monotonic() - started,
        details=details,
    )


mark("kit_app_ready", {"identity_calls": 2})
report = {
    "schema": boundary.OPERATION_SCHEMA,
    "phase": "phase6in",
    "attempt_id": attempt_id,
    "phase6im_helper_contract_sha256": policy["dependencies"]["phase6im_contract_sha256"],
    "phase6im_helper_evidence": helper_report,
    "process_identity": {
        key: identity[key] for key in ("pid", "creation_time_filetime_ticks", "creation_time_utc_epoch", "executable_path")
    },
    "operation_complete": True,
    "shutdown_requested": False,
    "shutdown_complete": False,
    "forbidden_calls": {
        "stage": 0, "layer": 0, "timeline_play": 0, "flow": 0,
        "renderer_update": 0, "readback": 0, "camera": 0, "capture": 0,
        "cdb_attach": 0, "dump_analysis": 0,
    },
}
boundary.write_json(report_path, report)
mark("operation_complete")
report["shutdown_requested"] = True
boundary.write_json(report_path, report)
mark("shutdown_requested")
report["shutdown_complete"] = True
boundary.write_json(report_path, report)
mark("shutdown_complete")
omni.kit.app.get_app().post_uncancellable_quit(0)
