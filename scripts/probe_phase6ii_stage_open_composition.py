from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import carb

WRAPPER = Path(__file__).absolute()
SCRIPTS = WRAPPER.parent
ROOT = SCRIPTS.parent
CONTRACT = SCRIPTS / "phase6ii_stage_open_composition_contract.json"
SIDECAR = SCRIPTS / "phase6ii_stage_open_composition_contract.sha256"


def _bootstrap(path, expected, name):
    resolved = Path(path).resolve(strict=True)
    if resolved.parent != SCRIPTS.resolve(strict=True):
        raise ImportError(name + "_root_escape")
    if hashlib.sha256(resolved.read_bytes()).hexdigest().upper() != expected:
        raise ImportError(name + "_sha256_mismatch")
    if name in sys.modules:
        raise ImportError(name + "_shadowing")
    spec = importlib.util.spec_from_file_location(name, resolved)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve(strict=True) != resolved:
        raise ImportError(name + "_path_mismatch")
    return module


policy = json.loads(CONTRACT.read_text())
digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
if SIDECAR.read_text().split()[0].upper() != digest:
    raise ImportError("contract_digest_mismatch")
loader = _bootstrap(ROOT / policy["bootstrap_sources"]["dependency_loader"]["path"], policy["bootstrap_sources"]["dependency_loader"]["sha256"], "phase6ii_dependency_loader_runtime")
markers = _bootstrap(ROOT / policy["bootstrap_sources"]["marker_contract"]["path"], policy["bootstrap_sources"]["marker_contract"]["sha256"], "phase6ii_marker_contract_runtime")
settings = carb.settings.get_settings()
marker_path = Path(settings.get_as_string("/phase6ii/markers")).resolve()
report_path = Path(settings.get_as_string("/phase6ii/report")).resolve()
identity_path = Path(settings.get_as_string("/phase6ii/identity")).resolve()
stage_root = Path(settings.get_as_string("/phase6ii/stageRoot")).resolve()
attempt_id = settings.get_as_string("/phase6ii/attemptId")
condition = settings.get_as_string("/phase6ii/condition")


def emit(name, **values):
    event, payload = markers.produce_marker(name, **values)
    markers.append_marker(marker_path, event, payload)


emit("process_started", attempt_id=attempt_id, condition=condition)
emit("kit_app_ready", attempt_id=attempt_id, condition=condition)
manifest, audit = loader.read_manifest(ROOT / policy["dependency_manifest"]["path"], ROOT / policy["dependency_manifest"]["sidecar_path"], ROOT)
modules, loaded = loader.load_dependencies(manifest, audit)
modules["stage_authoring"].configure_repository_dependencies(modules["stage_builder"].topology)
frozen_path = ROOT / policy["frozen_probe_contract"]["path"]
if hashlib.sha256(frozen_path.read_bytes()).hexdigest().upper() != policy["frozen_probe_contract"]["sha256"]:
    raise ImportError("frozen_contract_mismatch")
runtime = {**policy, "frozen_contract": json.loads(frozen_path.read_text()), "repository_root": str(ROOT.resolve()), "dependency_load_audit": loaded}
modules["stage_open_source"].start_probe(modules["stage_authoring"], modules["stage_composition"], modules["atomic_report"], emit, runtime, report_path, identity_path, stage_root, attempt_id, condition)
