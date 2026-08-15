"""Deterministic Kit --exec wrapper for the frozen Phase 6HX operation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app


WRAPPER = Path(__file__).absolute()
SCRIPTS = WRAPPER.parent
CONTRACT = SCRIPTS / "phase6hy_exact_kit_import_contract.json"
SIDECAR = SCRIPTS / "phase6hy_exact_kit_import_contract.sha256"


def _append(path: Path, marker: str, **values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"marker": marker, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **values}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


settings = carb.settings.get_settings()
markers = Path(settings.get_as_string("/phase6hs/markers")).resolve()
audit_setting = settings.get_as_string("/phase6hy/importAudit")
if audit_setting:
    audit_path = Path(audit_setting).resolve()
else:
    audit_path = Path(settings.get_as_string("/phase6hs/output")).resolve().parent / "import_audit.json"
attempt_id = settings.get_as_string("/phase6hs/attemptId")
app = omni.kit.app.get_app()
_append(markers, "kit_app_ready", attempt_id=attempt_id)

policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
loader_path = SCRIPTS / policy["sources"]["loader"]["path"].split("scripts/", 1)[1]
if hashlib.sha256(loader_path.read_bytes()).hexdigest().upper() != policy["sources"]["loader"]["sha256"]:
    raise ImportError("exact_loader_sha256_mismatch")
spec = importlib.util.spec_from_file_location("phase6hy_exact_kit_import_runtime", loader_path)
if spec is None or spec.loader is None:
    raise ImportError("exact_loader_spec_unavailable")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)
policy, boundary = loader.read_contract(WRAPPER, CONTRACT, SIDECAR)
if loader.sha256_file(WRAPPER) != policy["sources"]["wrapper"]["sha256"]:
    raise ImportError("wrapper_sha256_mismatch")
_append(markers, "wrapper_resolved", path=str(WRAPPER.resolve(strict=True)))
_append(markers, "scripts_resolved", path=boundary["scripts_path"])
probe_entry = policy["sources"]["probe_builder"]
probe_path = Path(boundary["repository_root"]) / probe_entry["path"]
_append(markers, "probe_source_resolved", path=str(probe_path.resolve(strict=True)))
_append(markers, "probe_source_sha256", sha256=loader.sha256_file(probe_path))
module, audit = loader.load_exact_module(
    probe_path, Path(boundary["scripts_path"]), probe_entry["sha256"],
    "phase6hy_probe_source_exact", probe_entry["required_callables"],
)
_append(markers, "loaded_module_file", path=audit["loaded_module_file"])
_append(markers, "required_callable_identity", identity=audit["required_callable_identity"])
_append(markers, "import_complete", attempt_id=attempt_id)
audit.update(boundary)
audit.update({"schema": "campfire.phase6hy.kit-import-audit.v1", "status": "qualified", "attempt_id": attempt_id,
              "wrapper_resolved_path": str(WRAPPER.resolve(strict=True)), "wrapper_sha256": loader.sha256_file(WRAPPER)})
_write(audit_path, audit)

if settings.get_as_bool("/phase6hy/importSmoke"):
    _append(markers, "operation_complete", scope="import_smoke")
    _append(markers, "smoke_shutdown_complete")
    app.post_uncancellable_quit(0)
else:
    source = module.build_probe_source(SCRIPTS / "probe_phase6hw_single_log_occlusion.py")
    exec(compile(source, __file__, "exec"), globals(), globals())
