"""Kit app-ready smoke for the exact Phase 6GN wrapper and patch wiring."""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6fz_import_contract import load_exact_module
from phase6gn_exact_wrapper_contract import audit_phase6gl_and_shared


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    data = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with partial.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


def _marker(path: Path, name: str, **fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "campfire.phase6gn.exact-wrapper-smoke-marker.v1",
        "marker": name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "process_id": os.getpid(),
        **fields,
    }
    with path.open("ab") as stream:
        stream.write((json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())


settings = carb.settings.get_settings()
report_path = Path(settings.get_as_string("/phase6gn/smokeReport")).resolve()
marker_path = Path(settings.get_as_string("/phase6gn/smokeMarkers")).resolve()
wrapper_path = Path(settings.get_as_string("/phase6gn/wrapperPath")).resolve()
expected_wrapper_path = Path(settings.get_as_string("/phase6gn/expectedWrapperPath")).resolve()
import_audit_path = Path(settings.get_as_string("/phase6fz/importAuditPath")).resolve()
mode = settings.get_as_string("/phase6gn/smokeMode") or "positive"
phase6gl_path = (SCRIPT_DIR / "probe_phase6gl_supply_comparison.py").resolve()
shared_path = (SCRIPT_DIR / "probe_phase6gc_shared_supply_comparison.py").resolve()

report = {
    "schema": "campfire.phase6gn.exact-wrapper-app-ready-smoke.v1",
    "mode": mode,
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "kit_app_ready": bool(omni.kit.app.get_app().is_running()),
    "wrapper_path": str(wrapper_path),
    "expected_wrapper_path": str(expected_wrapper_path),
    "working_directory": str(Path.cwd()),
    "process_id": os.getpid(),
    "sys_path_at_exec": list(sys.path),
    "stage_authoring_performed": False,
    "timeline_started": False,
    "flow_started": False,
    "readback_calls": 0,
    "formal_slots_consumed": 0,
}
_marker(marker_path, "import_started", mode=mode)
exit_code = 0
try:
    if mode == "positive":
        wrapper, wrapper_loader_audit = load_exact_module(
            wrapper_path,
            expected_wrapper_path,
            module_name="campfire_phase6gn_exact_wrapper_smoke_target",
            required_entrypoints=("_build_stage_with_qualified_exports",),
        )
        _marker(marker_path, "import_complete", resolved_file=str(Path(wrapper.__file__).resolve()))
        module_contract = audit_phase6gl_and_shared(wrapper.phase6gl, phase6gl_path, shared_path)
        wiring = dict(wrapper.WRAPPER_WIRING_AUDIT)
        if not wiring.get("patched_identity_matches") or wrapper.shared._build_stage is not wrapper._build_stage_with_qualified_exports:
            raise ImportError("Phase 6GN patch target does not resolve to the exact wrapper function")
        if not callable(wrapper._base_build_stage) or wrapper._base_build_stage is wrapper._build_stage_with_qualified_exports:
            raise ImportError("Phase 6GN original stage builder is missing or aliases the patch")
        descriptor = wrapper.export_state.load_descriptor()
        digest = wrapper.export_state.descriptor_digest(descriptor)
        if digest != wrapper.EXPECTED_DESCRIPTOR_DIGEST:
            raise ImportError("Phase 6GN immutable descriptor digest mismatch")
        _marker(marker_path, "wrapper_wiring_complete", descriptor_digest=digest)
        report.update(
            status="pass",
            wrapper_loader_audit=wrapper_loader_audit,
            wrapper_runtime_import_audit=json.loads(import_audit_path.read_text(encoding="utf-8")),
            module_contract=module_contract,
            wrapper_wiring=wiring,
            descriptor_digest=digest,
        )
        _marker(marker_path, "smoke_complete", status="pass")
    elif mode == "wrong_path":
        load_exact_module(
            wrapper_path,
            expected_wrapper_path,
            module_name="campfire_phase6gn_wrong_path",
            required_entrypoints=("_build_stage_with_qualified_exports",),
        )
        raise AssertionError("wrong path unexpectedly loaded")
    elif mode == "legacy_shared_callable_declaration":
        load_exact_module(
            phase6gl_path,
            phase6gl_path,
            module_name="campfire_phase6gn_legacy_declaration",
            required_entrypoints=("_qualified_spatial_boundary", "shared"),
        )
        raise AssertionError("legacy shared-as-callable declaration unexpectedly passed")
    elif mode == "missing_required_attribute":
        module, _ = load_exact_module(
            phase6gl_path,
            phase6gl_path,
            module_name="campfire_phase6gn_missing_attribute",
            required_entrypoints=("_qualified_spatial_boundary",),
        )
        delattr(module.shared, "_type_name")
        audit_phase6gl_and_shared(module, phase6gl_path, shared_path)
        raise AssertionError("missing shared attribute unexpectedly passed")
    elif mode == "exit_code_propagation":
        raise RuntimeError("intentional exact-wrapper smoke exit-code propagation fixture")
    else:
        raise ValueError(f"unknown smoke mode: {mode}")
except BaseException as exc:
    expected_negative = mode in {"wrong_path", "legacy_shared_callable_declaration", "missing_required_attribute"}
    report.update(
        status="expected_failure" if expected_negative else "fail",
        error_type=type(exc).__name__,
        error=str(exc),
        traceback=traceback.format_exc(limit=8),
    )
    _marker(marker_path, "smoke_complete", status=report["status"], error_type=type(exc).__name__)
    if mode == "exit_code_propagation":
        exit_code = 29
    elif not expected_negative:
        exit_code = 12

_atomic_json(report_path, report)
omni.kit.app.get_app().post_uncancellable_quit(exit_code)
