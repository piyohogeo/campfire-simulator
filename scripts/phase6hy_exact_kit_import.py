"""Fail-closed exact repository-local loader for Phase 6HY Kit --exec."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _norm(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=True)))


def _is_reparse(path: Path) -> bool:
    return bool(getattr(path.stat(), "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except ValueError:
        return False


def read_contract(wrapper_file: Path, contract_path: Path, sidecar_path: Path) -> tuple[dict, dict]:
    wrapper = wrapper_file.resolve(strict=True)
    scripts = wrapper.parent.resolve(strict=True)
    root = scripts.parent.resolve(strict=True)
    contract = contract_path.resolve(strict=True)
    sidecar = sidecar_path.resolve(strict=True)
    if not root.is_dir() or not scripts.is_dir() or _is_reparse(scripts):
        raise ImportError("canonical_scripts_directory_invalid")
    if not _inside(scripts, root) or wrapper.parent != scripts:
        raise ImportError("canonical_scripts_root_escape")
    if _is_reparse(root):
        raise ImportError("canonical_repository_reparse_rejected")
    expected_contract = scripts / "phase6hy_exact_kit_import_contract.json"
    expected_sidecar = scripts / "phase6hy_exact_kit_import_contract.sha256"
    if _norm(contract) != _norm(expected_contract) or _norm(sidecar) != _norm(expected_sidecar):
        raise ImportError("import_contract_path_mismatch")
    digest = sha256_file(contract)
    if sidecar.read_text(encoding="ascii").split()[0].upper() != digest:
        raise ImportError("import_contract_digest_mismatch")
    policy = json.loads(contract.read_text(encoding="utf-8"))
    if policy.get("schema") != "campfire.phase6hy.exact-kit-import-contract.v1":
        raise ImportError("import_contract_schema_mismatch")
    return policy, {"repository_root": str(root), "scripts_path": str(scripts), "contract_sha256": digest}


def validate_source(path: Path, scripts: Path, expected_sha256: str, role: str) -> Path:
    lexical = Path(path).absolute()
    if not lexical.is_file() or _is_reparse(lexical):
        raise ImportError(f"{role}_source_invalid")
    resolved = lexical.resolve(strict=True)
    if not _inside(resolved, scripts) or resolved.parent != scripts:
        raise ImportError(f"{role}_source_root_escape")
    if sha256_file(resolved) != expected_sha256.upper():
        raise ImportError(f"{role}_source_sha256_mismatch")
    return resolved


def load_exact_module(
    source: Path,
    scripts: Path,
    expected_sha256: str,
    module_name: str,
    required_callables: Iterable[str],
) -> tuple[ModuleType, dict]:
    if not scripts.is_dir():
        raise ImportError("canonical_scripts_directory_invalid")
    scripts = scripts.resolve(strict=True)
    source = validate_source(source, scripts, expected_sha256, "probe")
    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_file = getattr(existing, "__file__", None)
        if not isinstance(existing_file, str) or not Path(existing_file).is_file() or _norm(existing_file) != _norm(source):
            raise ImportError("same_name_module_shadowing")
        raise ImportError("same_name_module_preloaded")
    before = list(sys.path)
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None or spec.origin is None:
        raise ImportError("probe_import_spec_unavailable")
    if _norm(spec.origin) != _norm(source):
        raise ImportError("probe_import_origin_mismatch")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    loaded = getattr(module, "__file__", None)
    if not isinstance(loaded, str) or not Path(loaded).is_file() or _norm(loaded) != _norm(source):
        sys.modules.pop(module_name, None)
        raise ImportError("loaded_module_file_mismatch")
    missing = [name for name in required_callables if not callable(getattr(module, name, None))]
    if missing:
        sys.modules.pop(module_name, None)
        raise ImportError("required_callable_missing:" + ",".join(missing))
    nested = {}
    for name, item in list(sys.modules.items()):
        file_name = getattr(item, "__file__", None)
        if name.startswith("phase6h") and isinstance(file_name, str):
            resolved = Path(file_name).resolve(strict=True)
            if not _inside(resolved, scripts):
                raise ImportError("nested_local_import_outside_scripts:" + name)
            nested[name] = str(resolved)
    return module, {
        "module_name": module_name,
        "source_resolved_path": str(source),
        "source_sha256": sha256_file(source),
        "loaded_module_file": str(Path(loaded).resolve(strict=True)),
        "required_callables": list(required_callables),
        "required_callable_identity": {name: f"{module.__name__}.{name}" for name in required_callables},
        "nested_repository_modules": nested,
        "sys_path_before_bounded": before[:32],
        "sys_path_after_bounded": list(sys.path)[:32],
    }
