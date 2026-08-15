"""Exact Phase 6HZ import boundary feeding the frozen Phase 6HX operation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import carb


WRAPPER = Path(__file__).absolute()
SCRIPTS = WRAPPER.parent
CONTRACT = SCRIPTS / "phase6ia_single_log_occlusion_contract.json"
SIDECAR = SCRIPTS / "phase6ia_single_log_occlusion_contract.sha256"


def _bootstrap(path: Path, expected_sha256: str, name: str):
    resolved = path.resolve(strict=True)
    if resolved.parent != SCRIPTS.resolve(strict=True):
        raise ImportError(name + "_root_escape")
    if hashlib.sha256(resolved.read_bytes()).hexdigest().upper() != expected_sha256.upper():
        raise ImportError(name + "_sha256_mismatch")
    spec = importlib.util.spec_from_file_location(name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(name + "_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != resolved:
        raise ImportError(name + "_loaded_path_mismatch")
    return module


raw_policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
contract_digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
if SIDECAR.read_text(encoding="ascii").split()[0].upper() != contract_digest:
    raise ImportError("phase6ia_contract_digest_mismatch")
loader_entry = raw_policy["exact_import"]["loader"]
marker_entry = raw_policy["exact_import"]["marker_contract"]
loader = _bootstrap(SCRIPTS / Path(loader_entry["path"]).name, loader_entry["sha256"], "phase6ia_exact_loader_runtime")
marker_contract = _bootstrap(SCRIPTS / Path(marker_entry["path"]).name, marker_entry["sha256"], "phase6ia_marker_contract_runtime")

settings = carb.settings.get_settings()
marker_file = Path(settings.get_as_string("/phase6hs/markers")).resolve()
attempt_id = settings.get_as_string("/phase6hs/attemptId")


def emit(event_name: str, **values: object) -> None:
    name, payload = marker_contract.produce_marker(event_name, **values)
    marker_contract.append_marker(marker_file, name, payload)


emit("kit_launch", attempt_id=attempt_id, executable_path=sys.executable)
emit("kit_app_ready", attempt_id=attempt_id)
emit("wrapper_resolution_started", expected_wrapper_path=str(WRAPPER))
wrapper_resolved = WRAPPER.resolve(strict=True)
wrapper_sha = loader.sha256_file(wrapper_resolved)
if wrapper_sha != raw_policy["exact_import"]["wrapper_sha256"]:
    raise ImportError("phase6ia_wrapper_sha256_mismatch")
emit("wrapper_resolution_complete", resolved_path=str(wrapper_resolved), sha256=wrapper_sha)

probe_entry = raw_policy["exact_import"]["probe_builder"]
repository_root = SCRIPTS.resolve(strict=True).parent
probe_path = repository_root / probe_entry["path"]
emit("probe_resolution_started", repository_root=str(repository_root), source_name=probe_path.name)
validated_probe = loader.validate_source(probe_path, SCRIPTS, probe_entry["sha256"], "probe")
emit("probe_resolution_complete", module_path=str(validated_probe))
emit("module_identity_validated", module_path=str(validated_probe), sha256=loader.sha256_file(validated_probe))
module, audit = loader.load_exact_module(
    validated_probe,
    SCRIPTS,
    probe_entry["sha256"],
    "phase6ia_probe_source_exact",
    probe_entry["required_callables"],
)
emit("import_complete", loaded_module_file=audit["loaded_module_file"])
emit("required_callable_validated", callable_identity=audit["required_callable_identity"])

source = module.build_probe_source(SCRIPTS / "probe_phase6hw_single_log_occlusion.py")
exec(compile(source, __file__, "exec"), globals(), globals())

