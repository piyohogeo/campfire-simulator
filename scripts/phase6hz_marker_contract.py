"""Canonical, fail-closed marker boundary for the Phase 6HZ Kit import smoke."""

from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA = "campfire.phase6hz.marker-contract.v1"
AUTO_KEYS = frozenset({"marker", "timestamp_utc", "path"})


def append_marker(marker_file: Path, event_name: str, payload: Mapping[str, object]) -> dict:
    """Validate and durably append exactly one canonical marker record."""
    canonical = canonical_payload(event_name, [payload])
    marker_file = Path(marker_file)
    marker_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "marker": event_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **canonical,
    }
    with marker_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record


HELPER_ARGUMENT_KEYS = frozenset(inspect.signature(append_marker).parameters)
RESERVED_KEYS = AUTO_KEYS | HELPER_ARGUMENT_KEYS


EVENT_FIELDS: dict[str, dict[str, type]] = {
    "kit_launch": {"attempt_id": str, "executable_path": str},
    "kit_app_ready": {"attempt_id": str},
    "wrapper_resolution_started": {"expected_wrapper_path": str},
    "wrapper_resolution_complete": {"resolved_path": str, "sha256": str},
    "probe_resolution_started": {"repository_root": str, "source_name": str},
    "probe_resolution_complete": {"module_path": str},
    "module_identity_validated": {"module_path": str, "sha256": str},
    "import_complete": {"loaded_module_file": str},
    "required_callable_validated": {"callable_identity": dict},
    "operation_complete": {"scope": str},
    "shutdown_started": {"method": str},
    "shutdown_complete": {"requested": bool},
}


def canonical_payload(event_name: str, fragments: Sequence[Mapping[str, object]]) -> dict:
    if event_name not in EVENT_FIELDS:
        raise ValueError("unknown_marker_event:" + str(event_name))
    combined: dict[str, object] = {}
    for fragment in fragments:
        if not isinstance(fragment, Mapping):
            raise TypeError("marker_payload_fragment_type_invalid")
        for key, value in fragment.items():
            if not isinstance(key, str):
                raise TypeError("marker_payload_key_type_invalid")
            if key in RESERVED_KEYS:
                raise ValueError("reserved_marker_key_collision:" + key)
            if key in combined:
                reason = "conflicting_marker_value:" if combined[key] != value else "duplicate_marker_key:"
                raise ValueError(reason + key)
            combined[key] = value
    expected = EVENT_FIELDS[event_name]
    missing = sorted(set(expected) - set(combined))
    unknown = sorted(set(combined) - set(expected))
    if missing:
        raise ValueError("required_marker_key_missing:" + missing[0])
    if unknown:
        raise ValueError("unknown_marker_payload_key:" + unknown[0])
    for key, expected_type in expected.items():
        value = combined[key]
        if expected_type is bool:
            valid = type(value) is bool
        else:
            valid = isinstance(value, expected_type)
        if not valid:
            raise TypeError("marker_payload_type_invalid:" + key)
        if expected_type is str and not value:
            raise ValueError("marker_payload_empty:" + key)
    return combined


def produce_marker(event_name: str, **values: object) -> tuple[str, dict]:
    """The single producer used by both the runtime wrapper and no-Kit fixture."""
    return event_name, canonical_payload(event_name, [values])


def representative_wrapper_events(root: Path) -> list[tuple[str, dict]]:
    """Generate every complete payload shape emitted by the real wrapper."""
    root = Path(root).resolve()
    scripts = root / "scripts"
    wrapper = scripts / "probe_phase6hz_import_smoke.py"
    probe = scripts / "phase6hy_probe_source.py"
    digest = "A" * 64
    examples = [
        ("kit_launch", {"attempt_id": "phase6hz-import-smoke-attempt01", "executable_path": "kit.exe"}),
        ("kit_app_ready", {"attempt_id": "phase6hz-import-smoke-attempt01"}),
        ("wrapper_resolution_started", {"expected_wrapper_path": str(wrapper)}),
        ("wrapper_resolution_complete", {"resolved_path": str(wrapper), "sha256": digest}),
        ("probe_resolution_started", {"repository_root": str(root), "source_name": probe.name}),
        ("probe_resolution_complete", {"module_path": str(probe)}),
        ("module_identity_validated", {"module_path": str(probe), "sha256": digest}),
        ("import_complete", {"loaded_module_file": str(probe)}),
        ("required_callable_validated", {"callable_identity": {"build_probe_source": "phase6hz_probe_source_exact.build_probe_source"}}),
        ("operation_complete", {"scope": "exact_import_smoke"}),
        ("shutdown_started", {"method": "post_uncancellable_quit"}),
        ("shutdown_complete", {"requested": True}),
    ]
    return [produce_marker(name, **payload) for name, payload in examples]
