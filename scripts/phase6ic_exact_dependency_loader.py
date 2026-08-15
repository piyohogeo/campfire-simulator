"""Deterministic exact dependency graph loader for Phase 6IC.

Repository-local modules are loaded from declared absolute files.  The loader
does not add the repository or scripts directory to ``sys.path``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
MAX_MANIFEST_BYTES = 64 * 1024


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _norm(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=True)))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except ValueError:
        return False


def _is_reparse(path: Path) -> bool:
    return bool(getattr(path.stat(), "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _local_import_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names if alias.name.startswith("phase6"))
        elif isinstance(node, ast.ImportFrom) and isinstance(node.module, str) and node.module.startswith("phase6"):
            names.add(node.module.split(".")[0])
    return sorted(names)


def read_manifest(manifest_path: Path, sidecar_path: Path, repository_root: Path) -> tuple[dict, dict]:
    root = repository_root.resolve(strict=True)
    scripts = (root / "scripts").resolve(strict=True)
    manifest = manifest_path.resolve(strict=True)
    sidecar = sidecar_path.resolve(strict=True)
    if _is_reparse(root) or _is_reparse(scripts) or not _inside(scripts, root):
        raise ImportError("dependency_root_reparse_or_escape")
    if manifest.parent != scripts or sidecar.parent != scripts:
        raise ImportError("dependency_manifest_root_escape")
    if manifest.stat().st_size > MAX_MANIFEST_BYTES:
        raise ImportError("dependency_manifest_oversize")
    digest = sha256_file(manifest)
    if sidecar.read_text(encoding="ascii").split()[0].upper() != digest:
        raise ImportError("dependency_manifest_digest_mismatch")
    policy = json.loads(manifest.read_text(encoding="utf-8"))
    if policy.get("schema") != "campfire.phase6ic.authoring-dependencies.v1":
        raise ImportError("dependency_manifest_schema_mismatch")
    entries = policy.get("modules")
    if not isinstance(entries, list) or not entries:
        raise ImportError("dependency_manifest_modules_invalid")
    ids = [item.get("module_id") for item in entries if isinstance(item, dict)]
    paths = [item.get("repository_relative_path") for item in entries if isinstance(item, dict)]
    runtime_names = [item.get("runtime_module_name") for item in entries if isinstance(item, dict)]
    if len(ids) != len(entries) or any(not isinstance(value, str) or not value for value in ids):
        raise ImportError("dependency_module_id_invalid")
    if len(set(ids)) != len(ids):
        raise ImportError("dependency_module_id_duplicate")
    if len(set(paths)) != len(paths):
        raise ImportError("dependency_source_identity_duplicate")
    if len(set(runtime_names)) != len(runtime_names):
        raise ImportError("dependency_runtime_name_duplicate")
    seen: set[str] = set()
    declared = set(ids)
    audit_modules = []
    for index, entry in enumerate(entries):
        module_id = entry["module_id"]
        dependencies = entry.get("allowed_repository_dependencies")
        symbols = entry.get("required_symbols")
        if not isinstance(dependencies, list) or any(item not in declared for item in dependencies):
            raise ImportError("dependency_undeclared:" + module_id)
        if module_id in dependencies or any(item not in seen for item in dependencies):
            raise ImportError("dependency_order_or_cycle:" + module_id)
        if not isinstance(symbols, list) or any(not isinstance(item, dict) for item in symbols):
            raise ImportError("dependency_required_symbols_invalid:" + module_id)
        relative = Path(entry["repository_relative_path"])
        if relative.is_absolute() or relative.parts[:1] != ("scripts",):
            raise ImportError("dependency_source_root_escape:" + module_id)
        source = (root / relative).absolute()
        if not source.is_file() or _is_reparse(source):
            raise ImportError("dependency_source_invalid:" + module_id)
        resolved = source.resolve(strict=True)
        if not _inside(resolved, scripts) or resolved.parent != scripts:
            raise ImportError("dependency_source_root_escape:" + module_id)
        expected_absolute = entry.get("expected_absolute_path")
        if not isinstance(expected_absolute, str) or _norm(expected_absolute) != _norm(resolved):
            raise ImportError("dependency_absolute_path_mismatch:" + module_id)
        if sha256_file(resolved) != entry.get("sha256", "").upper():
            raise ImportError("dependency_sha256_mismatch:" + module_id)
        local_imports = _local_import_names(resolved)
        allowed_import_names = set(entry.get("allowed_local_import_names", []))
        undeclared_imports = sorted(set(local_imports) - allowed_import_names)
        if undeclared_imports:
            raise ImportError("dependency_local_import_undeclared:" + module_id + ":" + undeclared_imports[0])
        seen.add(module_id)
        audit_modules.append({
            "index": index, "module_id": module_id, "absolute_path": str(resolved),
            "repository_relative_path": relative.as_posix(), "sha256": sha256_file(resolved),
            "dependencies": list(dependencies), "local_import_names": local_imports,
            "required_symbols": symbols,
        })
    return policy, {"manifest_sha256": digest, "repository_root": str(root), "scripts_path": str(scripts), "modules": audit_modules}


def load_dependencies(
    policy: dict,
    audit: dict,
    *,
    module_ids: Iterable[str] | None = None,
    on_loaded: Callable[[dict], None] | None = None,
) -> tuple[dict[str, ModuleType], list[dict]]:
    selected = set(module_ids) if module_ids is not None else {item["module_id"] for item in audit["modules"]}
    entries = {item["module_id"]: item for item in policy["modules"]}
    audit_entries = {item["module_id"]: item for item in audit["modules"]}
    unknown = sorted(selected - set(entries))
    if unknown:
        raise ImportError("dependency_selection_unknown:" + unknown[0])
    loaded: dict[str, ModuleType] = {}
    loaded_audit: list[dict] = []
    for entry in policy["modules"]:
        module_id = entry["module_id"]
        if module_id not in selected:
            continue
        missing_dependencies = [item for item in entry["allowed_repository_dependencies"] if item in selected and item not in loaded]
        if missing_dependencies:
            raise ImportError("dependency_load_order_invalid:" + module_id)
        runtime_name = entry["runtime_module_name"]
        if runtime_name in sys.modules:
            raise ImportError("dependency_module_shadowing:" + module_id)
        source = Path(audit_entries[module_id]["absolute_path"])
        spec = importlib.util.spec_from_file_location(runtime_name, source)
        if spec is None or spec.loader is None or spec.origin is None or _norm(spec.origin) != _norm(source):
            raise ImportError("dependency_spec_origin_mismatch:" + module_id)
        module = importlib.util.module_from_spec(spec)
        sys.modules[runtime_name] = module
        try:
            spec.loader.exec_module(module)
            loaded_file = getattr(module, "__file__", None)
            if not isinstance(loaded_file, str) or _norm(loaded_file) != _norm(source):
                raise ImportError("dependency_loaded_file_mismatch:" + module_id)
            for symbol in entry["required_symbols"]:
                value = getattr(module, symbol["name"], None)
                kind = symbol["kind"]
                if kind == "callable" and not callable(value):
                    raise ImportError("dependency_callable_missing:" + module_id + ":" + symbol["name"])
                if kind == "module" and not isinstance(value, ModuleType):
                    raise ImportError("dependency_module_symbol_missing:" + module_id + ":" + symbol["name"])
            row = {
                "module_id": module_id, "runtime_module_name": runtime_name,
                "absolute_path": str(source), "sha256": sha256_file(source),
                "loaded_file": str(Path(module.__file__).resolve(strict=True)),
                "required_symbol_names": [item["name"] for item in entry["required_symbols"]],
            }
            loaded[module_id] = module
            loaded_audit.append(row)
            if on_loaded is not None:
                on_loaded(row)
        except BaseException:
            sys.modules.pop(runtime_name, None)
            for prior in loaded_audit:
                sys.modules.pop(prior["runtime_module_name"], None)
            raise
    return loaded, loaded_audit


def unload_dependencies(loaded_audit: Iterable[dict]) -> None:
    for item in reversed(list(loaded_audit)):
        sys.modules.pop(item["runtime_module_name"], None)
