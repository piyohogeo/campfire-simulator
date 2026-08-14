"""Deterministic, process-local loader used by Phase 6FZ Kit --exec probes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable


def load_exact_module(
    target_path: str | Path,
    expected_path: str | Path,
    *,
    module_name: str,
    required_entrypoints: Iterable[str] = (),
) -> tuple[ModuleType, dict]:
    """Load exactly *target_path* and reject a missing or different origin.

    Only the target's directory is added to this Kit process' ``sys.path``.
    No parent environment variable, working directory, production app setting,
    or persistent Python configuration is consulted or modified.
    """

    before = list(sys.path)
    target = Path(target_path).resolve(strict=True)
    expected = Path(expected_path).resolve(strict=True)
    if target != expected:
        raise ImportError(f"module origin mismatch: target={target} expected={expected}")
    module_dir = str(expected.parent)
    inserted = module_dir not in sys.path
    if inserted:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location(module_name, expected)
    if spec is None or spec.loader is None or spec.origin is None:
        raise ImportError(f"unable to create import spec for {expected}")
    origin = Path(spec.origin).resolve(strict=True)
    if origin != expected:
        raise ImportError(f"resolved import origin mismatch: {origin} != {expected}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    resolved_file = Path(module.__file__).resolve(strict=True)
    if resolved_file != expected:
        sys.modules.pop(module_name, None)
        raise ImportError(f"loaded module file mismatch: {resolved_file} != {expected}")
    missing = [name for name in required_entrypoints if not callable(getattr(module, name, None))]
    if missing:
        sys.modules.pop(module_name, None)
        raise ImportError(f"required entry points missing: {missing}")
    return module, {
        "target_path": str(target),
        "expected_path": str(expected),
        "resolved_file": str(resolved_file),
        "module_name": module_name,
        "required_entrypoints": list(required_entrypoints),
        "module_directory_inserted": inserted,
        "sys_path_before": before,
        "sys_path_after": list(sys.path),
    }

