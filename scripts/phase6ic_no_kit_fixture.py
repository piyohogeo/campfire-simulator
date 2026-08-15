"""No-Kit producer-to-consumer fixture for Phase 6IC exact dependencies."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import phase6ic_exact_dependency_loader as loader
import phase6ic_marker_contract as markers


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_manifest(path: Path, policy: dict) -> Path:
    path.write_text(json.dumps(policy, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    sidecar = path.with_suffix(".sha256")
    sidecar.write_text(f"{_sha(path)}  {path.name}\n", encoding="ascii")
    return sidecar


def _mirror(output_root: Path, repository_root: Path, policy: dict, name: str) -> tuple[Path, Path, Path, dict]:
    root = output_root / name
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    mirrored = copy.deepcopy(policy)
    for entry in mirrored["modules"]:
        source = repository_root / entry["repository_relative_path"]
        target = scripts / source.name
        shutil.copy2(source, target)
        entry["repository_relative_path"] = "scripts/" + target.name
        entry["expected_absolute_path"] = str(target.resolve(strict=True))
        entry["sha256"] = _sha(target)
    manifest = scripts / "phase6ic_authoring_dependencies.json"
    sidecar = _write_manifest(manifest, mirrored)
    return root, manifest, sidecar, mirrored


def run_fixture(output_root: Path, manifest_path: Path, sidecar_path: Path, repository_root: Path, frozen_path: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6IC no-Kit fixture refuses root reuse")
    output_root.mkdir(parents=True)
    cases: list[dict] = []

    def case(name: str, passed: bool, **evidence) -> None:
        cases.append({"name": name, "passed": bool(passed), **evidence})

    policy, audit = loader.read_manifest(manifest_path, sidecar_path, repository_root)
    before = list(sys.path)
    selected = ["stage_builder", "atomic_report", "stage_authoring"]
    modules, loaded_audit = loader.load_dependencies(policy, audit, module_ids=selected)
    authoring = modules["stage_authoring"]
    authoring.configure_repository_dependencies(modules["stage_builder"].topology)
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    off = authoring.stage_spec(frozen, "collision_off")
    validated = authoring.validate_spec(off, frozen, "collision_off")
    case("actual_manifest_producer_to_consumer", validated["accepted"] and list(sys.path) == before, loaded=loaded_audit)
    case("actual_phase6hw_topology", off["scene"]["proxy_topology"] == [26, 36, 120])
    case("authoring_entrypoint_callable", callable(authoring.author_stage) and callable(authoring.validate_stage))
    case("manifest_bounded", manifest_path.stat().st_size < loader.MAX_MANIFEST_BYTES)
    case("all_dependencies_enumerated", [item["module_id"] for item in policy["modules"]] == ["stage_builder", "atomic_report", "stage_authoring", "stage_open_source"])
    loader.unload_dependencies(loaded_audit)

    events = [
        ("kit_launch", {"attempt_id": "fixture", "executable_path": "kit.exe"}),
        ("kit_app_ready", {"attempt_id": "fixture"}),
        ("authoring_manifest_validation_started", {"manifest_path": str(manifest_path)}),
        ("authoring_manifest_validation_complete", {"manifest_sha256": audit["manifest_sha256"], "module_count": 4}),
        ("authoring_dependencies_load_started", {"module_count": 4}),
    ]
    for item in audit["modules"]:
        events.append(("authoring_dependency_loaded", {"module_id": item["module_id"], "module_path": item["absolute_path"], "sha256": item["sha256"]}))
    events.extend([
        ("authoring_dependencies_load_complete", {"module_count": 4}),
        ("authoring_callable_validation_complete", {"callable_count": 13}),
        ("stage_generation_started", {"condition": "collision_off_and_collision_on_fixture"}),
        ("stage_generation_complete", {"off_sha256": "A" * 64, "on_sha256": "B" * 64}),
        ("stage_parse_started", {"parser": "pxr.Usd.Stage.Open"}),
        ("stage_parse_complete", {"positive_count": 2, "negative_count": 6}),
        ("stage_open_complete", {"stage_identifier": "off.usda", "root_layer_identifier": "off.usda"}),
        ("required_prims_validated", {"prim_count": 24, "flow_setting_count": 12}),
        ("operation_complete", {"scope": "registered_schema_stage_open_only"}),
        ("stage_close_started", {"stage_identifier": "off.usda"}),
        ("stage_close_complete", {"context_empty": True}),
        ("shutdown_complete", {"requested": True}),
    ])
    marker_path = output_root / "markers.jsonl"
    for name, payload in events:
        event, canonical = markers.produce_marker(name, **payload)
        markers.append_marker(marker_path, event, canonical)
    rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
    case("actual_marker_payloads", [item["marker"] for item in rows] == [name for name, _ in events])

    def negative(name: str, mutate, expected_prefix: str, *, shadow: bool = False, reparse: bool = False) -> None:
        root, manifest, sidecar, candidate = _mirror(output_root, repository_root, policy, "negative_" + name)
        mutate(candidate, root)
        sidecar = _write_manifest(manifest, candidate)
        inserted = None
        try:
            if shadow:
                inserted = candidate["modules"][0]["runtime_module_name"]
                dummy = ModuleType(inserted); dummy.__file__ = str(Path(root) / "wrong.py")
                sys.modules[inserted] = dummy
            context = patch.object(loader, "_is_reparse", side_effect=lambda path: reparse and Path(path).name == "scripts") if reparse else None
            if context: context.start()
            candidate_policy, candidate_audit = loader.read_manifest(manifest, sidecar, root)
            loader.load_dependencies(candidate_policy, candidate_audit, module_ids=["stage_builder"])
            reason = None
        except Exception as error:
            reason = str(error)
        finally:
            if reparse and context: context.stop()
            if inserted: sys.modules.pop(inserted, None)
            sys.modules.pop(candidate["modules"][0]["runtime_module_name"], None)
        case(name, isinstance(reason, str) and reason.startswith(expected_prefix), reason=reason)

    negative("missing_module", lambda p, r: Path(r, p["modules"][0]["repository_relative_path"]).unlink(), "dependency_source_invalid")
    negative("hash_mismatch", lambda p, r: p["modules"][0].update(sha256="0" * 64), "dependency_sha256_mismatch")
    negative("root_escape", lambda p, r: p["modules"][0].update(repository_relative_path="../outside.py"), "dependency_source_root_escape")
    negative("reparse_redirection", lambda p, r: None, "dependency_root_reparse_or_escape", reparse=True)
    negative("same_name_shadowing", lambda p, r: None, "dependency_module_shadowing", shadow=True)
    negative("loaded_file_mismatch", lambda p, r: p["modules"][0].update(expected_absolute_path=str(Path(r, "scripts", "phase6hu_atomic_report.py"))), "dependency_absolute_path_mismatch")
    negative("required_symbol_missing", lambda p, r: p["modules"][0]["required_symbols"].append({"name":"missing_symbol", "kind":"callable"}), "dependency_callable_missing")
    def add_undeclared_dependency(candidate: dict, root: Path) -> None:
        entry = candidate["modules"][0]
        source = Path(root, entry["repository_relative_path"])
        source.write_text("import phase6undeclared\n" + source.read_text(encoding="utf-8"), encoding="utf-8")
        entry["sha256"] = _sha(source)

    negative("undeclared_dependency", add_undeclared_dependency, "dependency_local_import_undeclared")
    negative("duplicate_source_identity", lambda p, r: p["modules"][1].update(repository_relative_path=p["modules"][0]["repository_relative_path"]), "dependency_source_identity_duplicate")
    negative("dependency_cycle", lambda p, r: p["modules"][0]["allowed_repository_dependencies"].append("stage_authoring"), "dependency_order_or_cycle")
    negative("dependency_order_contradiction", lambda p, r: p["modules"].insert(0, p["modules"].pop(2)), "dependency_order_or_cycle")
    case("nested_local_import_absent", all(not item["local_import_names"] for item in audit["modules"]))
    report = {
        "schema": "campfire.phase6ic.no-kit-fixture.v1", "phase": "phase6ic",
        "status": "qualified" if all(item["passed"] for item in cases) else "failed",
        "kit_launch_count": 0, "case_count": [sum(item["passed"] for item in cases), len(cases)],
        "manifest_sha256": audit["manifest_sha256"], "cases": cases,
    }
    (output_root / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
