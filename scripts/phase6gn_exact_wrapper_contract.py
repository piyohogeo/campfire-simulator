"""Fail-closed type and origin contract for the Phase 6GN exact wrapper."""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType


SHARED_CALLABLES = (
    "_run",
    "_build_stage",
    "_append_resource_marker",
    "_p3_world_rois",
    "_bounded_object_metadata",
    "_save_and_sample",
    "process_memory_snapshot",
    "_type_name",
)
SHARED_MODULES = ("Usd", "point_core")
WRAPPER_CALLABLES = ("_qualified_spatial_boundary",)
EXPORT_CALLABLES = ("author", "validate", "descriptor_digest", "load_descriptor")


def _resolved_module_file(module: ModuleType) -> Path:
    value = getattr(module, "__file__", None)
    if not isinstance(value, str) or not value:
        raise ImportError("module has no resolved __file__")
    return Path(value).resolve(strict=True)


def audit_module(
    module: object,
    expected_path: str | Path,
    *,
    label: str,
    required_callables: tuple[str, ...] = (),
    required_modules: tuple[str, ...] = (),
) -> dict:
    """Validate a module separately from the attributes consumed from it."""

    expected = Path(expected_path).resolve(strict=True)
    if not isinstance(module, ModuleType):
        raise ImportError(f"{label} is not types.ModuleType: {type(module).__name__}")
    resolved = _resolved_module_file(module)
    if resolved != expected:
        raise ImportError(f"{label} module path mismatch: {resolved} != {expected}")

    attributes: list[dict] = []
    for name in required_callables:
        value = getattr(module, name, None)
        ok = callable(value)
        attributes.append({"name": name, "contract": "callable", "type": type(value).__name__, "pass": ok})
        if not ok:
            raise ImportError(f"{label} required callable missing or noncallable: {name}")
    for name in required_modules:
        value = getattr(module, name, None)
        ok = isinstance(value, ModuleType)
        attributes.append({"name": name, "contract": "module", "type": type(value).__name__, "pass": ok})
        if not ok:
            raise ImportError(f"{label} required module missing or wrong type: {name}")
    return {
        "label": label,
        "module_type": type(module).__name__,
        "module_type_is_types_ModuleType": True,
        "resolved_file": str(resolved),
        "expected_file": str(expected),
        "process_id": os.getpid(),
        "attributes": attributes,
        "pass": True,
    }


def audit_phase6gl_and_shared(phase6gl: object, phase6gl_path: str | Path, shared_path: str | Path) -> dict:
    wrapper = audit_module(
        phase6gl,
        phase6gl_path,
        label="phase6gl_wrapper",
        required_callables=WRAPPER_CALLABLES,
    )
    shared = getattr(phase6gl, "shared", None)
    shared_audit = audit_module(
        shared,
        shared_path,
        label="shared_probe_module",
        required_callables=SHARED_CALLABLES,
        required_modules=SHARED_MODULES,
    )
    return {"pass": True, "phase6gl": wrapper, "shared": shared_audit}


def audit_export_module(module: object, expected_path: str | Path) -> dict:
    return audit_module(
        module,
        expected_path,
        label="phase6gm_export_state_module",
        required_callables=EXPORT_CALLABLES,
    )
