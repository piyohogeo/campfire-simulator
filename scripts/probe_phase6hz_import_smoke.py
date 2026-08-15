"""Phase 6HZ Kit --exec wrapper: exact import only; no stage or Flow work."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import carb
import omni.kit.app


WRAPPER = Path(__file__).absolute()
SCRIPTS = WRAPPER.parent
CONTRACT = SCRIPTS / "phase6hz_import_smoke_contract.json"
SIDECAR = SCRIPTS / "phase6hz_import_smoke_contract.sha256"


def _bootstrap_module(path: Path, expected_sha256: str, name: str):
    if hashlib.sha256(path.read_bytes()).hexdigest().upper() != expected_sha256.upper():
        raise ImportError(name + "_sha256_mismatch")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name + "_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != path.resolve(strict=True):
        raise ImportError(name + "_loaded_path_mismatch")
    return module


raw_policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
loader_entry = raw_policy["sources"]["loader"]
marker_entry = raw_policy["sources"]["marker_contract"]
loader = _bootstrap_module(SCRIPTS / Path(loader_entry["path"]).name, loader_entry["sha256"], "phase6hz_exact_kit_import_runtime")
marker_contract = _bootstrap_module(SCRIPTS / Path(marker_entry["path"]).name, marker_entry["sha256"], "phase6hz_marker_contract_runtime")
policy, boundary = loader.read_contract(WRAPPER, CONTRACT, SIDECAR)

settings = carb.settings.get_settings()
marker_file = Path(settings.get_as_string("/phase6hz/markers")).resolve()
audit_path = Path(settings.get_as_string("/phase6hz/importAudit")).resolve()
attempt_id = settings.get_as_string("/phase6hz/attemptId")
app = omni.kit.app.get_app()


def emit(event_name: str, **values: object) -> None:
    name, payload = marker_contract.produce_marker(event_name, **values)
    marker_contract.append_marker(marker_file, name, payload)


def write_audit(payload: dict) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = audit_path.with_suffix(audit_path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, audit_path)


emit("kit_launch", attempt_id=attempt_id, executable_path=sys.executable)
emit("kit_app_ready", attempt_id=attempt_id)
emit("wrapper_resolution_started", expected_wrapper_path=str(WRAPPER))
wrapper_resolved = WRAPPER.resolve(strict=True)
wrapper_sha = loader.sha256_file(wrapper_resolved)
if wrapper_sha != policy["sources"]["wrapper"]["sha256"]:
    raise ImportError("wrapper_sha256_mismatch")
emit("wrapper_resolution_complete", resolved_path=str(wrapper_resolved), sha256=wrapper_sha)

probe_entry = policy["sources"]["probe_builder"]
probe_path = Path(boundary["repository_root"]) / probe_entry["path"]
emit("probe_resolution_started", repository_root=boundary["repository_root"], source_name=probe_path.name)
validated_probe = loader.validate_source(probe_path, Path(boundary["scripts_path"]), probe_entry["sha256"], "probe")
emit("probe_resolution_complete", module_path=str(validated_probe))
emit("module_identity_validated", module_path=str(validated_probe), sha256=loader.sha256_file(validated_probe))
module, import_audit = loader.load_exact_module(
    validated_probe,
    Path(boundary["scripts_path"]),
    probe_entry["sha256"],
    "phase6hz_probe_source_exact",
    probe_entry["required_callables"],
)
emit("import_complete", loaded_module_file=import_audit["loaded_module_file"])
emit("required_callable_validated", callable_identity=import_audit["required_callable_identity"])
emit("operation_complete", scope="exact_import_smoke")
emit("shutdown_started", method="post_uncancellable_quit")
emit("shutdown_complete", requested=True)

audit = {
    "schema": "campfire.phase6hz.kit-import-audit.v1",
    "phase": "phase6hz",
    "status": "qualified",
    "attempt_id": attempt_id,
    "operation_complete": True,
    "shutdown_complete": True,
    "readback_calls": 0,
    "stage_created": False,
    "flow_interface_calls": 0,
    "collision_proxy_created": False,
    "capture_calls": 0,
    "repository_root": boundary["repository_root"],
    "scripts_path": boundary["scripts_path"],
    "wrapper_resolved_path": str(wrapper_resolved),
    "wrapper_sha256": wrapper_sha,
    "probe_source_resolved_path": str(validated_probe),
    "probe_source_sha256": loader.sha256_file(validated_probe),
    "loaded_module_file": import_audit["loaded_module_file"],
    "required_callable_identity": import_audit["required_callable_identity"],
    "sys_path_before_bounded": import_audit["sys_path_before_bounded"],
    "sys_path_after_bounded": import_audit["sys_path_after_bounded"],
}
write_audit(audit)
app.post_uncancellable_quit(0)
