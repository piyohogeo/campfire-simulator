"""Phase 6IG exact dependency wrapper for one camera-only audit process."""
from __future__ import annotations
import hashlib,importlib.util,json,sys
from pathlib import Path
import carb

WRAPPER=Path(__file__).absolute();SCRIPTS=WRAPPER.parent;ROOT=SCRIPTS.parent
CONTRACT=SCRIPTS/"phase6ig_camera_opinion_contract.json";SIDECAR=SCRIPTS/"phase6ig_camera_opinion_contract.sha256"
def _bootstrap(path:Path,expected_sha256:str,name:str):
 resolved=path.resolve(strict=True)
 if resolved.parent!=SCRIPTS.resolve(strict=True):raise ImportError(name+"_root_escape")
 if hashlib.sha256(resolved.read_bytes()).hexdigest().upper()!=expected_sha256.upper():raise ImportError(name+"_sha256_mismatch")
 if name in sys.modules:raise ImportError(name+"_shadowing")
 spec=importlib.util.spec_from_file_location(name,resolved)
 if spec is None or spec.loader is None:raise ImportError(name+"_spec_unavailable")
 module=importlib.util.module_from_spec(spec);sys.modules[name]=module
 try:spec.loader.exec_module(module)
 except BaseException:sys.modules.pop(name,None);raise
 if Path(module.__file__).resolve(strict=True)!=resolved:raise ImportError(name+"_loaded_path_mismatch")
 return module
policy=json.loads(CONTRACT.read_text(encoding="utf-8"));digest=hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
if SIDECAR.read_text(encoding="ascii").split()[0].upper()!=digest:raise ImportError("phase6ig_contract_digest_mismatch")
if policy.get("schema")!="campfire.phase6ig.camera-opinion-contract.v1":raise ImportError("phase6ig_contract_schema_mismatch")
loader_entry=policy["bootstrap_sources"]["dependency_loader"];marker_entry=policy["bootstrap_sources"]["marker_contract"]
loader=_bootstrap(ROOT/loader_entry["path"],loader_entry["sha256"],"phase6ig_dependency_loader_runtime");marker_contract=_bootstrap(ROOT/marker_entry["path"],marker_entry["sha256"],"phase6ig_marker_contract_runtime")
settings=carb.settings.get_settings();marker_file=Path(settings.get_as_string("/phase6ig/markers")).resolve();audit_path=Path(settings.get_as_string("/phase6ig/audit")).resolve();stage_root=Path(settings.get_as_string("/phase6ig/stageRoot")).resolve();attempt_id=settings.get_as_string("/phase6ig/attemptId")
def emit(event_name:str,**values:object)->None:name,payload=marker_contract.produce_marker(event_name,**values);marker_contract.append_marker(marker_file,name,payload)
emit("kit_launch",attempt_id=attempt_id,executable_path=sys.executable);emit("kit_app_ready",attempt_id=attempt_id)
manifest_path=ROOT/policy["dependency_manifest"]["path"];manifest_sidecar=ROOT/policy["dependency_manifest"]["sidecar_path"]
manifest,manifest_audit=loader.read_manifest(manifest_path,manifest_sidecar,ROOT)
modules,loaded_audit=loader.load_dependencies(manifest,manifest_audit)
modules["stage_authoring"].configure_repository_dependencies(modules["stage_builder"].topology);emit("dependencies_complete",module_count=len(loaded_audit))
frozen_path=ROOT/policy["frozen_probe_contract"]["path"]
if hashlib.sha256(frozen_path.read_bytes()).hexdigest().upper()!=policy["frozen_probe_contract"]["sha256"]:raise ImportError("frozen_probe_contract_digest_mismatch")
runtime_policy={**policy,"repository_root":str(ROOT.resolve(strict=True)),"dependency_load_audit":loaded_audit,"frozen_contract":json.loads(frozen_path.read_text(encoding="utf-8"))}
modules["stage_open_source"].start_audit(modules["stage_authoring"],modules["runtime_prim_policy"],modules["layer_opinion_audit"],modules["camera_opinion_audit"],modules["atomic_report"],emit,runtime_policy,audit_path,stage_root,attempt_id)
