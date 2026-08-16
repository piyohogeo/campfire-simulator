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
CONTRACT = SCRIPTS / "phase6im_process_identity_contract.json"
SIDECAR = SCRIPTS / "phase6im_process_identity_contract.sha256"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_exact(path: Path, expected: str, name: str):
    resolved = path.resolve(strict=True)
    if resolved.parent != SCRIPTS or _sha(resolved) != expected:
        raise ImportError("phase6im_exact_module_identity_invalid:" + path.name)
    if name in sys.modules:
        raise ImportError("phase6im_module_shadowed:" + name)
    spec = importlib.util.spec_from_file_location(name, resolved)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != resolved:
        raise ImportError("phase6im_loaded_module_path_invalid")
    return module


policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
if _sha(CONTRACT) != SIDECAR.read_text(encoding="ascii").split()[0].upper():
    raise ImportError("phase6im_contract_digest_mismatch")
atomic_path = SCRIPTS / "phase6hu_atomic_report.py"
_load_exact(atomic_path, _sha(atomic_path), "phase6hu_atomic_report")
helper_spec = policy["modules"]["helper"]
helper = _load_exact(SCRIPTS / helper_spec["path"], helper_spec["sha256"], "phase6im_identity_runtime")

settings = carb.settings.get_settings()
attempt_id = settings.get_as_string("/phase6im/attemptId")
markers = Path(settings.get_as_string("/phase6im/markers")).resolve()
report_path = Path(settings.get_as_string("/phase6im/report")).resolve()
expected_kit = Path(settings.get_as_string("/phase6im/expectedKitPath")).resolve(strict=True)
started = time.monotonic()

# Executing --exec is the app-ready boundary. No Stage, Layer, timeline, Flow,
# renderer, readback, camera, capture, CDB, or post-shutdown schedule is used.
report = helper.produce_helper_report(attempt_id=attempt_id, pid=os.getpid(), expected_path=expected_kit)
identity = report["identities"][0]
helper.append_marker(markers, attempt_id=attempt_id, step_id="kit_app_ready", identity=identity, elapsed=time.monotonic() - started)
helper.append_marker(markers, attempt_id=attempt_id, step_id="process_started", identity=identity, elapsed=time.monotonic() - started)
helper.append_marker(markers, attempt_id=attempt_id, step_id="identity_helper_complete", identity=identity, elapsed=time.monotonic() - started, details={"identity_calls": 2})
report["operation_complete"] = True
report["lifecycle_marker"] = "operation_complete"
helper.write_report(report_path, report)
helper.append_marker(markers, attempt_id=attempt_id, step_id="operation_complete", identity=identity, elapsed=time.monotonic() - started)
report["shutdown_complete"] = True
report["lifecycle_marker"] = "shutdown_complete"
helper.write_report(report_path, report)
helper.append_marker(markers, attempt_id=attempt_id, step_id="shutdown_complete", identity=identity, elapsed=time.monotonic() - started)
omni.kit.app.get_app().post_uncancellable_quit(0)

