"""Deterministically derive the Phase 6HS probe from the frozen Phase 6HK probe."""

from __future__ import annotations

import hashlib
from pathlib import Path


EXPECTED_SHA256 = "7CDBFD7DBC5076095BA0BF352EFD96FFDD56CB1678AF6F5E2B7AD8835D640EC1"


def build_probe_source(source_path: Path) -> str:
    source_bytes = source_path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest().upper() != EXPECTED_SHA256:
        raise RuntimeError("Frozen Phase 6HK boundary probe hash mismatch")
    source = source_bytes.decode("utf-8").replace("phase6hk", "phase6hs").replace("Phase 6HK", "Phase 6HS")
    replacements = (
        (
            '    markers = Path(settings.get_as_string("/phase6hs/markers")).resolve()',
            '    markers = Path(settings.get_as_string("/phase6hs/markers")).resolve()\n    attempt_id = settings.get_as_string("/phase6hs/attemptId")',
        ),
        (
            '        record = {"timestamp_utc": _utc(), "name": name, **values}',
            '        record = {"timestamp_utc": _utc(), "name": name, "attempt_id": attempt_id, **values}',
        ),
        ('"timeline_play_calls": 0,', '"timeline_play_calls": 0,\n        "flow_interface_calls": 0,'),
        (
            '    try:\n        mark("contract_started")',
            '''    try:
        manager = app.get_extension_manager()
        anim_id = manager.get_enabled_extension_id("omni.anim.curve.core")
        campfire_id = manager.get_enabled_extension_id("campfire.app")
        if not anim_id or not campfire_id:
            raise RuntimeError("required_extension_not_enabled")
        expected_anim = Path(settings.get_as_string("/phase6hs/expectedAnimPath"))
        anim_path = Path(manager.get_extension_path(anim_id))
        campfire_path = Path(manager.get_extension_path(campfire_id))
        if anim_path.resolve(strict=True) != expected_anim.resolve(strict=True):
            raise RuntimeError("anim_extension_path_mismatch")
        module_evidence = collect_module_path_evidence(
            extension_id=campfire_id,
            extension_root=campfire_path,
            module_name=campfire.app.__name__,
            package_name=campfire.__name__,
            module_file=campfire.app.__file__,
        )
        module_ok, module_reason = validate_module_path_evidence(module_evidence)
        if not module_ok:
            raise RuntimeError("junction_module_path_gate:" + module_reason)
        report["app_ready_evidence"] = {
            "anim_extension_id": anim_id,
            "campfire_extension_id": campfire_id,
            "module_path_gate": {"passed": True, "reason": module_reason},
            "module_path_evidence": module_evidence,
        }
        mark("app_ready_gate_complete", module_gate_reason=module_reason)
        mark("contract_started")''',
        ),
        (
            '        flow = _flowusd.acquire_flowusd_interface()\n        held["flow"] = flow',
            '        flow = _flowusd.acquire_flowusd_interface()\n        report["flow_interface_calls"] += 1\n        held["flow"] = flow',
        ),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError("Phase 6HS probe replacement cardinality mismatch")
        source = source.replace(before, after)
    return source
