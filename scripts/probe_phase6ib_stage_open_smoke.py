"""Exact Phase 6HZ loader boundary for the Phase 6IB stage-open smoke."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import carb


WRAPPER = Path(__file__).absolute()
SCRIPTS = WRAPPER.parent
CONTRACT = SCRIPTS / "phase6ib_stage_open_contract.json"
SIDECAR = SCRIPTS / "phase6ib_stage_open_contract.sha256"


def _bootstrap(path: Path, expected_sha256: str, name: str):
    resolved = path.resolve(strict=True)
    if resolved.parent != SCRIPTS.resolve(strict=True): raise ImportError(name + "_root_escape")
    if hashlib.sha256(resolved.read_bytes()).hexdigest().upper() != expected_sha256.upper(): raise ImportError(name + "_sha256_mismatch")
    spec = importlib.util.spec_from_file_location(name, resolved)
    if spec is None or spec.loader is None: raise ImportError(name + "_spec_unavailable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != resolved: raise ImportError(name + "_loaded_path_mismatch")
    return module


policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
if SIDECAR.read_text(encoding="ascii").split()[0].upper() != digest: raise ImportError("phase6ib_contract_digest_mismatch")
if policy.get("schema") != "campfire.phase6ib.stage-open-contract.v1": raise ImportError("phase6ib_contract_schema_mismatch")
loader_entry, marker_entry, authoring_entry = policy["sources"]["loader"], policy["sources"]["marker_contract"], policy["sources"]["authoring"]
loader = _bootstrap(SCRIPTS / Path(loader_entry["path"]).name, loader_entry["sha256"], "phase6ib_exact_loader_runtime")
marker_contract = _bootstrap(SCRIPTS / Path(marker_entry["path"]).name, marker_entry["sha256"], "phase6ib_marker_contract_runtime")
authoring = _bootstrap(SCRIPTS / Path(authoring_entry["path"]).name, authoring_entry["sha256"], "phase6ib_stage_authoring_runtime")
settings = carb.settings.get_settings()
marker_file = Path(settings.get_as_string("/phase6ib/markers")).resolve()
audit_path = Path(settings.get_as_string("/phase6ib/audit")).resolve()
stage_root = Path(settings.get_as_string("/phase6ib/stageRoot")).resolve()
attempt_id = settings.get_as_string("/phase6ib/attemptId")


def emit(event_name: str, **values: object) -> None:
    name, payload = marker_contract.produce_marker(event_name, **values)
    marker_contract.append_marker(marker_file, name, payload)


emit("kit_launch", attempt_id=attempt_id, executable_path=sys.executable)
emit("kit_app_ready", attempt_id=attempt_id)
source_entry = policy["sources"]["probe_source"]
source_path = loader.validate_source(SCRIPTS / Path(source_entry["path"]).name, SCRIPTS, source_entry["sha256"], "probe")
module, import_audit = loader.load_exact_module(source_path, SCRIPTS, source_entry["sha256"], "phase6ib_stage_open_source_exact", source_entry["required_callables"])
emit("probe_import_complete", module_path=import_audit["loaded_module_file"], sha256=import_audit["source_sha256"], callable_identity=import_audit["required_callable_identity"])
runtime_policy = {**policy, "repository_root": str(SCRIPTS.parent.resolve(strict=True))}
module.start_smoke(authoring, emit, runtime_policy, audit_path, stage_root, attempt_id)
