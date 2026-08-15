"""Reserved-key-safe durable markers for the Phase 6IB stage-open boundary."""

from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


AUTO_KEYS = frozenset({"marker", "timestamp_utc", "path"})
EVENT_FIELDS = {
    "kit_launch": {"attempt_id": str, "executable_path": str},
    "kit_app_ready": {"attempt_id": str},
    "probe_import_complete": {"module_path": str, "sha256": str, "callable_identity": dict},
    "stage_generation_started": {"condition": str},
    "stage_generation_complete": {"off_sha256": str, "on_sha256": str},
    "stage_parse_started": {"parser": str},
    "stage_parse_complete": {"positive_count": int, "negative_count": int},
    "stage_open_complete": {"stage_identifier": str, "root_layer_identifier": str},
    "required_prims_validated": {"prim_count": int, "flow_setting_count": int},
    "operation_complete": {"scope": str},
    "stage_close_started": {"stage_identifier": str},
    "stage_close_complete": {"context_empty": bool},
    "shutdown_complete": {"requested": bool},
}


def append_marker(marker_file: Path, event_name: str, payload: Mapping[str, object]) -> dict:
    canonical = canonical_payload(event_name, payload)
    marker_file = Path(marker_file)
    marker_file.parent.mkdir(parents=True, exist_ok=True)
    row = {"marker": event_name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **canonical}
    with marker_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush(); os.fsync(stream.fileno())
    return row


RESERVED_KEYS = AUTO_KEYS | frozenset(inspect.signature(append_marker).parameters)


def canonical_payload(event_name: str, payload: Mapping[str, object]) -> dict:
    if event_name not in EVENT_FIELDS: raise ValueError("unknown_marker_event:" + event_name)
    if not isinstance(payload, Mapping): raise TypeError("marker_payload_type_invalid")
    collision = sorted(set(payload) & RESERVED_KEYS)
    if collision: raise ValueError("reserved_marker_key_collision:" + collision[0])
    expected = EVENT_FIELDS[event_name]
    missing, unknown = sorted(set(expected)-set(payload)), sorted(set(payload)-set(expected))
    if missing: raise ValueError("required_marker_key_missing:" + missing[0])
    if unknown: raise ValueError("unknown_marker_payload_key:" + unknown[0])
    result = dict(payload)
    for key, expected_type in expected.items():
        value = result[key]
        valid = type(value) is expected_type if expected_type in (bool, int) else isinstance(value, expected_type)
        if not valid: raise TypeError("marker_payload_type_invalid:" + key)
        if expected_type is str and not value: raise ValueError("marker_payload_empty:" + key)
    return result


def produce_marker(event_name: str, **values: object) -> tuple[str, dict]:
    return event_name, canonical_payload(event_name, values)
